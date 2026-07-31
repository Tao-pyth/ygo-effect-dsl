from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.desktop.shell import (
    MINIMUM_WEBVIEW2_RUNTIME_VERSION,
    WEBVIEW2_RUNTIME_DOWNLOAD_URL,
    webview2_runtime_policy_document,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_WEBVIEW2_RUNTIME_SCHEMA_VERSION = "v1-webview2-runtime-v1"


def _contains_all(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value not in text]


def evaluate_v1_webview2_runtime(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    policy_evidence = "docs/adr/0019_v1_webview2_runtime_policy.md"
    shell_evidence = "src/ygo_effect_dsl/desktop/shell.py"
    test_evidence = "tests/test_desktop_shell.py"
    workflow_evidence = ".github/workflows/build-windows-exe.yml"
    checks = [
        _policy_document_check(root / policy_evidence, evidence=policy_evidence),
        _shell_policy_check(root / shell_evidence, evidence=shell_evidence),
        _test_coverage_check(root / test_evidence, evidence=test_evidence),
        _workflow_preflight_check(root / workflow_evidence, evidence=workflow_evidence),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 357,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "policy": webview2_runtime_policy_document(),
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_WEBVIEW2_RUNTIME_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1webview2runtime_"),
    }


def _policy_document_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = {
        "evidence": evidence,
        "id": "compatibility_policy_records_user_guidance",
        "passed": False,
        "reason": "not_evaluated",
    }
    if not path.exists():
        check["reason"] = "missing_document"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "Microsoft Evergreen WebView2 Runtime",
            "minimum qualified WebView2 Runtime version",
            MINIMUM_WEBVIEW2_RUNTIME_VERSION,
            "missing",
            "outdated",
            "unsupported",
            "user-facing diagnostic",
            "does not silently download",
            WEBVIEW2_RUNTIME_DOWNLOAD_URL,
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _shell_policy_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = {
        "evidence": evidence,
        "id": "desktop_preflight_blocks_before_bridge_or_worker",
        "passed": False,
        "reason": "not_evaluated",
    }
    if not path.exists():
        check["reason"] = "missing_source"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "MINIMUM_WEBVIEW2_RUNTIME_VERSION",
            "WEBVIEW2_RUNTIME_DOWNLOAD_URL",
            "webview2_failure_guidance",
            "webview2_runtime_missing",
            "webview2_runtime_outdated",
            "preflight_desktop_runtime()",
            "start_desktop(data_root=data_root",
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
    check = {
        "evidence": evidence,
        "id": "smoke_tests_cover_runtime_failure_modes",
        "passed": False,
        "reason": "not_evaluated",
    }
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "test_webview2_and_pywebview_preflight_fail_before_window_creation",
            "webview2_runtime_missing",
            "webview2_runtime_outdated",
            "unsupported_platform",
            "test_webview2_failure_guidance_is_user_facing",
            "test_desktop_preflight_only_writes_packaged_diagnostics",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _workflow_preflight_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = {
        "evidence": evidence,
        "id": "windows_package_smokes_preflight_before_bridge",
        "passed": False,
        "reason": "not_evaluated",
    }
    if not path.exists():
        check["reason"] = "missing_workflow"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "--preflight-only --diagnostics-out desktop-preflight.json",
            "--bridge-smoke-out desktop-bridge-smoke.json",
            "--preflight-only --diagnostics-out package-desktop-preflight.json",
            "--bridge-smoke-out package-desktop-bridge-smoke.json",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    if text.index("--preflight-only --diagnostics-out desktop-preflight.json") > text.index(
        "--bridge-smoke-out desktop-bridge-smoke.json"
    ):
        check["reason"] = "desktop_bridge_smoke_before_preflight"
        return check
    if text.index("--preflight-only --diagnostics-out package-desktop-preflight.json") > text.index(
        "--bridge-smoke-out package-desktop-bridge-smoke.json"
    ):
        check["reason"] = "package_bridge_smoke_before_preflight"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def validate_v1_webview2_runtime(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 WebView2 runtime evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 WebView2 runtime evidence must be an object")
    if document.get("schema_version") != V1_WEBVIEW2_RUNTIME_SCHEMA_VERSION:
        raise ValueError("unsupported v1 WebView2 runtime schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1webview2runtime_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 WebView2 runtime evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 WebView2 runtime checks must be a list")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 WebView2 runtime rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 WebView2 runtime passed is inconsistent")
    return document


def read_v1_webview2_runtime(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_webview2_runtime(value)


def write_v1_webview2_runtime(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_webview2_runtime(repo_root)
    validate_v1_webview2_runtime(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
