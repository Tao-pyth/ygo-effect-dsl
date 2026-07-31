from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_COMPATIBILITY_POLICY_SCHEMA_VERSION = "v1-compatibility-policy-v1"

REQUIRED_MATRIX_ROWS = (
    "experiment_0_3a_backward_read_explicit_migration",
    "experiment_0_3b_executable_compatibility",
    "experiment_0_4_current",
    "route_replay_strict_version",
    "forward_schema_rejection",
    "unknown_field_enum_rejection",
    "diagnostic_code_policy",
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


def _doc_policy_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("schema_cli_api_artifact_compatibility_policy_documented", evidence)
    if not path.exists():
        check["reason"] = "missing_policy_document"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "Package SemVer",
            "schema/contract version",
            "strategy version",
            "evaluator version",
            "cache/worker policy version",
            "backward read",
            "Replay compatibility",
            "forward rejection",
            "deprecation warning",
            "removal window",
            "experiment-migrate",
            "unknown field",
            "enum",
            "diagnostic code",
            "CLI exit category",
            "no silent migration",
            "0.3a",
            "0.3b",
            "0.4",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _experiment_contract_check(root: Path) -> dict[str, Any]:
    check = _check(
        "experiment_legacy_current_and_future_schema_boundaries_tested",
        "src/ygo_effect_dsl/experiment/schema.py;src/ygo_effect_dsl/experiment/resolution.py;tests/test_experiment_schema.py",
    )
    paths = (
        root / "src" / "ygo_effect_dsl" / "experiment" / "schema.py",
        root / "src" / "ygo_effect_dsl" / "experiment" / "resolution.py",
        root / "tests" / "test_experiment_schema.py",
        root / "tests" / "test_compatibility_policy_release_gate.py",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_source_or_tests"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            'LEGACY_EXPERIMENT_SCHEMA_VERSION = "0.3a"',
            'INFORMATION_POLICY_EXPERIMENT_SCHEMA_VERSION = "0.3b"',
            'EXPERIMENT_SCHEMA_VERSION = "0.4"',
            "SUPPORTED_EXPERIMENT_SCHEMA_VERSIONS",
            "unknown_experiment_field",
            "unsupported_schema_version",
            "explicitly migrate it to '0.3b' or '0.4'",
            "migration source must be an Experiment 0.3a document",
            "test_v03a_requires_explicit_policy_choices_to_migrate",
            "test_migration_cli_requires_explicit_policy_dimensions",
            "test_unknown_experiment_top_level_fields_are_rejected",
            "test_future_experiment_schema_is_rejected",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "contract_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _route_replay_contract_check(root: Path) -> dict[str, Any]:
    check = _check(
        "route_replay_version_mismatch_fails_closed",
        "src/ygo_effect_dsl/route_dsl/validator.py;src/ygo_effect_dsl/experiment/resolution.py;tests/test_route_dsl.py",
    )
    paths = (
        root / "src" / "ygo_effect_dsl" / "route_dsl" / "validator.py",
        root / "src" / "ygo_effect_dsl" / "experiment" / "resolution.py",
        root / "tests" / "test_compatibility_policy_release_gate.py",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_source_or_tests"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            'ROUTE_DSL_SCHEMA_VERSION = "0.1"',
            "unsupported_schema_version",
            "$.replay.schema_version",
            "Experiment file does not match Route DSL experiment",
            "test_future_route_schema_is_rejected",
            "test_route_experiment_mismatch_is_rejected",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "route_replay_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _bridge_fail_close_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("bridge_and_replay_unknown_messages_fail_closed", evidence)
    if not path.exists():
        check["reason"] = "missing_bridge_matrix"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "unknown_message_policy: fail_close",
            "UnsupportedBridgeMessageError",
            "registry",
            "not card-rule correctness",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "bridge_fail_close_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _cli_command_check(root: Path) -> dict[str, Any]:
    check = _check(
        "migration_and_compatibility_gate_cli_exposed",
        "src/ygo_effect_dsl/cli/main.py;src/ygo_effect_dsl/cli/cmd_qualification.py",
    )
    paths = (
        root / "src" / "ygo_effect_dsl" / "cli" / "main.py",
        root / "src" / "ygo_effect_dsl" / "cli" / "cmd_qualification.py",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_cli_source"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            "experiment-migrate",
            "cmd_migrate_experiment",
            "v1-compatibility-policy",
            "cmd_v1_compatibility_policy",
            "write_v1_compatibility_policy",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "cli_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _test_coverage_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("tests_cover_v1_compatibility_policy_gate", evidence)
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "test_v1_compatibility_policy_evidence_passes_current_contract",
            "test_committed_v1_compatibility_policy_matches_current_checkout",
            "test_v1_compatibility_policy_cli_writes_evidence",
            "test_v1_compatibility_matrix_records_expected_boundaries",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_tests_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def evaluate_v1_compatibility_policy(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _doc_policy_check(
            root / "docs" / "adr" / "0024_v1_compatibility_policy.md",
            evidence="docs/adr/0024_v1_compatibility_policy.md",
        ),
        _experiment_contract_check(root),
        _route_replay_contract_check(root),
        _bridge_fail_close_check(
            root / "docs" / "bridge" / "50_compatibility_matrix.md",
            evidence="docs/bridge/50_compatibility_matrix.md",
        ),
        _cli_command_check(root),
        _test_coverage_check(
            root / "tests" / "test_compatibility_policy_release_gate.py",
            evidence="tests/test_compatibility_policy_release_gate.py",
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    matrix = [
        {
            "id": row,
            "requires_explicit_migration": row
            == "experiment_0_3a_backward_read_explicit_migration",
            "status": "verified" if not rejection_reasons else "blocked",
        }
        for row in REQUIRED_MATRIX_ROWS
    ]
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 174,
            "matrix": matrix,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "policy": {
                "backward_read": ["Experiment 0.3a explicit migration input"],
                "current_execution": ["Experiment 0.3b", "Experiment 0.4"],
                "forward_rejection": True,
                "migration_command": "experiment-migrate",
                "no_silent_migration": True,
                "semver_scope": "package and CLI distribution only",
            },
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_COMPATIBILITY_POLICY_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1compatpolicy_"),
    }


def validate_v1_compatibility_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 compatibility policy evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 compatibility policy evidence must be an object")
    if document.get("schema_version") != V1_COMPATIBILITY_POLICY_SCHEMA_VERSION:
        raise ValueError("unsupported v1 compatibility policy schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1compatpolicy_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 compatibility policy evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 compatibility policy checks must be a list")
    matrix = document.get("matrix")
    if not isinstance(matrix, list):
        raise ValueError("v1 compatibility policy matrix must be a list")
    observed_rows = tuple(row.get("id") for row in matrix if isinstance(row, Mapping))
    if observed_rows != REQUIRED_MATRIX_ROWS:
        raise ValueError("v1 compatibility policy matrix rows are inconsistent")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 compatibility policy rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 compatibility policy passed is inconsistent")
    return document


def read_v1_compatibility_policy(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_compatibility_policy(value)


def write_v1_compatibility_policy(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_compatibility_policy(repo_root)
    validate_v1_compatibility_policy(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
