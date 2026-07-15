from __future__ import annotations

from pathlib import Path

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind
from ygo_effect_dsl.engine.search import SearchFrontier
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


def _advance_to_final_turn_stop(
    experiment: dict, adapter: RealCoreFrontierAdapter
) -> tuple[list[Action], SearchFrontier, list[dict]]:
    prefix: list[Action] = []
    frontier = adapter.replay(experiment, prefix)
    observed_lifecycles: list[dict] = []
    for _step in range(24):
        lifecycle = frontier.request["turn_lifecycle"]
        observed_lifecycles.append(lifecycle)
        if frontier.legal_stop and lifecycle["turn_limit_reached"]:
            return prefix, frontier, observed_lifecycles
        if frontier.legal_stop:
            next_action = next(
                action
                for action in frontier.actions
                if action.kind == ActionKind.END_TURN
            )
        else:
            next_action = next(
                (action for action in frontier.actions if action.kind == ActionKind.PASS),
                frontier.actions[0],
            )
        prefix.append(next_action)
        frontier = adapter.replay(experiment, prefix)
    raise AssertionError("real-core lifecycle did not reach the final-turn legal stop")


@pytest.mark.parametrize("turn_limit", [1, 2, 3])
def test_real_core_reaches_deterministic_multi_turn_boundary(turn_limit: int) -> None:
    _runtime_or_skip()
    experiment = load_experiment_document(EXPERIMENT)
    experiment["turn_limit"] = turn_limit
    preflight = preflight_scenario(experiment, experiment_path=EXPERIMENT)
    assert preflight.ok
    adapter = RealCoreFrontierAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )

    prefix, terminal, lifecycles = _advance_to_final_turn_stop(experiment, adapter)

    assert terminal.legal_stop
    assert terminal.route_document is not None
    terminal_lifecycle = terminal.request["turn_lifecycle"]
    assert terminal_lifecycle["turn"] == turn_limit
    assert terminal_lifecycle["phase"] == "main1"
    assert terminal_lifecycle["boundary_reason"] == "turn_limit"
    assert terminal_lifecycle["end_turn_allowed"] is False
    assert ActionKind.END_TURN not in {action.kind for action in terminal.actions}
    main_phase_turns = {
        item["turn"] for item in lifecycles if item["phase"] == "main1"
    }
    assert main_phase_turns == set(range(1, turn_limit + 1))
    assert sum(action.kind == ActionKind.END_TURN for action in prefix) == turn_limit - 1
    verification = verify_general_search_route(
        terminal.route_document,
        experiment_path=EXPERIMENT,
    )
    assert verification.event_count == len(prefix)
    assert verification.route_id == terminal.route_document["route_id"]
