from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.windows_desktop_shell_evidence import (
    WINDOWS_DESKTOP_SHELL_EVIDENCE_SCHEMA_VERSION,
    build_windows_desktop_shell_evidence,
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
    assert decision["desktop_integration"]["single_instance"] == (
        "required_for_single_writer_catalog"
    )
    assert decision["desktop_integration"]["file_picker"] == (
        "native_select_then_python_path_validation"
    )
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


def test_electron_preflight_requires_both_node_and_npm() -> None:
    checked = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    host = deepcopy(checked["host"])
    host["toolchains"]["node"] = "C:/Program Files/nodejs/node.exe"
    host["toolchains"]["npm"] = None

    evidence = build_windows_desktop_shell_evidence(
        host=host,
        pywebview_live=checked["candidates"]["pywebview"]["live_probe"],
        package_downloads={
            "pyside6": checked["candidates"]["pyside6"]["package_download"],
            "pywebview": checked["candidates"]["pywebview"]["package_download"],
        },
    )

    assert evidence["candidates"]["electron"]["host_gate"] == (
        "missing_node_and_npm"
    )
