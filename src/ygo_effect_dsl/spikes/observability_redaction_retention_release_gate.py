from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_OBSERVABILITY_REDACTION_RETENTION_SCHEMA_VERSION = (
    "v1-observability-redaction-retention-v1"
)

REQUIRED_MATRIX_ROWS = (
    "structured_observability_records",
    "player_view_redaction_boundary",
    "private_canary_leak_tests",
    "raw_hidden_payload_default_off",
    "worker_crash_safe_failure_report",
    "retention_and_deletion_policy",
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


def _policy_doc_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("observability_redaction_retention_policy_documented", evidence)
    if not path.exists():
        check["reason"] = "missing_policy_document"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "structured observability records",
            "correlation ID",
            "diagnostic code",
            "CLI exit category",
            "raw hidden payload",
            "worker stdout/stderr",
            "crash dump",
            "information-access-audit-v2",
            "canary leak tests",
            "artifact_commit: not_published",
            "Retention policy",
            "30 days",
            "delete",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _information_audit_check(root: Path) -> dict[str, Any]:
    check = _check(
        "information_access_audit_blocks_private_canaries_and_side_channels",
        "src/ygo_effect_dsl/engine/information/artifact_audit.py;tests/test_information_artifact_audit.py",
    )
    paths = (
        root / "src" / "ygo_effect_dsl" / "engine" / "information" / "artifact_audit.py",
        root / "tests" / "test_information_artifact_audit.py",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_source_or_tests"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            "INFORMATION_ACCESS_AUDIT_V2_SCHEMA_VERSION",
            "_FORBIDDEN_FIELD_NAMES",
            "_SIDE_CHANNEL_FIELD_NAMES",
            "InformationCanaryRegistry",
            "private_canary_match",
            "forbidden_side_channel",
            "test_private_canary_is_detected_across_every_export_surface",
            "test_leak_fixture_matrix_fails_closed",
            "PRIVATE_CANARY not in json.dumps(report",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "audit_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _player_view_publication_check(root: Path) -> dict[str, Any]:
    check = _check(
        "player_view_publication_blocks_leaks_and_writes_safe_failures",
        "src/ygo_effect_dsl/cli/cmd_experiment.py;tests/test_player_view_cli.py;tests/test_player_view_replay.py",
    )
    paths = (
        root / "src" / "ygo_effect_dsl" / "cli" / "cmd_experiment.py",
        root / "tests" / "test_player_view_cli.py",
        root / "tests" / "test_player_view_replay.py",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_source_or_tests"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            "PLAYER_VIEW_PUBLICATION_FAILURE_SCHEMA_VERSION",
            "artifact_commit",
            "not_published",
            "assert_information_artifact_safe",
            "publication blocked",
            "test_player_view_cli_worker_failure_writes_only_safe_failure_report",
            "test_player_view_cli_blocks_publication_when_support_artifact_leaks",
            "test_player_view_replay_is_deterministic_and_excludes_private_identifiers",
            "PRIVATE_CANARY not in failure",
            "assert not (tmp_path / \"player-view.json\").exists()",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "player_view_publication_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _failure_and_worker_diagnostic_check(root: Path) -> dict[str, Any]:
    check = _check(
        "worker_crash_diagnostics_are_digest_or_code_based",
        "src/ygo_effect_dsl/engine/failures.py;src/ygo_effect_dsl/prototype/frontier.py;docs/bridge/60_failure_policy.md",
    )
    paths = (
        root / "src" / "ygo_effect_dsl" / "engine" / "failures.py",
        root / "src" / "ygo_effect_dsl" / "prototype" / "frontier.py",
        root / "docs" / "bridge" / "60_failure_policy.md",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_source_or_docs"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            "FailureRecord",
            "category",
            "retryable",
            "pointer-free context",
            "worker crash",
            "stderr_digest",
            "stdout_digest",
            "worker_input_digest",
            "diagnostic digests recorded",
            "Unsupported message and version mismatch retain",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "failure_diagnostic_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _retention_policy_check(root: Path) -> dict[str, Any]:
    check = _check(
        "retention_policy_separates_private_local_and_committed_evidence",
        "docs/adr/0025_v1_observability_redaction_retention.md;src/ygo_effect_dsl/storage/policy.py",
    )
    paths = (
        root / "docs" / "adr" / "0025_v1_observability_redaction_retention.md",
        root / "src" / "ygo_effect_dsl" / "storage" / "policy.py",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_retention_policy"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            "local raw logs and private lineage",
            "CI release evidence",
            "committed release evidence",
            "production support artifacts",
            "deliberate crash dumps",
            "automatic_in_place_migration",
            "retain_or_explicitly_archive_source",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "retention_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _test_coverage_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("tests_cover_v1_observability_redaction_retention_gate", evidence)
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "test_v1_observability_redaction_retention_evidence_passes_current_contract",
            "test_committed_v1_observability_redaction_retention_matches_current_checkout",
            "test_v1_observability_redaction_retention_cli_writes_evidence",
            "test_raw_hidden_payload_is_rejected_by_information_audit",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_tests_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def evaluate_v1_observability_redaction_retention(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _policy_doc_check(
            root / "docs" / "adr" / "0025_v1_observability_redaction_retention.md",
            evidence="docs/adr/0025_v1_observability_redaction_retention.md",
        ),
        _information_audit_check(root),
        _player_view_publication_check(root),
        _failure_and_worker_diagnostic_check(root),
        _retention_policy_check(root),
        _test_coverage_check(
            root / "tests" / "test_observability_redaction_retention_release_gate.py",
            evidence="tests/test_observability_redaction_retention_release_gate.py",
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    matrix = [
        {
            "id": row,
            "raw_payload_retained_by_default": False,
            "status": "verified" if not rejection_reasons else "blocked",
        }
        for row in REQUIRED_MATRIX_ROWS
    ]
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 175,
            "matrix": matrix,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "policy": {
                "crash_dumps_default": "disabled",
                "public_failure_report": "safe_code_only",
                "redaction_gate": "information-access-audit-v2",
                "retention_private_support_days": 30,
                "structured_observability_requires": [
                    "correlation_id",
                    "diagnostic_code",
                    "cli_exit_category",
                    "schema_or_contract_version",
                ],
            },
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_OBSERVABILITY_REDACTION_RETENTION_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1obsredactretention_"),
    }


def validate_v1_observability_redaction_retention(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 observability/redaction evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 observability/redaction evidence must be an object")
    if document.get("schema_version") != V1_OBSERVABILITY_REDACTION_RETENTION_SCHEMA_VERSION:
        raise ValueError("unsupported v1 observability/redaction schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1obsredactretention_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 observability/redaction evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 observability/redaction checks must be a list")
    matrix = document.get("matrix")
    if not isinstance(matrix, list):
        raise ValueError("v1 observability/redaction matrix must be a list")
    observed_rows = tuple(row.get("id") for row in matrix if isinstance(row, Mapping))
    if observed_rows != REQUIRED_MATRIX_ROWS:
        raise ValueError("v1 observability/redaction matrix rows are inconsistent")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 observability/redaction rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 observability/redaction passed is inconsistent")
    return document


def read_v1_observability_redaction_retention(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_observability_redaction_retention(value)


def write_v1_observability_redaction_retention(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_observability_redaction_retention(repo_root)
    validate_v1_observability_redaction_retention(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
