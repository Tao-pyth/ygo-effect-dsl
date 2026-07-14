from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ygo_effect_dsl.prototype import (
    build_prototype_route,
    dump_route_document,
    load_prototype_scenario,
    verify_prototype_route,
)
from ygo_effect_dsl.route_dsl import load_route_document, validate_route_document


SCENARIO = REPO_ROOT / "examples" / "prototype" / "fixed_hand_normal_summon.yaml"


def test_prototype_builds_valid_deterministic_route() -> None:
    scenario = load_prototype_scenario(SCENARIO)

    first = build_prototype_route(scenario)
    second = build_prototype_route(scenario)

    assert first == second
    assert validate_route_document(first) == ()
    assert first["status"] == "complete"
    assert first["result"]["success"] is True
    assert first["result"]["peak_board"]["checkpoint_step"] == 0
    assert first["replay"]["events"][0]["request_signature"].startswith("req_")
    assert first["replay"]["events"][0]["action_id"].startswith("act_")
    aggregation = first["presentation"]["action_aggregation"]
    assert aggregation["groups"][0]["atomic_steps"] == [0]
    assert aggregation["links"][0]["step"] == 0
    assert first["presentation"]["validation"] == {
        "status": "provisional",
        "issue": 92,
    }
    assert first["experiment"]["prototype"]["requires_validation"] is True


def test_prototype_yaml_round_trip_and_fresh_replay_verification(tmp_path: Path) -> None:
    scenario = load_prototype_scenario(SCENARIO)
    route = build_prototype_route(scenario)
    destination = tmp_path / "route.yaml"
    dump_route_document(route, destination)

    loaded = load_route_document(destination)
    result = verify_prototype_route(scenario, loaded)

    assert result.route_id == route["route_id"]
    assert result.event_count == 1
    assert result.final_state_hash == route["replay"]["events"][0]["state_hash_after"]


def test_prototype_verification_rejects_tampered_route() -> None:
    scenario = load_prototype_scenario(SCENARIO)
    route = build_prototype_route(scenario)
    route["checkpoints"][0]["board_summary"]["players"]["player_0"]["hand"] = ["tampered"]

    with pytest.raises(ValueError, match="fresh deterministic replay"):
        verify_prototype_route(scenario, route)


def test_route_validation_rejects_tampered_action_aggregation_link() -> None:
    scenario = load_prototype_scenario(SCENARIO)
    route = build_prototype_route(scenario)
    route["presentation"]["action_aggregation"]["links"][0]["part_index"] = 1

    issues = validate_route_document(route)

    assert "action_group_link_mismatch" in {issue.code for issue in issues}


def test_route_validation_rejects_tampered_replay_response_trace() -> None:
    scenario = load_prototype_scenario(SCENARIO)
    route = build_prototype_route(scenario)
    route["replay"]["events"][0]["core_response"]["request_signature"] = "req_tampered"

    issues = validate_route_document(route)

    assert "invalid_replay_io_trace" in {issue.code for issue in issues}


def test_prototype_cli_generates_and_verifies_in_separate_processes(tmp_path: Path) -> None:
    route_path = tmp_path / "route.yaml"
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}

    generated = subprocess.run(
        [
            sys.executable,
            "-m",
            "ygo_effect_dsl",
            "prototype-run",
            str(SCENARIO),
            "--out",
            str(route_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    verified = subprocess.run(
        [
            sys.executable,
            "-m",
            "ygo_effect_dsl",
            "prototype-verify",
            str(SCENARIO),
            str(route_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert generated.returncode == 0, generated.stdout + generated.stderr
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "prototype-run: ok" in generated.stdout
    assert "prototype-verify: ok" in verified.stdout
    assert yaml.safe_load(route_path.read_text(encoding="utf-8"))["status"] == "complete"
