from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import tempfile
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.storage.parquet import _arrow_schema, _require_pyarrow
from ygo_effect_dsl.storage.parquet_lifecycle import ParquetLayoutPolicy


PARQUET_LIFECYCLE_EVIDENCE_VERSION = "parquet-lifecycle-evidence-v1"
DEFAULT_CALIBRATION_ROWS = 20_000


def _row(index: int) -> dict[str, Any]:
    return {
        "action_count": index % 47,
        "aggregation_record_id": f"aggrecord_{index:064x}",
        "evaluator_config_hash": "evalcfg_lifecycle_calibration",
        "evaluator_id": "board-score",
        "evaluator_version": "1",
        "experiment_id": "experiment_lifecycle_calibration",
        "resource_consumption": float(index % 23) / 3,
        "route_id": f"route_{index:08d}",
        "run_date": "2026-07-15",
        "run_id": f"run_{index:08d}",
        "schema_version": "aggregation-v1",
        "score": float((index * 17) % 1009) / 10,
        "state_hash": hashlib.sha256(f"state:{index}".encode()).hexdigest(),
        "success": index % 5 != 0,
        "target_board": "peak_board",
    }


def _semantic_digest(rows: list[dict[str, Any]]) -> str:
    projection = [
        {
            "action_count": row["action_count"],
            "aggregation_record_id": row["aggregation_record_id"],
            "score": row["score"],
            "state_hash": row["state_hash"],
            "success": row["success"],
        }
        for row in sorted(rows, key=lambda item: item["aggregation_record_id"])
    ]
    return stable_digest(projection, prefix="lifecyclecalibrationsemantic_")


def _statistics_are_non_overlapping(parquet_file: Any, column_name: str) -> bool:
    index = parquet_file.schema_arrow.get_field_index(column_name)
    bounds: list[tuple[str, str]] = []
    for row_group in range(parquet_file.metadata.num_row_groups):
        statistics = parquet_file.metadata.row_group(row_group).column(index).statistics
        if statistics is None or not statistics.has_min_max:
            return False
        bounds.append((str(statistics.min), str(statistics.max)))
    return all(left[1] < right[0] for left, right in zip(bounds, bounds[1:]))


def _candidate(
    root: Path,
    *,
    name: str,
    rows: list[dict[str, Any]],
    compression: str,
    compression_level: int | None,
    row_group_size: int,
) -> dict[str, Any]:
    pa, pq = _require_pyarrow()
    path = root / f"{name}.parquet"
    table = pa.Table.from_pylist(rows, schema=_arrow_schema(pa))
    arguments: dict[str, Any] = {
        "compression": compression,
        "row_group_size": row_group_size,
        "version": "2.6",
        "write_statistics": True,
    }
    if compression_level is not None:
        arguments["compression_level"] = compression_level
    pq.write_table(table, path, **arguments)
    parquet_file = pq.ParquetFile(path)
    round_trip = parquet_file.read().to_pylist()
    return {
        "compression": compression,
        "compression_level": compression_level,
        "file_bytes": path.stat().st_size,
        "row_count": len(round_trip),
        "row_group_count": parquet_file.metadata.num_row_groups,
        "row_group_size": row_group_size,
        "run_id_statistics_non_overlapping": _statistics_are_non_overlapping(
            parquet_file, "run_id"
        ),
        "semantic_digest": _semantic_digest(round_trip),
    }


def build_parquet_lifecycle_calibration(
    *,
    row_count: int = DEFAULT_CALIBRATION_ROWS,
) -> dict[str, Any]:
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 2:
        raise ValueError("row_count must be an integer >= 2")
    _, pq = _require_pyarrow()
    del pq
    sorted_rows = [_row(index) for index in range(row_count)]
    multiplier = 7919
    while math.gcd(multiplier, row_count) != 1:
        multiplier += 2
    shuffled_rows = [
        sorted_rows[(index * multiplier) % row_count]
        for index in range(row_count)
    ]
    with tempfile.TemporaryDirectory(prefix="ygo-parquet-lifecycle-") as temporary:
        root = Path(temporary)
        candidates = {
            "snappy_rg16384_sorted": _candidate(
                root,
                name="snappy_rg16384_sorted",
                rows=sorted_rows,
                compression="snappy",
                compression_level=None,
                row_group_size=16_384,
            ),
            "zstd3_rg4096_sorted": _candidate(
                root,
                name="zstd3_rg4096_sorted",
                rows=sorted_rows,
                compression="zstd",
                compression_level=3,
                row_group_size=4_096,
            ),
            "zstd3_rg16384_sorted": _candidate(
                root,
                name="zstd3_rg16384_sorted",
                rows=sorted_rows,
                compression="zstd",
                compression_level=3,
                row_group_size=16_384,
            ),
            "zstd3_rg16384_unsorted": _candidate(
                root,
                name="zstd3_rg16384_unsorted",
                rows=shuffled_rows,
                compression="zstd",
                compression_level=3,
                row_group_size=16_384,
            ),
        }
    semantic_digests = {
        item["semantic_digest"] for item in candidates.values()
    }
    if len(semantic_digests) != 1:
        raise ValueError("Parquet calibration candidates changed semantic content")
    policy = ParquetLayoutPolicy()
    selected = candidates["zstd3_rg16384_sorted"]
    return to_canonical_data(
        {
            "candidates": candidates,
            "row_count": row_count,
            "selected": {
                "compression": policy.compression,
                "compression_level": policy.compression_level,
                "layout_policy_id": policy.policy_id,
                "observed_file_bytes": selected["file_bytes"],
                "observed_file_bytes_per_row": (
                    selected["file_bytes"] / row_count
                ),
                "planning_bytes_per_row": policy.bytes_per_row_estimate,
                "planning_rows_per_file": min(
                    policy.target_rows_per_file,
                    policy.target_file_size_bytes
                    // policy.bytes_per_row_estimate,
                ),
                "row_group_size": policy.row_group_size,
                "sort_keys": list(policy.sort_keys),
                "target_file_size_bytes": policy.target_file_size_bytes,
            },
            "semantic_digest": next(iter(semantic_digests)),
        }
    )


def build_parquet_lifecycle_evidence() -> dict[str, Any]:
    import pyarrow

    identity = {
        "calibration": build_parquet_lifecycle_calibration(),
        "limitations": [
            "single_partition_synthetic_unique_workload",
            "timings_excluded_as_machine_dependent",
            "production_scale_recalibration_remains_issue_167",
        ],
        "pyarrow_version": pyarrow.__version__,
        "schema_version": PARQUET_LIFECYCLE_EVIDENCE_VERSION,
    }
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="parquetlifecycleevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    atomic_write_text(
        args.out,
        json.dumps(
            build_parquet_lifecycle_evidence(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
