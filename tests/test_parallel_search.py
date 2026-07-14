from __future__ import annotations

from copy import deepcopy

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    FailureRecord,
    FailureRecordError,
    RecoveryAction,
)
from ygo_effect_dsl.engine.search import (
    LEGACY_PARALLEL_RESULT_SCHEMA_VERSION,
    ParallelCandidate,
    ParallelExecutionPlan,
    ParallelSearchPolicy,
    ParallelTaskResult,
    build_search_node_id,
)
from ygo_effect_dsl.route_dsl import load_route_document


def _candidate(index: int, *, prefix: str | None = None) -> ParallelCandidate:
    root = build_search_node_id(
        experiment_id="experiment_parallel",
        state_id="state_root",
        depth=0,
    )
    node = build_search_node_id(
        experiment_id="experiment_parallel",
        state_id=f"state_{index}",
        depth=1,
        parent_node_id=root,
        action_id=f"act_{index}",
    )
    return ParallelCandidate.from_prefix(
        node_id=node,
        prefix_key_id=prefix or f"prefix_{index}",
        action_id=f"act_{index}",
        payload_ref=f"route:input-{index}",
    )


def _plan(candidates: list[ParallelCandidate]) -> ParallelExecutionPlan:
    return ParallelExecutionPlan.build(
        experiment_id="experiment_parallel",
        run_id="run_parallel",
        policy=ParallelSearchPolicy(pool_size=2, base_seed=1234, max_retries=1),
        candidates=candidates,
    )


def _log(event_type: str) -> tuple[dict[str, object], ...]:
    return (
        {"event_type": event_type, "local_sequence": 0, "payload": {"ok": True}},
    )


def _failure(category: str, *, retryable: bool) -> FailureRecord:
    return FailureRecord(
        category=category,
        disposition=FailureDisposition.PATH_FAILURE,
        recovery=(
            RecoveryAction.REPLACE_WORKER
            if retryable
            else RecoveryAction.STOP_PATH
        ),
        retryable=retryable,
        message=f"{category} occurred",
        exception_type="TestFailure",
        context={"phase": "test"},
    )


def _v1_document(result: ParallelTaskResult) -> dict[str, object]:
    identity = to_canonical_data(
        {
            "attempt": result.attempt,
            "attempt_id": result.attempt_id,
            "failure_category": result.failure_category,
            "logs": list(result.logs),
            "node_id": result.node_id,
            "result_digest": result.result_digest,
            "result_ref": result.result_ref,
            "schema_version": LEGACY_PARALLEL_RESULT_SCHEMA_VERSION,
            "score": result.score,
            "status": result.status.value,
            "task_id": result.task_id,
        }
    )
    return {
        **identity,
        "result_id": stable_digest(identity, prefix="taskresult_"),
    }


def test_node_id_is_path_stable_and_changes_with_state_or_action() -> None:
    root = build_search_node_id(
        experiment_id="exp", state_id="state_root", depth=0
    )
    child = build_search_node_id(
        experiment_id="exp",
        state_id="state_child",
        depth=1,
        parent_node_id=root,
        action_id="act_a",
    )

    assert child == build_search_node_id(
        experiment_id="exp",
        state_id="state_child",
        depth=1,
        parent_node_id=root,
        action_id="act_a",
    )
    assert child != build_search_node_id(
        experiment_id="exp",
        state_id="state_other",
        depth=1,
        parent_node_id=root,
        action_id="act_a",
    )
    with pytest.raises(ValueError, match="non-root"):
        build_search_node_id(experiment_id="exp", state_id="state", depth=1)


def test_plan_is_input_order_independent_and_deduplicates_work() -> None:
    first = _candidate(1, prefix="shared_prefix")
    duplicate = ParallelCandidate.from_prefix(
        node_id=first.node_id,
        prefix_key_id="shared_prefix",
        action_id="act_1",
        payload_ref="route:duplicate-copy",
    )
    second = _candidate(2)

    forward = _plan([first, duplicate, second])
    reverse = _plan([second, duplicate, first])

    assert forward.to_dict() == reverse.to_dict()
    assert len(forward.tasks) == 2
    assert len(forward.duplicates) == 1
    assert [task.logical_worker_slot for task in forward.tasks] == [0, 1]

    conflicting_node = ParallelCandidate.from_prefix(
        node_id="searchnode_conflicting",
        prefix_key_id="shared_prefix",
        action_id="act_1",
        payload_ref="route:conflicting-node",
    )
    with pytest.raises(ValueError, match="same node_id"):
        _plan([first, conflicting_node])


def test_task_and_worker_seeds_are_stable_across_retry() -> None:
    plan = _plan([_candidate(0), _candidate(1), _candidate(2)])
    task = plan.tasks[2]
    first = plan.attempt(task.task_id, 0)
    retry = plan.attempt(task.task_id, 1)

    assert task.logical_worker_slot == task.task_ordinal % plan.policy.pool_size
    assert first.task.core_seed == retry.task.core_seed
    assert first.task.python_seed == retry.task.python_seed
    assert first.task.worker_seed == retry.task.worker_seed
    assert first.replacement_generation == 0
    assert retry.replacement_generation == 1
    assert first.attempt_id != retry.attempt_id

    single_worker = ParallelExecutionPlan.build(
        experiment_id="experiment_parallel",
        run_id="run_parallel",
        policy=ParallelSearchPolicy(pool_size=1, base_seed=1234, max_retries=1),
        candidates=[_candidate(0), _candidate(1), _candidate(2)],
    )
    assert [item.task_id for item in single_worker.tasks] == [
        item.task_id for item in plan.tasks
    ]
    assert [item.core_seed for item in single_worker.tasks] == [
        item.core_seed for item in plan.tasks
    ]
    assert task.to_dict()["task_id"] == task.task_id


def test_aggregate_is_completion_order_independent() -> None:
    plan = _plan([_candidate(0), _candidate(1), _candidate(2)])
    results = [
        ParallelTaskResult.success(
            plan.attempt(task.task_id),
            score=score,
            result_ref=f"route:{task.task_id}",
            result_digest=f"digest_{task.task_id}",
            logs=_log(f"task_{task.task_ordinal}"),
        )
        for task, score in zip(plan.tasks, (5, 10, 10), strict=True)
    ]

    forward = plan.aggregate(results)
    reverse = plan.aggregate(list(reversed(results)))

    assert forward == reverse
    assert forward["summary"]["success"] == 3
    assert forward["summary"]["total_score"] == 25
    assert forward["summary"]["best_task_id"] == plan.tasks[1].task_id
    assert [item["task_ordinal"] for item in forward["logs"]] == [0, 1, 2]
    assert results[0].to_dict()["result_id"].startswith("taskresult_")


def test_semantic_aggregate_is_pool_size_independent() -> None:
    candidates = [_candidate(0), _candidate(1), _candidate(2)]
    reports = []
    execution_ids = []
    for pool_size in (1, 2, 4):
        plan = ParallelExecutionPlan.build(
            experiment_id="experiment_parallel",
            run_id="run_parallel",
            policy=ParallelSearchPolicy(
                pool_size=pool_size, base_seed=1234, max_retries=1
            ),
            candidates=candidates,
        )
        results = [
            ParallelTaskResult.success(
                plan.attempt(task.task_id),
                score=task.task_ordinal,
                result_ref=f"route:{task.task_id}",
                result_digest=f"digest_{task.task_id}",
                logs=_log(f"task_{task.task_ordinal}"),
            )
            for task in plan.tasks
        ]
        report = plan.aggregate(list(reversed(results)))
        reports.append(report["semantic"])
        execution_ids.append(report["execution_id"])

    assert reports[0] == reports[1] == reports[2]
    assert len(set(execution_ids)) == 3


def test_retryable_failure_then_success_keeps_seed_and_orders_logs() -> None:
    plan = _plan([_candidate(0)])
    task = plan.tasks[0]
    first_attempt = plan.attempt(task.task_id, 0)
    retry_attempt = plan.attempt(task.task_id, 1)
    failure = ParallelTaskResult.from_failure(
        first_attempt,
        failure=_failure("worker_crash", retryable=True),
        logs=_log("worker_crash"),
    )
    success = ParallelTaskResult.success(
        retry_attempt,
        score=7,
        result_ref="route:recovered",
        result_digest="digest_recovered",
        logs=_log("retry_success"),
    )

    report = plan.aggregate([success, failure])

    assert report["outcomes"][0]["status"] == "success"
    assert report["outcomes"][0]["attempt_count"] == 2
    assert report["outcomes"][0]["failure"] is None
    history = report["outcomes"][0]["attempt_history"]
    assert [item["status"] for item in history] == [
        "retryable_failure",
        "success",
    ]
    assert history[0]["failure"] == failure.failure.to_dict()
    assert history[1]["failure"] is None
    assert [item["attempt"] for item in report["logs"]] == [0, 1]
    assert first_attempt.task.core_seed == retry_attempt.task.core_seed


def test_retry_exhaustion_and_permanent_failure_never_become_success() -> None:
    plan = _plan([_candidate(0), _candidate(1)])
    retry_results = [
        ParallelTaskResult.from_failure(
            plan.attempt(plan.tasks[0].task_id, attempt),
            failure=_failure("timeout", retryable=True),
        )
        for attempt in (0, 1)
    ]
    permanent = ParallelTaskResult.from_failure(
        plan.attempt(plan.tasks[1].task_id),
        failure=_failure("invalid_message", retryable=False),
    )

    report = plan.aggregate([permanent, *reversed(retry_results)])

    assert [item["status"] for item in report["outcomes"]] == [
        "failed_retry_exhausted",
        "failed_permanent",
    ]
    assert report["summary"]["failed"] == 2
    assert report["summary"]["success"] == 0


def test_parallel_result_v2_round_trip_and_derived_fields() -> None:
    plan = _plan([_candidate(0)])
    result = ParallelTaskResult.from_failure(
        plan.attempt(plan.tasks[0].task_id),
        failure=_failure("worker_crash", retryable=True),
        logs=_log("worker_crash"),
    )

    document = result.to_dict()
    restored = ParallelTaskResult.from_dict(document)

    assert restored == result
    assert document["schema_version"] == "parallel-search-result-v2"
    assert document["failure"] == result.failure.to_dict()
    assert "failure_category" not in document
    assert "retryable" not in document
    assert restored.status.value == "retryable_failure"
    assert restored.failure_category == "worker_crash"
    assert restored.retryable is True

    tampered = deepcopy(document)
    tampered["status"] = "permanent_failure"
    with pytest.raises(ValueError, match="does not match failure"):
        ParallelTaskResult.from_dict(tampered)


def test_parallel_result_v1_reader_migrates_failure_and_checks_digest() -> None:
    plan = _plan([_candidate(0)])
    result = ParallelTaskResult.from_failure(
        plan.attempt(plan.tasks[0].task_id),
        failure=_failure("worker_timeout", retryable=True),
    )
    legacy = _v1_document(result)

    migrated = ParallelTaskResult.from_dict(legacy)

    assert migrated.schema_version == "parallel-search-result-v2"
    assert migrated.failure is not None
    assert migrated.failure.disposition == FailureDisposition.PATH_FAILURE
    assert migrated.failure.recovery == RecoveryAction.REPLACE_WORKER
    assert migrated.failure.context == {
        "inferred_disposition": "path_failure",
        "inferred_recovery": "replace_worker",
        "source_schema_version": "parallel-search-result-v1",
        "source_status": "retryable_failure",
    }

    tampered = deepcopy(legacy)
    tampered["failure_category"] = "worker_crash"
    with pytest.raises(ValueError, match="result_id"):
        ParallelTaskResult.from_dict(tampered)


def test_parallel_result_v1_reader_migrates_success_and_permanent_failure() -> None:
    plan = _plan([_candidate(0), _candidate(1)])
    success = ParallelTaskResult.success(
        plan.attempt(plan.tasks[0].task_id),
        score=3,
        result_ref="route:legacy-success",
        result_digest="digest_legacy_success",
    )
    permanent = ParallelTaskResult.from_failure(
        plan.attempt(plan.tasks[1].task_id),
        failure=_failure("invalid_message", retryable=False),
    )

    migrated_success = ParallelTaskResult.from_dict(_v1_document(success))
    migrated_permanent = ParallelTaskResult.from_dict(_v1_document(permanent))

    assert migrated_success == success
    assert migrated_permanent.failure is not None
    assert migrated_permanent.failure.recovery == RecoveryAction.STOP_PATH
    assert migrated_permanent.status.value == "permanent_failure"


def test_aggregate_rejects_experiment_failure_without_evidence() -> None:
    plan = _plan([_candidate(0)])
    failure = FailureRecord(
        category="version_mismatch",
        disposition=FailureDisposition.EXPERIMENT_FAILURE,
        recovery=RecoveryAction.ABORT_EXPERIMENT,
        retryable=False,
        message="core version changed",
    )
    result = ParallelTaskResult.from_failure(
        plan.attempt(plan.tasks[0].task_id),
        failure=failure,
    )

    with pytest.raises(FailureRecordError) as captured:
        plan.aggregate([result])

    assert captured.value.failure == failure


def test_policy_resolves_from_experiment_and_rejects_result_gaps() -> None:
    experiment = load_route_document(
        "examples/prototype/real_core_effect_veiler.route.yaml"
    )["experiment"]
    experiment = deepcopy(experiment)
    experiment["search"].setdefault("parameters", {})["parallel"] = {
        "base_seed": 42,
        "max_retries": 1,
        "pool_size": 4,
    }
    policy = ParallelSearchPolicy.from_experiment(experiment)
    plan = ParallelExecutionPlan.build(
        experiment_id="experiment_parallel",
        run_id="run_parallel",
        policy=policy,
        candidates=[_candidate(0)],
    )
    retry_without_first = ParallelTaskResult.success(
        plan.attempt(plan.tasks[0].task_id, 1),
        score=1,
        result_ref="route:x",
        result_digest="digest_x",
    )

    assert policy.pool_size == 4
    assert policy.to_dict()["policy_id"].startswith("parallelpol_")
    with pytest.raises(ValueError, match="contiguous"):
        plan.aggregate([retry_without_first])
