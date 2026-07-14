from __future__ import annotations

from concurrent.futures import Future
from itertools import count

import pytest

from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    FailureRecord,
    FailureRecordError,
    RecoveryAction,
)
from ygo_effect_dsl.prototype.real_core import RealCoreWorkerProcessResult
from ygo_effect_dsl.prototype.real_core_stress import (
    _build_plan,
    _execute_plan,
    run_real_core_parallel_stress,
)


def test_parallel_stress_contract_with_injected_worker_outcomes() -> None:
    process_ids = count(1000)

    def fake_invoker(**kwargs: object) -> RealCoreWorkerProcessResult:
        process_id = next(process_ids)
        failure = kwargs["stress_failure"]
        if failure is not None:
            failure_record = (
                FailureRecord(
                    category="callback_error",
                    disposition=FailureDisposition.PATH_FAILURE,
                    recovery=RecoveryAction.REPLACE_WORKER,
                    retryable=True,
                    message="DataReader: injected callback failure",
                    exception_type="OcgcoreCallbackError",
                )
                if failure == "callback_error"
                else None
            )
            return RealCoreWorkerProcessResult(
                document=None,
                process_id=process_id,
                returncode=-9 if failure == "worker_timeout" else 86,
                timed_out=failure == "worker_timeout",
                terminated=True,
                failure_category=str(failure),
                stdout_digest=f"stdout_{process_id}",
                stderr_digest=f"stderr_{process_id}",
                diagnostic=(
                    "OcgcoreCallbackError: DataReader: injected"
                    if failure == "callback_error"
                    else str(failure)
                ),
                failure_record=failure_record,
            )
        return RealCoreWorkerProcessResult(
            document={
                "route_id": "route_stable",
                "replay": {"events": [{"step": 0}]},
                "result": {"terminal_board": {"score": 11}},
            },
            process_id=process_id,
            returncode=0,
            timed_out=False,
            terminated=True,
            failure_category=None,
            stdout_digest=f"stdout_{process_id}",
            stderr_digest=f"stderr_{process_id}",
            diagnostic="",
        )

    report = run_real_core_parallel_stress(
        pool_sizes=(1, 2, 4),
        task_count=4,
        include_failure_injection=True,
        invoker=fake_invoker,
    )

    assert report["semantic_report_id"].startswith("realcorestress_")
    assert all(report["verification"].values())
    assert {
        run["aggregate"]["aggregate_id"] for run in report["pool_runs"]
    } == {report["pool_runs"][0]["aggregate"]["aggregate_id"]}
    assert len(
        {run["aggregate"]["execution_id"] for run in report["pool_runs"]}
    ) == 3
    assert report["failure_injection"]["aggregate"]["summary"] == {
        "best_node_id": report["failure_injection"]["aggregate"]["summary"][
            "best_node_id"
        ],
        "best_task_id": report["failure_injection"]["aggregate"]["summary"][
            "best_task_id"
        ],
        "failed": 1,
        "pending": 0,
        "success": 3,
        "total_score": 33.0,
    }


def _classified_invoker() -> tuple[object, count]:
    process_ids = count(2000)

    def invoke(**kwargs: object) -> RealCoreWorkerProcessResult:
        process_id = next(process_ids)
        disposition = kwargs["stress_failure"]
        if disposition is not None:
            is_experiment = disposition == "experiment_failure"
            failure = FailureRecord(
                category="candidate_policy",
                disposition=(
                    FailureDisposition.EXPERIMENT_FAILURE
                    if is_experiment
                    else FailureDisposition.PATH_FAILURE
                ),
                recovery=(
                    RecoveryAction.ABORT_EXPERIMENT
                    if is_experiment
                    else RecoveryAction.STOP_PATH
                ),
                retryable=False,
                message=str(disposition),
                exception_type="InterruptionCandidatePolicyError",
                context={"step": 5},
            )
            return RealCoreWorkerProcessResult(
                document=None,
                process_id=process_id,
                returncode=1,
                timed_out=False,
                terminated=True,
                failure_category=failure.category,
                stdout_digest=f"stdout_{process_id}",
                stderr_digest=f"stderr_{process_id}",
                diagnostic=failure.message,
                failure_record=failure,
            )
        return RealCoreWorkerProcessResult(
            document={
                "route_id": f"route_{process_id}",
                "replay": {"events": [{"step": 0}]},
                "result": {"terminal_board": {"score": 11}},
            },
            process_id=process_id,
            returncode=0,
            timed_out=False,
            terminated=True,
            failure_category=None,
            stdout_digest=f"stdout_{process_id}",
            stderr_digest=f"stderr_{process_id}",
            diagnostic="",
        )

    return invoke, process_ids


def test_path_failure_stops_only_its_branch_and_keeps_siblings() -> None:
    plan = _build_plan(pool_size=3, task_count=3)
    invoker, _ = _classified_invoker()

    run = _execute_plan(
        plan,
        external_root=None,
        failure_schedules={plan.tasks[0].task_id: {0: "path_failure"}},
        reverse_aggregation_input=False,
        invoker=invoker,
    )

    assert run["aggregate"]["summary"]["failed"] == 1
    assert run["aggregate"]["summary"]["success"] == 2
    failed_process = next(
        process for process in run["processes"] if "failure" in process
    )
    assert failed_process["failure"]["disposition"] == "path_failure"
    assert failed_process["failure"]["recovery"] == "stop_path"


def test_experiment_failure_aborts_parallel_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _build_plan(pool_size=2, task_count=2)
    invoker, _ = _classified_invoker()
    cancelled: list[Future[object]] = []
    original_cancel = Future.cancel

    def record_cancel(future: Future[object]) -> bool:
        cancelled.append(future)
        return original_cancel(future)

    monkeypatch.setattr(Future, "cancel", record_cancel)
    monkeypatch.setattr(
        type(plan),
        "aggregate",
        lambda *_args, **_kwargs: pytest.fail(
            "experiment failure must not produce aggregate evidence"
        ),
    )

    with pytest.raises(FailureRecordError) as captured:
        _execute_plan(
            plan,
            external_root=None,
            failure_schedules={
                plan.tasks[0].task_id: {0: "experiment_failure"}
            },
            reverse_aggregation_input=False,
            invoker=invoker,
        )

    assert captured.value.failure.disposition == (
        FailureDisposition.EXPERIMENT_FAILURE
    )
    assert captured.value.failure.recovery == RecoveryAction.ABORT_EXPERIMENT
    assert cancelled
