from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind
from ygo_effect_dsl.experiment import load_experiment_document, preflight_scenario
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import (
    RealCoreFrontierAdapter,
    RealCorePlayerViewAdapter,
    verify_general_search_route,
)


ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "examples/experiments/board_break_corpus.yaml"
RAIGEKI = 12580477
MYSTICAL_SPACE_TYPHOON = 5318639
CALLED_BY_THE_GRAVE = 24224830
ASH_BLOSSOM = 14558127
SWORDS_OF_REVEALING_LIGHT = 72302403
MAXX_C = 23434538
SOLEMN_JUDGMENT = 41420027


def _runtime_or_skip() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")


def _action_uses_card(action: Action, card_code: int) -> bool:
    return any(
        selection.card_ref is not None
        and selection.card_ref.public_card_id == card_code
        for selection in action.selections
    )


def _semantic_action(action: Action) -> dict[str, Any]:
    def card_ref(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        return {
            "controller": value.controller,
            "location": value.location,
            "owner": value.owner,
            "public_card_id": value.public_card_id,
            "sequence": value.sequence,
        }

    return {
        "effect_index": (
            action.effect_ref.effect_index if action.effect_ref is not None else None
        ),
        "kind": action.kind.value,
        "player": action.player,
        "selections": [
            {
                "card_ref": card_ref(selection.card_ref),
                "effect_index": (
                    selection.effect_ref.effect_index
                    if selection.effect_ref is not None
                    else None
                ),
                "order": selection.order,
                "value": selection.value,
            }
            for selection in action.selections
        ],
        "source": card_ref(action.source),
    }


def _run_corpus_route(experiment: dict[str, Any]) -> tuple[dict[str, Any], list[Action]]:
    adapter = RealCoreFrontierAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )
    desired = [MYSTICAL_SPACE_TYPHOON, CALLED_BY_THE_GRAVE, RAIGEKI]
    targets = {
        MYSTICAL_SPACE_TYPHOON: SWORDS_OF_REVEALING_LIGHT,
        CALLED_BY_THE_GRAVE: MAXX_C,
    }
    prefix: list[Action] = []
    desired_index = 0
    pending_target: int | None = None
    solemn_activated = False
    interrupted = experiment["interruption"]["mode"] == "specified"
    for _step in range(48):
        frontier = adapter.replay(experiment, prefix)
        request_type = frontier.request["request_type"]
        action = None
        if request_type in {"select_place", "select_disabled_field"}:
            action = frontier.actions[0]
        elif request_type == "select_card" and pending_target is not None:
            action = next(
                candidate
                for candidate in frontier.actions
                if _action_uses_card(candidate, pending_target)
            )
            pending_target = None
        elif interrupted and not solemn_activated and desired_index == len(desired):
            action = next(
                (
                    candidate
                    for candidate in frontier.actions
                    if candidate.kind == ActionKind.ACTIVATE_EFFECT
                    and _action_uses_card(candidate, SOLEMN_JUDGMENT)
                ),
                None,
            )
            solemn_activated = action is not None
        if action is None and desired_index < len(desired):
            card_code = desired[desired_index]
            action = next(
                (
                    candidate
                    for candidate in frontier.actions
                    if candidate.kind == ActionKind.ACTIVATE_EFFECT
                    and _action_uses_card(candidate, card_code)
                ),
                None,
            )
            if action is not None:
                desired_index += 1
                pending_target = targets.get(card_code)
        if action is None and desired_index == len(desired) and frontier.legal_stop:
            assert frontier.route_document is not None
            return dict(frontier.route_document), prefix
        if action is None:
            action = next(
                (
                    candidate
                    for candidate in frontier.actions
                    if candidate.kind == ActionKind.PASS
                ),
                frontier.actions[0],
            )
        prefix.append(action)
    raise AssertionError("board-break corpus did not reach a legal stop")


@pytest.fixture(scope="module")
def board_break_routes() -> dict[str, Any]:
    _runtime_or_skip()
    baseline_experiment = load_experiment_document(EXPERIMENT)
    baseline_experiment["success_predicate"]["config"] = {
        "actor_player": 0,
        "max_opponent_monsters": 0,
        "max_opponent_spell_traps": 0,
        "min_opponent_banished": 1,
    }
    interrupted_experiment = deepcopy(baseline_experiment)
    interrupted_experiment["interruption"] = {
        "mode": "specified",
        "definitions": [
            {
                "id": "solemn_judgment_on_raigeki",
                "source_card_code": SOLEMN_JUDGMENT,
                "source_player": 1,
                "source_zone": "field",
                "core_location": 8,
                "sequence": 4,
                "position": 8,
                "response_roles": [],
            }
        ],
    }
    baseline, baseline_prefix = _run_corpus_route(baseline_experiment)
    interrupted, interrupted_prefix = _run_corpus_route(interrupted_experiment)
    return {
        "baseline": baseline,
        "baseline_prefix": baseline_prefix,
        "interrupted": interrupted,
        "interrupted_experiment": interrupted_experiment,
        "interrupted_prefix": interrupted_prefix,
    }


def test_board_break_manifest_pins_public_snapshot() -> None:
    _runtime_or_skip()
    experiment = load_experiment_document(EXPERIMENT)

    preflight = preflight_scenario(experiment, experiment_path=EXPERIMENT)

    assert preflight.ok
    assert preflight.manifest is not None
    assert preflight.manifest.initial_state_id.startswith("boardbreakstate_")
    assert {
        card["card_code"]
        for card in preflight.manifest.initial_state["public_cards"]
    } == {ASH_BLOSSOM, SWORDS_OF_REVEALING_LIGHT, MAXX_C}
    assert preflight.manifest.initial_state["turn_player"] == 0


def test_official_card_corpus_covers_targetless_targeting_and_grave_banish(
    board_break_routes: dict[str, Any],
) -> None:
    route = board_break_routes["baseline"]
    actions = [event["action"] for event in route["replay"]["events"]]
    activated_codes = {
        selection["card_ref"]["public_card_id"]
        for action in actions
        if action["kind"] == "ACTIVATE_EFFECT"
        for selection in action["selections"]
        if selection.get("card_ref") is not None
    }
    selected_codes = {
        selection["card_ref"]["public_card_id"]
        for action in actions
        if action["kind"] == "SELECT_CARD"
        for selection in action["selections"]
        if selection.get("card_ref") is not None
    }
    terminal = route["result"]["terminal_board"]

    assert {RAIGEKI, MYSTICAL_SPACE_TYPHOON, CALLED_BY_THE_GRAVE} <= activated_codes
    assert {SWORDS_OF_REVEALING_LIGHT, MAXX_C} <= selected_codes
    assert terminal["success"] is True
    assert terminal["evaluation"]["opponent_monster_count"] == 0
    assert terminal["evaluation"]["opponent_spell_trap_count"] == 0
    assert terminal["evaluation"]["opponent_banished_count"] >= 1
    verification = verify_general_search_route(route, experiment_path=EXPERIMENT)
    assert verification.route_id == route["route_id"]


def test_specified_hidden_interruption_changes_route_without_player_view_leak(
    board_break_routes: dict[str, Any],
) -> None:
    baseline = board_break_routes["baseline"]
    interrupted = board_break_routes["interrupted"]
    trace = interrupted["presentation"]["specified_interruption_trace"]

    assert baseline["result"]["terminal_board"]["success"] is True
    assert interrupted["result"]["terminal_board"]["success"] is False
    assert baseline["route_id"] != interrupted["route_id"]
    assert len(trace) == 1
    assert trace[0]["definition_id"] == "solemn_judgment_on_raigeki"
    assert trace[0]["source_card_code"] == SOLEMN_JUDGMENT
    baseline_prefix = board_break_routes["baseline_prefix"]
    interrupted_prefix = board_break_routes["interrupted_prefix"]
    desired = [MYSTICAL_SPACE_TYPHOON, CALLED_BY_THE_GRAVE, RAIGEKI]
    baseline_activation_order = [
        card_code
        for action in baseline_prefix
        if action.kind == ActionKind.ACTIVATE_EFFECT and action.player == 0
        for card_code in desired
        if _action_uses_card(action, card_code)
    ]
    interrupted_activation_order = [
        card_code
        for action in interrupted_prefix
        if action.kind == ActionKind.ACTIVATE_EFFECT and action.player == 0
        for card_code in desired
        if _action_uses_card(action, card_code)
    ]
    assert baseline_activation_order == desired
    assert interrupted_activation_order == desired
    baseline_anchor = next(
        index
        for index, action in enumerate(baseline_prefix)
        if _action_uses_card(action, RAIGEKI)
    )
    interrupted_anchor = next(
        index
        for index, action in enumerate(interrupted_prefix)
        if _action_uses_card(action, RAIGEKI)
    )
    assert _semantic_action(baseline_prefix[baseline_anchor]) == _semantic_action(
        interrupted_prefix[interrupted_anchor]
    )
    baseline_response_index = next(
        index
        for index in range(baseline_anchor + 1, len(baseline_prefix))
        if baseline_prefix[index].kind == ActionKind.PASS
    )
    interrupted_response_index = next(
        index
        for index in range(interrupted_anchor + 1, len(interrupted_prefix))
        if interrupted_prefix[index].kind == ActionKind.ACTIVATE_EFFECT
        and _action_uses_card(interrupted_prefix[index], SOLEMN_JUDGMENT)
    )
    assert [
        _semantic_action(action)
        for action in baseline_prefix[baseline_anchor + 1 : baseline_response_index]
    ] == [
        _semantic_action(action)
        for action in interrupted_prefix[
            interrupted_anchor + 1 : interrupted_response_index
        ]
    ]
    baseline_response = baseline_prefix[baseline_response_index]
    interrupted_response = interrupted_prefix[interrupted_response_index]
    assert baseline_response.kind == ActionKind.PASS
    assert interrupted_response.kind == ActionKind.ACTIVATE_EFFECT
    assert _action_uses_card(
        interrupted_response, SOLEMN_JUDGMENT
    )
    player_view = RealCorePlayerViewAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    ).project(interrupted, viewer=0)
    public_json = json.dumps(player_view.player_view, sort_keys=True)
    assert str(SOLEMN_JUDGMENT) not in public_json
    assert player_view.information_audit["status"] == "passed"
