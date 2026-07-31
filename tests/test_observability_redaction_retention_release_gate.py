from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from ygo_effect_dsl.cli.cmd_qualification import (
    cmd_v1_observability_redaction_retention,
)
from ygo_effect_dsl.engine.information import (
    InformationCanary,
    InformationCanaryRegistry,
    audit_information_artifact,
)
from ygo_effect_dsl.spikes.observability_redaction_retention_release_gate import (
    REQUIRED_MATRIX_ROWS,
    V1_OBSERVABILITY_REDACTION_RETENTION_SCHEMA_VERSION,
    evaluate_v1_observability_redaction_retention,
    read_v1_observability_redaction_retention,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT
    / "docs"
    / "release"
    / "evidence"
    / "v1_0_0_observability_redaction_retention.json"
)
PRIVATE_CANARY = "private-hidden-payload-canary-175"


def _registry(artifact_kind: str = "support_report") -> InformationCanaryRegistry:
    return InformationCanaryRegistry(
        artifact_kind=artifact_kind,
        viewer=0,
        canaries=(
            InformationCanary(
                canary_id="canary_v1_observability_private",
                classification="hidden_payload",
                matcher_kind="substring",
                source_path="worker.stdout",
                value=PRIVATE_CANARY,
            ),
        ),
    )


def test_v1_observability_redaction_retention_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_observability_redaction_retention(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_OBSERVABILITY_REDACTION_RETENTION_SCHEMA_VERSION
    assert evidence["issue"] == 175
    assert evidence["passed"] is True
    assert evidence["evidence_id"].startswith("v1obsredactretention_")
    assert tuple(row["id"] for row in evidence["matrix"]) == REQUIRED_MATRIX_ROWS
    assert all(check["passed"] is True for check in checks.values())
    assert evidence["policy"]["crash_dumps_default"] == "disabled"


def test_committed_v1_observability_redaction_retention_matches_current_checkout() -> None:
    assert read_v1_observability_redaction_retention(
        EVIDENCE_PATH
    ) == evaluate_v1_observability_redaction_retention(REPO_ROOT)


def test_v1_observability_redaction_retention_cli_writes_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "v1-observability-redaction-retention.json"

    status = cmd_v1_observability_redaction_retention(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-observability-redaction-retention: passed" in captured.out
    assert read_v1_observability_redaction_retention(
        output
    ) == evaluate_v1_observability_redaction_retention(REPO_ROOT)


def test_v1_observability_matrix_records_expected_boundaries() -> None:
    evidence = evaluate_v1_observability_redaction_retention(REPO_ROOT)
    matrix = {row["id"]: row for row in evidence["matrix"]}

    assert matrix["structured_observability_records"]["status"] == "verified"
    assert matrix["raw_hidden_payload_default_off"][
        "raw_payload_retained_by_default"
    ] is False
    assert matrix["worker_crash_safe_failure_report"][
        "raw_payload_retained_by_default"
    ] is False


def test_raw_hidden_payload_is_rejected_by_information_audit() -> None:
    artifact = {
        "diagnostic_code": "worker_crash",
        "raw_hidden_payload": PRIVATE_CANARY,
        "schema_version": "support-report-v1",
        "status": "failed",
    }

    report = audit_information_artifact(
        artifact,
        artifact_kind="support_report",
        registry=_registry(),
    )

    assert report["status"] == "failed"
    assert {
        finding["rule"] for finding in report["findings"]
    } == {"forbidden_field_name", "private_canary_match"}
    assert PRIVATE_CANARY not in json.dumps(report, sort_keys=True)
