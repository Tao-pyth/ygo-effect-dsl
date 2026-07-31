from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_compatibility_policy
from ygo_effect_dsl.experiment import (
    assert_experiment_matches_route,
    load_experiment_document,
    resolve_experiment_overrides,
    validate_experiment,
)
from ygo_effect_dsl.route_dsl import load_route_document, validate_route_document
from ygo_effect_dsl.spikes.compatibility_policy_release_gate import (
    REQUIRED_MATRIX_ROWS,
    V1_COMPATIBILITY_POLICY_SCHEMA_VERSION,
    evaluate_v1_compatibility_policy,
    read_v1_compatibility_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_compatibility_policy.json"
)
SAMPLE = REPO_ROOT / "examples" / "experiments" / "real_core_effect_veiler.yaml"
ROUTE_SAMPLE = REPO_ROOT / "examples" / "route_dsl" / "minimal_route.yaml"


def test_v1_compatibility_policy_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_compatibility_policy(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_COMPATIBILITY_POLICY_SCHEMA_VERSION
    assert evidence["issue"] == 174
    assert evidence["passed"] is True
    assert evidence["evidence_id"].startswith("v1compatpolicy_")
    assert tuple(row["id"] for row in evidence["matrix"]) == REQUIRED_MATRIX_ROWS
    assert all(check["passed"] is True for check in checks.values())
    assert evidence["policy"]["migration_command"] == "experiment-migrate"
    assert evidence["policy"]["no_silent_migration"] is True


def test_committed_v1_compatibility_policy_matches_current_checkout() -> None:
    assert read_v1_compatibility_policy(
        EVIDENCE_PATH
    ) == evaluate_v1_compatibility_policy(REPO_ROOT)


def test_v1_compatibility_policy_cli_writes_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "v1-compatibility-policy.json"

    status = cmd_v1_compatibility_policy(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-compatibility-policy: passed" in captured.out
    assert read_v1_compatibility_policy(output) == evaluate_v1_compatibility_policy(
        REPO_ROOT
    )


def test_v1_compatibility_matrix_records_expected_boundaries() -> None:
    evidence = evaluate_v1_compatibility_policy(REPO_ROOT)
    matrix = {row["id"]: row for row in evidence["matrix"]}

    assert matrix["experiment_0_3a_backward_read_explicit_migration"][
        "requires_explicit_migration"
    ] is True
    assert matrix["experiment_0_3b_executable_compatibility"][
        "requires_explicit_migration"
    ] is False
    assert matrix["experiment_0_4_current"]["status"] == "verified"


def test_unknown_experiment_top_level_fields_are_rejected() -> None:
    experiment = load_experiment_document(SAMPLE)
    experiment["future_required_field"] = {"meaning": "not in 0.3b"}

    issues = validate_experiment(experiment)

    assert ("$.future_required_field", "unknown_experiment_field") in {
        (issue.path, issue.code) for issue in issues
    }


def test_future_experiment_schema_is_rejected() -> None:
    experiment = load_experiment_document(SAMPLE)
    future = deepcopy(experiment)
    future["schema_version"] = "9.9"

    issues = validate_experiment(future)

    assert ("$.schema_version", "unsupported_schema_version") in {
        (issue.path, issue.code) for issue in issues
    }


def test_future_route_schema_is_rejected() -> None:
    route = load_route_document(ROUTE_SAMPLE)
    route["schema_version"] = "9.9"

    issues = validate_route_document(route)

    assert ("$.schema_version", "unsupported_schema_version") in {
        (issue.path, issue.code) for issue in issues
    }


def test_route_experiment_mismatch_is_rejected() -> None:
    route = load_route_document(ROUTE_SAMPLE)
    experiment = deepcopy(route["experiment"])
    route["experiment"]["experiment_id"] = "different_experiment"

    try:
        assert_experiment_matches_route(experiment, route)
    except ValueError as exc:
        assert "Experiment file does not match Route DSL experiment" in str(exc)
    else:  # pragma: no cover - the assertion above should always raise
        raise AssertionError("mismatched Experiment and Route were accepted")


def test_v03a_readable_but_current_execution_requires_explicit_migration() -> None:
    legacy = load_experiment_document(SAMPLE)
    legacy["schema_version"] = "0.3a"
    legacy.pop("information_policy")

    assert validate_experiment(legacy) == ()
    try:
        resolve_experiment_overrides(legacy)
    except ValueError as exc:
        assert "explicitly migrate" in str(exc)
    else:  # pragma: no cover - the assertion above should always raise
        raise AssertionError("0.3a Experiment executed without explicit migration")
