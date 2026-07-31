from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.support_bundle import (
    DEFAULT_SUPPORT_BUNDLE_SIZE_LIMIT_BYTES,
    REDACTED_SUPPORT_BUNDLE_MANIFEST_SCHEMA_VERSION,
    REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION,
)


V1_REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION = "v1-redacted-support-bundle-v1"

REQUIRED_MATRIX_ROWS = (
    "cli_generates_local_bundle",
    "manifest_and_schema_versions",
    "redaction_report_and_canary_tests",
    "size_limit_and_retention_policy",
    "no_auto_upload_no_raw_payloads",
)


def _contains_all(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value not in text]


def _check(check_id: str, evidence: str) -> dict[str, Any]:
    return {
        "evidence": evidence,
        "id": check_id,
        "passed": False,
        "reason": "not_evaluated",
    }


def _source_check(root: Path) -> dict[str, Any]:
    check = _check(
        "support_bundle_source_writes_manifest_diagnostics_and_redaction_report",
        "src/ygo_effect_dsl/support_bundle.py;src/ygo_effect_dsl/cli/cmd_support.py;src/ygo_effect_dsl/cli/main.py",
    )
    paths = (
        root / "src" / "ygo_effect_dsl" / "support_bundle.py",
        root / "src" / "ygo_effect_dsl" / "cli" / "cmd_support.py",
        root / "src" / "ygo_effect_dsl" / "cli" / "main.py",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_source"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            "support-bundle",
            "write_redacted_support_bundle",
            "manifest.json",
            "diagnostics.json",
            "redaction-report.json",
            "README.json",
            "automatic_upload",
            "False",
            "raw_payloads_included",
            "raw_crash_dumps_included",
            REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION,
            REDACTED_SUPPORT_BUNDLE_MANIFEST_SCHEMA_VERSION,
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "source_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _redaction_check(root: Path) -> dict[str, Any]:
    check = _check(
        "support_bundle_uses_information_audit_and_private_canaries",
        "src/ygo_effect_dsl/support_bundle.py;tests/test_support_bundle.py",
    )
    paths = (
        root / "src" / "ygo_effect_dsl" / "support_bundle.py",
        root / "tests" / "test_support_bundle.py",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_source_or_tests"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            "audit_information_artifact",
            "assert_information_artifact_safe",
            "DEFAULT_PRIVATE_CANARY",
            "private_canary",
            "test_support_bundle_redacts_private_canary_paths_and_raw_payloads",
            "test_support_bundle_cli_writes_manifest_and_redaction_report",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "redaction_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _policy_doc_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("support_bundle_policy_documented", evidence)
    if not path.exists():
        check["reason"] = "missing_policy_document"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "local diagnostic bundle",
            "manifest",
            "redaction report",
            "size limits",
            "retention policy",
            "canary tests",
            "Do not automatically upload",
            "full deck lists",
            "private hands",
            "raw payloads",
            "absolute personal paths",
            "crash dumps",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "policy_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _test_coverage_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("tests_cover_v1_redacted_support_bundle_gate", evidence)
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "test_v1_redacted_support_bundle_evidence_passes_current_contract",
            "test_committed_v1_redacted_support_bundle_matches_current_checkout",
            "test_v1_redacted_support_bundle_cli_writes_evidence",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_tests_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def evaluate_v1_redacted_support_bundle(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _source_check(root),
        _redaction_check(root),
        _policy_doc_check(
            root / "docs" / "support" / "10_redacted_support_bundle.md",
            evidence="docs/support/10_redacted_support_bundle.md",
        ),
        _test_coverage_check(
            root / "tests" / "test_redacted_support_bundle_release_gate.py",
            evidence="tests/test_redacted_support_bundle_release_gate.py",
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    matrix = [
        {
            "id": row,
            "raw_private_payloads_allowed": False,
            "status": "verified" if not rejection_reasons else "blocked",
        }
        for row in REQUIRED_MATRIX_ROWS
    ]
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 360,
            "matrix": matrix,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "policy": {
                "automatic_upload": False,
                "bundle_schema_version": REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION,
                "manifest_schema_version": REDACTED_SUPPORT_BUNDLE_MANIFEST_SCHEMA_VERSION,
                "retention_days": 30,
                "size_limit_bytes": DEFAULT_SUPPORT_BUNDLE_SIZE_LIMIT_BYTES,
            },
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1supportbundle_"),
    }


def validate_v1_redacted_support_bundle(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 redacted support bundle evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 redacted support bundle evidence must be an object")
    if document.get("schema_version") != V1_REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION:
        raise ValueError("unsupported v1 redacted support bundle schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1supportbundle_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 redacted support bundle evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 redacted support bundle checks must be a list")
    matrix = document.get("matrix")
    if not isinstance(matrix, list):
        raise ValueError("v1 redacted support bundle matrix must be a list")
    observed_rows = tuple(row.get("id") for row in matrix if isinstance(row, Mapping))
    if observed_rows != REQUIRED_MATRIX_ROWS:
        raise ValueError("v1 redacted support bundle matrix rows are inconsistent")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 redacted support bundle rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 redacted support bundle passed is inconsistent")
    return document


def read_v1_redacted_support_bundle(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_redacted_support_bundle(value)


def write_v1_redacted_support_bundle(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_redacted_support_bundle(repo_root)
    validate_v1_redacted_support_bundle(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
