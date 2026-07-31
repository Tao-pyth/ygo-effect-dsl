from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_docs_support_guides
from ygo_effect_dsl.spikes.docs_support_guides_release_gate import (
    REQUIRED_MATRIX_ROWS,
    V1_DOCS_SUPPORT_GUIDES_SCHEMA_VERSION,
    evaluate_v1_docs_support_guides,
    read_v1_docs_support_guides,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_docs_support_guides.json"
)


def test_v1_docs_support_guides_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_docs_support_guides(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_DOCS_SUPPORT_GUIDES_SCHEMA_VERSION
    assert evidence["issue"] == 176
    assert evidence["passed"] is True
    assert evidence["evidence_id"].startswith("v1docssupport_")
    assert tuple(row["id"] for row in evidence["matrix"]) == REQUIRED_MATRIX_ROWS
    assert all(check["passed"] is True for check in checks.values())
    assert evidence["policy"][
        "destructive_operation_requires_backup_confirmation"
    ] is True
    assert evidence["exercise_evidence"]["restore_drill"]["status"] == "covered_by_test"


def test_committed_v1_docs_support_guides_matches_current_checkout() -> None:
    assert read_v1_docs_support_guides(
        EVIDENCE_PATH
    ) == evaluate_v1_docs_support_guides(REPO_ROOT)


def test_v1_docs_support_guides_cli_writes_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "v1-docs-support-guides.json"

    status = cmd_v1_docs_support_guides(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-docs-support-guides: passed" in captured.out
    assert read_v1_docs_support_guides(output) == evaluate_v1_docs_support_guides(
        REPO_ROOT
    )


def test_v1_docs_support_guides_rejects_incomplete_runbook(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    support = docs / "support"
    release = docs / "release"
    tests = tmp_path / "tests"
    support.mkdir(parents=True)
    release.mkdir(parents=True)
    tests.mkdir(parents=True)
    (support / "20_incident_rollback_backup_dr.md").write_text(
        "# incomplete\nDetection only\n",
        encoding="utf-8",
    )
    (release / "40_failed_publish_yank_rollback.md").write_text(
        "Draft release rollback\nPublic release yank\nRollback\n"
        "pre-migration backup\nartifact checksums\nsigned tag\n",
        encoding="utf-8",
    )
    (support / "10_redacted_support_bundle.md").write_text(
        "local diagnostic bundle\nredaction report\nretention policy\n"
        "Do not automatically upload\ncanary tests\n",
        encoding="utf-8",
    )
    (tests / "test_docs_support_guides_release_gate.py").write_text(
        "test_v1_docs_support_guides_evidence_passes_current_contract\n"
        "test_committed_v1_docs_support_guides_matches_current_checkout\n"
        "test_v1_docs_support_guides_cli_writes_evidence\n"
        "test_v1_docs_support_guides_rejects_incomplete_runbook\n",
        encoding="utf-8",
    )

    evidence = evaluate_v1_docs_support_guides(tmp_path)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["passed"] is False
    assert checks["incident_rollback_backup_dr_runbook_documented"]["reason"] == (
        "runbook_terms_missing"
    )


def test_v1_docs_support_guides_tabletop_matrix_covers_issue_scenarios() -> None:
    runbook = (REPO_ROOT / "docs" / "support" / "20_incident_rollback_backup_dr.md").read_text(
        encoding="utf-8"
    )

    for scenario in (
        "bad release",
        "schema migration failure",
        "corpus corruption",
        "worker crash storm",
        "asset upstream disappearance",
        "checksum mismatch",
        "disk exhaustion",
    ):
        assert scenario in runbook
    for operator_step in (
        "Detection",
        "Triage",
        "Containment",
        "Rollback",
        "Restore",
        "Verification",
        "Postmortem",
    ):
        assert operator_step in runbook


def test_v1_docs_support_guides_restore_drill_preserves_original_data(
    tmp_path: Path,
) -> None:
    original_root = tmp_path / "original-data-root"
    backup_root = tmp_path / "backup-data-root"
    drill_root = tmp_path / "restore-drill-copy"
    original_root.mkdir()
    source = original_root / "catalog.json"
    source.write_text('{"schema_version":"catalog-v1","status":"verified"}\n', encoding="utf-8")
    original_digest = source.read_bytes()

    backup_root.mkdir()
    (backup_root / source.name).write_bytes(source.read_bytes())
    drill_root.mkdir()
    copied = drill_root / source.name
    copied.write_bytes(source.read_bytes())
    copied.write_text("corrupted\n", encoding="utf-8")
    copied.write_bytes((backup_root / source.name).read_bytes())

    assert copied.read_bytes() == original_digest
    assert source.read_bytes() == original_digest
