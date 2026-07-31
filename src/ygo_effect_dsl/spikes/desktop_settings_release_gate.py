from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_DESKTOP_SETTINGS_SCHEMA_VERSION = "v1-desktop-settings-v1"


def _contains_all(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value not in text]


def evaluate_v1_desktop_settings(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _settings_store_check(
            root / "src" / "ygo_effect_dsl" / "desktop" / "settings.py",
            evidence="src/ygo_effect_dsl/desktop/settings.py",
        ),
        _desktop_bridge_check(root),
        _frontend_check(root),
        _test_coverage_check(
            root / "tests" / "test_desktop_settings.py",
            evidence="tests/test_desktop_settings.py",
        ),
        _packaged_smoke_check(
            root / ".github" / "workflows" / "build-windows-exe.yml",
            evidence=".github/workflows/build-windows-exe.yml",
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 361,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "release_policy": {
                "automatic_downloads": False,
                "settings_file": "desktop-settings.json",
                "update_channel": "manual",
                "worker_start_allowed_from_settings": False,
            },
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_DESKTOP_SETTINGS_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1desktopsettings_"),
    }


def _settings_store_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("versioned_settings_store_validates_and_writes_atomically", evidence)
    if not path.exists():
        check["reason"] = "missing_source"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "DESKTOP_SETTINGS_SCHEMA_VERSION",
            "DesktopSettingsStore",
            "validate_desktop_settings",
            "atomic_write_text",
            "schema_version",
            "safe_mode",
            "automatic_downloads",
            "v1.0.0ではmanual",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _desktop_bridge_check(root: Path) -> dict[str, Any]:
    check = _check(
        "settings_bridge_fails_closed_before_workers",
        "src/ygo_effect_dsl/desktop/service.py",
    )
    service = (root / "src" / "ygo_effect_dsl" / "desktop" / "service.py").read_text(
        encoding="utf-8"
    )
    shell = (root / "src" / "ygo_effect_dsl" / "desktop" / "shell.py").read_text(
        encoding="utf-8"
    )
    bridge = (
        root / "src" / "ygo_effect_dsl" / "resources" / "desktop-bridge-v1.json"
    ).read_text(encoding="utf-8")
    combined = "\n".join((service, shell, bridge))
    missing = _contains_all(
        combined,
        (
            "settings.get",
            "settings.update",
            "settings.reset",
            "versioned_desktop_settings",
            "desktop_settings_invalid",
            "デスクトップ設定ファイルが不正です",
            "worker_start_allowed",
            "configured_external_root",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _frontend_check(root: Path) -> dict[str, Any]:
    check = _check(
        "settings_ui_reachable_from_desktop_app",
        "src/ygo_effect_dsl/desktop/static/index.html",
    )
    index = (root / "src" / "ygo_effect_dsl" / "desktop" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "src" / "ygo_effect_dsl" / "desktop" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    bridge = (root / "src" / "ygo_effect_dsl" / "desktop" / "static" / "bridge.js").read_text(
        encoding="utf-8"
    )
    missing = _contains_all(
        "\n".join((index, app, bridge)),
        (
            'data-view="settings"',
            'id="settings-pane"',
            "settings.get",
            "settings.update",
            "settings.reset",
            "外部資産root",
            "safe-mode reset",
            "redact",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _test_coverage_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("tests_cover_settings_defaults_persistence_and_recovery", evidence)
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "test_desktop_settings_defaults_are_versioned_and_redacted",
            "test_desktop_settings_persist_with_atomic_versioned_file",
            "test_desktop_settings_reject_unknown_schema_and_invalid_values",
            "test_desktop_settings_reset_can_enter_safe_mode",
            "test_invalid_desktop_settings_fail_closed_before_search_worker",
            "test_desktop_settings_ui_and_bridge_contract_are_reachable",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _packaged_smoke_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("packaged_desktop_smoke_includes_static_settings_ui", evidence)
    if not path.exists():
        check["reason"] = "missing_workflow"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "ygo-effect-dsl-desktop",
            "--bridge-smoke-out",
            "src/ygo_effect_dsl/desktop/static;ygo_effect_dsl/desktop/static",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "workflow_smoke_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _check(check_id: str, evidence: str) -> dict[str, Any]:
    return {
        "evidence": evidence,
        "id": check_id,
        "passed": False,
        "reason": "not_evaluated",
    }


def validate_v1_desktop_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 desktop settings evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 desktop settings evidence must be an object")
    if document.get("schema_version") != V1_DESKTOP_SETTINGS_SCHEMA_VERSION:
        raise ValueError("unsupported v1 desktop settings schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1desktopsettings_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 desktop settings evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 desktop settings checks must be a list")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 desktop settings rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 desktop settings passed is inconsistent")
    return document


def read_v1_desktop_settings(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_desktop_settings(value)


def write_v1_desktop_settings(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_desktop_settings(repo_root)
    validate_v1_desktop_settings(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
