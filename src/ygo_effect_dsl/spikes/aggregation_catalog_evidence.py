from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import tempfile
import time
from typing import Any, Callable

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.storage import RUN_CATALOG_SCHEMA_VERSION, RunCatalog


AGGREGATION_CATALOG_EVIDENCE_SCHEMA_VERSION = (
    "aggregation-catalog-selection-evidence-v1"
)


def storage_boundary_decision() -> dict[str, Any]:
    return {
        "analytical_data": {
            "authority": "derived_rebuildable",
            "backend": "parquet_pyarrow",
            "mutation": "immutable_partition_publish",
        },
        "distributed_execution": {
            "decision": "out_of_scope_for_v0.5",
            "revisit_when": "multiple_hosts_or_multiple_catalog_writers_are_required",
        },
        "operational_catalog": {
            "authority": "run_job_and_artifact_references",
            "backend": "sqlite",
            "writer_model": "single_host_single_writer",
        },
        "query_accelerator": {
            "backend": "duckdb",
            "decision": "deferred_optional_reader",
            "restriction": "must_not_own_job_state_or_the_only_copy_of_evidence",
        },
        "raw_evidence": {
            "authority": "immutable_source",
            "backend": "jsonl_and_versioned_route_artifacts",
            "mutation": "append_then_seal",
        },
        "ui_cache": {
            "authority": "none",
            "backend": "separate_disposable_sqlite",
            "recovery": "drop_and_rebuild_from_catalog_and_parquet",
        },
    }


def _measure(callback: Callable[[], dict[str, Any]], samples: int) -> dict[str, Any]:
    timings: list[float] = []
    result: dict[str, Any] | None = None
    for _ in range(samples):
        started = time.perf_counter()
        result = callback()
        timings.append(round((time.perf_counter() - started) * 1000, 3))
    assert result is not None
    return {
        **result,
        "elapsed_ms": {
            "median": round(statistics.median(timings), 3),
            "samples": timings,
        },
    }


def _sqlite_catalog_workload(path: Path, row_count: int) -> dict[str, Any]:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                artifact_path TEXT
            )
            """
        )
        connection.executemany(
            "INSERT INTO jobs VALUES (?, 'queued', 0, NULL)",
            ((f"job_{index:08d}",) for index in range(row_count)),
        )
        connection.execute(
            "UPDATE jobs SET status = 'succeeded', artifact_path = 'part.parquet' "
            "WHERE CAST(SUBSTR(job_id, 5) AS INTEGER) % 3 = 0"
        )
        counts = dict(
            connection.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status ORDER BY status"
            ).fetchall()
        )
    return {
        "artifact_bytes": path.stat().st_size,
        "result": counts,
        "row_count": row_count,
    }


def _sqlite_analytics_workload(path: Path, table: Any) -> dict[str, Any]:
    rows = zip(
        table["experiment_id"].to_pylist(),
        table["score"].to_pylist(),
        table["success"].to_pylist(),
    )
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "CREATE TABLE metrics (experiment_id TEXT, score REAL, success INTEGER)"
        )
        connection.executemany("INSERT INTO metrics VALUES (?, ?, ?)", rows)
        result = _normalize_analytics_result(connection.execute(
            """
            SELECT experiment_id, ROUND(AVG(score), 6), SUM(success)
            FROM metrics GROUP BY experiment_id ORDER BY experiment_id
            """
        ).fetchall())
    return {
        "artifact_bytes": path.stat().st_size,
        "group_count": len(result),
        "result_sha256": _result_hash(result),
        "row_count": table.num_rows,
    }


def _parquet_analytics_workload(path: Path, table: Any) -> dict[str, Any]:
    import pyarrow.parquet as pq

    pq.write_table(table, path, compression="zstd")
    grouped = pq.read_table(path).group_by("experiment_id").aggregate(
        [("score", "mean"), ("success", "sum")]
    )
    result = _normalize_analytics_result(sorted(
        zip(
            grouped["experiment_id"].to_pylist(),
            grouped["score_mean"].to_pylist(),
            grouped["success_sum"].to_pylist(),
        )
    ))
    return {
        "artifact_bytes": path.stat().st_size,
        "group_count": len(result),
        "result_sha256": _result_hash(result),
        "row_count": table.num_rows,
    }


def _duckdb_catalog_workload(path: Path, row_count: int) -> dict[str, Any]:
    import duckdb

    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            CREATE TABLE jobs (
                job_id VARCHAR PRIMARY KEY,
                status VARCHAR NOT NULL,
                attempt INTEGER NOT NULL,
                artifact_path VARCHAR
            )
            """
        )
        connection.execute(
            """
            INSERT INTO jobs
            SELECT 'job_' || LPAD(CAST(i AS VARCHAR), 8, '0'), 'queued', 0, NULL
            FROM range(?) AS source(i)
            """,
            [row_count],
        )
        connection.execute(
            """
            UPDATE jobs SET status = 'succeeded', artifact_path = 'part.parquet'
            WHERE CAST(SUBSTR(job_id, 5) AS INTEGER) % 3 = 0
            """
        )
        counts = dict(
            connection.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status ORDER BY status"
            ).fetchall()
        )
    finally:
        connection.close()
    return {
        "artifact_bytes": path.stat().st_size,
        "result": counts,
        "row_count": row_count,
    }


def _duckdb_analytics_workload(path: Path, table: Any) -> dict[str, Any]:
    import duckdb

    connection = duckdb.connect(str(path))
    try:
        connection.register("metrics_arrow", table)
        connection.execute("CREATE TABLE metrics AS SELECT * FROM metrics_arrow")
        result = _normalize_analytics_result(connection.execute(
            """
            SELECT experiment_id, ROUND(AVG(score), 6), SUM(CAST(success AS INTEGER))
            FROM metrics GROUP BY experiment_id ORDER BY experiment_id
            """
        ).fetchall())
    finally:
        connection.close()
    return {
        "artifact_bytes": path.stat().st_size,
        "group_count": len(result),
        "result_sha256": _result_hash(result),
        "row_count": table.num_rows,
    }


def _result_hash(value: Any) -> str:
    payload = json.dumps(
        to_canonical_data(value), separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_analytics_result(rows: Any) -> list[tuple[str, float, int]]:
    return [
        (str(experiment_id), round(float(score), 6), int(success_count))
        for experiment_id, score, success_count in rows
    ]


def _analytics_table(row_count: int) -> Any:
    import pyarrow as pa

    return pa.table(
        {
            "experiment_id": [f"experiment_{index % 8}" for index in range(row_count)],
            "score": [float((index * 17) % 101) / 10 for index in range(row_count)],
            "success": [index % 5 != 0 for index in range(row_count)],
        }
    )


def collect_failure_mode_evidence(*, include_duckdb: bool) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    with tempfile.TemporaryDirectory(prefix="ygo-storage-failure-") as temporary:
        root = Path(temporary)
        sqlite_path = root / "rollback.sqlite3"
        connection = sqlite3.connect(sqlite_path)
        try:
            connection.execute("CREATE TABLE values_under_test (value INTEGER)")
            connection.commit()
            connection.execute("BEGIN")
            connection.execute("INSERT INTO values_under_test VALUES (1)")
            connection.rollback()
            sqlite_rows_after_rollback = connection.execute(
                "SELECT COUNT(*) FROM values_under_test"
            ).fetchone()[0]
        finally:
            connection.close()

        legacy_catalog = root / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy_catalog)) as connection, connection:
            connection.execute(
                "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO schema_meta VALUES ('schema_version', 'run-catalog-v0')"
            )
        schema_mismatch_rejected = False
        try:
            RunCatalog(legacy_catalog).initialize()
        except ValueError as exc:
            schema_mismatch_rejected = "explicit migration" in str(exc)

        parquet_path = root / "truncated.parquet"
        pq.write_table(pa.table({"value": [1, 2, 3]}), parquet_path)
        parquet_path.write_bytes(parquet_path.read_bytes()[:32])
        truncated_parquet_rejected = False
        try:
            pq.read_table(parquet_path)
        except Exception:
            truncated_parquet_rejected = True

        duckdb_rollback: bool | None = None
        if include_duckdb:
            import duckdb

            duckdb_path = root / "rollback.duckdb"
            connection = duckdb.connect(str(duckdb_path))
            try:
                connection.execute("CREATE TABLE values_under_test (value INTEGER)")
                connection.execute("BEGIN")
                connection.execute("INSERT INTO values_under_test VALUES (1)")
                connection.execute("ROLLBACK")
                duckdb_rollback = (
                    connection.execute(
                        "SELECT COUNT(*) FROM values_under_test"
                    ).fetchone()[0]
                    == 0
                )
            finally:
                connection.close()

    return {
        "duckdb_transaction_rollback": duckdb_rollback,
        "parquet_truncation_rejected": truncated_parquet_rejected,
        "sqlite_schema_mismatch_rejected_without_mutation": (
            schema_mismatch_rejected
        ),
        "sqlite_transaction_rollback": sqlite_rows_after_rollback == 0,
    }


def build_aggregation_catalog_evidence(
    *,
    catalog_rows: int = 10_000,
    analytical_rows: int = 100_000,
    samples: int = 3,
    include_duckdb: bool = True,
) -> dict[str, Any]:
    if catalog_rows <= 0 or analytical_rows <= 0 or samples <= 0:
        raise ValueError("row counts and samples must be positive")
    import pyarrow

    duckdb_version: str | None = None
    if include_duckdb:
        try:
            import duckdb
        except ImportError as exc:
            raise ValueError(
                "DuckDB comparison requested but duckdb is not installed"
            ) from exc
        duckdb_version = duckdb.__version__

    table = _analytics_table(analytical_rows)
    with tempfile.TemporaryDirectory(prefix="ygo-storage-selection-") as temporary:
        root = Path(temporary)
        sqlite_catalog = _measure(
            lambda: _sqlite_catalog_workload(
                root / f"catalog-{time.perf_counter_ns()}.sqlite3", catalog_rows
            ),
            samples,
        )
        sqlite_analytics = _measure(
            lambda: _sqlite_analytics_workload(
                root / f"analytics-{time.perf_counter_ns()}.sqlite3", table
            ),
            samples,
        )
        parquet_analytics = _measure(
            lambda: _parquet_analytics_workload(
                root / f"analytics-{time.perf_counter_ns()}.parquet", table
            ),
            samples,
        )
        duckdb_catalog = None
        duckdb_analytics = None
        if include_duckdb:
            duckdb_catalog = _measure(
                lambda: _duckdb_catalog_workload(
                    root / f"catalog-{time.perf_counter_ns()}.duckdb", catalog_rows
                ),
                samples,
            )
            duckdb_analytics = _measure(
                lambda: _duckdb_analytics_workload(
                    root / f"analytics-{time.perf_counter_ns()}.duckdb", table
                ),
                samples,
            )

    identity = to_canonical_data(
        {
            "decision": storage_boundary_decision(),
            "failure_modes": collect_failure_mode_evidence(
                include_duckdb=include_duckdb
            ),
            "limitations": [
                "single_windows_host_only",
                "synthetic_uniform_workload_not_release_calibration",
                "timings_are_directional_not_acceptance_thresholds",
                "distributed_writer_and_network_filesystem_not_tested",
            ],
            "runtime": {
                "duckdb": duckdb_version,
                "platform": platform.platform(),
                "pyarrow": pyarrow.__version__,
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
            },
            "schema_version": AGGREGATION_CATALOG_EVIDENCE_SCHEMA_VERSION,
            "selected_schema_versions": {
                "aggregation": "aggregation-v1",
                "run_catalog": RUN_CATALOG_SCHEMA_VERSION,
            },
            "workload": {
                "analytical_rows": analytical_rows,
                "catalog_rows": catalog_rows,
                "duckdb": {
                    "analytics": duckdb_analytics,
                    "catalog": duckdb_catalog,
                },
                "parquet": {"analytics": parquet_analytics},
                "samples": samples,
                "sqlite": {
                    "analytics": sqlite_analytics,
                    "catalog": sqlite_catalog,
                },
            },
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="storageevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="benchmark and record the v0.5 aggregation catalog decision"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--catalog-rows", type=int, default=10_000)
    parser.add_argument("--analytical-rows", type=int, default=100_000)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--without-duckdb", action="store_true")
    args = parser.parse_args()
    evidence = build_aggregation_catalog_evidence(
        catalog_rows=args.catalog_rows,
        analytical_rows=args.analytical_rows,
        samples=args.samples,
        include_duckdb=not args.without_duckdb,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"aggregation-catalog-evidence: wrote {args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
