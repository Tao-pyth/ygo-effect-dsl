from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
import hashlib
import math
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote
import uuid

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation import (
    EvaluatorSpec,
    build_route_resource_consumption,
)
from ygo_effect_dsl.storage.catalog import (
    AggregationArtifactRecord,
    RunCatalog,
    RunStatus,
)
from ygo_effect_dsl.storage.jsonl import read_raw_log


AGGREGATION_SCHEMA_VERSION = "aggregation-v1"
AGGREGATION_PARTITION_KEYS = (
    "evaluator_version",
    "experiment_id",
    "run_date",
)
AGGREGATION_OPTIONAL_METRICS = ("resource_consumption",)
_SCHEMA_METADATA = {
    b"ygo.schema_version": AGGREGATION_SCHEMA_VERSION.encode("ascii"),
    b"ygo.partition_layout": "/".join(AGGREGATION_PARTITION_KEYS).encode(
        "ascii"
    ),
}


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _finite_number(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


@dataclass(frozen=True)
class AggregationRecord:
    run_id: str
    route_id: str
    experiment_id: str
    evaluator_id: str
    evaluator_version: str
    evaluator_config_hash: str
    run_date: str
    target_board: str
    state_hash: str
    success: bool
    score: float
    action_count: int
    resource_consumption: float | None = None
    schema_version: str = AGGREGATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "route_id",
            "experiment_id",
            "evaluator_id",
            "evaluator_version",
            "evaluator_config_hash",
            "run_date",
            "target_board",
            "state_hash",
        ):
            _non_empty_string(getattr(self, name), name)
        if self.schema_version != AGGREGATION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {AGGREGATION_SCHEMA_VERSION!r}"
            )
        if self.target_board not in {"peak_board", "terminal_board"}:
            raise ValueError("target_board must be peak_board or terminal_board")
        try:
            parsed_date = date.fromisoformat(self.run_date)
        except ValueError as exc:
            raise ValueError("run_date must be an ISO YYYY-MM-DD date") from exc
        if parsed_date.isoformat() != self.run_date:
            raise ValueError("run_date must be an ISO YYYY-MM-DD date")
        if not isinstance(self.success, bool):
            raise ValueError("success must be a boolean")
        object.__setattr__(self, "score", _finite_number(self.score, "score"))
        if (
            not isinstance(self.action_count, int)
            or isinstance(self.action_count, bool)
            or self.action_count < 0
        ):
            raise ValueError("action_count must be an integer >= 0")
        if self.resource_consumption is not None:
            value = _finite_number(
                self.resource_consumption, "resource_consumption"
            )
            if value < 0:
                raise ValueError("resource_consumption must be >= 0")
            object.__setattr__(self, "resource_consumption", value)

    @property
    def record_id(self) -> str:
        return stable_digest(
            {
                "evaluator_config_hash": self.evaluator_config_hash,
                "evaluator_id": self.evaluator_id,
                "evaluator_version": self.evaluator_version,
                "route_id": self.route_id,
                "run_id": self.run_id,
                "schema_version": self.schema_version,
                "target_board": self.target_board,
            },
            prefix="aggrecord_",
        )

    @property
    def partition(self) -> tuple[str, str, str]:
        return self.evaluator_version, self.experiment_id, self.run_date

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "action_count": self.action_count,
                "aggregation_record_id": self.record_id,
                "evaluator_config_hash": self.evaluator_config_hash,
                "evaluator_id": self.evaluator_id,
                "evaluator_version": self.evaluator_version,
                "experiment_id": self.experiment_id,
                "resource_consumption": self.resource_consumption,
                "route_id": self.route_id,
                "run_date": self.run_date,
                "run_id": self.run_id,
                "schema_version": self.schema_version,
                "score": self.score,
                "state_hash": self.state_hash,
                "success": self.success,
                "target_board": self.target_board,
            }
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AggregationRecord":
        if not isinstance(value, Mapping):
            raise ValueError("aggregation row must be a mapping")
        record = cls(
            run_id=value.get("run_id"),
            route_id=value.get("route_id"),
            experiment_id=value.get("experiment_id"),
            evaluator_id=value.get("evaluator_id"),
            evaluator_version=value.get("evaluator_version"),
            evaluator_config_hash=value.get("evaluator_config_hash"),
            run_date=value.get("run_date"),
            target_board=value.get("target_board"),
            state_hash=value.get("state_hash"),
            success=value.get("success"),
            score=value.get("score"),
            action_count=value.get("action_count"),
            resource_consumption=value.get("resource_consumption"),
            schema_version=value.get("schema_version"),
        )
        stored_id = value.get("aggregation_record_id")
        if stored_id is not None and stored_id != record.record_id:
            raise ValueError("aggregation_record_id does not match row identity")
        return record


@dataclass(frozen=True)
class AggregationArtifact:
    batch_id: str
    path: Path
    row_count: int
    sha256: str
    partition: tuple[str, str, str]


def _require_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet analytics requires the optional dependency; "
            "install with `pip install -e .[analytics]`"
        ) from exc
    return pa, pq


def _arrow_schema(pa: Any) -> Any:
    return pa.schema(
        [
            pa.field("action_count", pa.int32(), nullable=False),
            pa.field("aggregation_record_id", pa.string(), nullable=False),
            pa.field("evaluator_config_hash", pa.string(), nullable=False),
            pa.field("evaluator_id", pa.string(), nullable=False),
            pa.field("evaluator_version", pa.string(), nullable=False),
            pa.field("experiment_id", pa.string(), nullable=False),
            pa.field("resource_consumption", pa.float64(), nullable=True),
            pa.field("route_id", pa.string(), nullable=False),
            pa.field("run_date", pa.string(), nullable=False),
            pa.field("run_id", pa.string(), nullable=False),
            pa.field("schema_version", pa.string(), nullable=False),
            pa.field("score", pa.float64(), nullable=False),
            pa.field("state_hash", pa.string(), nullable=False),
            pa.field("success", pa.bool_(), nullable=False),
            pa.field("target_board", pa.string(), nullable=False),
        ],
        metadata=_SCHEMA_METADATA,
    )


def aggregation_arrow_schema() -> Any:
    pa, _ = _require_pyarrow()
    return _arrow_schema(pa)


def _partition_directory(
    root: Path, partition: tuple[str, str, str]
) -> Path:
    destination = root
    for key, value in zip(AGGREGATION_PARTITION_KEYS, partition, strict=True):
        destination /= f"{key}={quote(value, safe='')}"
    return destination


def _normalize_table(table: Any, path: Path) -> Any:
    pa, _ = _require_pyarrow()
    metadata = table.schema.metadata or {}
    if metadata.get(b"ygo.schema_version") != _SCHEMA_METADATA[
        b"ygo.schema_version"
    ]:
        raise ValueError(f"{path} has unsupported aggregation schema metadata")
    if metadata.get(b"ygo.partition_layout") != _SCHEMA_METADATA[
        b"ygo.partition_layout"
    ]:
        raise ValueError(f"{path} has unsupported partition metadata")
    expected = _arrow_schema(pa)
    names = set(table.schema.names)
    required = {
        field.name for field in expected if not field.nullable
    }
    missing_required = sorted(required - names)
    if missing_required:
        raise ValueError(
            f"{path} is missing required aggregation columns {missing_required}"
        )
    unknown = sorted(names - set(expected.names))
    if unknown:
        raise ValueError(f"{path} has unknown aggregation columns {unknown}")
    for field in expected:
        if field.name not in names:
            table = table.append_column(
                field, pa.nulls(table.num_rows, type=field.type)
            )
            continue
        actual = table.schema.field(field.name)
        if actual.type != field.type:
            raise ValueError(
                f"{path} column {field.name!r} has type {actual.type}; "
                f"expected {field.type}; explicit migration is required"
            )
        if not field.nullable and actual.nullable:
            column = table[field.name]
            if column.null_count:
                raise ValueError(f"{path} required column {field.name!r} contains null")
    return table.select(expected.names).replace_schema_metadata(_SCHEMA_METADATA)


def _read_file(path: Path) -> tuple[AggregationRecord, ...]:
    _, pq = _require_pyarrow()
    table = pq.ParquetFile(path).read()
    normalized = _normalize_table(table, path)
    return tuple(AggregationRecord.from_mapping(row) for row in normalized.to_pylist())


def _assert_partition_path(
    root: Path, path: Path, records: Sequence[AggregationRecord]
) -> None:
    if not records:
        return
    expected_parent = _partition_directory(root, records[0].partition).resolve()
    if path.resolve().parent != expected_parent:
        raise ValueError(f"{path} does not match its aggregation partition columns")
    if any(record.partition != records[0].partition for record in records):
        raise ValueError(f"{path} contains rows from multiple partitions")


def write_aggregation_partition(
    root: str | Path,
    records: Iterable[AggregationRecord],
) -> AggregationArtifact:
    pa, pq = _require_pyarrow()
    destination_root = Path(root)
    materialized = tuple(records)
    if not materialized:
        raise ValueError("at least one aggregation record is required")
    if any(not isinstance(record, AggregationRecord) for record in materialized):
        raise ValueError("records must contain AggregationRecord values")
    ordered = tuple(sorted(materialized, key=lambda item: item.record_id))
    if len({record.record_id for record in ordered}) != len(ordered):
        raise ValueError("aggregation records must have unique identities")
    if len({record.run_id for record in ordered}) != 1:
        raise ValueError("one aggregation file must contain exactly one run_id")
    if any(record.partition != ordered[0].partition for record in ordered):
        raise ValueError("one aggregation file must contain exactly one partition")
    batch_identity = {
        "records": [record.to_dict() for record in ordered],
        "schema_version": AGGREGATION_SCHEMA_VERSION,
    }
    batch_id = stable_digest(batch_identity, prefix="aggbatch_")
    partition_directory = _partition_directory(
        destination_root, ordered[0].partition
    )
    partition_directory.mkdir(parents=True, exist_ok=True)
    destination = partition_directory / f"part-{batch_id}.parquet"
    if destination.exists():
        existing = _read_file(destination)
        if existing != ordered:
            raise ValueError(f"aggregation batch collision at {destination}")
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return AggregationArtifact(
            batch_id, destination, len(ordered), digest, ordered[0].partition
        )
    temporary = partition_directory / (
        f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        table = pa.Table.from_pylist(
            [record.to_dict() for record in ordered], schema=_arrow_schema(pa)
        )
        pq.write_table(table, temporary, compression="zstd", version="2.6")
        with temporary.open("rb+") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        written = _read_file(temporary)
        if written != ordered:
            raise ValueError("Parquet round trip changed aggregation records")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return AggregationArtifact(
        batch_id, destination, len(ordered), digest, ordered[0].partition
    )


def read_aggregation_dataset(root: str | Path) -> tuple[AggregationRecord, ...]:
    source_root = Path(root)
    records: list[AggregationRecord] = []
    for path in sorted(source_root.rglob("*.parquet")):
        file_records = _read_file(path)
        _assert_partition_path(source_root, path, file_records)
        records.extend(file_records)
    ordered = tuple(sorted(records, key=lambda item: item.record_id))
    if len({record.record_id for record in ordered}) != len(ordered):
        raise ValueError("aggregation dataset contains duplicate record identities")
    return ordered


def build_route_aggregation_record(
    route: Mapping[str, Any],
    *,
    run_id: str,
    run_date: str,
    target_board: str = "peak_board",
) -> AggregationRecord:
    from ygo_effect_dsl.route_dsl import assert_valid_route_document

    assert_valid_route_document(route)
    experiment = route["experiment"]
    evaluator = EvaluatorSpec.from_mapping(experiment["evaluator"])
    board = route["result"][target_board]
    replay = route["replay"]
    snapshot = replay.get("initial_snapshot", {})
    resource_consumption = None
    if isinstance(snapshot, Mapping) and isinstance(snapshot.get("zones"), list):
        resource_consumption = build_route_resource_consumption(
            route, target_board=target_board
        )["scalar"]["total"]
    return AggregationRecord(
        run_id=run_id,
        route_id=route["route_id"],
        experiment_id=experiment["experiment_id"],
        evaluator_id=evaluator.evaluator_id,
        evaluator_version=evaluator.version,
        evaluator_config_hash=evaluator.config_hash,
        run_date=run_date,
        target_board=target_board,
        state_hash=board["state_hash"],
        success=route["result"]["success"],
        score=board["score"],
        action_count=len(replay["events"]),
        resource_consumption=resource_consumption,
    )


def publish_aggregation_partition(
    *,
    catalog: RunCatalog,
    raw_log_path: str | Path,
    root: str | Path,
    records: Iterable[AggregationRecord],
) -> AggregationArtifact:
    ordered = tuple(records)
    if not ordered:
        raise ValueError("at least one aggregation record is required")
    run_ids = {record.run_id for record in ordered}
    if len(run_ids) != 1:
        raise ValueError("published aggregation must belong to one run")
    run_id = next(iter(run_ids))
    raw_records = read_raw_log(raw_log_path)
    if not raw_records or {record.run_id for record in raw_records} != {run_id}:
        raise ValueError("raw log must be a validated log for the aggregation run")
    completed_route_ids = {
        record.payload.get("route_id")
        for record in raw_records
        if record.event_type == "route_completed"
    }
    missing_routes = sorted(
        record.route_id
        for record in ordered
        if record.route_id not in completed_route_ids
    )
    if missing_routes:
        raise ValueError(
            f"raw log has no route_completed events for {missing_routes}"
        )
    run = catalog.get_run(run_id)
    if run is None or run.status != RunStatus.COMPLETE:
        raise ValueError("aggregation publication requires a completed catalog run")
    if any(record.experiment_id != run.experiment_id for record in ordered):
        raise ValueError("aggregation experiment_id must match the catalog run")
    artifact = write_aggregation_partition(root, ordered)
    catalog_record = AggregationArtifactRecord(
        batch_id=artifact.batch_id,
        run_id=run_id,
        schema_version=AGGREGATION_SCHEMA_VERSION,
        evaluator_version=artifact.partition[0],
        experiment_id=artifact.partition[1],
        run_date=artifact.partition[2],
        artifact_path=str(artifact.path.resolve()),
        row_count=artifact.row_count,
        sha256=artifact.sha256,
    )
    existing = catalog.get_aggregation_artifact(artifact.batch_id)
    if existing is None:
        catalog.add_aggregation_artifact(catalog_record)
    elif existing != catalog_record:
        raise ValueError("catalog aggregation batch conflicts with published artifact")
    return artifact
