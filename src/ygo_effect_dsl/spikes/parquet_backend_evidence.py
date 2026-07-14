from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.route_dsl import load_route_document
from ygo_effect_dsl.storage import (
    AGGREGATION_PARTITION_KEYS,
    AGGREGATION_SCHEMA_VERSION,
    RawLogRecord,
    RunCatalog,
    RunRecord,
    RunStatus,
    aggregation_arrow_schema,
    build_route_aggregation_record,
    publish_aggregation_partition,
    read_aggregation_dataset,
    write_raw_log,
)


PARQUET_BACKEND_EVIDENCE_SCHEMA_VERSION = "parquet-backend-evidence-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package_size(root: Path) -> int:
    return sum(
        path.stat().st_size
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )


def collect_windows_distribution_probe(
    *,
    pyarrow_wheel: str | Path,
    polars_wheels: Sequence[str | Path],
    import_samples: int = 5,
) -> dict[str, Any]:
    import pyarrow

    if platform.system() != "Windows":
        raise ValueError("distribution probe must run on Windows")
    if not isinstance(import_samples, int) or import_samples <= 0:
        raise ValueError("import_samples must be an integer > 0")
    pyarrow_path = Path(pyarrow_wheel).resolve()
    polars_paths = sorted(Path(path).resolve() for path in polars_wheels)
    for path in (pyarrow_path, *polars_paths):
        if not path.is_file() or path.suffix != ".whl":
            raise ValueError(f"wheel path is invalid: {path}")
    timings = []
    for _ in range(import_samples):
        started = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-c", "import pyarrow, pyarrow.parquet"],
            check=False,
            capture_output=True,
            text=True,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        if result.returncode != 0:
            raise ValueError(
                "cold pyarrow import failed: " + result.stderr.strip()
            )
        timings.append(elapsed_ms)
    package_root = Path(pyarrow.__file__).resolve().parent
    wheel_records = [
        {
            "filename": path.name,
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in polars_paths
    ]
    return to_canonical_data(
        {
            "cold_import": {
                "command": "python -c import pyarrow, pyarrow.parquet",
                "median_ms": round(statistics.median(timings), 3),
                "samples_ms": timings,
                "succeeded": True,
            },
            "installed_pyarrow": {
                "package_size_bytes": _package_size(package_root),
                "version": pyarrow.__version__,
            },
            "platform": {
                "machine": platform.machine(),
                "python": platform.python_version(),
                "system": platform.system(),
                "version": platform.version(),
            },
            "polars_wheels": {
                "files": wheel_records,
                "total_size_bytes": sum(item["size_bytes"] for item in wheel_records),
            },
            "pyarrow_wheel": {
                "filename": pyarrow_path.name,
                "sha256": _sha256(pyarrow_path),
                "size_bytes": pyarrow_path.stat().st_size,
            },
            "selection": {
                "backend": "pyarrow_direct",
                "reason": (
                    "direct schema metadata, nullable-column migration, and "
                    "partition control without a dataframe dependency"
                ),
            },
        }
    )


def build_parquet_functional_evidence(
    *, repo_root: str | Path | None = None
) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    route = load_route_document(
        root
        / "examples"
        / "prototype"
        / "real_core_action_aggregation.route.yaml"
    )
    record = build_route_aggregation_record(
        route,
        run_id="run_parquet_evidence",
        run_date="2026-07-13",
    )
    with tempfile.TemporaryDirectory(prefix="ygo-parquet-evidence-") as temporary:
        work = Path(temporary)
        raw_log_path = work / "run.jsonl"
        write_raw_log(
            raw_log_path,
            (
                RawLogRecord(record.run_id, 0, "run_started", {}),
                RawLogRecord(
                    record.run_id,
                    1,
                    "route_completed",
                    {"route_id": record.route_id},
                ),
            ),
        )
        catalog = RunCatalog(work / "runs.sqlite3")
        catalog.create_run(
            RunRecord(
                run_id=record.run_id,
                experiment_id=record.experiment_id,
                status=RunStatus.RUNNING,
                started_at="2026-07-13T10:00:00Z",
            )
        )
        catalog.finish_run(
            record.run_id,
            status=RunStatus.COMPLETE,
            finished_at="2026-07-13T10:01:00Z",
        )
        dataset_root = work / "aggregation"
        artifact = publish_aggregation_partition(
            catalog=catalog,
            raw_log_path=raw_log_path,
            root=dataset_root,
            records=(record,),
        )
        round_trip = read_aggregation_dataset(dataset_root)
        if round_trip != (record,):
            raise ValueError("representative Parquet round trip did not match")
        catalog_record = catalog.get_aggregation_artifact(artifact.batch_id)
        if catalog_record is None:
            raise ValueError("catalog did not publish the Parquet artifact")

        legacy_root = work / "legacy"
        legacy_partition = (
            legacy_root
            / "evaluator_version=1"
            / "experiment_id=prototype_real_core_action_aggregation"
            / "run_date=2026-07-13"
        )
        legacy_partition.mkdir(parents=True)
        legacy_row = record.to_dict()
        legacy_row.pop("resource_consumption")
        legacy_schema = aggregation_arrow_schema()
        legacy_schema = legacy_schema.remove(
            legacy_schema.get_field_index("resource_consumption")
        )
        pq.write_table(
            pa.Table.from_pylist([legacy_row], schema=legacy_schema),
            legacy_partition / "part-legacy.parquet",
        )
        legacy_records = read_aggregation_dataset(legacy_root)
        nullable_metric_added = (
            len(legacy_records) == 1
            and legacy_records[0].resource_consumption is None
        )

        type_root = work / "type-change"
        type_partition = (
            type_root
            / "evaluator_version=1"
            / "experiment_id=prototype_real_core_action_aggregation"
            / "run_date=2026-07-13"
        )
        type_partition.mkdir(parents=True)
        schema = aggregation_arrow_schema()
        changed_schema = pa.schema(
            [
                pa.field("score", pa.int64(), nullable=False)
                if field.name == "score"
                else field
                for field in schema
            ],
            metadata=schema.metadata,
        )
        changed_row = record.to_dict()
        changed_row["score"] = int(changed_row["score"])
        pq.write_table(
            pa.Table.from_pylist([changed_row], schema=changed_schema),
            type_partition / "part-changed.parquet",
        )
        type_change_failed_closed = False
        try:
            read_aggregation_dataset(type_root)
        except ValueError as exc:
            type_change_failed_closed = "explicit migration is required" in str(exc)
        if not type_change_failed_closed:
            raise ValueError("Parquet type change did not require explicit migration")

        relative_path = artifact.path.relative_to(dataset_root).as_posix()
        return to_canonical_data(
            {
                "artifact": {
                    "batch_id": artifact.batch_id,
                    "catalog_published": True,
                    "parquet_sha256": artifact.sha256,
                    "relative_path": relative_path,
                    "row_count": artifact.row_count,
                },
                "partition_keys": list(AGGREGATION_PARTITION_KEYS),
                "publication_order": [
                    "validate_jsonl",
                    "require_completed_catalog_run",
                    "write_and_reread_temporary_parquet",
                    "atomic_replace",
                    "register_sqlite_reference",
                ],
                "record": record.to_dict(),
                "round_trip_equal": True,
                "schema_evolution": {
                    "missing_nullable_metric_reads_as_null": nullable_metric_added,
                    "type_change_requires_explicit_migration": (
                        type_change_failed_closed
                    ),
                },
                "schema_version": AGGREGATION_SCHEMA_VERSION,
            }
        )


def build_parquet_backend_evidence(
    *,
    repo_root: str | Path | None = None,
    distribution_probe: dict[str, Any],
) -> dict[str, Any]:
    import pyarrow

    identity = to_canonical_data(
        {
            "backend": {
                "implementation": "pyarrow_direct",
                "optional_dependency": "pyarrow==25.0.0",
                "runtime_version": pyarrow.__version__,
            },
            "distribution_probe": distribution_probe,
            "functional": build_parquet_functional_evidence(repo_root=repo_root),
            "schema_version": PARQUET_BACKEND_EVIDENCE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="parquetevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="build checked Parquet backend and Windows distribution evidence"
    )
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pyarrow-wheel", type=Path, required=True)
    parser.add_argument("--polars-wheel", type=Path, action="append", required=True)
    args = parser.parse_args()
    probe = collect_windows_distribution_probe(
        pyarrow_wheel=args.pyarrow_wheel,
        polars_wheels=args.polars_wheel,
    )
    evidence = build_parquet_backend_evidence(
        repo_root=args.repo_root,
        distribution_probe=probe,
    )
    serialized = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialized, encoding="utf-8")
    print(
        f"parquet-backend-evidence: wrote {args.out} "
        f"evidence_id={evidence['evidence_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
