from __future__ import annotations

import json
from pathlib import Path

import pytest

from ygo_effect_dsl.desktop.bridge import DESKTOP_BRIDGE_CONTRACT_VERSION, DesktopBridge
from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.desktop.settings import (
    DESKTOP_SETTINGS_SCHEMA_VERSION,
    DesktopSettingsStore,
    default_desktop_settings,
    validate_desktop_settings,
)
from ygo_effect_dsl.desktop.shell import DesktopStartupError, configured_external_root
from ygo_effect_dsl.spikes.desktop_settings_release_gate import (
    V1_DESKTOP_SETTINGS_SCHEMA_VERSION,
    evaluate_v1_desktop_settings,
    read_v1_desktop_settings,
    write_v1_desktop_settings,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_desktop_settings.json"
)


def _request(method: str, payload: dict) -> dict:
    return {
        "method": method,
        "payload": payload,
        "request_id": "settings-test",
        "version": DESKTOP_BRIDGE_CONTRACT_VERSION,
    }


def test_desktop_settings_defaults_are_versioned_and_redacted() -> None:
    settings = default_desktop_settings()

    assert settings["schema_version"] == DESKTOP_SETTINGS_SCHEMA_VERSION
    assert settings["external_asset_root"] is None
    assert settings["privacy"] == {
        "include_local_paths_in_support_bundle": False,
        "redact_card_names": True,
        "redact_user_text": True,
    }
    assert settings["updates"] == {
        "automatic_downloads": False,
        "channel": "manual",
    }
    assert validate_desktop_settings(settings) == settings


def test_desktop_settings_persist_with_atomic_versioned_file(tmp_path: Path) -> None:
    store = DesktopSettingsStore(tmp_path / "desktop-settings.json")
    settings = default_desktop_settings(external_asset_root=tmp_path / "external")
    settings["storage"]["retention_days"] = 90
    settings["display"]["density"] = "comfortable"

    written = store.write(settings)

    assert store.read() == written
    assert json.loads(store.path.read_text(encoding="utf-8")) == written
    assert not list(tmp_path.glob(".desktop-settings.json.*.tmp"))


def test_desktop_settings_reject_unknown_schema_and_invalid_values(
    tmp_path: Path,
) -> None:
    store = DesktopSettingsStore(tmp_path / "desktop-settings.json")
    store.path.write_text(
        json.dumps(
            {
                **default_desktop_settings(),
                "schema_version": "desktop-settings-v0",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version"):
        store.read()

    invalid = default_desktop_settings()
    invalid["updates"]["automatic_downloads"] = True
    with pytest.raises(ValueError, match="自動ダウンロード"):
        validate_desktop_settings(invalid)


def test_desktop_settings_reset_can_enter_safe_mode(tmp_path: Path) -> None:
    store = DesktopSettingsStore(tmp_path / "desktop-settings.json")
    store.write(default_desktop_settings(external_asset_root=tmp_path / "external"))

    reset = store.reset(safe_mode=True)

    assert reset["external_asset_root"] is None
    assert reset["recovery"]["safe_mode"] is True


def test_desktop_service_settings_bridge_round_trips_and_reports_environment(
    tmp_path: Path,
) -> None:
    blocked_status = {
        "asset_lock_id": "asset-lock",
        "checks": [],
        "core_lock_id": "core-lock",
        "dependent_features": {
            "card_names": "blocked",
            "deck_card_options": "blocked",
            "search_jobs": "blocked",
        },
        "external_root": str(tmp_path / "external"),
        "guidance": {"commands": ["python -m ygo_effect_dsl ocgcore-assets-verify"]},
        "ready": False,
        "schema_version": "external-asset-setup-status-v1",
    }
    service = DesktopApplicationService(
        tmp_path,
        external_asset_status=lambda *, external_root=None: blocked_status,
    )
    bridge = DesktopBridge(service.handlers())

    initial = bridge.invoke(_request("settings.get", {}))
    settings = initial["result"]["settings"]
    settings["external_asset_root"] = str(tmp_path / "external")
    settings["storage"]["cache_limit_mb"] = 1024
    updated = bridge.invoke(_request("settings.update", {"settings": settings}))
    reset = bridge.invoke(_request("settings.reset", {"safe_mode": True}))

    assert initial["ok"] is True
    assert initial["result"]["external_assets"] == blocked_status
    assert initial["result"]["storage_locations"]["settings_file"].endswith(
        "desktop-settings.json"
    )
    assert updated["ok"] is True
    assert updated["result"]["settings"]["storage"]["cache_limit_mb"] == 1024
    assert reset["ok"] is True
    assert reset["result"]["settings"]["recovery"]["safe_mode"] is True


def test_invalid_desktop_settings_fail_closed_before_search_worker(
    tmp_path: Path,
) -> None:
    (tmp_path / "desktop-settings.json").write_text("{broken json", encoding="utf-8")
    service = DesktopApplicationService(tmp_path)
    bridge = DesktopBridge(service.handlers())

    response = bridge.invoke(_request("settings.get", {}))

    assert response["ok"] is False
    assert response["diagnostics"][0]["code"] == "desktop_settings_invalid"
    assert "デスクトップ設定ファイルが不正です" in response["diagnostics"][0]["message"]


def test_desktop_shell_uses_persisted_external_root_and_rejects_bad_config(
    tmp_path: Path,
) -> None:
    configured = tmp_path / "external"
    DesktopSettingsStore(tmp_path / "desktop-settings.json").write(
        default_desktop_settings(external_asset_root=configured)
    )

    assert configured_external_root(tmp_path) == configured.resolve()
    assert configured_external_root(tmp_path, override=tmp_path / "override") == (
        tmp_path / "override"
    ).resolve()

    (tmp_path / "desktop-settings.json").write_text("{broken json", encoding="utf-8")
    with pytest.raises(DesktopStartupError) as failure:
        configured_external_root(tmp_path)
    assert failure.value.code == "desktop_settings_invalid"


def test_desktop_settings_ui_and_bridge_contract_are_reachable() -> None:
    index = (REPO_ROOT / "src/ygo_effect_dsl/desktop/static/index.html").read_text(
        encoding="utf-8"
    )
    app = (REPO_ROOT / "src/ygo_effect_dsl/desktop/static/app.js").read_text(
        encoding="utf-8"
    )
    bridge = (REPO_ROOT / "src/ygo_effect_dsl/desktop/static/bridge.js").read_text(
        encoding="utf-8"
    )
    contract = json.loads(
        (REPO_ROOT / "src/ygo_effect_dsl/resources/desktop-bridge-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert 'data-view="settings"' in index
    assert 'id="settings-pane"' in index
    assert "settings.get" in bridge
    assert "settings.update" in app
    assert "settings.reset" in app
    assert contract["methods"]["settings.get"]["worker_start_allowed"] is False
    assert contract["methods"]["settings.update"]["source"] == (
        "versioned_desktop_settings"
    )


def test_v1_desktop_settings_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_desktop_settings(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_DESKTOP_SETTINGS_SCHEMA_VERSION
    assert evidence["issue"] == 361
    assert evidence["passed"] is True
    assert set(checks) == {
        "packaged_desktop_smoke_includes_static_settings_ui",
        "settings_bridge_fails_closed_before_workers",
        "settings_ui_reachable_from_desktop_app",
        "tests_cover_settings_defaults_persistence_and_recovery",
        "versioned_settings_store_validates_and_writes_atomically",
    }
    assert all(check["passed"] is True for check in checks.values())


def test_committed_v1_desktop_settings_matches_current_checkout() -> None:
    assert read_v1_desktop_settings(EVIDENCE_PATH) == evaluate_v1_desktop_settings(
        REPO_ROOT
    )


def test_v1_desktop_settings_writer_round_trips(tmp_path: Path) -> None:
    output = tmp_path / "desktop-settings.json"

    evidence = write_v1_desktop_settings(REPO_ROOT, output_path=output)

    assert read_v1_desktop_settings(output) == evidence
