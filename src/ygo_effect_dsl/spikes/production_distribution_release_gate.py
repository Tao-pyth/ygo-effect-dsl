from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


PRODUCTION_DISTRIBUTION_RELEASE_GATE_SCHEMA_VERSION = (
    "production-distribution-release-gate-v1"
)

_PLACEHOLDER_PASS_VALUES = {"", "TODO", "TBD", "PLACEHOLDER", "PENDING", "PASS"}


def _evidence_ref(evidence_dir: Path, name: str) -> str:
    return (evidence_dir / name).as_posix()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _base_check(
    *,
    check_id: str,
    category: str,
    evidence: str,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "category": category,
        "evidence": evidence,
        "id": check_id,
        "passed": False,
        "reason": "not_evaluated",
        "required": required,
    }


def _missing_or_invalid_json_check(
    repo_root: Path,
    *,
    check_id: str,
    category: str,
    evidence: str,
    schema_version: str,
    require_passed: bool = False,
) -> dict[str, Any]:
    check = _base_check(check_id=check_id, category=category, evidence=evidence)
    path = repo_root / evidence
    document = _read_json(path)
    if document is None:
        check["reason"] = "missing_evidence"
        return check
    if document.get("schema_version") != schema_version:
        check["reason"] = "schema_version_mismatch"
        return check
    if require_passed:
        passed_value = document.get("passed")
        if isinstance(passed_value, str) and passed_value.upper() in _PLACEHOLDER_PASS_VALUES:
            check["reason"] = "placeholder_pass_value"
            return check
        if not isinstance(passed_value, bool):
            check["reason"] = "passed_field_not_boolean"
            return check
        if not passed_value:
            check["reason"] = "evidence_not_passed"
            return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _support_matrix_check(repo_root: Path, evidence_dir: Path) -> dict[str, Any]:
    evidence = _evidence_ref(evidence_dir, "v1_0_0_support_matrix.json")
    check = _base_check(
        check_id="support_matrix_supported_rows_verified",
        category="support",
        evidence=evidence,
    )
    matrix = _read_json(repo_root / evidence)
    if matrix is None:
        check["reason"] = "missing_evidence"
        return check
    if matrix.get("schema_version") != "v1-support-matrix-v1":
        check["reason"] = "schema_version_mismatch"
        return check
    pending = [
        row["id"]
        for row in matrix.get("matrix", [])
        if row.get("support_level") == "supported"
        and row.get("evidence_state") != "verified"
    ]
    if pending:
        check["pending_supported_rows"] = pending
        check["reason"] = "supported_rows_not_verified"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _project_license_check(repo_root: Path, evidence_dir: Path) -> dict[str, Any]:
    evidence = _evidence_ref(evidence_dir, "project_license_approval_status.json")
    check = _base_check(
        check_id="root_project_license_approved",
        category="legal",
        evidence=evidence,
    )
    status = _read_json(repo_root / evidence)
    if status is None:
        check["reason"] = "missing_evidence"
        return check
    if status.get("schema_version") != "project-license-approval-status-v1":
        check["reason"] = "schema_version_mismatch"
        return check
    metadata = status.get("package_metadata", {})
    project_license = status.get("project_license", {})
    if status.get("approval_state") != "approved":
        check["blocking_issues"] = status.get("blocking_issues", [])
        check["reason"] = "approval_not_recorded"
        return check
    if status.get("public_distribution") != "allowed":
        check["reason"] = "public_distribution_not_allowed"
        return check
    if metadata.get("license_expression") in (None, "NOASSERTION"):
        check["reason"] = "package_license_metadata_missing"
        return check
    if project_license.get("spdx") in (None, "NOASSERTION"):
        check["reason"] = "project_license_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _third_party_payload_check(repo_root: Path, evidence_dir: Path) -> dict[str, Any]:
    evidence = _evidence_ref(evidence_dir, "v1_0_0_asset_allowlist.json")
    check = _base_check(
        check_id="third_party_payload_allowlist_default_deny",
        category="legal",
        evidence=evidence,
    )
    allowlist = _read_json(repo_root / evidence)
    if allowlist is None:
        check["reason"] = "missing_evidence"
        return check
    if allowlist.get("schema_version") != "v1-asset-allowlist-v1":
        check["reason"] = "schema_version_mismatch"
        return check
    if allowlist.get("default_action") != "reject":
        check["reason"] = "default_action_not_reject"
        return check
    if allowlist.get("release_artifact_allowed_third_party_payloads") != []:
        check["reason"] = "third_party_payloads_allowed"
        return check
    rows = allowlist.get("external_local_only_assets", [])
    if any(row.get("include_in_release") is not False for row in rows):
        check["reason"] = "external_asset_marked_for_release"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _release_artifact_composition_check(repo_root: Path, evidence_dir: Path) -> dict[str, Any]:
    evidence = _evidence_ref(evidence_dir, "v1_0_0_release_artifact_composition.json")
    check = _base_check(
        check_id="release_artifact_composition_references_exist",
        category="release",
        evidence=evidence,
    )
    composition = _read_json(repo_root / evidence)
    if composition is None:
        check["reason"] = "missing_evidence"
        return check
    if composition.get("schema_version") != "v1-release-artifact-composition-v1":
        check["reason"] = "schema_version_mismatch"
        return check
    missing: list[str] = []
    for artifact in composition.get("artifacts", []):
        for key in ("asset_allowlist", "notice", "sbom"):
            ref = artifact.get(key)
            if not isinstance(ref, str) or not (repo_root / ref).exists():
                missing.append(str(ref))
        if artifact.get("release_audit_required") is not True:
            missing.append(f"{artifact.get('artifact_kind')}:release_audit_required")
        if artifact.get("third_party_payload_policy") != "none_allowed":
            missing.append(f"{artifact.get('artifact_kind')}:third_party_payload_policy")
    if missing:
        check["missing_refs"] = sorted(set(missing))
        check["reason"] = "referenced_artifact_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _windows_executable_workflow_check(repo_root: Path) -> dict[str, Any]:
    evidence = ".github/workflows/build-windows-exe.yml"
    check = _base_check(
        check_id="windows_gui_executable_workflow_smoke",
        category="build",
        evidence=evidence,
    )
    path = repo_root / evidence
    if not path.exists():
        check["reason"] = "missing_evidence"
        return check
    raw = path.read_text(encoding="utf-8")
    required = [
        "ygo-effect-dsl-desktop",
        "--preflight-only",
        "--diagnostics-out",
        "--bridge-smoke-out",
        "src/ygo_effect_dsl/desktop/static;ygo_effect_dsl/desktop/static",
    ]
    missing = [value for value in required if value not in raw]
    forbidden = [value for value in ("--add-binary", "YGO_EFFECT_DSL_EXTERNAL_ROOT") if value in raw]
    if missing:
        check["missing_workflow_terms"] = missing
        check["reason"] = "workflow_smoke_missing"
        return check
    if forbidden:
        check["forbidden_workflow_terms"] = forbidden
        check["reason"] = "forbidden_payload_reference"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def evaluate_production_distribution_release_gate(
    repo_root: str | Path,
    *,
    evidence_dir: str | Path = "docs/release/evidence",
) -> dict[str, Any]:
    root = Path(repo_root)
    evidence_path = Path(evidence_dir)
    checks = [
        _support_matrix_check(root, evidence_path),
        _project_license_check(root, evidence_path),
        _missing_or_invalid_json_check(
            root,
            check_id="sbom_present",
            category="legal",
            evidence=_evidence_ref(evidence_path, "v1_0_0_sbom.json"),
            schema_version="v1-sbom-v1",
        ),
        _third_party_payload_check(root, evidence_path),
        _release_artifact_composition_check(root, evidence_path),
        _windows_executable_workflow_check(root),
        _missing_or_invalid_json_check(
            root,
            check_id="installer_packaging_verified",
            category="installer",
            evidence=_evidence_ref(evidence_path, "v1_0_0_installer_packaging.json"),
            schema_version="v1-installer-packaging-v1",
            require_passed=True,
        ),
        _missing_or_invalid_json_check(
            root,
            check_id="authenticode_signing_verified",
            category="signing",
            evidence=_evidence_ref(evidence_path, "v1_0_0_authenticode_signing.json"),
            schema_version="v1-authenticode-signing-v1",
            require_passed=True,
        ),
        _missing_or_invalid_json_check(
            root,
            check_id="webview2_runtime_failure_ux_verified",
            category="runtime",
            evidence=_evidence_ref(evidence_path, "v1_0_0_webview2_runtime.json"),
            schema_version="v1-webview2-runtime-v1",
            require_passed=True,
        ),
        _missing_or_invalid_json_check(
            root,
            check_id="external_asset_setup_verified",
            category="assets",
            evidence=_evidence_ref(evidence_path, "v1_0_0_external_asset_setup.json"),
            schema_version="v1-external-asset-setup-v1",
            require_passed=True,
        ),
        _missing_or_invalid_json_check(
            root,
            check_id="desktop_settings_preferences_verified",
            category="desktop",
            evidence=_evidence_ref(evidence_path, "v1_0_0_desktop_settings.json"),
            schema_version="v1-desktop-settings-v1",
            require_passed=True,
        ),
        _missing_or_invalid_json_check(
            root,
            check_id="security_threat_model_approved",
            category="security",
            evidence=_evidence_ref(evidence_path, "v1_0_0_security_threat_model.json"),
            schema_version="v1-security-threat-model-v1",
            require_passed=True,
        ),
        _missing_or_invalid_json_check(
            root,
            check_id="soak_crash_recovery_verified",
            category="validation",
            evidence=_evidence_ref(evidence_path, "v1_0_0_soak_crash_recovery.json"),
            schema_version="v1-soak-crash-recovery-v1",
            require_passed=True,
        ),
        _missing_or_invalid_json_check(
            root,
            check_id="stable_docs_and_support_guides_published",
            category="docs",
            evidence=_evidence_ref(evidence_path, "v1_0_0_docs_support_guides.json"),
            schema_version="v1-docs-support-guides-v1",
            require_passed=True,
        ),
        _missing_or_invalid_json_check(
            root,
            check_id="redacted_support_bundle_verified",
            category="support",
            evidence=_evidence_ref(evidence_path, "v1_0_0_redacted_support_bundle.json"),
            schema_version="v1-redacted-support-bundle-v1",
            require_passed=True,
        ),
    ]
    mandatory = [check for check in checks if check["required"]]
    rejection_reasons = sorted(
        {
            f"{check['id']}:{check['reason']}"
            for check in mandatory
            if not check["passed"]
        }
    )
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 359,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "rejection_reasons": rejection_reasons,
            "schema_version": PRODUCTION_DISTRIBUTION_RELEASE_GATE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="productiondistgate_"),
    }


def validate_production_distribution_release_gate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("production distribution release gate must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("production distribution release gate must be an object")
    if document.get("schema_version") != PRODUCTION_DISTRIBUTION_RELEASE_GATE_SCHEMA_VERSION:
        raise ValueError("unsupported production distribution release gate schema_version")
    evidence_id = document.get("evidence_id")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="productiondistgate_")
    if evidence_id != expected:
        raise ValueError("production distribution release gate evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("production distribution release gate checks must be a list")
    for check in checks:
        if not isinstance(check, Mapping):
            raise ValueError("production distribution release gate check must be an object")
        if not isinstance(check.get("passed"), bool):
            raise ValueError("production distribution release gate check passed is invalid")
        if not check.get("id") or not check.get("category") or not check.get("evidence"):
            raise ValueError("production distribution release gate check identity is invalid")
        if not check.get("reason"):
            raise ValueError("production distribution release gate check reason is invalid")
    expected_rejections = sorted(
        {
            f"{check['id']}:{check['reason']}"
            for check in checks
            if check.get("required") is True and check.get("passed") is not True
        }
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("production distribution release gate rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("production distribution release gate passed is inconsistent")
    return document


def read_production_distribution_release_gate(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_production_distribution_release_gate(value)


def write_production_distribution_release_gate(
    repo_root: str | Path,
    *,
    evidence_dir: str | Path = "docs/release/evidence",
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_production_distribution_release_gate(
        repo_root,
        evidence_dir=evidence_dir,
    )
    validate_production_distribution_release_gate(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
