from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import build_real_core_route, verify_real_core_route
from ygo_effect_dsl.route_dsl import assert_valid_route_document


EXPERIMENT = (
    Path(__file__).parents[1]
    / "examples"
    / "experiments"
    / "real_core_action_aggregation_selection_edges.yaml"
)
TARGET_LOSS_EXPERIMENTS = {
    name: (
        Path(__file__).parents[1]
        / "examples"
        / "experiments"
        / f"real_core_action_aggregation_target_loss{suffix}.yaml"
    )
    for name, suffix in (("control", "_control"), ("interrupted", ""))
}


@pytest.fixture(scope="module")
def selection_edge_route() -> dict[str, Any]:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    return build_real_core_route(
        experiment=load_experiment_document(EXPERIMENT)
    )


@pytest.fixture(scope="module")
def target_loss_routes() -> dict[str, dict[str, Any]]:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    return {
        name: build_real_core_route(
            experiment=load_experiment_document(path)
        )
        for name, path in TARGET_LOSS_EXPERIMENTS.items()
    }


def test_repeated_cost_and_resolution_selections_use_distinct_core_groups(
    selection_edge_route: dict[str, Any],
) -> None:
    route = selection_edge_route
    assert_valid_route_document(route)
    assert route["route_id"] == (
        "route_0ec912d6b69cde4a3bce62d05937861afe932618b191504f9a5c3c148639a77b"
    )

    groups = route["presentation"]["action_aggregation"]["groups"]
    activation = next(group for group in groups if group["atomic_steps"] == [4, 5, 6])
    resolution = next(group for group in groups if group["atomic_steps"] == [9, 10])
    assert [part["role"] for part in activation["parts"]] == [
        "primary",
        "cost",
        "cost",
    ]
    assert [part["role"] for part in resolution["parts"]] == [
        "resolution",
        "resolution",
    ]

    evidence = route["presentation"]["action_aggregation_evidence"]
    assert [boundary["group_kind"] for boundary in evidence["group_boundaries"]] == [
        "activation_setup",
        "resolution",
    ]
    assert [boundary["end_message_type"] for boundary in evidence["group_boundaries"]] == [
        71,
        74,
    ]
    assert [item["message_name"] for item in evidence["chain_lifecycle"]] == [
        "MSG_CHAINING",
        "MSG_CHAINED",
        "MSG_CHAIN_SOLVING",
        "MSG_CHAIN_SOLVED",
        "MSG_CHAIN_END",
    ]


def test_selection_edge_manifest_pins_runtime_assets_and_fixture(
    selection_edge_route: dict[str, Any],
) -> None:
    manifest = selection_edge_route["replay"]["manifest"]
    environment = manifest["environment"]

    assert manifest["reproducible"] is True
    assert manifest["randomness"]["core_seed"] == [1, 2, 3, 4]
    assert environment["core"]["api"] == "11.0"
    assert environment["core"]["binary_sha256"]
    assert environment["assets"]["card_database_commit"]
    assert environment["assets"]["database_sha256"]
    fixture = environment["fixture_script"]
    assert fixture["id"] == "action_aggregation_selection_edges_v1"
    assert fixture["name"] == "c97268402.lua"
    assert fixture["purpose"] == (
        "repeated_cost_and_resolution_selection_action_aggregation"
    )
    assert fixture["sha256"] == (
        "94f6ec5f4b482e40b32ea41f572e9676b888b8e6d04eb41fdd3b2c10041034bd"
    )
    assert fixture["card_database_rows"] == [
        {
            "alias": 0,
            "atk": 0,
            "attribute": 16,
            "def": 0,
            "id": 97268402,
            "level": 1,
            "race": 2,
            "setcode": 0,
            "type": 4129,
        }
    ]


def test_selection_edge_route_matches_fresh_real_core_worker(
    selection_edge_route: dict[str, Any],
) -> None:
    verified = verify_real_core_route(selection_edge_route)
    rebuilt = build_real_core_route(
        experiment=load_experiment_document(EXPERIMENT)
    )

    assert verified.route_id == selection_edge_route["route_id"]
    assert verified.event_count == 15
    assert rebuilt["route_id"] == selection_edge_route["route_id"]
    assert rebuilt["replay"] == selection_edge_route["replay"]


def test_target_loss_fizzle_is_separate_from_negated_and_disabled_lifecycles(
    target_loss_routes: dict[str, dict[str, Any]],
) -> None:
    control = target_loss_routes["control"]
    interrupted = target_loss_routes["interrupted"]

    assert control["route_id"] == (
        "route_b03ee526064cbccbe4b5242875f313fd3ae4ce78545de5817ba195a714438553"
    )
    assert interrupted["route_id"] == (
        "route_5c6737e3a888dc919dfdf6f19c0c9d1ea2178738a45eaa2aa7cdb933fd847b43"
    )
    assert interrupted["lineage"] == {
        "fork_step": 6,
        "parent_route_id": control["route_id"],
    }
    assert control["result"]["terminal_board"]["evaluation"]["field_count"] == 2
    assert interrupted["result"]["terminal_board"]["evaluation"]["field_count"] == 1

    resolution_event = interrupted["replay"]["events"][9]
    assert resolution_event["state_hash_before"] == (
        "state_eaa4a3361b49b489caccabb3345b744bf4b78b8bbe481f844e7284134c10e523"
    )
    assert resolution_event["state_hash_after"] == (
        "state_983dcc4a0f5d113ad411ef9c25f84e2f0b50df095d384b81645b52a8906297d8"
    )
    assert [
        frame["message_type"]
        for frame in resolution_event["core_output"]["frames"]
    ] == [72, 50, 73, 72, 73, 74, 16]
    move = resolution_event["core_output"]["frames"][1]
    assert move["payload_hex"] == (
        "d1c27805000400000000010000000020000000000500000040000000"
    )

    lifecycle = interrupted["presentation"]["action_aggregation_evidence"][
        "chain_lifecycle"
    ]
    lifecycle_names = [item["message_name"] for item in lifecycle]
    assert lifecycle_names.count("MSG_CHAINED") == 2
    assert "MSG_CHAIN_NEGATED" not in lifecycle_names
    assert "MSG_CHAIN_DISABLED" not in lifecycle_names
    assert lifecycle_names[-5:] == [
        "MSG_CHAIN_SOLVING",
        "MSG_CHAIN_SOLVED",
        "MSG_CHAIN_SOLVING",
        "MSG_CHAIN_SOLVED",
        "MSG_CHAIN_END",
    ]


def test_target_loss_route_pins_scripts_and_matches_fresh_worker(
    target_loss_routes: dict[str, dict[str, Any]],
) -> None:
    route = target_loss_routes["interrupted"]
    assert_valid_route_document(route)
    fixture = route["replay"]["manifest"]["environment"]["fixture_script"]

    assert fixture["id"] == "action_aggregation_target_loss_v1"
    assert fixture["purpose"] == "target_loss_fizzle_action_aggregation"
    assert fixture["sha256"] == (
        "e4255a572d349dc77679b94000ba1d8d3f7bd305cc0010570c055438c243e1e5"
    )
    assert [script["card_code"] for script in fixture["scripts"]] == [
        10045474,
        23434538,
        91800273,
    ]
    assert [row["id"] for row in fixture["card_database_rows"]] == [
        10045474,
        23434538,
        91800273,
    ]

    verified = verify_real_core_route(route)
    assert verified.route_id == route["route_id"]
    assert verified.event_count == 14
