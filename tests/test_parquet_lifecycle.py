from __future__ import annotations

from dataclasses import replace
import importlib.resources
import json
from pathlib import Path

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from ygo_effect_dsl.storage.parquet import (
    AggregationRecord,
    aggregation_arrow_schema,
    read_aggregation_dataset,
    write_aggregation_partition,
)
from ygo_effect_dsl.storage.parquet_lifecycle import (
    PARQUET_LIFECYCLE_CONTRACT_VERSION,
    AggregationSnapshotOperation,
    InjectedParquetLifecycleFault,
    ParquetLayoutPolicy,
    ParquetLifecycleFaultPoint,
    compact_aggregation_dataset,
    current_aggregation_snapshot_id,
    migrate_aggregation_snapshot,
    parquet_fault_at,
    parquet_lifecycle_contract_document,
    read_aggregation_snapshot,
    rollback_aggregation_snapshot,
)
from ygo_effect_dsl.spikes.parquet_lifecycle_evidence import (
    build_parquet_lifecycle_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "storage" / "evidence" / "parquet_lifecycle.json"
)


def _record(
    index: int,
    *,
    run_date: str = "2026-07-15",
    resource_consumption: float | None = None,
) -> AggregationRecord:
    return AggregationRecord(
        run_id=f"run_{index:04d}",
        route_id=f"route_{index:04d}",
        experiment_id="experiment_parquet_lifecycle",
        evaluator_id="board-score",
        evaluator_version="1",
        evaluator_config_hash="evalcfg_parquet_lifecycle",
        run_date=run_date,
        target_board="peak_board",
        state_hash=f"state_{index:04d}",
        success=index % 2 == 0,
        score=float(index) / 10,
        action_count=index + 1,
        resource_consumption=resource_consumption,
    )


def _legacy_dataset(root: Path, count: int = 4) -> tuple[AggregationRecord, ...]:
    records = tuple(_record(index) for index in range(count))
    for record in records:
        write_aggregation_partition(root, (record,))
    return tuple(sorted(records, key=lambda item: item.record_id))


def _small_policy(*, rows_per_file: int = 100) -> ParquetLayoutPolicy:
    return ParquetLayoutPolicy(
        target_file_size_bytes=1024 * 1024,
        target_rows_per_file=rows_per_file,
        row_group_size=min(2, rows_per_file),
        minimum_free_headroom_bytes=0,
        bytes_per_row_estimate=1,
    )


def test_compaction_publishes_one_manifest_bound_snapshot(tmp_path: Path) -> None:
    records = _legacy_dataset(tmp_path)

    snapshot = compact_aggregation_dataset(
        tmp_path,
        created_by_job_id="job_compaction_fixture",
        policy=_small_policy(),
    )

    manifest = snapshot.manifest
    assert manifest.operation == AggregationSnapshotOperation.COMPACTION
    assert manifest.created_by_job_id == "job_compaction_fixture"
    assert manifest.source_snapshot_ids == ()
    assert len(manifest.source_file_ids) == 4
    assert len(manifest.files) == 1
    assert manifest.write_metrics.file_count_before == 4
    assert manifest.write_metrics.file_count_after == 1
    assert manifest.write_metrics.write_amplification is not None
    assert manifest.disk_preflight.status == "passed"
    assert current_aggregation_snapshot_id(tmp_path) == manifest.snapshot_id
    assert read_aggregation_dataset(tmp_path) == records
    assert read_aggregation_snapshot(tmp_path).records == records


def test_layout_chunks_files_and_sets_real_min_max_bounds(tmp_path: Path) -> None:
    records = _legacy_dataset(tmp_path, count=5)

    snapshot = compact_aggregation_dataset(
        tmp_path,
        created_by_job_id="job_chunk_fixture",
        policy=_small_policy(rows_per_file=2),
    )

    assert sorted(item.row_count for item in snapshot.manifest.files) == [1, 2, 2]
    for item in snapshot.manifest.files:
        path = snapshot.manifest_path.parent / item.relative_path
        parquet_file = pq.ParquetFile(path)
        assert parquet_file.metadata.num_row_groups == 1
        assert path.stat().st_size == item.size_bytes
    assert read_aggregation_dataset(tmp_path) == records


def test_target_file_size_constrains_planned_rows_per_file(
    tmp_path: Path,
) -> None:
    _legacy_dataset(tmp_path, count=5)
    policy = ParquetLayoutPolicy(
        target_file_size_bytes=2,
        target_rows_per_file=100,
        row_group_size=2,
        minimum_free_headroom_bytes=0,
        bytes_per_row_estimate=1,
    )

    snapshot = compact_aggregation_dataset(
        tmp_path,
        created_by_job_id="job_file_size_planning",
        policy=policy,
    )

    assert sorted(item.row_count for item in snapshot.manifest.files) == [1, 2, 2]


def test_nullable_column_physical_migration_rewrites_current_schema(
    tmp_path: Path,
) -> None:
    record = _record(0, resource_consumption=None)
    row = record.to_dict()
    row.pop("resource_consumption")
    schema = aggregation_arrow_schema()
    schema = schema.remove(schema.get_field_index("resource_consumption"))
    partition = (
        tmp_path
        / "evaluator_version=1"
        / "experiment_id=experiment_parquet_lifecycle"
        / "run_date=2026-07-15"
    )
    partition.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist([row], schema=schema),
        partition / "part-legacy.parquet",
    )

    snapshot = migrate_aggregation_snapshot(
        tmp_path,
        created_by_job_id="job_nullable_migration",
        migration_id="add-nullable-resource-column-v1",
        transform=lambda item: item,
        policy=_small_policy(),
    )

    path = snapshot.manifest_path.parent / snapshot.manifest.files[0].relative_path
    assert "resource_consumption" in pq.ParquetFile(path).schema_arrow.names
    assert snapshot.records == (record,)
    assert snapshot.manifest.operation == AggregationSnapshotOperation.MIGRATION
    assert snapshot.manifest.migration_id == "add-nullable-resource-column-v1"


def test_backfill_preserves_core_semantics_and_can_rollback(tmp_path: Path) -> None:
    records = _legacy_dataset(tmp_path, count=3)
    before = compact_aggregation_dataset(
        tmp_path,
        created_by_job_id="job_before_backfill",
        policy=_small_policy(),
    )

    after = migrate_aggregation_snapshot(
        tmp_path,
        created_by_job_id="job_resource_backfill",
        migration_id="resource-backfill-v1",
        transform=lambda item: replace(item, resource_consumption=7.0),
        policy=_small_policy(),
    )

    assert after.manifest.source_snapshot_ids == (before.manifest.snapshot_id,)
    assert after.manifest.source_semantic_summary_id == (
        before.manifest.semantic_summary.summary_id
    )
    consumptions = {
        item.resource_consumption
        for item in read_aggregation_dataset(tmp_path)
    }
    assert consumptions == {7.0}

    rolled_back = rollback_aggregation_snapshot(
        tmp_path,
        before.manifest.snapshot_id,
        expected_current_snapshot_id=after.manifest.snapshot_id,
    )

    assert rolled_back.records == records
    assert read_aggregation_dataset(tmp_path) == records
    assert current_aggregation_snapshot_id(tmp_path) == before.manifest.snapshot_id


def test_compaction_absorbs_new_legacy_delta_without_mixing_snapshots(
    tmp_path: Path,
) -> None:
    initial = _legacy_dataset(tmp_path, count=2)
    first = compact_aggregation_dataset(
        tmp_path,
        created_by_job_id="job_initial_compaction",
        policy=_small_policy(),
    )
    delta = _record(2)
    write_aggregation_partition(tmp_path, (delta,))

    assert read_aggregation_dataset(tmp_path) == initial

    second = compact_aggregation_dataset(
        tmp_path,
        created_by_job_id="job_delta_compaction",
        policy=_small_policy(),
    )

    expected = tuple(sorted((*initial, delta), key=lambda item: item.record_id))
    assert second.records == expected
    assert second.manifest.source_snapshot_ids == (first.manifest.snapshot_id,)
    assert read_aggregation_dataset(tmp_path) == expected

    conflicting = replace(initial[0], resource_consumption=9.0)
    with pytest.raises(ValueError, match="already contains record identities"):
        write_aggregation_partition(tmp_path, (conflicting,))


def test_migration_rejects_semantic_change_and_unknown_schema(
    tmp_path: Path,
) -> None:
    records = _legacy_dataset(tmp_path, count=2)

    with pytest.raises(ValueError, match="changed the aggregation semantic"):
        migrate_aggregation_snapshot(
            tmp_path,
            created_by_job_id="job_bad_migration",
            migration_id="change-score",
            transform=lambda item: replace(item, score=item.score + 1.0),
            policy=_small_policy(),
        )
    with pytest.raises(ValueError, match="no explicit aggregation codec"):
        migrate_aggregation_snapshot(
            tmp_path,
            created_by_job_id="job_unknown_schema",
            migration_id="invent-v2",
            transform=lambda item: item,
            target_schema_version="aggregation-v2",
            policy=_small_policy(),
        )

    assert read_aggregation_dataset(tmp_path) == records
    assert current_aggregation_snapshot_id(tmp_path) is None


def test_disk_preflight_fails_before_snapshot_staging(tmp_path: Path) -> None:
    records = _legacy_dataset(tmp_path, count=2)

    with pytest.raises(OSError, match="insufficient disk"):
        compact_aggregation_dataset(
            tmp_path,
            created_by_job_id="job_no_disk",
            policy=_small_policy(),
            available_free_bytes=0,
        )

    assert read_aggregation_dataset(tmp_path) == records
    assert not (tmp_path / "_snapshots").exists()
    assert not (tmp_path / "_staging").exists()


@pytest.mark.parametrize(
    "point",
    (
        ParquetLifecycleFaultPoint.AFTER_STAGED_FILES,
        ParquetLifecycleFaultPoint.AFTER_SNAPSHOT_RENAME,
        ParquetLifecycleFaultPoint.BEFORE_POINTER_REPLACE,
    ),
)
def test_crash_before_pointer_keeps_legacy_reader_visible(
    tmp_path: Path,
    point: ParquetLifecycleFaultPoint,
) -> None:
    records = _legacy_dataset(tmp_path, count=2)

    with pytest.raises(InjectedParquetLifecycleFault, match=point.value):
        compact_aggregation_dataset(
            tmp_path,
            created_by_job_id=f"job_fault_{point.value}",
            policy=_small_policy(),
            injector=parquet_fault_at(point),
        )

    assert current_aggregation_snapshot_id(tmp_path) is None
    assert read_aggregation_dataset(tmp_path) == records


def test_crash_after_pointer_exposes_only_complete_new_snapshot(
    tmp_path: Path,
) -> None:
    records = _legacy_dataset(tmp_path, count=2)

    with pytest.raises(
        InjectedParquetLifecycleFault,
        match=ParquetLifecycleFaultPoint.AFTER_POINTER_REPLACE.value,
    ):
        compact_aggregation_dataset(
            tmp_path,
            created_by_job_id="job_fault_after_pointer",
            policy=_small_policy(),
            injector=parquet_fault_at(
                ParquetLifecycleFaultPoint.AFTER_POINTER_REPLACE
            ),
        )

    snapshot_id = current_aggregation_snapshot_id(tmp_path)
    assert snapshot_id is not None
    assert read_aggregation_snapshot(tmp_path).records == records
    assert read_aggregation_dataset(tmp_path) == records


def test_new_snapshot_crash_keeps_previous_pointer(tmp_path: Path) -> None:
    _legacy_dataset(tmp_path, count=2)
    before = compact_aggregation_dataset(
        tmp_path,
        created_by_job_id="job_initial_snapshot",
        policy=_small_policy(),
    )

    with pytest.raises(
        InjectedParquetLifecycleFault,
        match=ParquetLifecycleFaultPoint.AFTER_SNAPSHOT_RENAME.value,
    ):
        migrate_aggregation_snapshot(
            tmp_path,
            created_by_job_id="job_orphan_new_snapshot",
            migration_id="resource-backfill-orphan",
            transform=lambda item: replace(item, resource_consumption=8.0),
            policy=_small_policy(),
            injector=parquet_fault_at(
                ParquetLifecycleFaultPoint.AFTER_SNAPSHOT_RENAME
            ),
        )

    assert current_aggregation_snapshot_id(tmp_path) == before.manifest.snapshot_id
    assert all(
        item.resource_consumption is None
        for item in read_aggregation_dataset(tmp_path)
    )


def test_snapshot_file_and_manifest_tampering_fail_close(tmp_path: Path) -> None:
    _legacy_dataset(tmp_path, count=2)
    snapshot = compact_aggregation_dataset(
        tmp_path,
        created_by_job_id="job_tamper_fixture",
        policy=_small_policy(),
    )
    file_path = snapshot.manifest_path.parent / snapshot.manifest.files[0].relative_path
    file_path.write_bytes(file_path.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="file size mismatch"):
        read_aggregation_snapshot(tmp_path)

    other_root = tmp_path / "manifest"
    _legacy_dataset(other_root, count=1)
    other = compact_aggregation_dataset(
        other_root,
        created_by_job_id="job_manifest_tamper",
        policy=_small_policy(),
    )
    document = json.loads(other.manifest_path.read_text(encoding="utf-8"))
    document["created_by_job_id"] = "tampered_job"
    other.manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest checksum mismatch"):
        read_aggregation_snapshot(other_root)


def test_pointer_tampering_fails_close(tmp_path: Path) -> None:
    _legacy_dataset(tmp_path, count=1)
    compact_aggregation_dataset(
        tmp_path,
        created_by_job_id="job_pointer_tamper",
        policy=_small_policy(),
    )
    pointer_path = tmp_path / "current-snapshot.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["manifest_sha256"] = "0" * 64
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(ValueError, match="pointer_id"):
        read_aggregation_dataset(tmp_path)

    with pytest.raises(ValueError, match="recognized content ID"):
        read_aggregation_snapshot(tmp_path, snapshot_id="..")


def test_machine_readable_lifecycle_contract_matches_runtime() -> None:
    resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
        "parquet-lifecycle-contract-v1.json"
    )
    stored = json.loads(resource.read_text(encoding="utf-8"))
    runtime = parquet_lifecycle_contract_document()

    assert stored == runtime
    assert runtime["version"] == PARQUET_LIFECYCLE_CONTRACT_VERSION
    assert runtime["atomic_publication"]["reader_visibility"] == (
        "one_complete_old_or_new_snapshot"
    )


def test_fixed_lifecycle_calibration_matches_fresh_measurement() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert build_parquet_lifecycle_evidence() == evidence
    candidates = evidence["calibration"]["candidates"]
    selected = candidates["zstd3_rg16384_sorted"]
    assert selected["file_bytes"] < candidates["snappy_rg16384_sorted"][
        "file_bytes"
    ]
    assert selected["file_bytes"] < candidates["zstd3_rg4096_sorted"][
        "file_bytes"
    ]
    assert selected["run_id_statistics_non_overlapping"] is True
    assert candidates["zstd3_rg16384_unsorted"][
        "run_id_statistics_non_overlapping"
    ] is False
