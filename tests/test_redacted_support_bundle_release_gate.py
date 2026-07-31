from __future__ import annotations

import argparse
from pathlib import Path

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_redacted_support_bundle
from ygo_effect_dsl.spikes.redacted_support_bundle_release_gate import (
    REQUIRED_MATRIX_ROWS,
    V1_REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION,
    evaluate_v1_redacted_support_bundle,
    read_v1_redacted_support_bundle,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_redacted_support_bundle.json"
)


def test_v1_redacted_support_bundle_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_redacted_support_bundle(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION
    assert evidence["issue"] == 360
    assert evidence["passed"] is True
    assert evidence["evidence_id"].startswith("v1supportbundle_")
    assert tuple(row["id"] for row in evidence["matrix"]) == REQUIRED_MATRIX_ROWS
    assert all(check["passed"] is True for check in checks.values())
    assert evidence["policy"]["automatic_upload"] is False


def test_committed_v1_redacted_support_bundle_matches_current_checkout() -> None:
    assert read_v1_redacted_support_bundle(
        EVIDENCE_PATH
    ) == evaluate_v1_redacted_support_bundle(REPO_ROOT)


def test_v1_redacted_support_bundle_cli_writes_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "v1-redacted-support-bundle.json"

    status = cmd_v1_redacted_support_bundle(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-redacted-support-bundle: passed" in captured.out
    assert read_v1_redacted_support_bundle(output) == evaluate_v1_redacted_support_bundle(
        REPO_ROOT
    )
