from __future__ import annotations

from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sqlite3


RUN_CATALOG_SCHEMA_VERSION = "run-catalog-v2"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    experiment_id: str
    status: RunStatus
    started_at: str
    finished_at: str | None = None
    error_summary: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RunStatus):
            object.__setattr__(self, "status", RunStatus(self.status))
        for name in ("run_id", "experiment_id", "started_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.finished_at is not None and not self.finished_at:
            raise ValueError("finished_at must be non-empty or None")


@dataclass(frozen=True)
class AggregationArtifactRecord:
    batch_id: str
    run_id: str
    schema_version: str
    evaluator_version: str
    experiment_id: str
    run_date: str
    artifact_path: str
    row_count: int
    sha256: str

    def __post_init__(self) -> None:
        for name in (
            "batch_id",
            "run_id",
            "schema_version",
            "evaluator_version",
            "experiment_id",
            "run_date",
            "artifact_path",
            "sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if (
            not isinstance(self.row_count, int)
            or isinstance(self.row_count, bool)
            or self.row_count <= 0
        ):
            raise ValueError("row_count must be an integer > 0")


class RunCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            has_schema_meta = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'schema_meta'
                """
            ).fetchone() is not None
            if has_schema_meta:
                row = connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
                if row is None:
                    raise ValueError("run catalog has no schema_version metadata")
                if row[0] != RUN_CATALOG_SCHEMA_VERSION:
                    raise ValueError(
                        f"run catalog schema {row[0]!r} requires explicit migration to "
                        f"{RUN_CATALOG_SCHEMA_VERSION!r}"
                    )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    error_summary TEXT
                );
                CREATE TABLE IF NOT EXISTS routes (
                    route_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    route_path TEXT NOT NULL,
                    state_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS aggregation_artifacts (
                    batch_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    schema_version TEXT NOT NULL,
                    evaluator_version TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    run_date TEXT NOT NULL,
                    artifact_path TEXT NOT NULL UNIQUE,
                    row_count INTEGER NOT NULL CHECK(row_count > 0),
                    sha256 TEXT NOT NULL
                );
                """
            )
            if not has_schema_meta:
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?)",
                    (RUN_CATALOG_SCHEMA_VERSION,),
                )

    def create_run(self, record: RunRecord) -> None:
        self.create_runs((record,))

    def create_runs(self, records: Iterable[RunRecord]) -> int:
        received = tuple(records)
        if not received:
            raise ValueError("batch run creation requires at least one record")
        if any(not isinstance(record, RunRecord) for record in received):
            raise TypeError("records must contain RunRecord values")
        if any(
            record.status != RunStatus.RUNNING or record.finished_at is not None
            for record in received
        ):
            raise ValueError("new run must have status=running and no finished_at")
        if len({record.run_id for record in received}) != len(received):
            raise ValueError("batch run creation contains duplicate run IDs")
        self.initialize()
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                (
                    (
                        record.run_id,
                        record.experiment_id,
                        record.status.value,
                        record.started_at,
                        record.finished_at,
                        record.error_summary,
                    )
                    for record in received
                ),
            )
        return len(received)

    def finish_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        finished_at: str,
        error_summary: str | None = None,
    ) -> None:
        self.finish_runs(
            (run_id,),
            status=status,
            finished_at=finished_at,
            error_summary=error_summary,
        )

    def finish_runs(
        self,
        run_ids: Iterable[str],
        *,
        status: RunStatus,
        finished_at: str,
        error_summary: str | None = None,
    ) -> int:
        if status not in {RunStatus.COMPLETE, RunStatus.FAILED}:
            raise ValueError("finished run status must be complete or failed")
        received = tuple(run_ids)
        if not received:
            raise ValueError("batch run completion requires at least one run ID")
        if any(not isinstance(run_id, str) or not run_id for run_id in received):
            raise ValueError("run IDs must be non-empty strings")
        if len(set(received)) != len(received):
            raise ValueError("batch run completion contains duplicate run IDs")
        self.initialize()
        with closing(self._connect()) as connection, connection:
            cursor = connection.executemany(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, error_summary = ?
                WHERE run_id = ? AND status = 'running'
                """,
                (
                    (status.value, finished_at, error_summary, run_id)
                    for run_id in received
                ),
            )
            if cursor.rowcount != len(received):
                raise ValueError(
                    "one or more batch runs are missing or already finished"
                )
        return len(received)

    def add_route(
        self,
        *,
        route_id: str,
        run_id: str,
        route_path: str,
        state_hash: str,
    ) -> None:
        self.initialize()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO routes VALUES (?, ?, ?, ?)",
                (route_id, run_id, route_path, state_hash),
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        self.initialize()
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT run_id, experiment_id, status, started_at, finished_at, error_summary
                FROM runs WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunRecord(
            run_id=row[0],
            experiment_id=row[1],
            status=RunStatus(row[2]),
            started_at=row[3],
            finished_at=row[4],
            error_summary=row[5],
        )

    def add_aggregation_artifact(
        self, record: AggregationArtifactRecord
    ) -> None:
        self.initialize()
        with closing(self._connect()) as connection, connection:
            run = connection.execute(
                "SELECT experiment_id, status FROM runs WHERE run_id = ?",
                (record.run_id,),
            ).fetchone()
            if run is None:
                raise ValueError(
                    f"aggregation run {record.run_id!r} does not exist"
                )
            if run[1] != RunStatus.COMPLETE.value:
                raise ValueError("aggregation can only reference a completed run")
            if run[0] != record.experiment_id:
                raise ValueError(
                    "aggregation experiment_id must match its catalog run"
                )
            connection.execute(
                """
                INSERT INTO aggregation_artifacts
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.batch_id,
                    record.run_id,
                    record.schema_version,
                    record.evaluator_version,
                    record.experiment_id,
                    record.run_date,
                    record.artifact_path,
                    record.row_count,
                    record.sha256,
                ),
            )

    def get_aggregation_artifact(
        self, batch_id: str
    ) -> AggregationArtifactRecord | None:
        self.initialize()
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT batch_id, run_id, schema_version, evaluator_version,
                       experiment_id, run_date, artifact_path, row_count, sha256
                FROM aggregation_artifacts WHERE batch_id = ?
                """,
                (batch_id,),
            ).fetchone()
        return AggregationArtifactRecord(*row) if row is not None else None
