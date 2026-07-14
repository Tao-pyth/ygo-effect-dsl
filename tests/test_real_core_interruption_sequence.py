from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from ygo_effect_dsl.engine.interruption import build_interruption_comparison
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import build_real_core_route
from ygo_effect_dsl.prototype.real_core import _resolve_interruption_plans
from ygo_effect_dsl.route_dsl import validate_route_document


EXPERIMENTS = Path(__file__).parents[1] / "examples" / "experiments"
SEQUENCE_EXPERIMENTS = {
    name: EXPERIMENTS / f"real_core_interruption_sequence_{name}.yaml"
    for name in ("control", "stage1", "stage2")
}


@pytest.fixture(scope="module")
def sequence_routes() -> dict[str, dict[str, Any]]:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    return {
        name: build_real_core_route(
            experiment=load_experiment_document(path)
        )
        for name, path in SEQUENCE_EXPERIMENTS.items()
    }


def test_two_interruptions_form_control_child_grandchild_lineage(
    sequence_routes: dict[str, dict[str, Any]],
) -> None:
    control = sequence_routes["control"]
    stage1 = sequence_routes["stage1"]
    stage2 = sequence_routes["stage2"]

    assert control["route_id"] == (
        "route_9967b36a2fe7c032765ecf1dcb3dfe677fdafc2eb10168694d0c24eb82d5cd36"
    )
    assert stage1["route_id"] == (
        "route_a12d4341b6781fbeca5b1fa96cd5c4f08fc89674222e371238147a2a6ef71f87"
    )
    assert stage2["route_id"] == (
        "route_6932cc27ad8ddce92d78d14fb8c34dd2a172b73483fd808a5aa1d0698fd9bb82"
    )
    assert stage1["lineage"] == {
        "fork_step": 5,
        "parent_route_id": control["route_id"],
    }
    assert stage2["lineage"] == {
        "fork_step": 9,
        "parent_route_id": stage1["route_id"],
    }
    assert [
        event["action_id"] for event in control["replay"]["events"][:5]
    ] == [event["action_id"] for event in stage1["replay"]["events"][:5]]
    assert [
        event["action_id"] for event in stage1["replay"]["events"][:9]
    ] == [event["action_id"] for event in stage2["replay"]["events"][:9]]


def test_second_stage_inherits_first_interruption_and_adds_cost_response(
    sequence_routes: dict[str, dict[str, Any]],
) -> None:
    stage1 = sequence_routes["stage1"]
    stage2 = sequence_routes["stage2"]

    assert stage2["interruptions"][0] == stage1["interruptions"][0]
    assert stage2["interruptions"][1]["at_step"] == 9
    assert stage2["interruptions"][1]["response_steps"] == [
        {
            "action_step": 10,
            "candidate_ids": ["card:0"],
            "response_index": 0,
            "role": "cost",
        }
    ]
    comparison = build_interruption_comparison(stage1, stage2)
    assert comparison["fork_step"] == 9
    assert comparison["interruption"]["interruption_id"] == (
        "sequence_cost_stage2"
    )


def test_staged_definition_order_and_parent_fail_closed() -> None:
    experiment = load_experiment_document(SEQUENCE_EXPERIMENTS["stage2"])
    reversed_definitions = deepcopy(experiment)
    reversed_definitions["interruption"]["definitions"].reverse()

    with pytest.raises(
        ValueError,
        match=r"\$\.interruption\.definitions\[1\]\.target\.step",
    ):
        _resolve_interruption_plans(reversed_definitions)


def test_validator_rejects_tampered_final_stage_parent(
    sequence_routes: dict[str, dict[str, Any]],
) -> None:
    tampered = deepcopy(sequence_routes["stage2"])
    tampered["lineage"]["parent_route_id"] = sequence_routes["control"][
        "route_id"
    ]

    assert "interruption_parent_route_mismatch" in {
        issue.code for issue in validate_route_document(tampered)
    }


def test_two_interruption_route_identity_is_deterministic(
    sequence_routes: dict[str, dict[str, Any]],
) -> None:
    experiment = load_experiment_document(SEQUENCE_EXPERIMENTS["stage2"])
    replayed = build_real_core_route(experiment=experiment)

    assert replayed["route_id"] == sequence_routes["stage2"]["route_id"]
    assert replayed["replay"] == sequence_routes["stage2"]["replay"]
