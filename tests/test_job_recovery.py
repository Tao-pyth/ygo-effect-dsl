from __future__ import annotations

import errno
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.storage import (
    InjectedJobFault,
    JobArtifact,
    JobArtifactIntegrityError,
    JobArtifactPublisher,
    JobCatalog,
    JobCheckpointConflict,
    JobFaultPoint,
    JobLeaseError,
    JobRecoverySupervisor,
    JobRetryPolicy,
    JobSpec,
    JobState,
    JobStateTransitionError,
    fault_at,
    job_status_document,
    save_checkpoint_with_fault,
)


def _id(prefix: str, character: str) -> str:
    return prefix + character * 64


def _policy(
    *,
    timeout: float = 10.0,
    initial_backoff: float = 0.0,
) -> JobRetryPolicy:
    return JobRetryPolicy(
        attempt_timeout_seconds=timeout,
        initial_backoff_seconds=initial_backoff,
        backoff_multiplier=2,
        max_backoff_seconds=max(initial_backoff * 4, initial_backoff),
    )


def _spec(
    key: str,
    *,
    deadline_at: str | None = None,
    max_attempts: int = 3,
    retry_policy: JobRetryPolicy | None = None,
) -> JobSpec:
    return JobSpec(
        kind="search",
        idempotency_key=key,
        input_digest=_id("jobinput_", "a"),
        payload={
            "experiment_digest": _id("experiment_", "b"),
            "experiment_id": f"experiment-{key}",
        },
        max_attempts=max_attempts,
        deadline_at=deadline_at,
        retry_policy=retry_policy or _policy(),
    )


def _aggregate_spec(key: str) -> JobSpec:
    return JobSpec(
        kind="aggregate",
        idempotency_key=key,
        input_digest=_id("jobinput_", "c"),
        payload={
            "corpus_item_ids": [
                _id("corpusitem_", "d"),
                _id("corpusitem_", "e"),
            ],
            "evaluator_id": "resource-consumption",
            "evaluator_version": "v1",
        },
        retry_policy=_policy(),
    )


def _running_job(
    tmp_path: Path,
    *,
    key: str = "job",
    spec: JobSpec | None = None,
    now: str = "2026-07-15T10:00:00Z",
):
    catalog = JobCatalog(tmp_path / f"{key}.sqlite3")
    created = catalog.create_job(spec or _spec(key), created_at=now)
    claimed = catalog.claim_next(
        worker_id="worker-1",
        now=now,
        lease_seconds=100,
    )
    assert claimed is not None
    assert claimed.job_id == created.job_id
    assert claimed.lease_token is not None
    return catalog, claimed


def _checkpoint_fields(job, *, position: str = "row:2") -> dict[str, object]:
    return {
        "job_id": job.job_id,
        "lease_token": job.lease_token,
        "now": "2026-07-15T10:00:02Z",
        "recovery_position": position,
        "completed_units": 2,
        "total_units": 4,
        "payload": {"next_index": 2, "sum": 3},
    }


def test_retry_policy_has_capped_deterministic_backoff() -> None:
    policy = JobRetryPolicy(
        attempt_timeout_seconds=5,
        initial_backoff_seconds=2,
        backoff_multiplier=3,
        max_backoff_seconds=10,
    )

    assert policy.backoff_after(1) == 2
    assert policy.backoff_after(2) == 6
    assert policy.backoff_after(3) == 10
    assert JobRetryPolicy.from_dict(policy.to_dict()) == policy
    with pytest.raises(ValueError, match="backoff_multiplier"):
        JobRetryPolicy(backoff_multiplier=0.5)


def test_attempt_timeout_is_capped_by_job_deadline_and_heartbeat(
    tmp_path: Path,
) -> None:
    spec = _spec(
        "deadline-cap",
        deadline_at="2026-07-15T10:00:10Z",
        retry_policy=_policy(timeout=30),
    )
    catalog, job = _running_job(tmp_path, spec=spec)

    assert job.attempt_deadline_at == "2026-07-15T10:00:10Z"
    heartbeat = catalog.heartbeat(
        job.job_id,
        lease_token=job.lease_token,
        now="2026-07-15T10:00:05Z",
        lease_seconds=30,
    )
    assert heartbeat.lease_expires_at == "2026-07-15T10:00:10Z"
    signal = catalog.control_signal(
        job.job_id,
        lease_token=job.lease_token,
        now="2026-07-15T10:00:10Z",
    )
    assert signal.should_stop is True
    assert signal.job_deadline_exceeded is True
    assert signal.attempt_timeout_exceeded is True
    with pytest.raises(JobLeaseError, match="expired"):
        catalog.heartbeat(
            job.job_id,
            lease_token=job.lease_token,
            now="2026-07-15T10:00:10Z",
            lease_seconds=1,
        )


def test_pending_deadline_expires_without_becoming_runnable(tmp_path: Path) -> None:
    catalog = JobCatalog(tmp_path / "jobs.sqlite3")
    job = catalog.create_job(
        _spec("pending-deadline", deadline_at="2026-07-15T10:00:05Z"),
        created_at="2026-07-15T10:00:00Z",
    )

    assert (
        catalog.claim_next(
            worker_id="worker-1",
            now="2026-07-15T10:00:05Z",
            lease_seconds=10,
        )
        is None
    )
    expired = catalog.expire_pending_deadlines(
        now="2026-07-15T10:00:05Z"
    )

    assert expired[0].job_id == job.job_id
    assert expired[0].state == JobState.FAILED
    assert expired[0].error_code == "deadline_exceeded"


def test_supervisor_kills_before_retry_and_applies_retry_gate(tmp_path: Path) -> None:
    catalog, job = _running_job(
        tmp_path,
        spec=_spec(
            "hard-timeout",
            max_attempts=2,
            retry_policy=_policy(timeout=5, initial_backoff=2),
        ),
    )
    terminated: list[str] = []

    report = JobRecoverySupervisor(catalog).enforce_timeouts(
        now="2026-07-15T10:00:05Z",
        terminate_attempt=lambda record: terminated.append(record.job_id),
    )

    recovered = catalog.get_job(job.job_id)
    assert recovered is not None
    assert terminated == [job.job_id]
    assert report.recovered_attempt_job_ids == (job.job_id,)
    assert recovered.state == JobState.RETRYING
    assert recovered.retry_not_before_at == "2026-07-15T10:00:07Z"
    assert (
        catalog.claim_next(
            worker_id="worker-2",
            now="2026-07-15T10:00:06Z",
            lease_seconds=10,
        )
        is None
    )
    retry = catalog.claim_next(
        worker_id="worker-2",
        now="2026-07-15T10:00:07Z",
        lease_seconds=10,
    )
    assert retry is not None
    assert retry.attempt == 2


def test_failed_process_termination_does_not_release_attempt(tmp_path: Path) -> None:
    catalog, job = _running_job(
        tmp_path,
        spec=_spec("kill-failure", retry_policy=_policy(timeout=1)),
    )

    def fail_to_terminate(_job) -> None:
        raise RuntimeError("process still alive")

    with pytest.raises(RuntimeError, match="still alive"):
        JobRecoverySupervisor(catalog).enforce_timeouts(
            now="2026-07-15T10:00:01Z",
            terminate_attempt=fail_to_terminate,
        )

    current = catalog.get_job(job.job_id)
    assert current is not None
    assert current.state == JobState.RUNNING
    assert current.lease_token == job.lease_token


def test_fractional_retry_gate_uses_timestamp_value(tmp_path: Path) -> None:
    catalog, _job = _running_job(
        tmp_path,
        spec=_spec(
            "fractional-backoff",
            retry_policy=_policy(timeout=5, initial_backoff=0.5),
        ),
    )
    JobRecoverySupervisor(catalog).enforce_timeouts(
        now="2026-07-15T10:00:05Z",
        terminate_attempt=lambda _record: None,
    )

    assert (
        catalog.claim_next(
            worker_id="worker-2",
            now="2026-07-15T10:00:05.400000Z",
            lease_seconds=10,
        )
        is None
    )
    claimed = catalog.claim_next(
        worker_id="worker-2",
        now="2026-07-15T10:00:05.500000Z",
        lease_seconds=10,
    )
    assert claimed is not None
    assert claimed.attempt == 2


def test_cancelling_timed_out_attempt_becomes_cancelled(tmp_path: Path) -> None:
    catalog, job = _running_job(
        tmp_path,
        spec=_spec("cancel-timeout", retry_policy=_policy(timeout=2)),
    )
    catalog.request_cancel(
        job.job_id,
        actor="operator",
        now="2026-07-15T10:00:01Z",
        reason="user_request",
    )

    JobRecoverySupervisor(catalog).enforce_timeouts(
        now="2026-07-15T10:00:02Z",
        terminate_attempt=lambda _record: None,
    )

    current = catalog.get_job(job.job_id)
    assert current is not None
    assert current.state == JobState.CANCELLED
    assert catalog.transitions(job.job_id)[-1].reason == "cancel_timeout"


def test_checkpoint_is_idempotent_monotonic_and_input_bound(tmp_path: Path) -> None:
    catalog, job = _running_job(tmp_path, key="checkpoint")
    fields = _checkpoint_fields(job)

    first = catalog.save_checkpoint(**fields)
    repeated = catalog.save_checkpoint(
        **{**fields, "now": "2026-07-15T10:00:03Z"}
    )

    assert repeated == first
    assert catalog.resume_checkpoint(
        job.job_id,
        expected_input_digest=job.spec.input_digest,
    ) == first
    with pytest.raises(JobCheckpointConflict, match="different checkpoint"):
        catalog.save_checkpoint(
            **{**fields, "payload": {"next_index": 2, "sum": 99}}
        )
    with pytest.raises(JobCheckpointConflict, match="move backwards"):
        catalog.save_checkpoint(
            **{
                **fields,
                "recovery_position": "row:1",
                "completed_units": 1,
            }
        )
    with pytest.raises(JobCheckpointConflict, match="resume input digest"):
        catalog.resume_checkpoint(
            job.job_id,
            expected_input_digest=_id("jobinput_", "f"),
        )


def test_cancelling_worker_can_checkpoint_before_ack(tmp_path: Path) -> None:
    catalog, job = _running_job(tmp_path, key="cancel-checkpoint")
    catalog.request_cancel(
        job.job_id,
        actor="operator",
        now="2026-07-15T10:00:01Z",
        reason="user_request",
    )

    checkpoint = catalog.save_checkpoint(**_checkpoint_fields(job))
    cancelled = catalog.finish_cancelled(
        job.job_id,
        actor="worker-1",
        now="2026-07-15T10:00:03Z",
        reason="cancel_ack",
        lease_token=job.lease_token,
    )

    assert checkpoint.recovery_position == "row:2"
    assert cancelled.state == JobState.CANCELLED
    assert cancelled.recovery_position == "row:2"


def test_unknown_progress_total_can_become_known_but_not_change(tmp_path: Path) -> None:
    catalog, job = _running_job(tmp_path, key="progress")
    common = _checkpoint_fields(job)
    catalog.save_checkpoint(**{**common, "total_units": None})
    known = catalog.save_checkpoint(
        **{
            **common,
            "now": "2026-07-15T10:00:03Z",
            "recovery_position": "row:3",
            "completed_units": 3,
            "total_units": 5,
        }
    )

    assert known.total_units == 5
    with pytest.raises(JobCheckpointConflict, match="cannot change"):
        catalog.save_checkpoint(
            **{
                **common,
                "now": "2026-07-15T10:00:04Z",
                "recovery_position": "row:4",
                "completed_units": 4,
                "total_units": 6,
            }
        )


def test_checkpoint_faults_are_atomic_on_both_sides_of_commit(tmp_path: Path) -> None:
    catalog, job = _running_job(tmp_path, key="checkpoint-fault")
    fields = _checkpoint_fields(job)

    with pytest.raises(InjectedJobFault):
        save_checkpoint_with_fault(
            catalog,
            injector=fault_at(JobFaultPoint.BEFORE_CHECKPOINT_COMMIT),
            **fields,
        )
    assert catalog.latest_checkpoint(job.job_id) is None
    with pytest.raises(InjectedJobFault):
        save_checkpoint_with_fault(
            catalog,
            injector=fault_at(JobFaultPoint.AFTER_CHECKPOINT_COMMIT),
            **fields,
        )
    assert catalog.latest_checkpoint(job.job_id) is not None


def test_checkpoint_resume_matches_fresh_semantic_result(tmp_path: Path) -> None:
    catalog, job = _running_job(tmp_path, key="semantic-resume")
    rows = [2, 3, 5, 7, 11, 13]
    partial = {"next_index": 3, "sum": sum(rows[:3])}
    catalog.save_checkpoint(
        job.job_id,
        lease_token=job.lease_token,
        now="2026-07-15T10:00:02Z",
        recovery_position="row:3",
        completed_units=3,
        total_units=len(rows),
        payload=partial,
    )
    catalog.schedule_retry(
        job.job_id,
        actor="scheduler",
        now="2026-07-15T10:00:03Z",
        reason="worker_crash",
        error_code="worker_crash",
        lease_token=job.lease_token,
    )
    retry = catalog.claim_next(
        worker_id="worker-2",
        now="2026-07-15T10:00:03Z",
        lease_seconds=10,
    )
    assert retry is not None
    checkpoint = catalog.resume_checkpoint(
        job.job_id,
        expected_input_digest=job.spec.input_digest,
    )
    assert checkpoint is not None
    resumed = checkpoint.payload["sum"] + sum(
        rows[checkpoint.payload["next_index"] :]
    )
    fresh = sum(rows)

    assert resumed == fresh
    assert stable_digest(resumed, prefix="jobsemantic_") == stable_digest(
        fresh,
        prefix="jobsemantic_",
    )


def test_artifact_publish_and_reconcile_preserve_committed_content(
    tmp_path: Path,
) -> None:
    catalog, job = _running_job(tmp_path, key="publish")
    publisher = JobArtifactPublisher(tmp_path / "artifacts", catalog)
    staged = publisher.stage_bytes(
        job,
        lease_token=job.lease_token,
        now="2026-07-15T10:00:01Z",
        logical_path="aggregate/routes.json",
        kind="route-aggregate",
        artifact_schema_version="route-aggregate-v1",
        content=b'{"count":2}',
        row_count=2,
    )
    with pytest.raises(ValueError, match="final path"):
        publisher.publish(
            job,
            actor="worker-1",
            now="2026-07-15T10:00:02Z",
            lease_token=job.lease_token,
            staged_artifacts=[
                replace(staged, final_path=tmp_path / "outside.json")
            ],
        )

    succeeded = publisher.publish(
        job,
        actor="worker-1",
        now="2026-07-15T10:00:02Z",
        lease_token=job.lease_token,
        staged_artifacts=[staged],
    )
    report = publisher.reconcile()

    assert succeeded.state == JobState.SUCCEEDED
    assert staged.final_path.read_bytes() == b'{"count":2}'
    assert report.referenced_artifact_count == 1
    assert report.removed_paths == ()
    with pytest.raises(ValueError, match="traversal-free"):
        publisher.stage_bytes(
            job,
            lease_token="released",
            now="2026-07-15T10:00:03Z",
            logical_path="../escape.json",
            kind="bad",
            artifact_schema_version="bad-v1",
            content=b"bad",
        )


def test_partial_write_is_removed_after_attempt_enters_retry(tmp_path: Path) -> None:
    catalog, job = _running_job(tmp_path, key="partial-write")
    root = tmp_path / "artifacts"
    publisher = JobArtifactPublisher(root, catalog)

    with pytest.raises(InjectedJobFault):
        publisher.stage_bytes(
            job,
            lease_token=job.lease_token,
            now="2026-07-15T10:00:01Z",
            logical_path="aggregate/before.json",
            kind="aggregate",
            artifact_schema_version="aggregate-v1",
            content=b"not-written",
            injector=fault_at(JobFaultPoint.BEFORE_ARTIFACT_WRITE),
        )
    assert not root.exists()

    def disk_full(point: JobFaultPoint) -> None:
        if point == JobFaultPoint.DURING_ARTIFACT_WRITE:
            raise OSError(errno.ENOSPC, "disk full")

    with pytest.raises(OSError, match="disk full"):
        publisher.stage_bytes(
            job,
            lease_token=job.lease_token,
            now="2026-07-15T10:00:01Z",
            logical_path="aggregate/data.json",
            kind="aggregate",
            artifact_schema_version="aggregate-v1",
            content=b"0123456789",
            injector=disk_full,
        )
    assert any(path.is_file() for path in root.rglob("*"))
    catalog.schedule_retry(
        job.job_id,
        actor="scheduler",
        now="2026-07-15T10:00:02Z",
        reason="disk_full",
        error_code="disk_full",
        lease_token=job.lease_token,
    )

    report = publisher.reconcile()

    assert report.removed_paths
    assert not any(path.is_file() for path in root.rglob("*"))
    assert catalog.artifacts(job.job_id) == ()


def test_publisher_ignores_catalog_artifacts_owned_by_other_stores(
    tmp_path: Path,
) -> None:
    catalog, job = _running_job(tmp_path, key="external-artifact")
    catalog.succeed_job(
        job.job_id,
        actor="worker-1",
        now="2026-07-15T10:00:02Z",
        lease_token=job.lease_token,
        artifacts=[
            JobArtifact(
                kind="external-result",
                path="results/search.json",
                sha256="f" * 64,
                schema_version="search-result-v1",
            )
        ],
    )

    report = JobArtifactPublisher(tmp_path / "managed", catalog).reconcile()

    assert report.referenced_artifact_count == 0
    assert report.removed_paths == ()


def test_crash_after_rename_recovers_without_duplicate_rows_or_orphans(
    tmp_path: Path,
) -> None:
    catalog, job = _running_job(
        tmp_path,
        key="rename-crash",
        spec=_aggregate_spec("rename-crash"),
    )
    root = tmp_path / "artifacts"
    publisher = JobArtifactPublisher(root, catalog)

    def stage_all(active_job, now: str):
        return [
            publisher.stage_bytes(
                active_job,
                lease_token=active_job.lease_token,
                now=now,
                logical_path=f"aggregate/{name}.json",
                kind="aggregate",
                artifact_schema_version="aggregate-v1",
                content=content,
                row_count=1,
            )
            for name, content in (("a", b"a"), ("b", b"b"))
        ]

    first_staged = stage_all(job, "2026-07-15T10:00:01Z")
    with pytest.raises(InjectedJobFault):
        publisher.publish(
            job,
            actor="worker-1",
            now="2026-07-15T10:00:02Z",
            lease_token=job.lease_token,
            staged_artifacts=first_staged,
            injector=fault_at(JobFaultPoint.AFTER_ARTIFACT_RENAME),
        )
    assert catalog.artifacts(job.job_id) == ()
    active_report = publisher.reconcile()
    assert active_report.preserved_active_paths
    assert active_report.removed_paths == ()
    catalog.schedule_retry(
        job.job_id,
        actor="scheduler",
        now="2026-07-15T10:00:03Z",
        reason="worker_crash",
        error_code="worker_crash",
        lease_token=job.lease_token,
    )
    cleanup = publisher.reconcile()
    assert cleanup.removed_paths
    retry = catalog.claim_next(
        worker_id="worker-2",
        now="2026-07-15T10:00:03Z",
        lease_seconds=10,
    )
    assert retry is not None
    second_staged = stage_all(retry, "2026-07-15T10:00:03Z")

    publisher.publish(
        retry,
        actor="worker-2",
        now="2026-07-15T10:00:04Z",
        lease_token=retry.lease_token,
        staged_artifacts=second_staged,
    )
    final_report = publisher.reconcile()

    references = catalog.artifacts(job.job_id)
    assert len(references) == 2
    assert len({item.artifact_id for item in references}) == 2
    assert final_report.referenced_artifact_count == 2
    assert final_report.removed_paths == ()


def test_crash_after_catalog_commit_is_reconciled_as_success(tmp_path: Path) -> None:
    catalog, job = _running_job(tmp_path, key="commit-crash")
    publisher = JobArtifactPublisher(tmp_path / "artifacts", catalog)
    staged = publisher.stage_bytes(
        job,
        lease_token=job.lease_token,
        now="2026-07-15T10:00:01Z",
        logical_path="result.json",
        kind="result",
        artifact_schema_version="result-v1",
        content=b"result",
    )

    with pytest.raises(InjectedJobFault):
        publisher.publish(
            job,
            actor="worker-1",
            now="2026-07-15T10:00:02Z",
            lease_token=job.lease_token,
            staged_artifacts=[staged],
            injector=fault_at(JobFaultPoint.AFTER_CATALOG_COMMIT),
        )

    current = catalog.get_job(job.job_id)
    assert current is not None
    assert current.state == JobState.SUCCEEDED
    report = publisher.reconcile()
    assert report.referenced_artifact_count == 1
    assert report.removed_paths == ()
    repeated = catalog.succeed_job(
        job.job_id,
        actor="recovery",
        now="2026-07-15T10:00:03Z",
        lease_token="already-released",
        artifacts=[staged.artifact],
    )
    assert repeated == current


def test_missing_committed_artifact_fails_closed(tmp_path: Path) -> None:
    catalog, job = _running_job(tmp_path, key="missing-artifact")
    publisher = JobArtifactPublisher(tmp_path / "artifacts", catalog)
    staged = publisher.stage_bytes(
        job,
        lease_token=job.lease_token,
        now="2026-07-15T10:00:01Z",
        logical_path="result.json",
        kind="result",
        artifact_schema_version="result-v1",
        content=b"result",
    )
    publisher.publish(
        job,
        actor="worker-1",
        now="2026-07-15T10:00:02Z",
        lease_token=job.lease_token,
        staged_artifacts=[staged],
    )
    staged.final_path.unlink()

    with pytest.raises(JobArtifactIntegrityError, match="missing artifact"):
        publisher.reconcile()


def test_status_api_and_cli_show_attempt_reason_and_recovery_position(
    tmp_path: Path,
) -> None:
    catalog, job = _running_job(tmp_path, key="inspect")
    catalog.save_checkpoint(**_checkpoint_fields(job))
    catalog.schedule_retry(
        job.job_id,
        actor="scheduler",
        now="2026-07-15T10:00:03Z",
        reason="worker_crash",
        error_code="worker_crash",
        lease_token=job.lease_token,
    )
    document = job_status_document(catalog, job.job_id)

    assert document["job"]["attempt"] == 1
    assert document["job"]["recovery_position"] == "row:2"
    assert document["latest_checkpoint"]["recovery_position"] == "row:2"
    assert document["transitions"][-1]["reason"] == "worker_crash"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ygo_effect_dsl",
            "job-inspect",
            job.job_id,
            "--catalog",
            str(catalog.path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    cli_document = json.loads(completed.stdout)
    assert cli_document == document


def test_non_retryable_error_code_is_rejected_by_policy(tmp_path: Path) -> None:
    catalog, job = _running_job(tmp_path, key="non-retryable")

    with pytest.raises(JobStateTransitionError, match="not retryable"):
        catalog.schedule_retry(
            job.job_id,
            actor="scheduler",
            now="2026-07-15T10:00:01Z",
            reason="invalid_input",
            error_code="invalid_input",
            lease_token=job.lease_token,
        )
