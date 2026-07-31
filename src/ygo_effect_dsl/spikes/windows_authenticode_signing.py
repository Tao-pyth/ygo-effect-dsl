from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_AUTHENTICODE_SIGNING_SCHEMA_VERSION = "v1-authenticode-signing-v1"
V1_AUTHENTICODE_SIGNED_ARTIFACTS_SCHEMA_VERSION = (
    "v1-authenticode-signed-artifacts-v1"
)


def _contains_all(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value not in text]


def evaluate_v1_authenticode_signing(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    policy_evidence = "docs/adr/0018_v1_authenticode_signing.md"
    workflow_evidence = ".github/workflows/build-windows-exe.yml"
    signed_artifacts_evidence = (
        "docs/release/evidence/v1_0_0_authenticode_signed_artifacts.json"
    )
    checks = [
        _policy_document_check(root / policy_evidence, evidence=policy_evidence),
        _workflow_unsigned_rejection_check(
            root / workflow_evidence,
            evidence=workflow_evidence,
        ),
        _signed_artifacts_check(
            root / signed_artifacts_evidence,
            evidence=signed_artifacts_evidence,
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    identity = to_canonical_data(
        {
            "artifact_scope": [
                "dist/ygo-effect-dsl.exe",
                "dist/ygo-effect-dsl-desktop.exe",
                "ygo-effect-dsl-win64-portable.zip",
            ],
            "checks": checks,
            "credential_policy": {
                "repository_storage": "forbidden",
                "runtime_artifact_storage": "forbidden",
                "standard_ci_log_storage": "forbidden",
                "storage": "github_actions_secrets_or_external_signing_service",
            },
            "issue": 356,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "rejection_reasons": rejection_reasons,
            "release_state": "blocked_until_signed_artifact_evidence_exists",
            "schema_version": V1_AUTHENTICODE_SIGNING_SCHEMA_VERSION,
            "signer_identity_policy": {
                "certificate_thumbprint_required": True,
                "extended_key_usage": "code_signing",
                "subject_must_match_release_approval": True,
            },
            "timestamp_policy": {
                "rfc3161_timestamp_required": True,
                "timestamp_server_must_be_release_approved": True,
            },
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1authenticode_"),
    }


def _policy_document_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = {
        "evidence": evidence,
        "id": "signing_policy_documented",
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
            "Authenticode",
            "Get-AuthenticodeSignature",
            "RFC 3161",
            "timestamp",
            "certificate thumbprint",
            "SHA-256",
            "unsigned",
            "tampered",
            "GitHub Actions secrets",
            "must not store signing credentials",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _workflow_unsigned_rejection_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = {
        "evidence": evidence,
        "id": "unsigned_artifact_rejection_recorded_in_ci",
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
            "Verify unsigned Authenticode artifacts are not release eligible",
            "Get-AuthenticodeSignature",
            "unsigned-authenticode-verification.json",
            "release_eligible",
            "unsigned_or_untrusted_signature",
        ),
    )
    forbidden = [
        value
        for value in (
            "YGO_EFFECT_DSL_AUTHENTICODE_CERT_BASE64",
            "YGO_EFFECT_DSL_AUTHENTICODE_CERT_PASSWORD",
            "codesign-password",
        )
        if value in text
    ]
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    if forbidden:
        check["forbidden_terms"] = forbidden
        check["reason"] = "credential_reference_in_unsigned_workflow"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _signed_artifacts_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = {
        "evidence": evidence,
        "id": "signed_artifacts_verified",
        "passed": False,
        "reason": "not_evaluated",
    }
    if not path.exists():
        check["reason"] = "missing_signed_artifact_evidence"
        return check
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != V1_AUTHENTICODE_SIGNED_ARTIFACTS_SCHEMA_VERSION:
        check["reason"] = "schema_version_mismatch"
        return check
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        check["reason"] = "signed_artifacts_missing"
        return check
    invalid = [
        artifact.get("artifact")
        for artifact in artifacts
        if artifact.get("signature_status") != "Valid"
        or artifact.get("timestamp_status") != "Valid"
        or not isinstance(artifact.get("sha256"), str)
        or len(artifact["sha256"]) != 64
        or not artifact.get("certificate_thumbprint")
        or not artifact.get("signer_subject")
    ]
    if invalid:
        check["invalid_artifacts"] = sorted(str(value) for value in invalid)
        check["reason"] = "signature_or_timestamp_invalid"
        return check
    if document.get("unsigned_failure_case") != "rejected":
        check["reason"] = "unsigned_failure_case_missing"
        return check
    if document.get("tampered_failure_case") != "rejected":
        check["reason"] = "tampered_failure_case_missing"
        return check
    if not document.get("commit") or not document.get("workflow_run_url"):
        check["reason"] = "provenance_linkage_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def validate_v1_authenticode_signing(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 Authenticode signing evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 Authenticode signing evidence must be an object")
    if document.get("schema_version") != V1_AUTHENTICODE_SIGNING_SCHEMA_VERSION:
        raise ValueError("unsupported v1 Authenticode signing schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1authenticode_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 Authenticode signing evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 Authenticode signing checks must be a list")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 Authenticode signing rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 Authenticode signing passed is inconsistent")
    return document


def read_v1_authenticode_signing(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_authenticode_signing(value)


def write_v1_authenticode_signing(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_authenticode_signing(repo_root)
    validate_v1_authenticode_signing(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
