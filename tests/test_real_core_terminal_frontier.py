from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind
from ygo_effect_dsl.engine.bridge.ocgcore import (
    DuelProcessStatus,
    OcgcoreMessageDecoder,
    ProcessBatch,
)
from ygo_effect_dsl.engine.search import (
    BeamSearchStrategyV1,
    MctsSearchStrategyV1,
    RandomSearchStrategyV1,
    SearchBudget,
    SearchExecutor,
    SearchFrontier,
)
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import (
    RealCoreFrontierAdapter,
    verify_general_search_route,
)
from ygo_effect_dsl.prototype.real_core import _decode_batch


ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "examples/experiments/general_search_inline.yaml"


def _runtime_or_skip() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")


def _message(message_type: int, payload: bytes) -> bytes:
    message = bytes((message_type,)) + payload
    return struct.pack("<I", len(message)) + message


def test_native_end_without_msg_win_fails_closed() -> None:
    with pytest.raises(ValueError, match="omitted MSG_WIN"):
        _decode_batch(
            OcgcoreMessageDecoder(),
            ProcessBatch(DuelProcessStatus.END, (), 1, 0.0),
            0,
        )


def test_conflicting_msg_win_frames_fail_closed() -> None:
    messages = (
        _message(5, b"\x00\x01") + _message(5, b"\x01\x01"),
    )
    with pytest.raises(ValueError, match="conflicting MSG_WIN"):
        _decode_batch(
            OcgcoreMessageDecoder(),
            ProcessBatch(DuelProcessStatus.AWAITING, messages, 1, 0.0),
            0,
        )


def _terminal_experiment(fixture_id: str) -> dict:
    experiment = load_experiment_document(EXPERIMENT)
    experiment["runner"] = {
        "adapter": "real_core_prototype",
        "fixture_script_id": fixture_id,
        "scenario_id": "general_search_terminal_fixture",
    }
    return experiment


@dataclass(frozen=True)
class _TerminalCase:
    experiment: Mapping
    prefix: tuple[Action, ...]
    frontiers: tuple[SearchFrontier, ...]


def _run_terminal_case(fixture_id: str) -> _TerminalCase:
    experiment = _terminal_experiment(fixture_id)
    adapter = RealCoreFrontierAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )
    prefix: list[Action] = []
    frontiers: list[SearchFrontier] = []
    activated = False
    for _ in range(8):
        frontier = adapter.replay(experiment, prefix)
        frontiers.append(frontier)
        if frontier.terminal_observation is not None:
            return _TerminalCase(experiment, tuple(prefix), tuple(frontiers))
        activation = next(
            (
                action
                for action in frontier.actions
                if action.kind == ActionKind.ACTIVATE_EFFECT
                and action.selections[0].card_ref is not None
                and action.selections[0].card_ref.public_card_id == 2511
            ),
            None,
        )
        action = (
            activation
            if activation is not None and not activated
            else next(
                action
                for action in frontier.actions
                if action.kind == ActionKind.PASS
            )
        )
        activated = activated or action.kind == ActionKind.ACTIVATE_EFFECT
        prefix.append(action)
    raise AssertionError("real-core terminal fixture did not reach MSG_WIN")


@pytest.fixture(scope="module")
def terminal_cases() -> Mapping[str, _TerminalCase]:
    _runtime_or_skip()
    return {
        fixture_id: _run_terminal_case(fixture_id)
        for fixture_id in ("terminal_lp_zero_v1", "terminal_deck_out_v1")
    }


@pytest.mark.parametrize(
    ("fixture_id", "reason_category", "reason_code"),
    [
        ("terminal_lp_zero_v1", "life_points_zero", 1),
        ("terminal_deck_out_v1", "deck_out", 2),
    ],
)
def test_real_core_terminal_frontier_has_no_request_or_actions(
    terminal_cases: Mapping[str, _TerminalCase],
    fixture_id: str,
    reason_category: str,
    reason_code: int,
) -> None:
    case = terminal_cases[fixture_id]
    terminal = case.frontiers[-1]
    observation = terminal.terminal_observation
    assert observation is not None
    assert terminal.request is None
    assert terminal.actions == ()
    assert terminal.legal_stop is True
    assert terminal.legal_stop_reason == "terminal"
    assert observation["pending_request"] is None
    assert observation["process_state"] == "ended"
    assert observation["outcome"]["winner_player"] == 0
    assert observation["outcome"]["reason_category"] == reason_category
    assert observation["outcome"]["reason_code"] == reason_code
    assert observation["turn_lifecycle"]["boundary_reason"] == "duel_end"
    assert observation["turn_lifecycle"]["duel_ended"] is True
    assert observation["final_action_id"] == case.prefix[-1].action_id

    route = terminal.route_document
    assert route is not None
    assert route["result"]["final_request_signature"] is None
    assert route["result"]["terminal_outcome"] == observation["outcome"]
    assert route["result"]["terminal_board"]["state_hash"] == terminal.state_id
    final_event = route["replay"]["events"][-1]
    assert final_event["state_hash_after"] == terminal.state_id
    assert final_event["core_output"]["terminal_events"]
    if fixture_id == "terminal_lp_zero_v1":
        assert route["checkpoints"][-1]["board_summary"]["life_points"]["1"] == 0

    verification = verify_general_search_route(
        route,
        experiment_path=EXPERIMENT,
    )
    assert verification.route_id == route["route_id"]
    assert verification.final_state_hash == terminal.state_id
    assert verification.event_count == len(case.prefix)


def test_mandatory_chain_is_not_misclassified_as_terminal(
    terminal_cases: Mapping[str, _TerminalCase],
) -> None:
    case = terminal_cases["terminal_lp_zero_v1"]
    after_activation = case.frontiers[1]
    assert after_activation.request is not None
    assert after_activation.request["turn_lifecycle"]["chain_count"] > 0
    assert after_activation.terminal_observation is None
    assert after_activation.legal_stop is False


@dataclass
class _RecordedTerminalAdapter:
    frontiers: Mapping[tuple[str, ...], SearchFrontier]

    def replay(
        self,
        experiment: Mapping,
        action_prefix: Sequence[Action],
    ) -> SearchFrontier:
        key = tuple(action.action_id for action in action_prefix)
        return self.frontiers[key]


def test_random_beam_and_mcts_report_the_same_terminal_boundary(
    terminal_cases: Mapping[str, _TerminalCase],
) -> None:
    case = terminal_cases["terminal_deck_out_v1"]
    recorded: dict[tuple[str, ...], SearchFrontier] = {}
    for index, frontier in enumerate(case.frontiers):
        key = tuple(action.action_id for action in case.prefix[:index])
        recorded[key] = (
            frontier
            if frontier.terminal_observation is not None
            else replace(frontier, actions=(case.prefix[index],))
        )
    strategies = (
        RandomSearchStrategyV1(seed=11),
        BeamSearchStrategyV1(beam_width=1, seed=11),
        MctsSearchStrategyV1(
            simulations=1,
            reward_floor=-1000,
            reward_ceiling=1000,
            seed=11,
        ),
    )

    boundaries = []
    route_ids = []
    for strategy in strategies:
        result = SearchExecutor(
            _RecordedTerminalAdapter(recorded),
            strategy,
            SearchBudget(max_nodes=16, max_depth=8),
            clock=lambda: 0.0,
        ).run(case.experiment)
        assert result.best_route is not None
        boundaries.append(result.best_route.lifecycle_boundary)
        route_ids.append(result.best_route.route_id)

    assert len(set(route_ids)) == 1
    assert all(boundary == boundaries[0] for boundary in boundaries)
    assert boundaries[0]["boundary_reason"] == "duel_end"
