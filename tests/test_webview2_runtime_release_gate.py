from __future__ import annotations

import argparse
from pathlib import Path

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_webview2_runtime
from ygo_effect_dsl.desktop.shell import MINIMUM_WEBVIEW2_RUNTIME_VERSION
from ygo_effect_dsl.spikes.webview2_runtime_release_gate import (
    V1_WEBVIEW2_RUNTIME_SCHEMA_VERSION,
    evaluate_v1_webview2_runtime,
    read_v1_webview2_runtime,
    write_v1_webview2_runtime,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_webview2_runtime.json"
)


def test_v1_webview2_runtime_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_webview2_runtime(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_WEBVIEW2_RUNTIME_SCHEMA_VERSION
    assert evidence["issue"] == 357
    assert evidence["passed"] is True
    assert evidence["policy"]["minimum_supported_version"] == (
        MINIMUM_WEBVIEW2_RUNTIME_VERSION
    )
    assert evidence["policy"]["silent_download_or_install"] is False
    assert set(checks) == {
        "compatibility_policy_records_user_guidance",
        "desktop_preflight_blocks_before_bridge_or_worker",
        "smoke_tests_cover_runtime_failure_modes",
        "windows_package_smokes_preflight_before_bridge",
    }
    assert all(check["passed"] is True for check in checks.values())


def test_committed_v1_webview2_runtime_matches_current_checkout() -> None:
    assert read_v1_webview2_runtime(EVIDENCE_PATH) == evaluate_v1_webview2_runtime(
        REPO_ROOT
    )


def test_v1_webview2_runtime_cli_writes_content_addressed_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "webview2-runtime.json"

    status = cmd_v1_webview2_runtime(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-webview2-runtime: passed" in captured.out
    assert read_v1_webview2_runtime(output)["passed"] is True


def test_v1_webview2_runtime_writer_round_trips(tmp_path: Path) -> None:
    output = tmp_path / "webview2-runtime.json"

    evidence = write_v1_webview2_runtime(REPO_ROOT, output_path=output)

    assert read_v1_webview2_runtime(output) == evidence
