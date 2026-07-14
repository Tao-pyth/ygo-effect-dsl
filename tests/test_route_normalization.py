from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from ygo_effect_dsl.route_dsl import (
    load_route_document,
    normalize_and_explain_routes,
    validate_route_document,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = yaml.safe_load(
    (REPO_ROOT / "examples" / "route_dsl" / "minimal_route.yaml").read_text(
        encoding="utf-8"
    )
)


def _route(
    route_id: str,
    action_kinds: tuple[str, ...],
    *,
    target_state_id: str,
    score: int | float,
) -> dict[str, object]:
    document = deepcopy(BASE)
    template = deepcopy(document["replay"]["events"][0])
    events = []
    state_before = "state_opening_hand"
    for step, kind in enumerate(action_kinds):
        event = deepcopy(template)
        state_after = (
            target_state_id
            if step == len(action_kinds) - 1
            else f"state_{route_id}_{step}"
        )
        request_signature = f"req_{route_id}_{step}"
        event["step"] = step
        event["request_signature"] = request_signature
        event["action"]["action_id"] = f"act_{route_id}_{step}_{kind.lower()}"
        event["action"]["kind"] = kind
        event["action"]["request_signature"] = request_signature
        event["state_hash_before"] = state_before
        event["state_hash_after"] = state_after
        events.append(event)
        state_before = state_after
    document["route_id"] = route_id
    document["replay"]["events"] = events
    checkpoint = document["checkpoints"][0]
    checkpoint["step"] = len(events) - 1
    checkpoint["state_hash"] = target_state_id
    for name in ("peak_board", "terminal_board"):
        document["result"][name]["checkpoint_step"] = len(events) - 1
        document["result"][name]["state_hash"] = target_state_id
        document["result"][name]["score"] = score
    assert validate_route_document(document) == ()
    return document


def test_same_exact_board_merges_choice_order_variants_and_explains_differences() -> None:
    first = _route(
        "route_first",
        ("NORMAL_SUMMON", "PASS"),
        target_state_id="state_shared_board",
        score=20,
    )
    reversed_order = _route(
        "route_reversed",
        ("PASS", "NORMAL_SUMMON"),
        target_state_id="state_shared_board",
        score=20,
    )

    report = normalize_and_explain_routes(
        [first, reversed_order],
        resource_costs={"route_first": 1, "route_reversed": 2},
    )

    assert report["schema_version"] == "route-normalization-v2"
    assert report["resource_measurement_mode"] == "external"
    assert len(report["groups"]) == 1
    group = report["groups"][0]
    assert group["merge_reason"] == "exact_target_state"
    assert group["route_ids"] == ["route_first", "route_reversed"]
    assert group["branch_points"]
    assert group["branch_points"][0]["reconvergence"] == {
        "kind": "exact_target_state",
        "state_id": "state_shared_board",
    }
    assert group["alternatives"][0]["differences"]
    assert report["report_id"].startswith("routenorm_")


def test_global_rankings_separate_shortest_resource_and_highest_score() -> None:
    shortest = _route(
        "route_shortest",
        ("NORMAL_SUMMON",),
        target_state_id="state_short",
        score=10,
    )
    cheapest = _route(
        "route_cheapest",
        ("NORMAL_SUMMON", "PASS"),
        target_state_id="state_cheap",
        score=20,
    )
    strongest = _route(
        "route_strongest",
        ("NORMAL_SUMMON", "PASS", "END_TURN"),
        target_state_id="state_strong",
        score=30,
    )

    report = normalize_and_explain_routes(
        [strongest, shortest, cheapest],
        resource_costs={
            "route_shortest": 4,
            "route_cheapest": 1,
            "route_strongest": 3,
        },
    )

    assert report["rankings"]["shortest"]["route_ids"] == ["route_shortest"]
    assert report["rankings"]["minimum_consumption"]["route_ids"] == [
        "route_cheapest"
    ]
    assert report["rankings"]["highest_score"]["route_ids"] == [
        "route_strongest"
    ]


def test_resource_ranking_is_explicitly_unavailable_without_all_measurements() -> None:
    first = _route(
        "route_a", ("PASS",), target_state_id="state_a", score=1
    )
    second = _route(
        "route_b", ("END_TURN",), target_state_id="state_b", score=2
    )

    report = normalize_and_explain_routes(
        [first, second], resource_costs={"route_a": 1}
    )

    ranking = report["rankings"]["minimum_consumption"]
    assert ranking["status"] == "unavailable_missing_measurement"
    assert ranking["missing_route_ids"] == ["route_b"]
    assert ranking["reason"] == "external_resource_cost_not_supplied"


def test_scores_from_different_evaluation_contexts_are_not_compared() -> None:
    first = _route(
        "route_v1", ("PASS",), target_state_id="state_a", score=1
    )
    second = _route(
        "route_v2", ("END_TURN",), target_state_id="state_b", score=999
    )
    second["experiment"]["evaluator"]["version"] = "2"

    report = normalize_and_explain_routes([first, second])

    assert report["rankings"]["highest_score"]["status"] == (
        "unavailable_incomparable_evaluation_contexts"
    )


def test_same_state_and_evaluator_reject_inconsistent_scores() -> None:
    first = _route(
        "route_a", ("PASS",), target_state_id="state_shared", score=1
    )
    second = _route(
        "route_b", ("END_TURN",), target_state_id="state_shared", score=2
    )

    with pytest.raises(ValueError, match="same exact target State"):
        normalize_and_explain_routes([first, second])


def test_duplicate_route_id_and_unknown_resource_cost_are_rejected() -> None:
    route = _route("route_a", ("PASS",), target_state_id="state_a", score=1)

    with pytest.raises(ValueError, match="route_id must be unique"):
        normalize_and_explain_routes([route, deepcopy(route)])
    with pytest.raises(ValueError, match="unknown routes"):
        normalize_and_explain_routes([route], resource_costs={"route_typo": 1})


def test_real_core_route_uses_composite_action_comparison_basis() -> None:
    route = load_route_document(
        REPO_ROOT
        / "examples"
        / "prototype"
        / "real_core_effect_veiler.route.yaml"
    )

    report = normalize_and_explain_routes([route])

    assert report["groups"][0]["comparison_basis"] == "composite_action"
    assert report["groups"][0]["routes"][0]["action_count"] == 8
    assert report["resource_measurement_mode"] == "recalculated_from_route"
    assert report["resource_metric"] == "resource_consumption_v1"
    assert report["groups"][0]["routes"][0]["resource_cost"] == 2.0
    assert report["groups"][0]["routes"][0]["resource_report_id"].startswith(
        "resourceeval_"
    )
