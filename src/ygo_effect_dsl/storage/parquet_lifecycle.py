from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import shutil
from typing import Any
import uuid

from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.storage.parquet import (
    AGGREGATION_PARTITION_KEYS,
    AGGREGATION_SCHEMA_VERSION,
    AggregationRecord,
    _arrow_schema,
    _assert_partition_path,
    _partition_directory,
    _read_file,
    _require_pyarrow,
)


PARQUET_LAYOUT_POLICY_VERSION = "parquet-layout-policy-v1"
AGGREGATION_SEMANTIC_SUMMARY_VERSION = "aggregation-semantic-summary-v1"
AGGREGATION_SNAPSHOT_FILE_VERSION = "aggregation-snapshot-file-v1"
AGGREGATION_SNAPSHOT_MANIFEST_VERSION = "aggregation-snapshot-manifest-v1"
AGGREGATION_SNAPSHOT_POINTER_VERSION = "aggregation-snapshot-pointer-v1"
AGGREGATION_DISK_PREFLIGHT_VERSION = "aggregation-disk-preflight-v1"
AGGREGATION_WRITE_METRICS_VERSION = "aggregation-write-metrics-v1"
PARQUET_LIFECYCLE_CONTRACT_VERSION = "parquet-lifecycle-contract-v1"

AGGREGATION_SNAPSHOT_DIRECTORY = "_snapshots"
AGGREGATION_STAGING_DIRECTORY = "_staging"
AGGREGATION_CURRENT_POINTER = "current-snapshot.json"
AGGREGATION_MANIFEST_FILENAME = "manifest.json"

DEFAULT_TARGET_FILE_SIZE_BYTES = 16 * 1024 * 1024
DEFAULT_TARGET_ROWS_PER_FILE = 131_072
DEFAULT_ROW_GROUP_SIZE = 16_384
DEFAULT_COMPRESSION = "zstd"
DEFAULT_COMPRESSION_LEVEL = 3
DEFAULT_MINIMUM_FREE_HEADROOM_BYTES = 64 * 1024 * 1024
DEFAULT_BYTES_PER_ROW_ESTIMATE = 256
DEFAULT_SORT_KEYS = (
    "run_id",
    "route_id",
    "target_board",
    "aggregation_record_id",
)


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
    ):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise ValueError(f"{name} must be a sequence")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(
            f"{name} fields must be exactly {sorted(expected)}; "
            f"observed {sorted(value)}"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_id(value: Any, prefixes: str | tuple[str, ...], name: str) -> str:
    parsed = _string(value, name)
    accepted = (prefixes,) if isinstance(prefixes, str) else prefixes
    for prefix in accepted:
        if parsed.startswith(prefix):
            suffix = parsed[len(prefix) :]
            if len(suffix) == 64 and all(
                character in "0123456789abcdef" for character in suffix
            ):
                return parsed
    raise ValueError(f"{name} must be a recognized content ID")


def _safe_relative_path(value: Any, name: str) -> PurePosixPath:
    path = PurePosixPath(_string(value, name))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"{name} must be a safe relative path")
    if path.as_posix() != str(value).replace("\\", "/"):
        raise ValueError(f"{name} must use normalized forward slashes")
    return path


def is_aggregation_lifecycle_internal_path(relative_path: Path) -> bool:
    return bool(relative_path.parts) and relative_path.parts[0] in {
        AGGREGATION_SNAPSHOT_DIRECTORY,
        AGGREGATION_STAGING_DIRECTORY,
    }


@dataclass(frozen=True)
class ParquetLayoutPolicy:
    partition_keys: tuple[str, ...] = AGGREGATION_PARTITION_KEYS
    sort_keys: tuple[str, ...] = DEFAULT_SORT_KEYS
    target_file_size_bytes: int = DEFAULT_TARGET_FILE_SIZE_BYTES
    target_rows_per_file: int = DEFAULT_TARGET_ROWS_PER_FILE
    row_group_size: int = DEFAULT_ROW_GROUP_SIZE
    compression: str = DEFAULT_COMPRESSION
    compression_level: int = DEFAULT_COMPRESSION_LEVEL
    minimum_free_headroom_bytes: int = DEFAULT_MINIMUM_FREE_HEADROOM_BYTES
    bytes_per_row_estimate: int = DEFAULT_BYTES_PER_ROW_ESTIMATE
    schema_version: str = PARQUET_LAYOUT_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PARQUET_LAYOUT_POLICY_VERSION:
            raise ValueError("unsupported Parquet layout policy schema")
        partition_keys = tuple(self.partition_keys)
        sort_keys = tuple(self.sort_keys)
        if partition_keys != AGGREGATION_PARTITION_KEYS:
            raise ValueError("v1 layout must retain the aggregation partition keys")
        if sort_keys != DEFAULT_SORT_KEYS:
            raise ValueError(
                "v1 layout must retain the measured deterministic sort keys"
            )
        _integer(
            self.target_file_size_bytes,
            "target_file_size_bytes",
            minimum=1,
        )
        _integer(
            self.target_rows_per_file,
            "target_rows_per_file",
            minimum=1,
        )
        _integer(self.row_group_size, "row_group_size", minimum=1)
        if self.row_group_size > self.target_rows_per_file:
            raise ValueError("row_group_size must not exceed target_rows_per_file")
        if self.compression != DEFAULT_COMPRESSION:
            raise ValueError("v1 layout supports only measured zstd compression")
        _integer(self.compression_level, "compression_level", minimum=1)
        _integer(
            self.minimum_free_headroom_bytes,
            "minimum_free_headroom_bytes",
        )
        _integer(
            self.bytes_per_row_estimate,
            "bytes_per_row_estimate",
            minimum=1,
        )
        object.__setattr__(self, "partition_keys", partition_keys)
        object.__setattr__(self, "sort_keys", sort_keys)

    @property
    def policy_id(self) -> str:
        return stable_digest(self.identity(), prefix="parquetlayout_")

    def identity(self) -> dict[str, Any]:
        return {
            "bytes_per_row_estimate": self.bytes_per_row_estimate,
            "compression": self.compression,
            "compression_level": self.compression_level,
            "minimum_free_headroom_bytes": self.minimum_free_headroom_bytes,
            "partition_keys": list(self.partition_keys),
            "row_group_size": self.row_group_size,
            "schema_version": self.schema_version,
            "sort_keys": list(self.sort_keys),
            "target_file_size_bytes": self.target_file_size_bytes,
            "target_rows_per_file": self.target_rows_per_file,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity(), "policy_id": self.policy_id}

    @classmethod
    def from_mapping(cls, value: Any) -> "ParquetLayoutPolicy":
        document = _mapping(value, "Parquet layout policy")
        _exact_keys(
            document,
            {
                "bytes_per_row_estimate",
                "compression",
                "compression_level",
                "minimum_free_headroom_bytes",
                "partition_keys",
                "policy_id",
                "row_group_size",
                "schema_version",
                "sort_keys",
                "target_file_size_bytes",
                "target_rows_per_file",
            },
            "Parquet layout policy",
        )
        policy = cls(
            partition_keys=tuple(
                _sequence(document.get("partition_keys"), "partition_keys")
            ),
            sort_keys=tuple(_sequence(document.get("sort_keys"), "sort_keys")),
            target_file_size_bytes=document.get("target_file_size_bytes"),
            target_rows_per_file=document.get("target_rows_per_file"),
            row_group_size=document.get("row_group_size"),
            compression=document.get("compression"),
            compression_level=document.get("compression_level"),
            minimum_free_headroom_bytes=document.get(
                "minimum_free_headroom_bytes"
            ),
            bytes_per_row_estimate=document.get("bytes_per_row_estimate"),
            schema_version=document.get("schema_version"),
        )
        if document.get("policy_id") != policy.policy_id:
            raise ValueError("Parquet layout policy_id does not match content")
        return policy


@dataclass(frozen=True)
class AggregationSemanticSummary:
    row_count: int
    record_set_digest: str
    core_metric_digest: str
    partition_counts: Mapping[str, int]
    success_count: int
    score_sum: float
    action_count_total: int
    schema_version: str = AGGREGATION_SEMANTIC_SUMMARY_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AGGREGATION_SEMANTIC_SUMMARY_VERSION:
            raise ValueError("unsupported aggregation semantic summary schema")
        _integer(self.row_count, "row_count")
        _string(self.record_set_digest, "record_set_digest")
        _string(self.core_metric_digest, "core_metric_digest")
        counts = dict(
            sorted(_mapping(self.partition_counts, "partition_counts").items())
        )
        if any(not isinstance(key, str) or not key for key in counts):
            raise ValueError("partition_counts keys must be non-empty strings")
        for key, value in counts.items():
            _integer(value, f"partition_counts[{key}]")
        if sum(counts.values()) != self.row_count:
            raise ValueError("partition_counts must sum to row_count")
        _integer(self.success_count, "success_count")
        _number(self.score_sum, "score_sum")
        _integer(self.action_count_total, "action_count_total")
        object.__setattr__(self, "partition_counts", counts)
        object.__setattr__(self, "score_sum", float(self.score_sum))

    @property
    def summary_id(self) -> str:
        return stable_digest(self.identity(), prefix="aggregationsemantic_")

    def identity(self) -> dict[str, Any]:
        return {
            "action_count_total": self.action_count_total,
            "core_metric_digest": self.core_metric_digest,
            "partition_counts": dict(self.partition_counts),
            "record_set_digest": self.record_set_digest,
            "row_count": self.row_count,
            "schema_version": self.schema_version,
            "score_sum": self.score_sum,
            "success_count": self.success_count,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity(), "summary_id": self.summary_id}

    @classmethod
    def from_mapping(cls, value: Any) -> "AggregationSemanticSummary":
        document = _mapping(value, "aggregation semantic summary")
        _exact_keys(
            document,
            {
                "action_count_total",
                "core_metric_digest",
                "partition_counts",
                "record_set_digest",
                "row_count",
                "schema_version",
                "score_sum",
                "success_count",
                "summary_id",
            },
            "aggregation semantic summary",
        )
        summary = cls(
            row_count=document.get("row_count"),
            record_set_digest=document.get("record_set_digest"),
            core_metric_digest=document.get("core_metric_digest"),
            partition_counts=document.get("partition_counts"),
            success_count=document.get("success_count"),
            score_sum=document.get("score_sum"),
            action_count_total=document.get("action_count_total"),
            schema_version=document.get("schema_version"),
        )
        if document.get("summary_id") != summary.summary_id:
            raise ValueError("aggregation semantic summary_id does not match content")
        return summary


def build_aggregation_semantic_summary(
    records: Iterable[AggregationRecord],
) -> AggregationSemanticSummary:
    received = tuple(records)
    if any(not isinstance(item, AggregationRecord) for item in received):
        raise ValueError("semantic summary requires AggregationRecord values")
    materialized = tuple(sorted(received, key=lambda item: item.record_id))
    if len({item.record_id for item in materialized}) != len(materialized):
        raise ValueError("semantic summary requires unique record identities")
    partition_counts: dict[str, int] = defaultdict(int)
    for item in materialized:
        partition_counts[canonical_json(list(item.partition))] += 1
    core_metrics = [
        {
            "action_count": item.action_count,
            "record_id": item.record_id,
            "score": item.score,
            "state_hash": item.state_hash,
            "success": item.success,
        }
        for item in materialized
    ]
    return AggregationSemanticSummary(
        row_count=len(materialized),
        record_set_digest=stable_digest(
            [item.record_id for item in materialized],
            prefix="aggregationrecordset_",
        ),
        core_metric_digest=stable_digest(
            core_metrics, prefix="aggregationcoremetrics_"
        ),
        partition_counts=partition_counts,
        success_count=sum(item.success for item in materialized),
        score_sum=math.fsum(item.score for item in materialized),
        action_count_total=sum(item.action_count for item in materialized),
    )


@dataclass(frozen=True)
class AggregationDiskPreflight:
    source_bytes: int
    estimated_output_bytes: int
    minimum_free_headroom_bytes: int
    required_free_bytes: int
    available_free_bytes: int
    status: str
    schema_version: str = AGGREGATION_DISK_PREFLIGHT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AGGREGATION_DISK_PREFLIGHT_VERSION:
            raise ValueError("unsupported aggregation disk preflight schema")
        for name in (
            "source_bytes",
            "estimated_output_bytes",
            "minimum_free_headroom_bytes",
            "required_free_bytes",
            "available_free_bytes",
        ):
            _integer(getattr(self, name), name)
        if self.required_free_bytes != (
            self.estimated_output_bytes + self.minimum_free_headroom_bytes
        ):
            raise ValueError("required_free_bytes does not match preflight inputs")
        expected_status = (
            "passed"
            if self.available_free_bytes >= self.required_free_bytes
            else "insufficient_disk"
        )
        if self.status != expected_status:
            raise ValueError("disk preflight status does not match available space")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(self)

    @classmethod
    def from_mapping(cls, value: Any) -> "AggregationDiskPreflight":
        document = _mapping(value, "aggregation disk preflight")
        _exact_keys(
            document,
            {
                "available_free_bytes",
                "estimated_output_bytes",
                "minimum_free_headroom_bytes",
                "required_free_bytes",
                "schema_version",
                "source_bytes",
                "status",
            },
            "aggregation disk preflight",
        )
        return cls(**document)


def build_aggregation_disk_preflight(
    root: str | Path,
    *,
    source_bytes: int,
    row_count: int,
    policy: ParquetLayoutPolicy,
    available_free_bytes: int | None = None,
) -> AggregationDiskPreflight:
    _integer(source_bytes, "source_bytes")
    _integer(row_count, "row_count", minimum=1)
    root_path = Path(root)
    probe = root_path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    available = (
        shutil.disk_usage(probe).free
        if available_free_bytes is None
        else _integer(available_free_bytes, "available_free_bytes")
    )
    estimated = max(
        source_bytes,
        row_count * policy.bytes_per_row_estimate,
        1024 * 1024,
    )
    required = estimated + policy.minimum_free_headroom_bytes
    return AggregationDiskPreflight(
        source_bytes=source_bytes,
        estimated_output_bytes=estimated,
        minimum_free_headroom_bytes=policy.minimum_free_headroom_bytes,
        required_free_bytes=required,
        available_free_bytes=available,
        status="passed" if available >= required else "insufficient_disk",
    )


@dataclass(frozen=True)
class AggregationSnapshotFile:
    relative_path: str
    sha256: str
    size_bytes: int
    row_count: int
    partition: Mapping[str, str]
    sort_min: Mapping[str, Any]
    sort_max: Mapping[str, Any]
    schema_version: str = AGGREGATION_SNAPSHOT_FILE_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AGGREGATION_SNAPSHOT_FILE_VERSION:
            raise ValueError("unsupported aggregation snapshot file schema")
        path = _safe_relative_path(self.relative_path, "relative_path")
        if path.parts[0] != "data" or path.suffix != ".parquet":
            raise ValueError("snapshot file must be a Parquet path under data/")
        if (
            not isinstance(self.sha256, str)
            or len(self.sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.sha256)
        ):
            raise ValueError("sha256 must be a lowercase SHA-256 digest")
        _integer(self.size_bytes, "size_bytes", minimum=1)
        _integer(self.row_count, "row_count", minimum=1)
        raw_partition = dict(_mapping(self.partition, "partition"))
        if set(raw_partition) != set(AGGREGATION_PARTITION_KEYS):
            raise ValueError("snapshot partition fields are invalid")
        partition = {
            key: raw_partition[key] for key in AGGREGATION_PARTITION_KEYS
        }
        for key, value in partition.items():
            _string(value, f"partition[{key}]")
        raw_sort_min = dict(_mapping(self.sort_min, "sort_min"))
        raw_sort_max = dict(_mapping(self.sort_max, "sort_max"))
        if set(raw_sort_min) != set(DEFAULT_SORT_KEYS) or set(
            raw_sort_max
        ) != set(DEFAULT_SORT_KEYS):
            raise ValueError("snapshot sort bounds must use the layout sort keys")
        sort_min = {key: raw_sort_min[key] for key in DEFAULT_SORT_KEYS}
        sort_max = {key: raw_sort_max[key] for key in DEFAULT_SORT_KEYS}
        for key in DEFAULT_SORT_KEYS:
            _string(sort_min[key], f"sort_min[{key}]")
            _string(sort_max[key], f"sort_max[{key}]")
            if sort_min[key] > sort_max[key]:
                raise ValueError(f"sort_min[{key}] must not exceed sort_max[{key}]")
        object.__setattr__(self, "relative_path", path.as_posix())
        object.__setattr__(self, "partition", partition)
        object.__setattr__(self, "sort_min", sort_min)
        object.__setattr__(self, "sort_max", sort_max)

    @property
    def file_id(self) -> str:
        return stable_digest(self.identity(), prefix="aggregationsnapshotfile_")

    def identity(self) -> dict[str, Any]:
        return {
            "partition": dict(self.partition),
            "relative_path": self.relative_path,
            "row_count": self.row_count,
            "schema_version": self.schema_version,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "sort_max": dict(self.sort_max),
            "sort_min": dict(self.sort_min),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity(), "file_id": self.file_id}

    @classmethod
    def from_mapping(cls, value: Any) -> "AggregationSnapshotFile":
        document = _mapping(value, "aggregation snapshot file")
        _exact_keys(
            document,
            {
                "file_id",
                "partition",
                "relative_path",
                "row_count",
                "schema_version",
                "sha256",
                "size_bytes",
                "sort_max",
                "sort_min",
            },
            "aggregation snapshot file",
        )
        item = cls(
            relative_path=document.get("relative_path"),
            sha256=document.get("sha256"),
            size_bytes=document.get("size_bytes"),
            row_count=document.get("row_count"),
            partition=document.get("partition"),
            sort_min=document.get("sort_min"),
            sort_max=document.get("sort_max"),
            schema_version=document.get("schema_version"),
        )
        if document.get("file_id") != item.file_id:
            raise ValueError("aggregation snapshot file_id does not match content")
        return item


@dataclass(frozen=True)
class AggregationWriteMetrics:
    source_bytes: int
    output_bytes: int
    file_count_before: int
    file_count_after: int
    write_amplification: float | None
    schema_version: str = AGGREGATION_WRITE_METRICS_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AGGREGATION_WRITE_METRICS_VERSION:
            raise ValueError("unsupported aggregation write metrics schema")
        _integer(self.source_bytes, "source_bytes")
        _integer(self.output_bytes, "output_bytes", minimum=1)
        _integer(self.file_count_before, "file_count_before")
        _integer(self.file_count_after, "file_count_after", minimum=1)
        expected = (
            None
            if self.source_bytes == 0
            else self.output_bytes / self.source_bytes
        )
        if expected is None:
            if self.write_amplification is not None:
                raise ValueError(
                    "write_amplification must be null without source bytes"
                )
        else:
            observed = _number(self.write_amplification, "write_amplification")
            if not math.isclose(observed, expected, rel_tol=1e-12):
                raise ValueError("write_amplification does not match byte counts")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(self)

    @classmethod
    def from_mapping(cls, value: Any) -> "AggregationWriteMetrics":
        document = _mapping(value, "aggregation write metrics")
        _exact_keys(
            document,
            {
                "file_count_after",
                "file_count_before",
                "output_bytes",
                "schema_version",
                "source_bytes",
                "write_amplification",
            },
            "aggregation write metrics",
        )
        return cls(**document)


class AggregationSnapshotOperation(str, Enum):
    COMPACTION = "compaction"
    MIGRATION = "migration"


@dataclass(frozen=True)
class AggregationSnapshotManifest:
    aggregation_schema_version: str
    operation: AggregationSnapshotOperation
    created_by_job_id: str
    layout_policy: ParquetLayoutPolicy
    files: tuple[AggregationSnapshotFile, ...]
    source_snapshot_ids: tuple[str, ...]
    source_file_ids: tuple[str, ...]
    semantic_summary: AggregationSemanticSummary
    source_semantic_summary_id: str
    disk_preflight: AggregationDiskPreflight
    write_metrics: AggregationWriteMetrics
    migration_id: str | None = None
    schema_version: str = AGGREGATION_SNAPSHOT_MANIFEST_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AGGREGATION_SNAPSHOT_MANIFEST_VERSION:
            raise ValueError("unsupported aggregation snapshot manifest schema")
        if self.aggregation_schema_version != AGGREGATION_SCHEMA_VERSION:
            raise ValueError(
                "snapshot reader has no codec for this aggregation schema"
            )
        operation = (
            self.operation
            if isinstance(self.operation, AggregationSnapshotOperation)
            else AggregationSnapshotOperation(self.operation)
        )
        _string(self.created_by_job_id, "created_by_job_id")
        if not isinstance(self.layout_policy, ParquetLayoutPolicy):
            raise ValueError("layout_policy must be ParquetLayoutPolicy")
        files = tuple(self.files)
        if not files or any(
            not isinstance(item, AggregationSnapshotFile) for item in files
        ):
            raise ValueError("snapshot files must contain typed file entries")
        if tuple(sorted(files, key=lambda item: item.relative_path)) != files:
            raise ValueError("snapshot files must be ordered by relative_path")
        if len({item.relative_path for item in files}) != len(files):
            raise ValueError("snapshot files must have unique paths")
        source_snapshot_ids = tuple(self.source_snapshot_ids)
        source_file_ids = tuple(self.source_file_ids)
        for name, values in (
            ("source_snapshot_ids", source_snapshot_ids),
            ("source_file_ids", source_file_ids),
        ):
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{name} must be sorted and unique")
        for value in source_snapshot_ids:
            _content_id(value, "aggregationsnapshot_", "source_snapshot_id")
        for value in source_file_ids:
            _content_id(
                value,
                ("aggregationlegacyfile_", "aggregationsnapshotfile_"),
                "source_file_id",
            )
        if not source_file_ids:
            raise ValueError("snapshot manifest requires a non-empty source file set")
        if not isinstance(self.semantic_summary, AggregationSemanticSummary):
            raise ValueError("semantic_summary must be typed")
        _content_id(
            self.source_semantic_summary_id,
            "aggregationsemantic_",
            "source_semantic_summary_id",
        )
        if self.source_semantic_summary_id != self.semantic_summary.summary_id:
            raise ValueError("source and output semantic summaries must match")
        if not isinstance(self.disk_preflight, AggregationDiskPreflight):
            raise ValueError("disk_preflight must be typed")
        if self.disk_preflight.status != "passed":
            raise ValueError("published snapshot requires a passed disk preflight")
        if not isinstance(self.write_metrics, AggregationWriteMetrics):
            raise ValueError("write_metrics must be typed")
        if self.write_metrics.file_count_after != len(files):
            raise ValueError("file_count_after does not match snapshot files")
        if self.write_metrics.output_bytes != sum(item.size_bytes for item in files):
            raise ValueError("output_bytes does not match snapshot files")
        if operation == AggregationSnapshotOperation.MIGRATION:
            _string(self.migration_id, "migration_id")
        elif self.migration_id is not None:
            raise ValueError("compaction must not declare migration_id")
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "files", files)
        object.__setattr__(self, "source_snapshot_ids", source_snapshot_ids)
        object.__setattr__(self, "source_file_ids", source_file_ids)

    @property
    def snapshot_id(self) -> str:
        return stable_digest(self.identity(), prefix="aggregationsnapshot_")

    def identity(self) -> dict[str, Any]:
        return {
            "aggregation_schema_version": self.aggregation_schema_version,
            "created_by_job_id": self.created_by_job_id,
            "disk_preflight": self.disk_preflight.to_dict(),
            "files": [item.to_dict() for item in self.files],
            "layout_policy": self.layout_policy.to_dict(),
            "migration_id": self.migration_id,
            "operation": self.operation.value,
            "schema_version": self.schema_version,
            "semantic_summary": self.semantic_summary.to_dict(),
            "source_file_ids": list(self.source_file_ids),
            "source_semantic_summary_id": self.source_semantic_summary_id,
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "write_metrics": self.write_metrics.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity(), "snapshot_id": self.snapshot_id}

    @classmethod
    def from_mapping(cls, value: Any) -> "AggregationSnapshotManifest":
        document = _mapping(value, "aggregation snapshot manifest")
        _exact_keys(
            document,
            {
                "aggregation_schema_version",
                "created_by_job_id",
                "disk_preflight",
                "files",
                "layout_policy",
                "migration_id",
                "operation",
                "schema_version",
                "semantic_summary",
                "snapshot_id",
                "source_file_ids",
                "source_semantic_summary_id",
                "source_snapshot_ids",
                "write_metrics",
            },
            "aggregation snapshot manifest",
        )
        manifest = cls(
            aggregation_schema_version=document.get(
                "aggregation_schema_version"
            ),
            operation=document.get("operation"),
            created_by_job_id=document.get("created_by_job_id"),
            layout_policy=ParquetLayoutPolicy.from_mapping(
                document.get("layout_policy")
            ),
            files=tuple(
                AggregationSnapshotFile.from_mapping(item)
                for item in _sequence(document.get("files"), "files")
            ),
            source_snapshot_ids=tuple(
                _sequence(
                    document.get("source_snapshot_ids"),
                    "source_snapshot_ids",
                )
            ),
            source_file_ids=tuple(
                _sequence(document.get("source_file_ids"), "source_file_ids")
            ),
            semantic_summary=AggregationSemanticSummary.from_mapping(
                document.get("semantic_summary")
            ),
            source_semantic_summary_id=document.get(
                "source_semantic_summary_id"
            ),
            disk_preflight=AggregationDiskPreflight.from_mapping(
                document.get("disk_preflight")
            ),
            write_metrics=AggregationWriteMetrics.from_mapping(
                document.get("write_metrics")
            ),
            migration_id=document.get("migration_id"),
            schema_version=document.get("schema_version"),
        )
        if document.get("snapshot_id") != manifest.snapshot_id:
            raise ValueError("aggregation snapshot_id does not match manifest")
        return manifest


@dataclass(frozen=True)
class AggregationSnapshot:
    manifest: AggregationSnapshotManifest
    records: tuple[AggregationRecord, ...]
    manifest_path: Path


class ParquetLifecycleFaultPoint(str, Enum):
    AFTER_STAGED_FILES = "after_staged_files"
    AFTER_SNAPSHOT_RENAME = "after_snapshot_rename"
    BEFORE_POINTER_REPLACE = "before_pointer_replace"
    AFTER_POINTER_REPLACE = "after_pointer_replace"


class InjectedParquetLifecycleFault(RuntimeError):
    def __init__(self, point: ParquetLifecycleFaultPoint) -> None:
        super().__init__(f"injected Parquet lifecycle fault at {point.value}")
        self.point = point


ParquetLifecycleFaultInjector = Callable[[ParquetLifecycleFaultPoint], None]


def parquet_fault_at(
    point: ParquetLifecycleFaultPoint,
) -> ParquetLifecycleFaultInjector:
    target = (
        point
        if isinstance(point, ParquetLifecycleFaultPoint)
        else ParquetLifecycleFaultPoint(point)
    )

    def inject(observed: ParquetLifecycleFaultPoint) -> None:
        if observed == target:
            raise InjectedParquetLifecycleFault(observed)

    return inject


def _inject(
    injector: ParquetLifecycleFaultInjector | None,
    point: ParquetLifecycleFaultPoint,
) -> None:
    if injector is not None:
        injector(point)


def _snapshot_root(root: Path) -> Path:
    return root / AGGREGATION_SNAPSHOT_DIRECTORY


def _staging_root(root: Path) -> Path:
    return root / AGGREGATION_STAGING_DIRECTORY


def aggregation_current_pointer_path(root: str | Path) -> Path:
    return Path(root) / AGGREGATION_CURRENT_POINTER


def _manifest_path(root: Path, snapshot_id: str) -> Path:
    parsed = _content_id(snapshot_id, "aggregationsnapshot_", "snapshot_id")
    return _snapshot_root(root) / parsed / AGGREGATION_MANIFEST_FILENAME


def _pointer_document(
    root: Path,
    manifest: AggregationSnapshotManifest,
) -> dict[str, Any]:
    manifest_path = _manifest_path(root, manifest.snapshot_id)
    relative = manifest_path.relative_to(root).as_posix()
    identity = {
        "manifest_path": relative,
        "manifest_sha256": _sha256_file(manifest_path),
        "schema_version": AGGREGATION_SNAPSHOT_POINTER_VERSION,
        "snapshot_id": manifest.snapshot_id,
    }
    return {
        **identity,
        "pointer_id": stable_digest(identity, prefix="aggregationsnapshotpointer_"),
    }


def _load_pointer(root: Path) -> Mapping[str, Any]:
    path = aggregation_current_pointer_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"aggregation snapshot pointer does not exist: {path}")
    import json

    document = _mapping(
        json.loads(path.read_text(encoding="utf-8")),
        "aggregation snapshot pointer",
    )
    _exact_keys(
        document,
        {
            "manifest_path",
            "manifest_sha256",
            "pointer_id",
            "schema_version",
            "snapshot_id",
        },
        "aggregation snapshot pointer",
    )
    if document.get("schema_version") != AGGREGATION_SNAPSHOT_POINTER_VERSION:
        raise ValueError("unsupported aggregation snapshot pointer schema")
    expected_path = _manifest_path(root, document.get("snapshot_id"))
    relative = _safe_relative_path(document.get("manifest_path"), "manifest_path")
    if (root / Path(*relative.parts)).resolve() != expected_path.resolve():
        raise ValueError("aggregation snapshot pointer manifest path is inconsistent")
    identity = {
        "manifest_path": document["manifest_path"],
        "manifest_sha256": document["manifest_sha256"],
        "schema_version": document["schema_version"],
        "snapshot_id": document["snapshot_id"],
    }
    if document.get("pointer_id") != stable_digest(
        identity, prefix="aggregationsnapshotpointer_"
    ):
        raise ValueError("aggregation snapshot pointer_id does not match content")
    return document


def current_aggregation_snapshot_id(root: str | Path) -> str | None:
    root_path = Path(root)
    if not aggregation_current_pointer_path(root_path).is_file():
        return None
    return str(_load_pointer(root_path)["snapshot_id"])


def _sort_value(record: AggregationRecord, key: str) -> str:
    if key == "aggregation_record_id":
        return record.record_id
    value = getattr(record, key)
    return str(value)


def _sort_key(
    record: AggregationRecord,
    policy: ParquetLayoutPolicy,
) -> tuple[str, ...]:
    return tuple(_sort_value(record, key) for key in policy.sort_keys)


def _partition_mapping(record: AggregationRecord) -> dict[str, str]:
    return {
        key: value
        for key, value in zip(
            AGGREGATION_PARTITION_KEYS,
            record.partition,
            strict=True,
        )
    }


def _snapshot_file_entry(
    stage_root: Path,
    path: Path,
    records: Sequence[AggregationRecord],
    policy: ParquetLayoutPolicy,
) -> AggregationSnapshotFile:
    first = records[0]
    return AggregationSnapshotFile(
        relative_path=path.relative_to(stage_root).as_posix(),
        sha256=_sha256_file(path),
        size_bytes=path.stat().st_size,
        row_count=len(records),
        partition=_partition_mapping(first),
        sort_min={
            key: min(_sort_value(record, key) for record in records)
            for key in policy.sort_keys
        },
        sort_max={
            key: max(_sort_value(record, key) for record in records)
            for key in policy.sort_keys
        },
    )


def _write_snapshot_file(
    stage_root: Path,
    records: Sequence[AggregationRecord],
    policy: ParquetLayoutPolicy,
) -> AggregationSnapshotFile:
    pa, pq = _require_pyarrow()
    ordered = tuple(sorted(records, key=lambda item: _sort_key(item, policy)))
    if not ordered:
        raise ValueError("snapshot file requires at least one record")
    if any(item.partition != ordered[0].partition for item in ordered):
        raise ValueError("snapshot file cannot cross aggregation partitions")
    file_identity = {
        "layout_policy_id": policy.policy_id,
        "record_ids": [item.record_id for item in ordered],
    }
    batch_id = stable_digest(file_identity, prefix="aggcompact_")
    data_root = stage_root / "data"
    partition_directory = _partition_directory(data_root, ordered[0].partition)
    partition_directory.mkdir(parents=True, exist_ok=True)
    destination = partition_directory / f"part-{batch_id}.parquet"
    table = pa.Table.from_pylist(
        [item.to_dict() for item in ordered],
        schema=_arrow_schema(pa),
    )
    pq.write_table(
        table,
        destination,
        compression=policy.compression,
        compression_level=policy.compression_level,
        row_group_size=policy.row_group_size,
        version="2.6",
        write_statistics=True,
    )
    with destination.open("rb+") as stream:
        stream.flush()
        os.fsync(stream.fileno())
    reread = _read_file(destination)
    if reread != ordered:
        raise ValueError("snapshot Parquet round trip changed aggregation records")
    return _snapshot_file_entry(stage_root, destination, ordered, policy)


@dataclass(frozen=True)
class _SourceDataset:
    records: tuple[AggregationRecord, ...]
    snapshot_ids: tuple[str, ...]
    file_ids: tuple[str, ...]
    source_bytes: int
    file_count: int
    semantic_summary: AggregationSemanticSummary


@dataclass(frozen=True)
class _LegacyFile:
    records: tuple[AggregationRecord, ...]
    file_id: str
    size_bytes: int


def _legacy_files(root: Path) -> tuple[_LegacyFile, ...]:
    files: list[_LegacyFile] = []
    for path in sorted(root.rglob("*.parquet")):
        relative = path.relative_to(root)
        if is_aggregation_lifecycle_internal_path(relative):
            continue
        file_records = _read_file(path)
        _assert_partition_path(root, path, file_records)
        size_bytes = path.stat().st_size
        files.append(
            _LegacyFile(
                records=file_records,
                file_id=stable_digest(
                    {
                        "relative_path": relative.as_posix(),
                        "row_count": len(file_records),
                        "sha256": _sha256_file(path),
                        "size_bytes": size_bytes,
                    },
                    prefix="aggregationlegacyfile_",
                ),
                size_bytes=size_bytes,
            )
        )
    return tuple(files)


def _legacy_source_dataset(root: Path) -> _SourceDataset:
    files = _legacy_files(root)
    records = tuple(record for item in files for record in item.records)
    ordered = tuple(sorted(records, key=lambda item: item.record_id))
    if not ordered:
        raise ValueError("legacy aggregation dataset contains no records")
    if len({item.record_id for item in ordered}) != len(ordered):
        raise ValueError("legacy aggregation dataset contains duplicate identities")
    return _SourceDataset(
        records=ordered,
        snapshot_ids=(),
        file_ids=tuple(sorted(item.file_id for item in files)),
        source_bytes=sum(item.size_bytes for item in files),
        file_count=len(files),
        semantic_summary=build_aggregation_semantic_summary(ordered),
    )


def _snapshot_with_legacy_deltas(
    root: Path,
    snapshot_id: str,
) -> _SourceDataset:
    source = _snapshot_source_dataset(root, snapshot_id)
    by_id = {record.record_id: record for record in source.records}
    delta_files: list[_LegacyFile] = []
    for item in _legacy_files(root):
        if item.file_id in source.file_ids:
            continue
        new_records = tuple(
            record for record in item.records if record.record_id not in by_id
        )
        if len(new_records) != len(item.records):
            raise ValueError(
                "untracked legacy delta file contains an active snapshot identity"
            )
        for record in new_records:
            if record.record_id in by_id:
                raise ValueError("legacy delta contains duplicate record identity")
            by_id[record.record_id] = record
        delta_files.append(item)
    if not delta_files:
        return source
    records = tuple(sorted(by_id.values(), key=lambda item: item.record_id))
    return _SourceDataset(
        records=records,
        snapshot_ids=source.snapshot_ids,
        file_ids=tuple(
            sorted(
                (
                    *source.file_ids,
                    *(item.file_id for item in delta_files),
                )
            )
        ),
        source_bytes=(
            source.source_bytes + sum(item.size_bytes for item in delta_files)
        ),
        file_count=source.file_count + len(delta_files),
        semantic_summary=build_aggregation_semantic_summary(records),
    )


def _read_manifest(path: Path) -> AggregationSnapshotManifest:
    import json

    document = json.loads(path.read_text(encoding="utf-8"))
    return AggregationSnapshotManifest.from_mapping(document)


def read_aggregation_snapshot(
    root: str | Path,
    *,
    snapshot_id: str | None = None,
) -> AggregationSnapshot:
    root_path = Path(root)
    pointer: Mapping[str, Any] | None = None
    selected_id = snapshot_id
    if selected_id is None:
        pointer = _load_pointer(root_path)
        selected_id = str(pointer["snapshot_id"])
    manifest_path = _manifest_path(root_path, selected_id)
    if not manifest_path.is_file():
        raise ValueError(f"aggregation snapshot manifest is missing: {manifest_path}")
    if pointer is not None and _sha256_file(manifest_path) != pointer[
        "manifest_sha256"
    ]:
        raise ValueError("aggregation snapshot manifest checksum mismatch")
    manifest = _read_manifest(manifest_path)
    if manifest.snapshot_id != selected_id:
        raise ValueError("aggregation snapshot directory does not match manifest ID")
    snapshot_directory = manifest_path.parent
    records: list[AggregationRecord] = []
    for item in manifest.files:
        relative = _safe_relative_path(item.relative_path, "relative_path")
        path = snapshot_directory / Path(*relative.parts)
        try:
            path.resolve().relative_to(snapshot_directory.resolve())
        except ValueError as exc:
            raise ValueError("snapshot file escapes its snapshot directory") from exc
        if not path.is_file():
            raise ValueError(f"aggregation snapshot file is missing: {path}")
        if path.stat().st_size != item.size_bytes:
            raise ValueError(f"aggregation snapshot file size mismatch: {path}")
        if _sha256_file(path) != item.sha256:
            raise ValueError(f"aggregation snapshot file checksum mismatch: {path}")
        file_records = _read_file(path)
        if len(file_records) != item.row_count:
            raise ValueError(f"aggregation snapshot row count mismatch: {path}")
        expected_partition = tuple(
            item.partition[key] for key in AGGREGATION_PARTITION_KEYS
        )
        if any(record.partition != expected_partition for record in file_records):
            raise ValueError(f"aggregation snapshot partition mismatch: {path}")
        for key in manifest.layout_policy.sort_keys:
            values = [_sort_value(record, key) for record in file_records]
            if min(values) != item.sort_min[key] or max(values) != item.sort_max[key]:
                raise ValueError(f"aggregation snapshot sort bounds mismatch: {path}")
        expected_order = tuple(
            sorted(
                file_records,
                key=lambda record: _sort_key(
                    record, manifest.layout_policy
                ),
            )
        )
        if expected_order != file_records:
            raise ValueError(
                "aggregation snapshot file is not deterministically sorted: "
                f"{path}"
            )
        records.extend(file_records)
    ordered = tuple(sorted(records, key=lambda item: item.record_id))
    if len({item.record_id for item in ordered}) != len(ordered):
        raise ValueError("aggregation snapshot contains duplicate record identities")
    summary = build_aggregation_semantic_summary(ordered)
    if summary != manifest.semantic_summary:
        raise ValueError("aggregation snapshot semantic summary mismatch")
    return AggregationSnapshot(manifest, ordered, manifest_path)


def _snapshot_source_dataset(
    root: Path,
    snapshot_id: str,
) -> _SourceDataset:
    snapshot = read_aggregation_snapshot(root, snapshot_id=snapshot_id)
    return _SourceDataset(
        records=snapshot.records,
        snapshot_ids=(snapshot.manifest.snapshot_id,),
        file_ids=tuple(
            sorted(
                {
                    *snapshot.manifest.source_file_ids,
                    *(item.file_id for item in snapshot.manifest.files),
                }
            )
        ),
        source_bytes=sum(item.size_bytes for item in snapshot.manifest.files),
        file_count=len(snapshot.manifest.files),
        semantic_summary=snapshot.manifest.semantic_summary,
    )


def _resolve_source_dataset(
    root: Path,
    source_snapshot_id: str | None,
) -> _SourceDataset:
    selected_id = source_snapshot_id
    if selected_id is None:
        selected_id = current_aggregation_snapshot_id(root)
    if selected_id is None:
        return _legacy_source_dataset(root)
    return _snapshot_with_legacy_deltas(root, selected_id)


def activate_aggregation_snapshot(
    root: str | Path,
    snapshot_id: str,
    *,
    expected_current_snapshot_id: str | None = None,
    injector: ParquetLifecycleFaultInjector | None = None,
) -> AggregationSnapshot:
    root_path = Path(root)
    snapshot = read_aggregation_snapshot(root_path, snapshot_id=snapshot_id)
    observed_current = current_aggregation_snapshot_id(root_path)
    if (
        expected_current_snapshot_id is not None
        and observed_current != expected_current_snapshot_id
    ):
        raise ValueError(
            "current aggregation snapshot changed before pointer activation"
        )
    pointer = _pointer_document(root_path, snapshot.manifest)
    _inject(injector, ParquetLifecycleFaultPoint.BEFORE_POINTER_REPLACE)
    atomic_write_text(
        aggregation_current_pointer_path(root_path),
        canonical_json(pointer) + "\n",
    )
    _inject(injector, ParquetLifecycleFaultPoint.AFTER_POINTER_REPLACE)
    return snapshot


def rollback_aggregation_snapshot(
    root: str | Path,
    target_snapshot_id: str,
    *,
    expected_current_snapshot_id: str,
) -> AggregationSnapshot:
    if target_snapshot_id == expected_current_snapshot_id:
        raise ValueError("rollback target must differ from current snapshot")
    return activate_aggregation_snapshot(
        root,
        target_snapshot_id,
        expected_current_snapshot_id=expected_current_snapshot_id,
    )


def _write_snapshot_files(
    stage_root: Path,
    records: Sequence[AggregationRecord],
    policy: ParquetLayoutPolicy,
) -> tuple[AggregationSnapshotFile, ...]:
    grouped: dict[tuple[str, str, str], list[AggregationRecord]] = defaultdict(list)
    for record in records:
        grouped[record.partition].append(record)
    file_row_limit = min(
        policy.target_rows_per_file,
        max(
            1,
            policy.target_file_size_bytes // policy.bytes_per_row_estimate,
        ),
    )
    files: list[AggregationSnapshotFile] = []
    for partition in sorted(grouped):
        ordered = sorted(grouped[partition], key=lambda item: _sort_key(item, policy))
        for offset in range(0, len(ordered), file_row_limit):
            files.append(
                _write_snapshot_file(
                    stage_root,
                    ordered[offset : offset + file_row_limit],
                    policy,
                )
            )
    return tuple(sorted(files, key=lambda item: item.relative_path))


def _remove_stage(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _publish_snapshot(
    root: Path,
    *,
    source: _SourceDataset,
    records: Sequence[AggregationRecord],
    operation: AggregationSnapshotOperation,
    created_by_job_id: str,
    policy: ParquetLayoutPolicy,
    migration_id: str | None,
    available_free_bytes: int | None,
    activate: bool,
    injector: ParquetLifecycleFaultInjector | None,
) -> AggregationSnapshot:
    if not records:
        raise ValueError("snapshot publication requires at least one record")
    received = tuple(records)
    if any(not isinstance(item, AggregationRecord) for item in received):
        raise ValueError("snapshot publication requires AggregationRecord values")
    ordered = tuple(sorted(received, key=lambda item: item.record_id))
    if len({item.record_id for item in ordered}) != len(ordered):
        raise ValueError("snapshot publication requires unique record identities")
    output_summary = build_aggregation_semantic_summary(ordered)
    if output_summary != source.semantic_summary:
        raise ValueError(
            "migration or compaction changed the aggregation semantic summary"
        )
    preflight = build_aggregation_disk_preflight(
        root,
        source_bytes=source.source_bytes,
        row_count=len(ordered),
        policy=policy,
        available_free_bytes=available_free_bytes,
    )
    if preflight.status != "passed":
        raise OSError(
            "insufficient disk for aggregation snapshot publication: "
            f"required={preflight.required_free_bytes}, "
            f"available={preflight.available_free_bytes}"
        )
    root.mkdir(parents=True, exist_ok=True)
    snapshots = _snapshot_root(root)
    staging = _staging_root(root)
    snapshots.mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True, exist_ok=True)
    stage_root = staging / f"snapshot-{os.getpid()}-{uuid.uuid4().hex}"
    stage_root.mkdir()
    try:
        files = _write_snapshot_files(stage_root, ordered, policy)
        _inject(injector, ParquetLifecycleFaultPoint.AFTER_STAGED_FILES)
        output_bytes = sum(item.size_bytes for item in files)
        metrics = AggregationWriteMetrics(
            source_bytes=source.source_bytes,
            output_bytes=output_bytes,
            file_count_before=source.file_count,
            file_count_after=len(files),
            write_amplification=(
                None
                if source.source_bytes == 0
                else output_bytes / source.source_bytes
            ),
        )
        manifest = AggregationSnapshotManifest(
            aggregation_schema_version=AGGREGATION_SCHEMA_VERSION,
            operation=operation,
            created_by_job_id=created_by_job_id,
            layout_policy=policy,
            files=files,
            source_snapshot_ids=source.snapshot_ids,
            source_file_ids=source.file_ids,
            semantic_summary=output_summary,
            source_semantic_summary_id=source.semantic_summary.summary_id,
            disk_preflight=preflight,
            write_metrics=metrics,
            migration_id=migration_id,
        )
        atomic_write_text(
            stage_root / AGGREGATION_MANIFEST_FILENAME,
            canonical_json(manifest.to_dict()) + "\n",
        )
        final_root = _snapshot_root(root) / manifest.snapshot_id
        if final_root.exists():
            existing = _read_manifest(final_root / AGGREGATION_MANIFEST_FILENAME)
            if existing != manifest:
                raise ValueError("aggregation snapshot ID collision")
            _remove_stage(stage_root)
        else:
            stage_root.replace(final_root)
        _inject(injector, ParquetLifecycleFaultPoint.AFTER_SNAPSHOT_RENAME)
        snapshot = read_aggregation_snapshot(
            root, snapshot_id=manifest.snapshot_id
        )
        if activate:
            expected_current = (
                source.snapshot_ids[0] if source.snapshot_ids else None
            )
            snapshot = activate_aggregation_snapshot(
                root,
                manifest.snapshot_id,
                expected_current_snapshot_id=expected_current,
                injector=injector,
            )
        return snapshot
    except InjectedParquetLifecycleFault:
        raise
    except BaseException:
        _remove_stage(stage_root)
        raise


def compact_aggregation_dataset(
    root: str | Path,
    *,
    created_by_job_id: str,
    source_snapshot_id: str | None = None,
    policy: ParquetLayoutPolicy | None = None,
    available_free_bytes: int | None = None,
    activate: bool = True,
    injector: ParquetLifecycleFaultInjector | None = None,
) -> AggregationSnapshot:
    root_path = Path(root)
    source = _resolve_source_dataset(root_path, source_snapshot_id)
    return _publish_snapshot(
        root_path,
        source=source,
        records=source.records,
        operation=AggregationSnapshotOperation.COMPACTION,
        created_by_job_id=created_by_job_id,
        policy=policy or ParquetLayoutPolicy(),
        migration_id=None,
        available_free_bytes=available_free_bytes,
        activate=activate,
        injector=injector,
    )


def migrate_aggregation_snapshot(
    root: str | Path,
    *,
    created_by_job_id: str,
    migration_id: str,
    transform: Callable[[AggregationRecord], AggregationRecord],
    source_snapshot_id: str | None = None,
    target_schema_version: str = AGGREGATION_SCHEMA_VERSION,
    policy: ParquetLayoutPolicy | None = None,
    available_free_bytes: int | None = None,
    activate: bool = True,
    injector: ParquetLifecycleFaultInjector | None = None,
) -> AggregationSnapshot:
    _string(migration_id, "migration_id")
    if not callable(transform):
        raise ValueError("migration transform must be callable")
    if target_schema_version != AGGREGATION_SCHEMA_VERSION:
        raise ValueError(
            "no explicit aggregation codec is registered for target schema "
            f"{target_schema_version!r}"
        )
    root_path = Path(root)
    source = _resolve_source_dataset(root_path, source_snapshot_id)
    transformed = tuple(transform(item) for item in source.records)
    return _publish_snapshot(
        root_path,
        source=source,
        records=transformed,
        operation=AggregationSnapshotOperation.MIGRATION,
        created_by_job_id=created_by_job_id,
        policy=policy or ParquetLayoutPolicy(),
        migration_id=migration_id,
        available_free_bytes=available_free_bytes,
        activate=activate,
        injector=injector,
    )


def parquet_lifecycle_contract_document() -> dict[str, Any]:
    policy = ParquetLayoutPolicy()
    return to_canonical_data(
        {
            "atomic_publication": {
                "legacy_delta_visibility": "next_compacted_snapshot_only",
                "pointer": AGGREGATION_CURRENT_POINTER,
                "reader_visibility": "one_complete_old_or_new_snapshot",
                "staging_directory": AGGREGATION_STAGING_DIRECTORY,
            },
            "calibration": {
                "evidence": "docs/storage/evidence/parquet_lifecycle.json",
                "production_recalibration_issue": 167,
                "status": "measured_provisional",
                "workload_rows": 20_000,
            },
            "disk_preflight": {
                "bytes_per_row_estimate": policy.bytes_per_row_estimate,
                "minimum_free_headroom_bytes": (
                    policy.minimum_free_headroom_bytes
                ),
                "required": True,
            },
            "layout": policy.to_dict(),
            "manifest": {
                "file_fields": [
                    "sha256",
                    "row_count",
                    "size_bytes",
                    "partition",
                    "sort_min",
                    "sort_max",
                ],
                "schema_version": AGGREGATION_SNAPSHOT_MANIFEST_VERSION,
                "source_set": ["snapshot_ids", "file_ids"],
            },
            "migration": {
                "in_place": False,
                "semantic_parity": AGGREGATION_SEMANTIC_SUMMARY_VERSION,
                "unknown_target_schema": "fail_close_without_explicit_codec",
            },
            "rollback": "atomic_pointer_reactivation",
            "version": PARQUET_LIFECYCLE_CONTRACT_VERSION,
        }
    )


__all__ = [
    "AGGREGATION_CURRENT_POINTER",
    "AGGREGATION_DISK_PREFLIGHT_VERSION",
    "AGGREGATION_MANIFEST_FILENAME",
    "AGGREGATION_SEMANTIC_SUMMARY_VERSION",
    "AGGREGATION_SNAPSHOT_DIRECTORY",
    "AGGREGATION_SNAPSHOT_FILE_VERSION",
    "AGGREGATION_SNAPSHOT_MANIFEST_VERSION",
    "AGGREGATION_SNAPSHOT_POINTER_VERSION",
    "AGGREGATION_STAGING_DIRECTORY",
    "AGGREGATION_WRITE_METRICS_VERSION",
    "PARQUET_LAYOUT_POLICY_VERSION",
    "PARQUET_LIFECYCLE_CONTRACT_VERSION",
    "AggregationDiskPreflight",
    "AggregationSemanticSummary",
    "AggregationSnapshot",
    "AggregationSnapshotFile",
    "AggregationSnapshotManifest",
    "AggregationSnapshotOperation",
    "AggregationWriteMetrics",
    "InjectedParquetLifecycleFault",
    "ParquetLayoutPolicy",
    "ParquetLifecycleFaultPoint",
    "activate_aggregation_snapshot",
    "aggregation_current_pointer_path",
    "build_aggregation_disk_preflight",
    "build_aggregation_semantic_summary",
    "compact_aggregation_dataset",
    "current_aggregation_snapshot_id",
    "is_aggregation_lifecycle_internal_path",
    "migrate_aggregation_snapshot",
    "parquet_fault_at",
    "parquet_lifecycle_contract_document",
    "read_aggregation_snapshot",
    "rollback_aggregation_snapshot",
]
