from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.spikes.aggregation_catalog_evidence import (
    AGGREGATION_CATALOG_EVIDENCE_SCHEMA_VERSION,
    collect_failure_mode_evidence,
    storage_boundary_decision,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT
    / "docs"
    / "storage"
    / "evidence"
    / "aggregation_catalog_selection.json"
)


def test_storage_boundary_keeps_authority_out_of_ui_and_query_caches() -> None:
    decision = storage_boundary_decision()

    assert decision["operational_catalog"]["backend"] == "sqlite"
    assert decision["analytical_data"]["backend"] == "parquet_pyarrow"
    assert decision["raw_evidence"]["authority"] == "immutable_source"
    assert decision["ui_cache"]["authority"] == "none"
    assert decision["query_accelerator"]["decision"] == "deferred_optional_reader"
    assert decision["distributed_execution"]["decision"] == (
        "out_of_scope_for_v0.5"
    )


def test_selected_backends_fail_closed_on_representative_corruption() -> None:
    evidence = collect_failure_mode_evidence(include_duckdb=False)

    assert evidence == {
        "duckdb_transaction_rollback": None,
        "parquet_truncation_rejected": True,
        "sqlite_schema_mismatch_rejected_without_mutation": True,
        "sqlite_transaction_rollback": True,
    }


def test_checked_workload_evidence_matches_the_architecture_decision() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert evidence["schema_version"] == (
        AGGREGATION_CATALOG_EVIDENCE_SCHEMA_VERSION
    )
    assert evidence["decision"] == storage_boundary_decision()
    assert evidence["selected_schema_versions"] == {
        "aggregation": "aggregation-v1",
        "run_catalog": "run-catalog-v2",
    }
    assert evidence["workload"]["catalog_rows"] == 10_000
    assert evidence["workload"]["analytical_rows"] == 100_000
    assert evidence["workload"]["samples"] == 3
    assert all(evidence["failure_modes"].values())

    workload = evidence["workload"]
    hashes = {
        workload["sqlite"]["analytics"]["result_sha256"],
        workload["parquet"]["analytics"]["result_sha256"],
        workload["duckdb"]["analytics"]["result_sha256"],
    }
    assert len(hashes) == 1
    assert workload["sqlite"]["catalog"]["result"] == (
        workload["duckdb"]["catalog"]["result"]
    )
