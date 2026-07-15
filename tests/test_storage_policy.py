from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from ygo_effect_dsl.storage import (
    ArtifactKind,
    RawLogRecord,
    RUN_CATALOG_SCHEMA_VERSION,
    RunCatalog,
    RunRecord,
    RunStatus,
    StorageFormat,
    artifact_policy,
    read_raw_log,
    storage_policy_document,
    write_raw_log,
)


def test_storage_policy_separates_operational_analytics_and_human_artifacts() -> None:
    assert artifact_policy(ArtifactKind.RAW_EVENT_LOG).storage_format == (
        StorageFormat.JSON_LINES
    )
    assert artifact_policy(ArtifactKind.RUN_CATALOG).storage_format == (
        StorageFormat.SQLITE
    )
    assert artifact_policy(ArtifactKind.RUN_CATALOG).schema_version == (
        RUN_CATALOG_SCHEMA_VERSION
    )
    assert artifact_policy(ArtifactKind.AGGREGATION).storage_format == (
        StorageFormat.PARQUET
    )
    assert artifact_policy(ArtifactKind.AGGREGATION).implementation == (
        "implemented_pyarrow_optional"
    )
    assert artifact_policy(ArtifactKind.HUMAN_REPORT).storage_format == (
        StorageFormat.MARKDOWN_HTML
    )
    policy = storage_policy_document()
    assert policy["schema_version"] == "storage-policy-v1"
    assert policy["migration_policy"]["automatic_in_place_migration"] is False


def test_raw_jsonl_round_trip_preserves_order_and_hashes(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    records = (
        RawLogRecord("run_1", 0, "run_started", {"experiment_id": "exp_1"}),
        RawLogRecord("run_1", 1, "route_completed", {"route_id": "route_1"}),
    )

    write_raw_log(path, records)

    assert read_raw_log(path) == records
    lines = path.read_text(encoding="utf-8").splitlines()
    assert all(json.loads(line)["record_id"].startswith("log_") for line in lines)


def test_raw_jsonl_rejects_non_contiguous_or_tampered_records(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="contiguous"):
        write_raw_log(
            tmp_path / "invalid.jsonl",
            (RawLogRecord("run_1", 1, "late", {}),),
        )
    path = tmp_path / "tampered.jsonl"
    record = RawLogRecord("run_1", 0, "started", {}).to_dict()
    record["payload"] = {"tampered": True}
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="record_id"):
        read_raw_log(path)


def test_sqlite_catalog_tracks_run_lifecycle_and_route_reference(tmp_path: Path) -> None:
    catalog = RunCatalog(tmp_path / "runs.sqlite3")
    catalog.create_run(
        RunRecord(
            run_id="run_1",
            experiment_id="exp_1",
            status=RunStatus.RUNNING,
            started_at="2026-07-13T10:00:00Z",
        )
    )
    catalog.add_route(
        route_id="route_1",
        run_id="run_1",
        route_path="routes/route_1.yaml",
        state_hash="state_1",
    )
    catalog.finish_run(
        "run_1",
        status=RunStatus.COMPLETE,
        finished_at="2026-07-13T10:01:00Z",
    )

    record = catalog.get_run("run_1")
    assert record is not None
    assert record.status == RunStatus.COMPLETE
    assert record.finished_at == "2026-07-13T10:01:00Z"
    with pytest.raises(ValueError, match="already finished"):
        catalog.finish_run(
            "run_1",
            status=RunStatus.COMPLETE,
            finished_at="2026-07-13T10:02:00Z",
        )


def test_sqlite_catalog_batches_run_lifecycle_atomically(tmp_path: Path) -> None:
    path = tmp_path / "batch-runs.sqlite3"
    catalog = RunCatalog(path)
    records = tuple(
        RunRecord(
            run_id=f"run_{index}",
            experiment_id="experiment_batch",
            status=RunStatus.RUNNING,
            started_at="2026-07-13T10:00:00Z",
        )
        for index in range(4)
    )

    assert catalog.create_runs(records) == 4
    assert catalog.finish_runs(
        (record.run_id for record in records),
        status=RunStatus.COMPLETE,
        finished_at="2026-07-13T10:01:00Z",
    ) == 4
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT status, COUNT(*) FROM runs GROUP BY status"
        ).fetchall() == [("complete", 4)]

    with pytest.raises(ValueError, match="missing or already finished"):
        catalog.finish_runs(
            ("run_0", "missing"),
            status=RunStatus.FAILED,
            finished_at="2026-07-13T10:02:00Z",
        )
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'failed'"
        ).fetchone() == (0,)

    pending = RunRecord(
        run_id="run_pending",
        experiment_id="experiment_batch",
        status=RunStatus.RUNNING,
        started_at="2026-07-13T10:03:00Z",
    )
    catalog.create_run(pending)
    with pytest.raises(ValueError, match="missing or already finished"):
        catalog.finish_runs(
            (pending.run_id, "missing"),
            status=RunStatus.FAILED,
            finished_at="2026-07-13T10:04:00Z",
        )
    assert catalog.get_run(pending.run_id).status == RunStatus.RUNNING


def test_sqlite_catalog_requires_explicit_schema_migration(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    catalog = RunCatalog(path)
    catalog.initialize()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE schema_meta SET value = 'run-catalog-v0' WHERE key = 'schema_version'"
        )

    with pytest.raises(ValueError, match="explicit migration"):
        catalog.initialize()


def test_legacy_catalog_is_not_modified_before_migration(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_meta VALUES ('schema_version', 'run-catalog-v1')"
        )
    catalog = RunCatalog(path)

    with pytest.raises(ValueError, match="explicit migration"):
        catalog.initialize()

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert tables == {"schema_meta"}


def test_sqlite_catalog_rejects_route_for_unknown_run(tmp_path: Path) -> None:
    catalog = RunCatalog(tmp_path / "runs.sqlite3")

    with pytest.raises(sqlite3.IntegrityError):
        catalog.add_route(
            route_id="route_1",
            run_id="missing",
            route_path="route.yaml",
            state_hash="state_1",
        )
