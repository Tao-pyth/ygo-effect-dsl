from __future__ import annotations

from pathlib import Path

import pytest

from ygo_effect_dsl.engine.action import ActionKind
from ygo_effect_dsl.experiment import load_experiment_document, preflight_scenario
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import (
    RealCoreFrontierAdapter,
    verify_general_search_route,
)


ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "examples/experiments/general_search_inline.yaml"


def _runtime_or_skip() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")


def test_fresh_real_core_frontier_replays_prefix_to_a_valid_route() -> None:
    _runtime_or_skip()
    experiment = load_experiment_document(EXPERIMENT)
    preflight = preflight_scenario(experiment, experiment_path=EXPERIMENT)
    assert preflight.ok
    adapter = RealCoreFrontierAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )

    root = adapter.replay(experiment, ())
    first_pass = next(action for action in root.actions if action.kind == ActionKind.PASS)
    standby = adapter.replay(experiment, (first_pass,))
    second_pass = next(
        action for action in standby.actions if action.kind == ActionKind.PASS
    )
    main_phase = adapter.replay(experiment, (first_pass, second_pass))
    summon = next(
        action for action in main_phase.actions if action.kind == ActionKind.NORMAL_SUMMON
    )
    prefix = [first_pass, second_pass, summon]
    terminal = adapter.replay(experiment, prefix)
    for _ in range(6):
        if terminal.legal_stop:
            break
        next_action = next(
            (action for action in terminal.actions if action.kind == ActionKind.PASS),
            terminal.actions[0],
        )
        prefix.append(next_action)
        terminal = adapter.replay(experiment, prefix)

    assert root.request["request_type"] == "select_chain"
    assert main_phase.request["request_type"] == "select_idle_command"
    assert terminal.legal_stop
    assert terminal.success
    assert terminal.route_document is not None
    verification = verify_general_search_route(
        terminal.route_document,
        experiment_path=EXPERIMENT,
    )
    assert verification.event_count == len(prefix)
    assert verification.route_id == terminal.route_document["route_id"]


def test_specified_card_activation_opportunity_branches_only_core_candidates() -> None:
    _runtime_or_skip()
    experiment = load_experiment_document(EXPERIMENT)
    experiment["interruption"] = {
        "mode": "specified",
        "definitions": [
            {
                "id": "opening_hand_trigger_all_opportunities",
                "source_card_code": 2511,
                "source_player": 0,
                "source_zone": "hand",
                "response_roles": [],
            }
        ],
    }
    adapter = RealCoreFrontierAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )

    frontier = adapter.replay(experiment, ())

    taxonomy = frontier.request["interruption_taxonomy"]
    assert len(taxonomy) == 1
    assert taxonomy[0]["status"] == "supported"
    supported_ids = {
        candidate["candidate_id"] for candidate in taxonomy[0]["candidates"]
    }
    activation_ids = {
        selection.candidate_id
        for action in frontier.actions
        if action.kind == ActionKind.ACTIVATE_EFFECT
        for selection in action.selections
    }
    assert supported_ids == activation_ids
    assert {action.kind for action in frontier.actions} == {
        ActionKind.ACTIVATE_EFFECT,
        ActionKind.PASS,
    }

    activation = next(
        action
        for action in frontier.actions
        if action.kind == ActionKind.ACTIVATE_EFFECT
    )
    prefix = [activation]
    terminal = adapter.replay(experiment, prefix)
    for _ in range(12):
        if terminal.legal_stop:
            break
        next_action = next(
            (action for action in terminal.actions if action.kind == ActionKind.PASS),
            terminal.actions[0],
        )
        prefix.append(next_action)
        terminal = adapter.replay(experiment, prefix)

    assert terminal.legal_stop
    assert terminal.route_document is not None
    trace = terminal.route_document["presentation"][
        "specified_interruption_trace"
    ]
    assert len(trace) == 1
    assert trace[0]["definition_id"] == "opening_hand_trigger_all_opportunities"
    assert trace[0]["activation"]["action_id"] == activation.action_id
    assert trace[0]["activation"]["candidate_ids"] == list(supported_ids)
    assert trace[0]["prefix_action_ids"] == []
    assert trace[0]["response_steps"] == []
    verify_general_search_route(
        terminal.route_document,
        experiment_path=EXPERIMENT,
    )
