from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ygo_effect_dsl.storage import (
    JOB_CATALOG_SCHEMA_VERSION,
    JobArtifact,
    JobCatalog,
    JobIdempotencyConflict,
    JobKind,
    JobLeaseError,
    JobSpec,
    JobState,
    JobStateTransitionError,
    is_job_transition_allowed,
    job_state_machine_document,
)


T0 = "2026-07-15T10:00:00Z"
T1 = "2026-07-15T10:00:01Z"
T2 = "2026-07-15T10:00:02Z"
T11 = "2026-07-15T10:00:11Z"
T12 = "2026-07-15T10:00:12Z"
T23 = "2026-07-15T10:00:23Z"


def _id(prefix: str, character: str) -> str:
    return prefix + character * 64


def _search_spec(
    key: str,
    *,
    priority: int = 0,
    max_attempts: int = 3,
    dependency_ids: tuple[str, ...] = (),
) -> JobSpec:
    return JobSpec(
        kind=JobKind.SEARCH,
        idempotency_key=key,
        input_digest=_id("jobinput_", "a"),
        payload={
            "experiment_digest": _id("experiment_", "b"),
            "experiment_id": f"experiment-{key}",
        },
        priority=priority,
        max_attempts=max_attempts,
        dependency_ids=dependency_ids,
    )


def _artifact(path: str = "results/search.json", character: str = "c") -> JobArtifact:
    return JobArtifact(
        kind="search-result",
        path=path,
        sha256=character * 64,
        schema_version="search-run-result-v5",
        row_count=1,
    )


def _claim(catalog: JobCatalog, *, now: str = T1):
    claimed = catalog.claim_next(
        worker_id="worker-1",
        now=now,
        lease_seconds=10,
    )
    assert claimed is not None
    assert claimed.lease_token is not None
    return claimed


def test_state_machine_document_is_complete_and_terminal_states_have_no_edges() -> None:
    document = job_state_machine_document()

    assert document["states"] == [state.value for state in JobState]
    assert set(document["transitions"]) == set(document["states"])
    assert document["transitions"]["cancelled"] == []
    assert document["transitions"]["succeeded"] == []
    assert document["transitions"]["quarantined"] == []
    assert document["transitions"]["running"] == [
        "cancelling",
        "failed",
        "quarantined",
        "retrying",
        "succeeded",
    ]
    for previous in JobState:
        for target in JobState:
            assert is_job_transition_allowed(previous, target) is (
                target.value in document["transitions"][previous.value]
            )


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        (
            JobKind.SEARCH,
            {
                "experiment_digest": _id("experiment_", "a"),
                "experiment_id": "exp-1",
            },
        ),
        (
            JobKind.REPLAY,
            {
                "replay_manifest_hash": _id("manifest_", "b"),
                "route_id": _id("route_", "c"),
            },
        ),
        (
            JobKind.IMPORT,
            {
                "corpus_item_id": _id("corpusitem_", "d"),
                "source_uri": "file:///evidence/item.json",
            },
        ),
        (
            JobKind.AGGREGATE,
            {
                "corpus_item_ids": [
                    _id("corpusitem_", "f"),
                    _id("corpusitem_", "e"),
                ],
                "evaluator_id": "resource-consumption",
                "evaluator_version": "v1",
            },
        ),
        (
            JobKind.EXPORT,
            {
                "format": "parquet",
                "query_snapshot_id": _id("querysnapshot_", "f"),
            },
        ),
    ],
)
def test_job_kind_payload_contracts_are_machine_validated(
    kind: JobKind,
    payload: dict[str, object],
) -> None:
    spec = JobSpec(
        kind=kind,
        idempotency_key=f"{kind.value}-1",
        input_digest=_id("jobinput_", "0"),
        payload=payload,
    )

    assert spec.kind == kind
    assert spec.job_id.startswith("job_")
    if kind == JobKind.AGGREGATE:
        assert spec.payload["corpus_item_ids"] == sorted(payload["corpus_item_ids"])


def test_job_payload_rejects_unknown_fields_and_duplicate_aggregate_items() -> None:
    with pytest.raises(ValueError, match="fields must be exactly"):
        JobSpec(
            kind=JobKind.SEARCH,
            idempotency_key="unknown-field",
            input_digest=_id("jobinput_", "0"),
            payload={
                "experiment_digest": _id("experiment_", "1"),
                "experiment_id": "exp-1",
                "guess_rules": True,
            },
        )
    item_id = _id("corpusitem_", "2")
    with pytest.raises(ValueError, match="must be unique"):
        JobSpec(
            kind=JobKind.AGGREGATE,
            idempotency_key="duplicate-items",
            input_digest=_id("jobinput_", "0"),
            payload={
                "corpus_item_ids": [item_id, item_id],
                "evaluator_id": "evaluator",
                "evaluator_version": "v1",
            },
        )


def test_create_is_idempotent_and_conflicting_key_fails_closed(tmp_path: Path) -> None:
    catalog = JobCatalog(tmp_path / "jobs.sqlite3")
    original = _search_spec("same-key")

    first = catalog.create_job(original, created_at=T0)
    second = catalog.create_job(original, created_at=T1)

    assert first == second
    assert first.spec == original
    assert [item.to_state for item in catalog.transitions(first.job_id)] == [
        JobState.QUEUED
    ]
    with pytest.raises(JobIdempotencyConflict, match="another JobSpec"):
        catalog.create_job(
            JobSpec(
                **{
                    **original.__dict__,
                    "payload": {
                        "experiment_digest": _id("experiment_", "d"),
                        "experiment_id": "different",
                    },
                }
            ),
            created_at=T2,
        )


def test_dependency_gate_and_priority_order_are_deterministic(tmp_path: Path) -> None:
    catalog = JobCatalog(tmp_path / "jobs.sqlite3")
    parent = catalog.create_job(
        _search_spec("parent", priority=1),
        created_at=T0,
    )
    catalog.create_job(
        _search_spec("independent", priority=5),
        created_at=T0,
    )
    child = catalog.create_job(
        _search_spec("child", priority=10, dependency_ids=(parent.job_id,)),
        created_at=T0,
    )

    independent_claim = _claim(catalog)
    assert independent_claim.job_id not in {parent.job_id, child.job_id}
    assert independent_claim.spec.payload["experiment_id"] == (
        "experiment-independent"
    )
    catalog.succeed_job(
        independent_claim.job_id,
        actor="worker-1",
        now=T2,
        lease_token=independent_claim.lease_token,
        artifacts=[_artifact("independent.json")],
    )
    parent_claim = _claim(catalog, now=T2)
    assert parent_claim.job_id == parent.job_id
    catalog.succeed_job(
        parent.job_id,
        actor="worker-1",
        now="2026-07-15T10:00:03Z",
        lease_token=parent_claim.lease_token,
        artifacts=[_artifact("parent.json", "d")],
    )

    child_claim = _claim(catalog, now="2026-07-15T10:00:04Z")
    assert child_claim.job_id == child.job_id


def test_heartbeat_extends_lease_and_wrong_token_is_rejected(tmp_path: Path) -> None:
    catalog = JobCatalog(tmp_path / "jobs.sqlite3")
    job = catalog.create_job(_search_spec("heartbeat"), created_at=T0)
    claimed = _claim(catalog)

    with pytest.raises(JobLeaseError, match="does not match"):
        catalog.heartbeat(
            job.job_id,
            lease_token="lease_wrong",
            now=T2,
            lease_seconds=20,
        )
    heartbeat = catalog.heartbeat(
        job.job_id,
        lease_token=claimed.lease_token,
        now=T2,
        lease_seconds=20,
    )

    assert heartbeat.heartbeat_at == T2
    assert heartbeat.lease_expires_at == "2026-07-15T10:00:22Z"
    assert catalog.reclaim_orphans(now=T12) == ()


def test_orphan_is_retried_then_failed_at_max_attempts(tmp_path: Path) -> None:
    catalog = JobCatalog(tmp_path / "jobs.sqlite3")
    job = catalog.create_job(
        _search_spec("orphan", max_attempts=2),
        created_at=T0,
    )
    first_claim = _claim(catalog)

    first_reclaim = catalog.reclaim_orphans(now=T12)
    assert first_reclaim[0].state == JobState.RETRYING
    second_claim = _claim(catalog, now=T12)
    assert second_claim.attempt == 2
    assert second_claim.lease_token != first_claim.lease_token
    with pytest.raises(JobLeaseError, match="does not match"):
        catalog.heartbeat(
            job.job_id,
            lease_token=first_claim.lease_token,
            now=T12,
            lease_seconds=10,
        )

    final_reclaim = catalog.reclaim_orphans(now=T23)

    assert final_reclaim[0].state == JobState.FAILED
    assert final_reclaim[0].error_code == "attempts_exhausted"
    assert [item.to_state for item in catalog.transitions(job.job_id)] == [
        JobState.QUEUED,
        JobState.RUNNING,
        JobState.RETRYING,
        JobState.RUNNING,
        JobState.FAILED,
    ]


def test_cancellation_preserves_active_lease_until_worker_ack(tmp_path: Path) -> None:
    catalog = JobCatalog(tmp_path / "jobs.sqlite3")
    job = catalog.create_job(_search_spec("cancel"), created_at=T0)
    claimed = _claim(catalog)

    cancelling = catalog.request_cancel(
        job.job_id,
        actor="operator",
        now=T2,
        reason="user_request",
    )

    assert cancelling.state == JobState.CANCELLING
    assert cancelling.lease_token == claimed.lease_token
    with pytest.raises(JobLeaseError, match="token is required"):
        catalog.finish_cancelled(
            job.job_id,
            actor="worker-1",
            now="2026-07-15T10:00:03Z",
            reason="cancel_ack",
        )
    cancelled = catalog.finish_cancelled(
        job.job_id,
        actor="worker-1",
        now="2026-07-15T10:00:03Z",
        reason="cancel_ack",
        lease_token=claimed.lease_token,
    )

    assert cancelled.state == JobState.CANCELLED
    assert cancelled.lease_token is None
    with pytest.raises(JobStateTransitionError, match="invalid job transition"):
        catalog.schedule_retry(
            job.job_id,
            actor="scheduler",
            now="2026-07-15T10:00:04Z",
            reason="invalid",
        )


def test_success_and_artifacts_commit_atomically_and_idempotently(
    tmp_path: Path,
) -> None:
    catalog = JobCatalog(tmp_path / "jobs.sqlite3")
    job = catalog.create_job(_search_spec("success"), created_at=T0)
    claimed = _claim(catalog)
    artifacts = [_artifact(), _artifact("results/route.yaml", "d")]

    succeeded = catalog.succeed_job(
        job.job_id,
        actor="worker-1",
        now=T2,
        lease_token=claimed.lease_token,
        artifacts=artifacts,
    )
    repeated = catalog.succeed_job(
        job.job_id,
        actor="worker-1",
        now=T11,
        lease_token="lease_already_released",
        artifacts=reversed(artifacts),
    )

    assert succeeded == repeated
    assert succeeded.state == JobState.SUCCEEDED
    assert succeeded.artifact_set_id is not None
    assert set(catalog.artifacts(job.job_id)) == set(artifacts)
    assert catalog.transitions(job.job_id)[-1].reason == "artifact_commit"
    with pytest.raises(JobIdempotencyConflict, match="different artifact set"):
        catalog.succeed_job(
            job.job_id,
            actor="worker-1",
            now=T12,
            lease_token="lease_already_released",
            artifacts=[_artifact("different.json", "e")],
        )


def test_artifact_constraint_failure_rolls_back_success_transition(
    tmp_path: Path,
) -> None:
    catalog = JobCatalog(tmp_path / "jobs.sqlite3")
    job = catalog.create_job(_search_spec("atomic-rollback"), created_at=T0)
    claimed = _claim(catalog)
    duplicate = _artifact()

    with pytest.raises(sqlite3.IntegrityError):
        catalog.succeed_job(
            job.job_id,
            actor="worker-1",
            now=T2,
            lease_token=claimed.lease_token,
            artifacts=[duplicate, duplicate],
        )

    current = catalog.get_job(job.job_id)
    assert current is not None
    assert current.state == JobState.RUNNING
    assert current.artifact_set_id is None
    assert catalog.artifacts(job.job_id) == ()
    assert catalog.transitions(job.job_id)[-1].to_state == JobState.RUNNING


def test_catalog_requires_explicit_schema_migration_without_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jobs.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_meta VALUES ('schema_version', 'job-catalog-v0')"
        )

    with pytest.raises(ValueError, match="explicit migration"):
        JobCatalog(path).initialize()

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        version = connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
    assert tables == {"schema_meta"}
    assert version == "job-catalog-v0"
    assert JOB_CATALOG_SCHEMA_VERSION == "job-catalog-v1"
