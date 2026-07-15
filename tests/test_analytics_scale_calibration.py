from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.analytics_scale_calibration import (
    ANALYTICS_SCALE_CALIBRATION_SCHEMA_VERSION,
    ANALYTICS_SCALE_SAMPLE_SCHEMA_VERSION,
    AnalyticsScaleWorkload,
    analytics_scale_calibration_contract_document,
    write_analytics_scale_evidence,
)

pq = pytest.importorskip("pyarrow.parquet")

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "storage" / "evidence" / "analytics_scale_calibration.json"
)
SAMPLES_PATH = (
    REPO_ROOT / "docs" / "storage" / "evidence" / "analytics_scale_samples.parquet"
)
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "analytics-scale-calibration.yml"


def test_scale_workload_rejects_underfilled_or_invalid_dimensions() -> None:
    with pytest.raises(ValueError, match="event_row_count"):
        AnalyticsScaleWorkload(run_count=2, event_row_count=1)
    with pytest.raises(ValueError, match="analytical_row_count"):
        AnalyticsScaleWorkload(run_count=2, event_row_count=2, analytical_row_count=1)
    with pytest.raises(ValueError, match="query_samples"):
        AnalyticsScaleWorkload(query_samples=0)


def test_scale_contract_resource_matches_runtime() -> None:
    resource = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ygo_effect_dsl"
        / "resources"
        / "analytics-scale-calibration-v1.json"
    )

    assert json.loads(resource.read_text(encoding="utf-8")) == (
        analytics_scale_calibration_contract_document()
    )


def test_scale_smoke_runs_the_production_contracts_and_writes_samples(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "analytics-scale.json"
    samples_path = tmp_path / "analytics-scale-samples.parquet"
    workload = AnalyticsScaleWorkload(
        run_count=20,
        event_row_count=100,
        analytical_row_count=40,
        query_samples=2,
        legacy_batch_rows=10,
    )

    evidence = write_analytics_scale_evidence(
        workload=workload,
        work_root=tmp_path / "work",
        out=evidence_path,
        samples_out=samples_path,
    )

    committed = json.loads(evidence_path.read_text(encoding="utf-8"))
    identity = {key: value for key, value in committed.items() if key != "evidence_id"}
    assert committed == evidence
    assert committed["schema_version"] == ANALYTICS_SCALE_CALIBRATION_SCHEMA_VERSION
    assert committed["evidence_id"] == stable_digest(
        identity, prefix="analyticsscaleevidence_"
    )
    assert committed["workload"] == {
        "analytical_row_count": 40,
        "event_row_count": 100,
        "full_scale": False,
        "legacy_batch_rows": 10,
        "query_samples": 2,
        "run_count": 20,
    }
    assert committed["acceptance"]["application_export_semantic_parity"] is True
    assert committed["acceptance"]["catalog_complete_runs"] == 20
    assert committed["acceptance"]["concurrent_compaction_reader_complete"] is True
    assert committed["acceptance"]["concurrent_ingest_kept_query_snapshot"] is True
    assert committed["acceptance"]["crash_kept_previous_snapshot"] is True
    assert committed["acceptance"]["migration_recovered"] is True
    assert committed["acceptance"]["raw_file_per_run"] is True
    assert committed["recovery"]["cancel"] == {
        "acknowledgement_ms": committed["recovery"]["cancel"][
            "acknowledgement_ms"
        ],
        "outcome": "cancelled",
        "state": "cancelled",
    }
    assert {
        item["semantic_digest"]
        for item in committed["artifacts"]["exports"].values()
    } == {
        committed["artifacts"]["exports"]["json"]["semantic_digest"]
    }
    assert committed["artifacts"]["lifecycle_writes"]["compaction"][
        "write_amplification"
    ] > 0
    assert committed["policy_decision"]["query"][
        "measured_application_bytes_per_row"
    ] >= 0
    assert committed["ui_evidence_boundary"]["renderer_evidence"][
        "loaded_rows"
    ] == 100_000

    sample_artifact = committed["sample_artifact"]
    assert sample_artifact["bytes"] == samples_path.stat().st_size
    assert sample_artifact["sha256"] == hashlib.sha256(
        samples_path.read_bytes()
    ).hexdigest()
    samples = pq.read_table(samples_path).to_pylist()
    assert sample_artifact["row_count"] == len(samples)
    assert all(
        item["schema_version"] == ANALYTICS_SCALE_SAMPLE_SCHEMA_VERSION
        for item in samples
    )
    operations = {item["operation"] for item in samples}
    assert {
        "aggregation_compaction",
        "aggregation_crash_before_pointer",
        "aggregation_migration_recovery",
        "application_export_json",
        "application_export_csv",
        "application_export_parquet",
        "application_query",
        "catalog_batch_create",
        "concurrent_catalog_ingest_query",
        "concurrent_compaction_read",
        "concurrent_export_cancel",
        "desktop_bridge_query",
        "persistent_comparison",
        "persistent_run_drill_down",
        "raw_event_ingest",
    } <= operations


def test_committed_full_scale_evidence_is_content_addressed_and_complete() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == ANALYTICS_SCALE_CALIBRATION_SCHEMA_VERSION
    assert evidence["evidence_id"] == stable_digest(
        identity, prefix="analyticsscaleevidence_"
    )
    assert evidence["workload"] == {
        "analytical_row_count": 100_000,
        "event_row_count": 1_000_000,
        "full_scale": True,
        "legacy_batch_rows": 1_000,
        "query_samples": 9,
        "run_count": 100_000,
    }
    assert all(evidence["acceptance"].values())
    assert evidence["policy_decision"]["export"] == {
        "max_bytes": 512 * 1024 * 1024,
        "max_output_rows": 100_000,
        "max_scan_rows": 100_000,
        "status": "reduced_to_measured_fail_close_hard_caps",
        "validated_rows": 100_000,
    }
    assert evidence["policy_decision"]["query"][
        "default_max_sync_scan_rows"
    ] == 10_000
    assert evidence["measurements"]["application_query"]["sample_count"] == 9
    assert evidence["measurements"]["desktop_bridge_query"]["sample_count"] == 9
    assert evidence["measurements"]["persistent_warm_filter_sort"][
        "sample_count"
    ] == 9
    assert evidence["recovery"]["cancel"]["state"] == "cancelled"
    assert evidence["artifacts"]["raw"]["file_count"] == 100_000
    assert evidence["artifacts"]["final_work_root"]["file_count"] >= 100_000

    sample_artifact = evidence["sample_artifact"]
    assert sample_artifact["bytes"] == SAMPLES_PATH.stat().st_size
    assert sample_artifact["sha256"] == hashlib.sha256(
        SAMPLES_PATH.read_bytes()
    ).hexdigest()
    samples = pq.read_table(SAMPLES_PATH).to_pylist()
    assert sample_artifact["row_count"] == len(samples) == 68
    assert all(
        item["schema_version"] == ANALYTICS_SCALE_SAMPLE_SCHEMA_VERSION
        for item in samples
    )


def test_full_scale_workflow_is_manual_self_hosted_and_uses_contract_defaults() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "runs-on: [self-hosted, Windows, X64]" in workflow
    assert 'default: "100000"' in workflow
    assert 'default: "1000000"' in workflow
    assert 'python -m pip install -e ".[analytics]"' in workflow
    assert "ygo_effect_dsl.spikes.analytics_scale_calibration" in workflow
    assert "actions/upload-artifact@v7" in workflow
