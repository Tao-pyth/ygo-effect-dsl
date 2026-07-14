from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


STORAGE_POLICY_SCHEMA_VERSION = "storage-policy-v1"


class ArtifactKind(str, Enum):
    RAW_EVENT_LOG = "raw_event_log"
    RUN_CATALOG = "run_catalog"
    AGGREGATION = "aggregation"
    EXPERIMENT = "experiment"
    ROUTE = "route"
    HUMAN_REPORT = "human_report"


class StorageFormat(str, Enum):
    JSON_LINES = "jsonl"
    SQLITE = "sqlite"
    PARQUET = "parquet"
    YAML = "yaml"
    MARKDOWN_HTML = "markdown_html"


@dataclass(frozen=True)
class ArtifactPolicy:
    kind: ArtifactKind
    storage_format: StorageFormat
    schema_version: str
    audience: str
    implementation: str
    purpose: str

    def to_dict(self) -> dict[str, str]:
        return {
            "audience": self.audience,
            "implementation": self.implementation,
            "kind": self.kind.value,
            "purpose": self.purpose,
            "schema_version": self.schema_version,
            "storage_format": self.storage_format.value,
        }


_POLICIES = {
    ArtifactKind.RAW_EVENT_LOG: ArtifactPolicy(
        ArtifactKind.RAW_EVENT_LOG,
        StorageFormat.JSON_LINES,
        "raw-event-log-v1",
        "machine",
        "implemented",
        "append-oriented ordered runtime observations",
    ),
    ArtifactKind.RUN_CATALOG: ArtifactPolicy(
        ArtifactKind.RUN_CATALOG,
        StorageFormat.SQLITE,
        "run-catalog-v2",
        "machine",
        "implemented",
        "transactional run and route lookup",
    ),
    ArtifactKind.AGGREGATION: ArtifactPolicy(
        ArtifactKind.AGGREGATION,
        StorageFormat.PARQUET,
        "aggregation-v1",
        "machine_analytics",
        "implemented_pyarrow_optional",
        "columnar metrics across many runs",
    ),
    ArtifactKind.EXPERIMENT: ArtifactPolicy(
        ArtifactKind.EXPERIMENT,
        StorageFormat.YAML,
        "0.3a",
        "human_and_machine",
        "implemented",
        "reviewable execution configuration",
    ),
    ArtifactKind.ROUTE: ArtifactPolicy(
        ArtifactKind.ROUTE,
        StorageFormat.YAML,
        "0.1",
        "human_and_machine",
        "implemented",
        "reviewable reproducible route artifact",
    ),
    ArtifactKind.HUMAN_REPORT: ArtifactPolicy(
        ArtifactKind.HUMAN_REPORT,
        StorageFormat.MARKDOWN_HTML,
        "report-v1",
        "human",
        "implemented_markdown",
        "rendered explanation and comparison output",
    ),
}


def artifact_policy(kind: ArtifactKind | str) -> ArtifactPolicy:
    if not isinstance(kind, ArtifactKind):
        kind = ArtifactKind(kind)
    return _POLICIES[kind]


def storage_policy_document() -> dict[str, Any]:
    return {
        "artifacts": [
            _POLICIES[kind].to_dict() for kind in sorted(_POLICIES, key=lambda item: item.value)
        ],
        "migration_policy": {
            "automatic_in_place_migration": False,
            "read_compatibility": "exact_schema_version_only",
            "required_process": [
                "read_and_validate_source",
                "write_new_version_to_new_artifact",
                "verify_counts_hashes_and_references",
                "atomically_switch_catalog_reference",
                "retain_or_explicitly_archive_source",
            ],
        },
        "schema_version": STORAGE_POLICY_SCHEMA_VERSION,
    }
