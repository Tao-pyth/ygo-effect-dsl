from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.windows_desktop_shell_evidence import (
    WINDOWS_DESKTOP_SHELL_EVIDENCE_SCHEMA_VERSION,
    desktop_shell_decision,
    official_references,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "adr" / "evidence" / "0181_windows_desktop_shell.json"
)


def test_desktop_shell_keeps_rules_and_authority_out_of_renderer() -> None:
    decision = desktop_shell_decision()

    assert decision["selected_shell"] == "pywebview_webview2"
    assert decision["process_boundary"]["rule_execution"] == (
        "existing_ocgcore_worker_subprocesses"
    )
    assert decision["process_boundary"]["renderer_api"] == (
        "allowlisted_async_js_bridge"
    )
    assert decision["security"]["local_rest_api"] is False
    assert decision["security"]["remote_content"] is False
    assert decision["distribution"]["third_party_card_assets"] == (
        "never_bundle_before_license_review"
    )


def test_official_reference_set_covers_every_candidate_boundary() -> None:
    references = official_references()

    assert set(references) == {
        "electron_process_model",
        "electron_security",
        "pyside_deployment",
        "pywebview_architecture",
        "pywebview_bridge",
        "pywebview_security",
        "tauri_prerequisites",
        "tauri_sidecar",
        "webview2_distribution",
    }
    assert all(value.startswith("https://") for value in references.values())


def test_checked_shell_evidence_matches_decision_and_content_id() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == (
        WINDOWS_DESKTOP_SHELL_EVIDENCE_SCHEMA_VERSION
    )
    assert evidence["decision"] == desktop_shell_decision()
    assert evidence["references"] == official_references()
    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="desktopshellevidence_",
    )

    candidates = evidence["candidates"]
    assert candidates["pywebview"]["decision"] == "selected"
    assert candidates["pywebview"]["host_gate"] == "passed"
    assert candidates["pywebview"]["live_probe"]["loaded"] is True
    assert candidates["tauri"]["decision"] == "rollback_candidate"
    assert candidates["electron"]["decision"] == "not_selected"
    assert candidates["pyside6"]["package_download"]["download_bytes"] > (
        candidates["pywebview"]["package_download"]["download_bytes"]
    )
