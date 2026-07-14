from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ygo_effect_dsl.route_dsl import load_route_document, validate_route_document


EXAMPLE = REPO_ROOT / "examples" / "route_dsl" / "minimal_route.yaml"


def test_minimal_route_example_is_valid() -> None:
    document = load_route_document(EXAMPLE)

    assert validate_route_document(document) == ()


def test_route_rejects_action_request_signature_mismatch() -> None:
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    document["replay"]["events"][0]["action"]["request_signature"] = "req_other"

    issues = validate_route_document(document)

    assert "request_signature_mismatch" in {issue.code for issue in issues}


def test_route_rejects_invalid_experiment_with_specific_code() -> None:
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    del document["experiment"]["deck"]

    issues = validate_route_document(document)

    assert "experiment_required_field" in {issue.code for issue in issues}
    assert "$.experiment.deck" in {issue.path for issue in issues}


def test_route_rejects_peak_board_checkpoint_mismatch() -> None:
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    document["result"]["peak_board"]["state_hash"] = "state_other"

    issues = validate_route_document(document)

    assert "checkpoint_state_mismatch" in {issue.code for issue in issues}


def test_route_rejects_checkpoint_replay_state_mismatch() -> None:
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    document["checkpoints"][0]["state_hash"] = "state_other"

    issues = validate_route_document(document)

    assert "replay_state_mismatch" in {issue.code for issue in issues}


def test_route_rejects_durability_checkpoint_mismatch() -> None:
    document = load_route_document(
        REPO_ROOT
        / "examples"
        / "prototype"
        / "real_core_effect_veiler.route.yaml"
    )
    document["result"]["durability"]["after"]["turn"] = 3

    issues = validate_route_document(document)

    assert "checkpoint_value_mismatch" in {issue.code for issue in issues}


def test_route_rejects_tampered_temporary_effect_report() -> None:
    document = load_route_document(
        REPO_ROOT
        / "examples"
        / "prototype"
        / "real_core_effect_veiler.route.yaml"
    )
    temporary = document["result"]["evaluation_explanation"]["temporary_effects"]
    temporary["values"]["field_count"]["durable"] = 99

    issues = validate_route_document(document)

    assert "invalid_temporary_effect_report" in {issue.code for issue in issues}


def test_route_rejects_tampered_score_breakdown() -> None:
    document = load_route_document(
        REPO_ROOT
        / "examples"
        / "prototype"
        / "real_core_effect_veiler.route.yaml"
    )
    result = document["checkpoints"][5]["evaluation_result"]
    result["score_breakdown"]["terms"][0]["contribution"] = 999

    issues = validate_route_document(document)

    assert "invalid_evaluation_result" in {issue.code for issue in issues}


def test_current_route_requires_matching_information_policy_ids() -> None:
    route_path = (
        REPO_ROOT
        / "examples"
        / "prototype"
        / "real_core_effect_veiler.route.yaml"
    )
    document = load_route_document(route_path)
    assert document["experiment"]["schema_version"] == "0.3b"
    expected = document["experiment"]["information_policy"]["policy_id"]

    assert document["replay"]["information_policy_id"] == expected
    assert document["replay"]["manifest"]["initial_conditions"][
        "information_policy_id"
    ] == expected
    assert document["information_audit"]["policy"]["policy_id"] == expected

    document["replay"]["information_policy_id"] = "infopol_tampered"
    issues = validate_route_document(document)
    assert "information_policy_id_mismatch" in {issue.code for issue in issues}


def test_route_rejects_action_occurrence_id_mismatch() -> None:
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    event = document["replay"]["events"][0]
    event.update(
        action_occurrence_id="aocc_tampered",
        turn=1,
        turn_action_index=0,
        chain_index=0,
    )

    issues = validate_route_document(document)

    assert "action_occurrence_id_mismatch" in {issue.code for issue in issues}


def test_validate_route_cli_accepts_example() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ygo_effect_dsl", "validate-route", str(EXAMPLE)],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "validate-route: ok route_id=route_example_normal_summon" in completed.stdout
