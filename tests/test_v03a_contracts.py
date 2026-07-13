from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.engine.bridge import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
    DecisionResponse,
    InvalidBridgeResponseError,
    validate_decision_response,
)
from ygo_effect_dsl.engine.replay import (
    ReplayEventV03a,
    ReplayHistoryV03a,
    ReplaySignatureMismatchError,
)


def _request(candidate_id: str = "card-1") -> DecisionRequest:
    return DecisionRequest(
        request_id="req-local-1",
        request_type="select_card",
        player=0,
        candidates=(
            Candidate(
                candidate_id=candidate_id,
                kind="card",
                label="Sample Card",
                payload={"core_choice": 7},
            ),
        ),
        constraints=DecisionConstraints(min_selections=1, max_selections=1),
        context=DecisionContext(
            phase="main1",
            turn_player=0,
            priority_player=0,
            visible_board={"turn": 1},
            request_source="mock",
            version_metadata={"ocgcore": "mock"},
        ),
    )


def test_bridge_decision_request_contract() -> None:
    request = _request()

    assert request.to_dict()["request_id"] == "req-local-1"
    assert request.request_signature.startswith("req_")

    same_decision_different_id = DecisionRequest(
        request_id="req-local-2",
        request_type=request.request_type,
        player=request.player,
        candidates=request.candidates,
        constraints=request.constraints,
        context=request.context,
    )
    assert same_decision_different_id.request_signature == request.request_signature

    response = DecisionResponse(
        request_id=request.request_id,
        request_signature=request.request_signature,
        selected_candidate_ids=("card-1",),
        payload={"selected": ["card-1"]},
    )
    validate_decision_response(request, response)


def test_bridge_rejects_invalid_response_signature() -> None:
    request = _request()
    response = DecisionResponse(
        request_id=request.request_id,
        request_signature="req_invalid",
        selected_candidate_ids=("card-1",),
    )

    with pytest.raises(InvalidBridgeResponseError, match="request_signature"):
        validate_decision_response(request, response)


def test_action_id_is_stable_for_same_request_and_selection() -> None:
    request = _request()
    first = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="card-1", order=0, payload_ref="core_choice"),),
        request_signature=request.request_signature,
    )
    second = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="card-1", order=0, payload_ref="core_choice"),),
        request_signature=request.request_signature,
    )

    assert first.action_id.startswith("act_")
    assert first.action_id == second.action_id


def test_action_distinguishes_stop_line_and_end_turn() -> None:
    request = _request()
    stop_line = Action(
        kind=ActionKind.STOP_LINE,
        player=0,
        selections=(),
        request_signature=request.request_signature,
    )
    end_turn = Action(
        kind=ActionKind.END_TURN,
        player=0,
        selections=(),
        request_signature=request.request_signature,
    )

    assert stop_line.action_id != end_turn.action_id
    assert stop_line.to_dict()["kind"] == "STOP_LINE"
    assert end_turn.to_dict()["kind"] == "END_TURN"


def test_replay_returns_to_same_decision_request() -> None:
    request = _request()
    action = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="card-1", order=0),),
        request_signature=request.request_signature,
    )
    replay = ReplayHistoryV03a(
        initial_snapshot={"main_deck_order": ["card-1"], "starting_player": 0},
        version_metadata={"project_version": "0.3a-test"},
        seeds={"duel_seed": 1, "shuffle_seed": 2},
        events=(
            ReplayEventV03a(
                step=0,
                request_signature=request.request_signature,
                action=action,
                request=request.to_dict(),
                state_hash_before="state_before",
                state_hash_after="state_after",
            ),
        ),
    )

    replay.assert_request_matches(0, request)
    assert replay.to_dict()["schema_version"] == "0.3a"
    assert replay.to_dict()["events"][0]["action_id"] == action.action_id


def test_replay_rejects_request_signature_mismatch() -> None:
    request = _request()
    different_request = _request(candidate_id="card-2")
    action = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="card-1", order=0),),
        request_signature=request.request_signature,
    )
    replay = ReplayHistoryV03a(
        initial_snapshot={"main_deck_order": ["card-1"], "starting_player": 0},
        version_metadata={"project_version": "0.3a-test"},
        events=(ReplayEventV03a(step=0, request_signature=request.request_signature, action=action),),
    )

    with pytest.raises(ReplaySignatureMismatchError, match="request_signature mismatch"):
        replay.assert_request_matches(0, different_request)
