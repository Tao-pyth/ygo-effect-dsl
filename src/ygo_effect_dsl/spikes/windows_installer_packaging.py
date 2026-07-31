from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_INSTALLER_PACKAGING_SCHEMA_VERSION = "v1-installer-packaging-v1"


def _contains_all(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value not in text]


def evaluate_v1_installer_packaging(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    contract_evidence = "docs/adr/0017_v1_windows_distribution_package.md"
    package_readme_evidence = "packaging/windows-portable/README.txt"
    workflow_evidence = ".github/workflows/build-windows-exe.yml"
    contract = root / contract_evidence
    package_readme = root / package_readme_evidence
    workflow = root / workflow_evidence
    checks: list[dict[str, Any]] = []

    checks.append(_document_check(contract, evidence=contract_evidence))
    checks.append(_package_readme_check(package_readme, evidence=package_readme_evidence))
    checks.append(_workflow_check(workflow, evidence=workflow_evidence))

    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    identity = to_canonical_data(
        {
            "artifact": {
                "archive_name": "ygo-effect-dsl-win64-portable.zip",
                "format": "portable_zip",
                "top_level_directory": "ygo-effect-dsl-win64",
            },
            "checks": checks,
            "distribution_boundary": {
                "admin_required": False,
                "auto_update": "not_included",
                "machine_wide_install": False,
                "public_release_blocked_until_parent_gate": True,
                "webview2_runtime_bundled": False,
            },
            "issue": 355,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_INSTALLER_PACKAGING_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1installerpackaging_"),
    }


def _document_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = {
        "evidence": evidence,
        "id": "packaging_adr_records_operational_contract",
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
            "portable ZIP",
            "per-user",
            "machine-wide",
            "uninstall",
            "upgrade",
            "rollback",
            "clean-machine",
            "WebView2 runtime is not bundled",
            "ocgcore",
            "CardScripts",
            "BabelCDB",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _package_readme_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = {
        "evidence": evidence,
        "id": "package_readme_records_install_uninstall_steps",
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
            "Extract",
            "ygo-effect-dsl-desktop.exe",
            "ygo-effect-dsl.exe",
            "Uninstall",
            "Upgrade",
            "Rollback",
            "No third-party card assets",
            "WebView2",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _workflow_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = {
        "evidence": evidence,
        "id": "ci_builds_and_smokes_portable_zip",
        "passed": False,
        "reason": "not_evaluated",
    }
    if not path.exists():
        check["reason"] = "missing_workflow"
        return check
    text = path.read_text(encoding="utf-8")
    required = (
        "Build portable Windows package",
        "Smoke test portable Windows package",
        "ygo-effect-dsl-win64-portable.zip",
        "Compress-Archive",
        "Expand-Archive",
        "package_smoke",
        "THIRD_PARTY_NOTICES.md",
        "DISTRIBUTION_POLICY.md",
        "packaging/windows-portable/README.txt",
    )
    missing = _contains_all(text, required)
    forbidden = [
        value
        for value in ("WebView2Loader", "YGO_EFFECT_DSL_EXTERNAL_ROOT", "--add-binary")
        if value in text
    ]
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    if forbidden:
        check["forbidden_terms"] = forbidden
        check["reason"] = "forbidden_payload_reference"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def validate_v1_installer_packaging(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 installer packaging evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 installer packaging evidence must be an object")
    if document.get("schema_version") != V1_INSTALLER_PACKAGING_SCHEMA_VERSION:
        raise ValueError("unsupported v1 installer packaging schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1installerpackaging_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 installer packaging evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 installer packaging checks must be a list")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 installer packaging rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 installer packaging passed is inconsistent")
    return document


def read_v1_installer_packaging(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_installer_packaging(value)


def write_v1_installer_packaging(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_installer_packaging(repo_root)
    validate_v1_installer_packaging(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
