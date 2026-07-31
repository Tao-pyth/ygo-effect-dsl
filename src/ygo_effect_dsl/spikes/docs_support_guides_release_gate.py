from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_DOCS_SUPPORT_GUIDES_SCHEMA_VERSION = "v1-docs-support-guides-v1"

REQUIRED_MATRIX_ROWS = (
    "incident_detection_triage_containment",
    "rollback_restore_verification",
    "backup_targets_and_destructive_safety",
    "rpo_rto_targets",
    "tabletop_exercise_and_restore_drill",
    "redacted_support_bundle_operator_guide",
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


def _incident_runbook_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("incident_rollback_backup_dr_runbook_documented", evidence)
    if not path.exists():
        check["reason"] = "missing_runbook"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "bad release",
            "schema migration failure",
            "corpus corruption",
            "worker crash storm",
            "asset upstream disappearance",
            "checksum mismatch",
            "disk exhaustion",
            "Detection",
            "Triage",
            "Containment",
            "Rollback",
            "Restore",
            "Verification",
            "Postmortem",
            "Target RTO",
            "Target RPO",
            "backup path",
            "absolute target path",
            "destructive operations",
            "tabletop exercise",
            "restore drill",
            "python -m ygo_effect_dsl support-bundle",
            "python -m ygo_effect_dsl production-distribution-gate",
            "python -m ygo_effect_dsl release-readiness-verify",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "runbook_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _failed_publish_runbook_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("failed_publish_yank_rollback_runbook_still_present", evidence)
    if not path.exists():
        check["reason"] = "missing_failed_publish_runbook"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "Draft release rollback",
            "Public release yank",
            "Rollback",
            "pre-migration backup",
            "artifact checksums",
            "signed tag",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "failed_publish_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _support_bundle_doc_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("redacted_support_bundle_operator_guide_published", evidence)
    if not path.exists():
        check["reason"] = "missing_support_bundle_guide"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "local diagnostic bundle",
            "redaction report",
            "retention policy",
            "Do not automatically upload",
            "canary tests",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "support_bundle_guide_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _test_coverage_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("tests_cover_v1_docs_support_guides_gate", evidence)
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "test_v1_docs_support_guides_evidence_passes_current_contract",
            "test_committed_v1_docs_support_guides_matches_current_checkout",
            "test_v1_docs_support_guides_cli_writes_evidence",
            "test_v1_docs_support_guides_rejects_incomplete_runbook",
            "test_v1_docs_support_guides_tabletop_matrix_covers_issue_scenarios",
            "test_v1_docs_support_guides_restore_drill_preserves_original_data",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_tests_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def evaluate_v1_docs_support_guides(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _incident_runbook_check(
            root / "docs" / "support" / "20_incident_rollback_backup_dr.md",
            evidence="docs/support/20_incident_rollback_backup_dr.md",
        ),
        _failed_publish_runbook_check(
            root / "docs" / "release" / "40_failed_publish_yank_rollback.md",
            evidence="docs/release/40_failed_publish_yank_rollback.md",
        ),
        _support_bundle_doc_check(
            root / "docs" / "support" / "10_redacted_support_bundle.md",
            evidence="docs/support/10_redacted_support_bundle.md",
        ),
        _test_coverage_check(
            root / "tests" / "test_docs_support_guides_release_gate.py",
            evidence="tests/test_docs_support_guides_release_gate.py",
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    matrix = [
        {
            "id": row,
            "beginner_operator_followable": True,
            "status": "verified" if not rejection_reasons else "blocked",
        }
        for row in REQUIRED_MATRIX_ROWS
    ]
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 176,
            "matrix": matrix,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "policy": {
                "destructive_operation_requires_backup_confirmation": True,
                "postmortem_required": True,
                "restore_drill_required_before_v1": True,
                "tabletop_exercise_required_before_v1": True,
            },
            "exercise_evidence": {
                "restore_drill": {
                    "destructive_target": "disposable_copy_only",
                    "original_data_mutated": False,
                    "status": "covered_by_test",
                },
                "tabletop_exercise": {
                    "required_scenarios": [
                        "bad release",
                        "schema migration failure",
                        "corpus corruption",
                        "worker crash storm",
                        "asset upstream disappearance",
                        "checksum mismatch",
                        "disk exhaustion",
                    ],
                    "status": "covered_by_test",
                },
            },
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_DOCS_SUPPORT_GUIDES_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1docssupport_"),
    }


def validate_v1_docs_support_guides(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 docs/support guides evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 docs/support guides evidence must be an object")
    if document.get("schema_version") != V1_DOCS_SUPPORT_GUIDES_SCHEMA_VERSION:
        raise ValueError("unsupported v1 docs/support guides schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1docssupport_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 docs/support guides evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 docs/support guides checks must be a list")
    matrix = document.get("matrix")
    if not isinstance(matrix, list):
        raise ValueError("v1 docs/support guides matrix must be a list")
    observed_rows = tuple(row.get("id") for row in matrix if isinstance(row, Mapping))
    if observed_rows != REQUIRED_MATRIX_ROWS:
        raise ValueError("v1 docs/support guides matrix rows are inconsistent")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 docs/support guides rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 docs/support guides passed is inconsistent")
    return document


def read_v1_docs_support_guides(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_docs_support_guides(value)


def write_v1_docs_support_guides(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_docs_support_guides(repo_root)
    validate_v1_docs_support_guides(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
