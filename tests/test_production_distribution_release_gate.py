from __future__ import annotations

import argparse
import json
from pathlib import Path

from ygo_effect_dsl.cli.cmd_qualification import cmd_production_distribution_gate
from ygo_effect_dsl.spikes.production_distribution_release_gate import (
    PRODUCTION_DISTRIBUTION_RELEASE_GATE_SCHEMA_VERSION,
    evaluate_production_distribution_release_gate,
    read_production_distribution_release_gate,
    validate_production_distribution_release_gate,
    write_production_distribution_release_gate,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "production_distribution_release_gate.json"
)


def test_current_production_distribution_gate_fails_closed_until_v1_evidence_exists() -> None:
    evidence = evaluate_production_distribution_release_gate(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == PRODUCTION_DISTRIBUTION_RELEASE_GATE_SCHEMA_VERSION
    assert evidence["issue"] == 359
    assert evidence["passed"] is False
    assert evidence["evidence_id"].startswith("productiondistgate_")
    assert checks["sbom_present"]["passed"] is True
    assert checks["third_party_payload_allowlist_default_deny"]["passed"] is True
    assert checks["release_artifact_composition_references_exist"]["passed"] is True
    assert checks["windows_gui_executable_workflow_smoke"]["passed"] is True
    assert checks["root_project_license_approved"]["reason"] == "approval_not_recorded"
    assert checks["support_matrix_supported_rows_verified"]["reason"] == (
        "supported_rows_not_verified"
    )
    assert checks["authenticode_signing_verified"]["reason"] == "missing_evidence"
    assert any(
        reason.startswith("authenticode_signing_verified:")
        for reason in evidence["rejection_reasons"]
    )
    validate_production_distribution_release_gate(evidence)


def test_production_distribution_gate_writes_content_addressed_json(tmp_path: Path) -> None:
    output = tmp_path / "production-distribution-gate.json"

    evidence = write_production_distribution_release_gate(
        REPO_ROOT,
        output_path=output,
    )

    assert read_production_distribution_release_gate(output) == evidence


def test_committed_production_distribution_gate_matches_current_checkout() -> None:
    assert read_production_distribution_release_gate(
        EVIDENCE_PATH
    ) == evaluate_production_distribution_release_gate(REPO_ROOT)


def test_production_distribution_gate_rejects_placeholder_pass_values(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "docs" / "release" / "evidence"
    workflow_dir = tmp_path / ".github" / "workflows"
    evidence_dir.mkdir(parents=True)
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "build-windows-exe.yml").write_text(
        "\n".join(
            [
                "name: Build Windows exe",
                "run: ygo-effect-dsl-desktop --preflight-only --diagnostics-out",
                "run: --bridge-smoke-out",
                "run: src/ygo_effect_dsl/desktop/static;ygo_effect_dsl/desktop/static",
            ]
        ),
        encoding="utf-8",
    )
    _write_json(
        evidence_dir / "v1_0_0_support_matrix.json",
        {
            "matrix": [
                {
                    "evidence_state": "verified",
                    "id": "windows",
                    "support_level": "supported",
                }
            ],
            "schema_version": "v1-support-matrix-v1",
        },
    )
    _write_json(
        evidence_dir / "project_license_approval_status.json",
        {
            "approval_state": "approved",
            "package_metadata": {"license_expression": "MIT"},
            "project_license": {"spdx": "MIT"},
            "public_distribution": "allowed",
            "schema_version": "project-license-approval-status-v1",
        },
    )
    _write_json(evidence_dir / "v1_0_0_sbom.json", {"schema_version": "v1-sbom-v1"})
    _write_json(
        evidence_dir / "v1_0_0_asset_allowlist.json",
        {
            "default_action": "reject",
            "external_local_only_assets": [],
            "release_artifact_allowed_third_party_payloads": [],
            "schema_version": "v1-asset-allowlist-v1",
        },
    )
    (evidence_dir / "v1_0_0_third_party_notices.md").write_text(
        "notices",
        encoding="utf-8",
    )
    _write_json(
        evidence_dir / "v1_0_0_release_artifact_composition.json",
        {
            "artifacts": [
                {
                    "artifact_kind": "wheel",
                    "asset_allowlist": "docs/release/evidence/v1_0_0_asset_allowlist.json",
                    "notice": "docs/release/evidence/v1_0_0_third_party_notices.md",
                    "release_audit_required": True,
                    "sbom": "docs/release/evidence/v1_0_0_sbom.json",
                    "third_party_payload_policy": "none_allowed",
                }
            ],
            "schema_version": "v1-release-artifact-composition-v1",
        },
    )
    _write_json(
        evidence_dir / "v1_0_0_authenticode_signing.json",
        {"passed": "TODO", "schema_version": "v1-authenticode-signing-v1"},
    )

    evidence = evaluate_production_distribution_release_gate(tmp_path)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert checks["authenticode_signing_verified"]["reason"] == "placeholder_pass_value"
    assert "authenticode_signing_verified:placeholder_pass_value" in (
        evidence["rejection_reasons"]
    )


def test_production_distribution_gate_cli_can_dry_run_failed_gate(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "gate.json"

    status = cmd_production_distribution_gate(
        argparse.Namespace(
            allow_failed=True,
            evidence_dir=Path("docs/release/evidence"),
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "production-distribution-gate: failed" in captured.out
    assert read_production_distribution_release_gate(output)["passed"] is False


def test_ci_dry_runs_production_distribution_gate() -> None:
    test_workflow = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(
        encoding="utf-8"
    )
    windows_workflow = (
        REPO_ROOT / ".github" / "workflows" / "build-windows-exe.yml"
    ).read_text(encoding="utf-8")

    assert "production-distribution-gate" in test_workflow
    assert "production-distribution-gate" in windows_workflow
    assert "--allow-failed" in test_workflow
    assert "--allow-failed" in windows_workflow


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
