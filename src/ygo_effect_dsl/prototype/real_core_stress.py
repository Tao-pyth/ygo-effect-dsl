from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    FailureRecord,
    FailureRecordError,
    RecoveryAction,
)
from ygo_effect_dsl.engine.search import (
    ParallelCandidate,
    ParallelExecutionPlan,
    ParallelSearchPolicy,
    ParallelTask,
    ParallelTaskResult,
    build_search_node_id,
)
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.prototype.real_core import (
    WORKER_TIMEOUT_SECONDS,
    RealCoreWorkerProcessResult,
    invoke_real_core_worker_process,
)


REAL_CORE_STRESS_SCHEMA_VERSION = "real-core-parallel-stress-v2"
REAL_CORE_STRESS_EXPERIMENT_ID = "real_core_parallel_stress"
REAL_CORE_STRESS_RUN_ID = "run_real_core_parallel_stress"
REAL_CORE_STRESS_BASE_SEED = 20260713
_RETRYABLE_FAILURES = {"callback_error", "worker_crash", "worker_timeout"}

WorkerInvoker = Callable[..., RealCoreWorkerProcessResult]


def _fallback_process_failure(
    process: RealCoreWorkerProcessResult,
) -> FailureRecord:
    category = process.failure_category or "worker_protocol"
    retryable = category in _RETRYABLE_FAILURES
    return FailureRecord(
        category=category,
        disposition=FailureDisposition.PATH_FAILURE,
        recovery=(
            RecoveryAction.REPLACE_WORKER
            if retryable
            else RecoveryAction.STOP_PATH
        ),
        retryable=retryable,
        message=process.diagnostic or category,
        context={"source": "legacy_process_result"},
    )


def _stress_candidates(task_count: int) -> tuple[ParallelCandidate, ...]:
    if not isinstance(task_count, int) or isinstance(task_count, bool) or task_count < 1:
        raise ValueError("task_count must be an integer >= 1")
    root = build_search_node_id(
        experiment_id=REAL_CORE_STRESS_EXPERIMENT_ID,
        state_id="state_real_core_stress_root",
        depth=0,
    )
    submissions: list[ParallelCandidate] = []
    for index in range(task_count):
        action_id = f"stress_action_{index}"
        node_id = build_search_node_id(
            experiment_id=REAL_CORE_STRESS_EXPERIMENT_ID,
            state_id=f"state_real_core_stress_{index}",
            depth=1,
            parent_node_id=root,
            action_id=action_id,
        )
        candidate = ParallelCandidate.from_prefix(
            node_id=node_id,
            prefix_key_id=f"stress_prefix_{index}",
            action_id=action_id,
            payload_ref="experiment:real_core_effect_veiler_base",
        )
        submissions.extend((candidate, candidate))
    return tuple(submissions)


def _route_result(document: Mapping[str, Any]) -> tuple[str, str, int | float]:
    route_id = document.get("route_id")
    replay = document.get("replay")
    result = document.get("result")
    if not isinstance(route_id, str) or not route_id:
        raise ValueError("real-core stress worker returned no route_id")
    if not isinstance(replay, Mapping):
        raise ValueError("real-core stress worker returned no replay")
    if not isinstance(result, Mapping):
        raise ValueError("real-core stress worker returned no result")
    terminal = result.get("terminal_board")
    if not isinstance(terminal, Mapping):
        raise ValueError("real-core stress worker returned no terminal board")
    score = terminal.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ValueError("real-core stress worker returned no numeric score")
    return route_id, stable_digest(replay, prefix="replay_"), score


def _execute_task(
    plan: ParallelExecutionPlan,
    task: ParallelTask,
    *,
    external_root: str | Path | None,
    failure_schedule: Mapping[int, str],
    invoker: WorkerInvoker,
) -> tuple[list[ParallelTaskResult], list[dict[str, Any]]]:
    results: list[ParallelTaskResult] = []
    process_evidence: list[dict[str, Any]] = []
    for attempt_index in range(plan.policy.max_retries + 1):
        attempt = plan.attempt(task.task_id, attempt_index)
        stress_failure = failure_schedule.get(attempt_index)
        timeout_seconds = (
            0.25 if stress_failure == "worker_timeout" else WORKER_TIMEOUT_SECONDS
        )
        process = invoker(
            external_root=external_root,
            experiment=None,
            stress_failure=stress_failure,
            timeout_seconds=timeout_seconds,
        )
        evidence = {
            **process.to_evidence_dict(),
            "attempt": attempt.attempt,
            "attempt_id": attempt.attempt_id,
            "core_seed": list(task.core_seed),
            "logical_worker_slot": task.logical_worker_slot,
            "python_seed": task.python_seed,
            "replacement_generation": attempt.replacement_generation,
            "stress_failure": stress_failure,
            "task_id": task.task_id,
            "task_ordinal": task.task_ordinal,
            "worker_seed": task.worker_seed,
        }
        if process.succeeded and process.document is not None:
            route_id, replay_id, score = _route_result(process.document)
            evidence.update({"replay_id": replay_id, "route_id": route_id})
            results.append(
                ParallelTaskResult.success(
                    attempt,
                    score=score,
                    result_ref=f"route:{route_id}",
                    result_digest=replay_id,
                    logs=(
                        {
                            "event_type": "route_completed",
                            "local_sequence": 0,
                            "payload": {
                                "replay_id": replay_id,
                                "route_id": route_id,
                            },
                        },
                    ),
                )
            )
            process_evidence.append(to_canonical_data(evidence))
            break
        failure = process.failure_record or _fallback_process_failure(process)
        failure_payload = failure.to_dict()
        evidence["failure"] = failure_payload
        results.append(
            ParallelTaskResult.from_failure(
                attempt,
                failure=failure,
                logs=(
                    {
                        "event_type": "worker_failure",
                        "local_sequence": 0,
                        "payload": failure_payload,
                    },
                ),
            )
        )
        process_evidence.append(to_canonical_data(evidence))
        if not failure.retryable:
            break
    return results, process_evidence


def _execute_plan(
    plan: ParallelExecutionPlan,
    *,
    external_root: str | Path | None,
    failure_schedules: Mapping[str, Mapping[int, str]] | None,
    reverse_aggregation_input: bool,
    invoker: WorkerInvoker,
) -> dict[str, Any]:
    schedules = failure_schedules or {}
    future_tasks: dict[
        Future[tuple[list[ParallelTaskResult], list[dict[str, Any]]]], ParallelTask
    ] = {}
    results_by_task: dict[str, list[ParallelTaskResult]] = {}
    processes_by_task: dict[str, list[dict[str, Any]]] = {}
    completion_order: list[str] = []
    executor = ThreadPoolExecutor(max_workers=plan.policy.pool_size)
    aborting = False
    try:
        for task in plan.tasks:
            future = executor.submit(
                _execute_task,
                plan,
                task,
                external_root=external_root,
                failure_schedule=schedules.get(task.task_id, {}),
                invoker=invoker,
            )
            future_tasks[future] = task
        for future in as_completed(future_tasks):
            task = future_tasks[future]
            task_results, process_evidence = future.result()
            experiment_failure = next(
                (
                    result.failure
                    for result in task_results
                    if result.failure is not None
                    and result.failure.disposition
                    == FailureDisposition.EXPERIMENT_FAILURE
                ),
                None,
            )
            if experiment_failure is not None:
                aborting = True
                for pending in future_tasks:
                    if pending is not future:
                        pending.cancel()
                raise FailureRecordError(experiment_failure)
            completion_order.append(task.task_id)
            results_by_task[task.task_id] = task_results
            processes_by_task[task.task_id] = process_evidence
    finally:
        executor.shutdown(wait=not aborting, cancel_futures=aborting)

    ordered_tasks: Sequence[ParallelTask] = plan.tasks
    if reverse_aggregation_input:
        ordered_tasks = tuple(reversed(ordered_tasks))
    aggregate_input = [
        result
        for task in ordered_tasks
        for result in results_by_task[task.task_id]
    ]
    process_evidence = [
        evidence
        for task in plan.tasks
        for evidence in processes_by_task[task.task_id]
    ]
    semantic_routes = sorted(
        (
            {
                "replay_id": evidence["replay_id"],
                "route_id": evidence["route_id"],
                "task_id": evidence["task_id"],
            }
            for evidence in process_evidence
            if "route_id" in evidence
        ),
        key=lambda item: item["task_id"],
    )
    return {
        "aggregate": plan.aggregate(aggregate_input),
        "aggregation_input_order": [task.task_id for task in ordered_tasks],
        "completion_order": completion_order,
        "plan": plan.to_dict(),
        "processes": process_evidence,
        "semantic_routes": semantic_routes,
    }


def _build_plan(
    *,
    pool_size: int,
    task_count: int,
    run_id: str = REAL_CORE_STRESS_RUN_ID,
) -> ParallelExecutionPlan:
    return ParallelExecutionPlan.build(
        experiment_id=REAL_CORE_STRESS_EXPERIMENT_ID,
        run_id=run_id,
        policy=ParallelSearchPolicy(
            pool_size=pool_size,
            base_seed=REAL_CORE_STRESS_BASE_SEED,
            max_retries=1,
        ),
        candidates=_stress_candidates(task_count),
    )


def _failure_schedules(plan: ParallelExecutionPlan) -> dict[str, dict[int, str]]:
    if len(plan.tasks) != 4:
        raise ValueError("failure injection plan must contain four tasks")
    return {
        plan.tasks[0].task_id: {0: "worker_crash"},
        plan.tasks[1].task_id: {0: "worker_timeout"},
        plan.tasks[2].task_id: {0: "callback_error"},
        plan.tasks[3].task_id: {0: "worker_timeout", 1: "worker_timeout"},
    }


def _failure_verification(
    run: Mapping[str, Any], schedules: Mapping[str, Mapping[int, str]]
) -> dict[str, Any]:
    processes = run["processes"]
    outcomes = {
        outcome["task_id"]: outcome for outcome in run["aggregate"]["outcomes"]
    }
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for process in processes:
        grouped.setdefault(process["task_id"], []).append(process)
    recovered = [task_id for task_id, schedule in schedules.items() if len(schedule) == 1]
    exhausted = [task_id for task_id, schedule in schedules.items() if len(schedule) == 2]
    retry_seed_stable = all(
        len({tuple(item["core_seed"]) for item in grouped[task_id]}) == 1
        and len({item["python_seed"] for item in grouped[task_id]}) == 1
        and len({item["logical_worker_slot"] for item in grouped[task_id]}) == 1
        for task_id in schedules
    )
    replacement_isolated = all(
        len(grouped[task_id]) == 2
        and grouped[task_id][0]["process_id"] != grouped[task_id][1]["process_id"]
        and all(item["terminated"] for item in grouped[task_id])
        for task_id in schedules
    )
    return {
        "all_failure_categories_observed": sorted(
            {
                item["failure_category"]
                for item in processes
                if item["failure_category"] is not None
            }
        )
        == ["callback_error", "worker_crash", "worker_timeout"],
        "callback_native_path_observed": any(
            item["failure_category"] == "callback_error"
            and (
                (
                    isinstance(item.get("failure"), Mapping)
                    and item["failure"].get("exception_type")
                    == "OcgcoreCallbackError"
                    and str(item["failure"].get("message", "")).startswith(
                        "DataReader:"
                    )
                )
                or "OcgcoreCallbackError" in item["diagnostic_tail"]
            )
            for item in processes
        ),
        "recovered_once": all(
            outcomes[task_id]["status"] == "success"
            and outcomes[task_id]["attempt_count"] == 2
            for task_id in recovered
        ),
        "replacement_process_isolated": replacement_isolated,
        "retry_exhaustion_failed": all(
            outcomes[task_id]["status"] == "failed_retry_exhausted"
            and outcomes[task_id]["attempt_count"] == 2
            for task_id in exhausted
        ),
        "retry_seed_and_slot_stable": retry_seed_stable,
    }


def run_real_core_parallel_stress(
    *,
    external_root: str | Path | None = None,
    pool_sizes: Sequence[int] = (1, 2, 4, 8),
    task_count: int = 8,
    include_failure_injection: bool = True,
    invoker: WorkerInvoker = invoke_real_core_worker_process,
) -> dict[str, Any]:
    normalized_pool_sizes = tuple(pool_sizes)
    if not normalized_pool_sizes or any(
        not isinstance(size, int) or isinstance(size, bool) or size < 1
        for size in normalized_pool_sizes
    ):
        raise ValueError("pool_sizes must contain integers >= 1")
    pool_runs: list[dict[str, Any]] = []
    for index, pool_size in enumerate(normalized_pool_sizes):
        plan = _build_plan(pool_size=pool_size, task_count=task_count)
        run = _execute_plan(
            plan,
            external_root=external_root,
            failure_schedules=None,
            reverse_aggregation_input=index % 2 == 1,
            invoker=invoker,
        )
        run["pool_size"] = pool_size
        pool_runs.append(run)

    baseline = pool_runs[0]
    semantic_equal = all(
        run["aggregate"]["semantic"] == baseline["aggregate"]["semantic"]
        for run in pool_runs[1:]
    )
    routes_equal = all(
        run["semantic_routes"] == baseline["semantic_routes"]
        for run in pool_runs[1:]
    )
    single_flight = all(
        len(run["plan"]["tasks"]) == task_count
        and len(run["plan"]["duplicates"]) == task_count
        and len(run["processes"]) == task_count
        for run in pool_runs
    )
    aggregation_orders = {
        tuple(run["aggregation_input_order"]) for run in pool_runs
    }
    completion_order_exercised = len(aggregation_orders) > 1 or len(pool_runs) == 1
    process_cleanup = all(
        process["terminated"]
        for run in pool_runs
        for process in run["processes"]
    )

    failure_run: dict[str, Any] | None = None
    failure_checks: dict[str, Any] | None = None
    if include_failure_injection:
        failure_plan = _build_plan(
            pool_size=4,
            task_count=4,
            run_id=f"{REAL_CORE_STRESS_RUN_ID}_failures",
        )
        schedules = _failure_schedules(failure_plan)
        failure_run = _execute_plan(
            failure_plan,
            external_root=external_root,
            failure_schedules=schedules,
            reverse_aggregation_input=True,
            invoker=invoker,
        )
        failure_run["failure_schedules"] = to_canonical_data(schedules)
        failure_checks = _failure_verification(failure_run, schedules)

    verification = {
        "completion_order_independent": completion_order_exercised and semantic_equal,
        "pool_independent_route_replay_ids": routes_equal,
        "pool_independent_semantic_result": semantic_equal,
        "process_cleanup_observed": process_cleanup,
        "single_flight_observed": single_flight,
    }
    if failure_checks is not None:
        verification.update(failure_checks)
    failed_checks = sorted(key for key, value in verification.items() if value is not True)
    if failed_checks:
        raise AssertionError(f"real-core parallel stress failed checks: {failed_checks}")

    semantic_report = to_canonical_data(
        {
            "baseline_routes": baseline["semantic_routes"],
            "baseline_semantic": baseline["aggregate"]["semantic"],
            "failure_semantic": (
                failure_run["aggregate"]["semantic"] if failure_run else None
            ),
            "pool_sizes": list(normalized_pool_sizes),
            "schema_version": REAL_CORE_STRESS_SCHEMA_VERSION,
            "task_count": task_count,
            "verification": verification,
        }
    )
    return {
        "failure_injection": failure_run,
        "pool_runs": pool_runs,
        "schema_version": REAL_CORE_STRESS_SCHEMA_VERSION,
        "semantic_report_id": stable_digest(
            semantic_report, prefix="realcorestress_"
        ),
        "task_count": task_count,
        "verification": verification,
    }


def dump_real_core_stress_report(
    report: Mapping[str, Any], path: str | Path
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        output,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
