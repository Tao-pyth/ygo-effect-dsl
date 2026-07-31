from __future__ import annotations

import argparse
from pathlib import Path

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_installer_packaging
from ygo_effect_dsl.spikes.windows_installer_packaging import (
    V1_INSTALLER_PACKAGING_SCHEMA_VERSION,
    evaluate_v1_installer_packaging,
    read_v1_installer_packaging,
    write_v1_installer_packaging,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_installer_packaging.json"
)


def test_v1_installer_packaging_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_installer_packaging(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_INSTALLER_PACKAGING_SCHEMA_VERSION
    assert evidence["issue"] == 355
    assert evidence["passed"] is True
    assert evidence["artifact"] == {
        "archive_name": "ygo-effect-dsl-win64-portable.zip",
        "format": "portable_zip",
        "top_level_directory": "ygo-effect-dsl-win64",
    }
    assert evidence["distribution_boundary"] == {
        "admin_required": False,
        "auto_update": "not_included",
        "machine_wide_install": False,
        "public_release_blocked_until_parent_gate": True,
        "webview2_runtime_bundled": False,
    }
    assert set(checks) == {
        "ci_builds_and_smokes_portable_zip",
        "package_readme_records_install_uninstall_steps",
        "packaging_adr_records_operational_contract",
    }
    assert all(check["passed"] is True for check in checks.values())


def test_committed_v1_installer_packaging_matches_current_checkout() -> None:
    assert read_v1_installer_packaging(EVIDENCE_PATH) == evaluate_v1_installer_packaging(
        REPO_ROOT
    )


def test_v1_installer_packaging_cli_writes_content_addressed_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "installer-packaging.json"

    status = cmd_v1_installer_packaging(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-installer-packaging: passed" in captured.out
    assert read_v1_installer_packaging(output)["passed"] is True


def test_v1_installer_packaging_writer_round_trips(tmp_path: Path) -> None:
    output = tmp_path / "installer-packaging.json"

    evidence = write_v1_installer_packaging(REPO_ROOT, output_path=output)

    assert read_v1_installer_packaging(output) == evidence
