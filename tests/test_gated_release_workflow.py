from __future__ import annotations

import argparse
from pathlib import Path

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_gated_release
from ygo_effect_dsl.spikes.gated_release_workflow_gate import (
    V1_GATED_RELEASE_SCHEMA_VERSION,
    evaluate_v1_gated_release,
    read_v1_gated_release,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_gated_release.json"
)


def test_v1_gated_release_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_gated_release(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_GATED_RELEASE_SCHEMA_VERSION
    assert evidence["issue"] == 173
    assert evidence["passed"] is True
    assert set(checks) == {
        "failed_publish_yank_and_rollback_runbook_exists",
        "gated_release_workflow_blocks_public_publish_until_gates_pass",
        "github_actions_runtime_and_pinning_policy_current",
        "signed_tag_and_release_policy_documented",
        "tests_cover_gated_release_workflow",
    }
    assert all(check["passed"] is True for check in checks.values())
    assert evidence["release_policy"]["default_public_publish"] is False


def test_committed_v1_gated_release_matches_current_checkout() -> None:
    assert read_v1_gated_release(EVIDENCE_PATH) == evaluate_v1_gated_release(REPO_ROOT)


def test_gated_release_workflow_defaults_to_dry_run() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "gated-release.yml").read_text(
        encoding="utf-8"
    )

    assert "default: 1.0.0-dry-run" in workflow
    assert "default: \"true\"" in workflow
    assert "environment: v1-production-release" in workflow
    assert "production-distribution-gate" in workflow
    assert "git tag -v" in workflow
    assert "gh release create" in workflow
    assert "--draft" in workflow


def test_v1_gated_release_cli_writes_evidence(tmp_path: Path, capsys) -> None:
    output = tmp_path / "v1-gated-release.json"

    status = cmd_v1_gated_release(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-gated-release: passed" in captured.out
    assert read_v1_gated_release(output) == evaluate_v1_gated_release(REPO_ROOT)
