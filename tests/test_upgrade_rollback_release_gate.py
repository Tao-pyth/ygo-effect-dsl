from __future__ import annotations

import argparse
from pathlib import Path

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_upgrade_rollback
from ygo_effect_dsl.spikes.upgrade_rollback_release_gate import (
    REQUIRED_MATRIX_ROWS,
    V1_UPGRADE_ROLLBACK_SCHEMA_VERSION,
    evaluate_v1_upgrade_rollback,
    read_v1_upgrade_rollback,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_upgrade_rollback.json"
)


def test_v1_upgrade_rollback_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_upgrade_rollback(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_UPGRADE_ROLLBACK_SCHEMA_VERSION
    assert evidence["issue"] == 172
    assert evidence["passed"] is True
    assert tuple(row["id"] for row in evidence["matrix"]) == REQUIRED_MATRIX_ROWS
    assert set(checks) == {
        "ci_smokes_clean_wheel_and_windows_executable_without_editable_install",
        "external_assets_remain_owned_cache_not_bundled",
        "parent_worker_subprocess_import_source_consistency_tested",
        "portable_package_has_manual_upgrade_and_rollback",
        "upgrade_rollback_matrix_documented",
    }
    assert all(check["passed"] is True for check in checks.values())
    assert evidence["release_policy"]["editable_install_dependency"] is False
    assert evidence["release_policy"]["external_assets_bundled"] is False


def test_committed_v1_upgrade_rollback_matches_current_checkout() -> None:
    assert read_v1_upgrade_rollback(EVIDENCE_PATH) == evaluate_v1_upgrade_rollback(
        REPO_ROOT
    )


def test_v1_upgrade_rollback_cli_writes_evidence(tmp_path: Path, capsys) -> None:
    output = tmp_path / "v1-upgrade-rollback.json"

    status = cmd_v1_upgrade_rollback(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-upgrade-rollback: passed" in captured.out
    assert read_v1_upgrade_rollback(output) == evaluate_v1_upgrade_rollback(REPO_ROOT)


def test_windows_portable_readme_keeps_user_data_outside_package() -> None:
    readme = (
        REPO_ROOT / "packaging" / "windows-portable" / "README.txt"
    ).read_text(encoding="utf-8")

    assert "Do not extract over a previous package directory" in readme
    assert "User data, external assets, caches, logs, and evidence" in readme
    assert "pre-migration backup and explicit confirmation" in readme
    assert "owned cache resolver" in readme
