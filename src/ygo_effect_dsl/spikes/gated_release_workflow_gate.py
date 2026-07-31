from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_GATED_RELEASE_SCHEMA_VERSION = "v1-gated-release-v1"


def _contains_all(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value not in text]


def _check(check_id: str, evidence: str) -> dict[str, Any]:
    return {
        "evidence": evidence,
        "id": check_id,
        "passed": False,
        "reason": "not_evaluated",
    }


def _doc_policy_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("signed_tag_and_release_policy_documented", evidence)
    if not path.exists():
        check["reason"] = "missing_policy_document"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "version",
            "changelog",
            "tag",
            "artifact",
            "provenance",
            "checksum",
            "protected environment",
            "manual approval",
            "signed tag",
            "dry-run",
            "#91",
            "production distribution gate",
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
    check = _check("gated_release_workflow_blocks_public_publish_until_gates_pass", evidence)
    if not path.exists():
        check["reason"] = "missing_workflow"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "workflow_dispatch",
            "environment: v1-production-release",
            "dry_run",
            "python -m ygo_effect_dsl v1-gated-release",
            "production-distribution-gate",
            "git tag -v",
            "gh release create",
            "--draft",
            "--verify-tag",
            "release-checksums.json",
            "build-provenance",
            "actions/checkout@v7",
            "actions/setup-python@v6",
            "actions/upload-artifact@v7",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "workflow_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _runbook_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("failed_publish_yank_and_rollback_runbook_exists", evidence)
    if not path.exists():
        check["reason"] = "missing_runbook"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "yank",
            "rollback",
            "draft release",
            "public release",
            "release-checksums.json",
            "build provenance",
            "signed tag",
            "pre-migration backup",
            "explicit confirmation",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "runbook_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _action_pinning_check(root: Path) -> dict[str, Any]:
    check = _check("github_actions_runtime_and_pinning_policy_current", ".github/workflows")
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / ".github" / "workflows").glob("*.yml"))
    )
    forbidden = [
        value
        for value in (
            "actions/checkout@v3",
            "actions/checkout@v4",
            "actions/setup-python@v4",
            "actions/upload-artifact@v3",
            "actions/upload-artifact@v4",
        )
        if value in workflows
    ]
    missing = _contains_all(
        workflows,
        ("actions/checkout@v7", "actions/setup-python@v6", "actions/upload-artifact@v7"),
    )
    if forbidden:
        check["forbidden_terms"] = forbidden
        check["reason"] = "deprecated_action_reference"
        return check
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_action_pin_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _test_coverage_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("tests_cover_gated_release_workflow", evidence)
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "test_v1_gated_release_evidence_passes_current_contract",
            "test_committed_v1_gated_release_matches_current_checkout",
            "test_gated_release_workflow_defaults_to_dry_run",
            "test_v1_gated_release_cli_writes_evidence",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_tests_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def evaluate_v1_gated_release(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _doc_policy_check(
            root / "docs" / "adr" / "0023_v1_gated_release.md",
            evidence="docs/adr/0023_v1_gated_release.md",
        ),
        _workflow_check(
            root / ".github" / "workflows" / "gated-release.yml",
            evidence=".github/workflows/gated-release.yml",
        ),
        _runbook_check(
            root / "docs" / "release" / "40_failed_publish_yank_rollback.md",
            evidence="docs/release/40_failed_publish_yank_rollback.md",
        ),
        _action_pinning_check(root),
        _test_coverage_check(
            root / "tests" / "test_gated_release_workflow.py",
            evidence="tests/test_gated_release_workflow.py",
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 173,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "release_policy": {
                "default_public_publish": False,
                "dry_run_version": "1.0.0-dry-run",
                "manual_approval_environment": "v1-production-release",
                "public_publish_requires": [
                    "#91",
                    "production-distribution-release-gate-v1 passed",
                    "signed tag verified",
                    "draft GitHub Release first",
                ],
                "signing_policy": "signed git tag or approved organization equivalent",
            },
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_GATED_RELEASE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1gatedrelease_"),
    }


def validate_v1_gated_release(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 gated release evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 gated release evidence must be an object")
    if document.get("schema_version") != V1_GATED_RELEASE_SCHEMA_VERSION:
        raise ValueError("unsupported v1 gated release schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1gatedrelease_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 gated release evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 gated release checks must be a list")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 gated release rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 gated release passed is inconsistent")
    return document


def read_v1_gated_release(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_gated_release(value)


def write_v1_gated_release(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_gated_release(repo_root)
    validate_v1_gated_release(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
