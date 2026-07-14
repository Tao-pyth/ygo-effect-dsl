from __future__ import annotations

import json
from pathlib import Path

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from ygo_effect_dsl.route_dsl import load_route_document
from ygo_effect_dsl.storage import (
    AGGREGATION_SCHEMA_VERSION,
    AggregationRecord,
    RawLogRecord,
    RunCatalog,
    RunRecord,
    RunStatus,
    aggregation_arrow_schema,
    build_route_aggregation_record,
    publish_aggregation_partition,
    read_aggregation_dataset,
    write_aggregation_partition,
    write_raw_log,
)
from ygo_effect_dsl.spikes.parquet_backend_evidence import (
    build_parquet_functional_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    REPO_ROOT
    / "examples"
    / "prototype"
    / "real_core_action_aggregation.route.yaml"
)
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "storage" / "evidence" / "parquet_backend.json"
)


def _record(*, resource_consumption: float | None = 3.0) -> AggregationRecord:
    route = load_route_document(ROUTE_PATH)
    built = build_route_aggregation_record(
        route,
        run_id="run_parquet_fixture",
        run_date="2026-07-13",
    )
    return AggregationRecord(
        **{
            **{
                key: value
                for key, value in built.to_dict().items()
                if key not in {"aggregation_record_id", "resource_consumption"}
            },
            "resource_consumption": resource_consumption,
        }
    )


def test_representative_route_round_trips_in_fixed_partition(tmp_path: Path) -> None:
    record = _record()

    artifact = write_aggregation_partition(tmp_path, (record,))

    assert artifact.row_count == 1
    assert artifact.path.relative_to(tmp_path).parts[:3] == (
        "evaluator_version=1",
        "experiment_id=prototype_real_core_action_aggregation",
        "run_date=2026-07-13",
    )
    assert read_aggregation_dataset(tmp_path) == (record,)
    metadata = pq.ParquetFile(artifact.path).schema_arrow.metadata
    assert metadata[b"ygo.schema_version"] == b"aggregation-v1"
    assert metadata[b"ygo.partition_layout"] == (
        b"evaluator_version/experiment_id/run_date"
    )


def test_publish_validates_raw_log_then_registers_completed_run(
    tmp_path: Path,
) -> None:
    record = _record()
    raw_log_path = tmp_path / "run.jsonl"
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
    catalog = RunCatalog(tmp_path / "runs.sqlite3")
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

    first = publish_aggregation_partition(
        catalog=catalog,
        raw_log_path=raw_log_path,
        root=tmp_path / "aggregation",
        records=(record,),
    )
    second = publish_aggregation_partition(
        catalog=catalog,
        raw_log_path=raw_log_path,
        root=tmp_path / "aggregation",
        records=(record,),
    )

    assert first == second
    catalog_record = catalog.get_aggregation_artifact(first.batch_id)
    assert catalog_record is not None
    assert catalog_record.sha256 == first.sha256
    assert Path(catalog_record.artifact_path) == first.path.resolve()


def test_publish_rejects_missing_raw_event_before_creating_parquet(
    tmp_path: Path,
) -> None:
    record = _record()
    raw_log_path = tmp_path / "run.jsonl"
    write_raw_log(
        raw_log_path,
        (RawLogRecord(record.run_id, 0, "run_started", {}),),
    )
    catalog = RunCatalog(tmp_path / "runs.sqlite3")
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

    with pytest.raises(ValueError, match="route_completed"):
        publish_aggregation_partition(
            catalog=catalog,
            raw_log_path=raw_log_path,
            root=tmp_path / "aggregation",
            records=(record,),
        )

    assert not (tmp_path / "aggregation").exists()


def test_missing_nullable_metric_column_reads_as_null(tmp_path: Path) -> None:
    record = _record(resource_consumption=None)
    row = record.to_dict()
    row.pop("resource_consumption")
    schema = aggregation_arrow_schema()
    schema = schema.remove(schema.get_field_index("resource_consumption"))
    partition = (
        tmp_path
        / "evaluator_version=1"
        / "experiment_id=prototype_real_core_action_aggregation"
        / "run_date=2026-07-13"
    )
    partition.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist([row], schema=schema),
        partition / "part-legacy.parquet",
    )

    assert read_aggregation_dataset(tmp_path) == (record,)


def test_metric_type_change_requires_explicit_migration(tmp_path: Path) -> None:
    record = _record()
    schema = aggregation_arrow_schema()
    fields = [
        pa.field("score", pa.int64(), nullable=False)
        if field.name == "score"
        else field
        for field in schema
    ]
    changed_schema = pa.schema(fields, metadata=schema.metadata)
    row = record.to_dict()
    row["score"] = int(row["score"])
    partition = (
        tmp_path
        / "evaluator_version=1"
        / "experiment_id=prototype_real_core_action_aggregation"
        / "run_date=2026-07-13"
    )
    partition.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist([row], schema=changed_schema),
        partition / "part-type-change.parquet",
    )

    with pytest.raises(ValueError, match="explicit migration is required"):
        read_aggregation_dataset(tmp_path)


def test_storage_policy_marks_parquet_backend_implemented() -> None:
    assert AGGREGATION_SCHEMA_VERSION == "aggregation-v1"


def test_fixed_parquet_evidence_matches_fresh_functional_run() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert build_parquet_functional_evidence(repo_root=REPO_ROOT) == evidence[
        "functional"
    ]
    probe = evidence["distribution_probe"]
    assert probe["platform"]["system"] == "Windows"
    assert probe["cold_import"]["succeeded"] is True
    assert probe["pyarrow_wheel"]["size_bytes"] < (
        probe["polars_wheels"]["total_size_bytes"]
    )
    assert evidence["backend"] == {
        "implementation": "pyarrow_direct",
        "optional_dependency": "pyarrow==25.0.0",
        "runtime_version": "25.0.0",
    }
