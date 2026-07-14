from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.engine.action import Action, ActionKind, CardRef, EffectRef, Selection
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
    build_action_occurrence_id,
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


def test_request_signature_ignores_candidate_display_label() -> None:
    first = _request()
    candidate = first.candidates[0]
    second = DecisionRequest(
        request_id=first.request_id,
        request_type=first.request_type,
        player=first.player,
        candidates=(
            Candidate(
                candidate_id=candidate.candidate_id,
                kind=candidate.kind,
                label="Renamed for UI only",
                payload=candidate.payload,
            ),
        ),
        constraints=first.constraints,
        context=first.context,
    )

    assert first.request_signature == second.request_signature
    assert first.to_dict()["candidates"][0]["label"] == "Sample Card"
    assert second.to_dict()["candidates"][0]["label"] == "Renamed for UI only"


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


def test_action_id_distinguishes_same_named_card_instances() -> None:
    request = DecisionRequest(
        request_id="duplicate-names",
        request_type="select_card",
        player=0,
        candidates=(
            Candidate(candidate_id="hand:0", kind="card", label="Same Card"),
            Candidate(candidate_id="hand:1", kind="card", label="Same Card"),
        ),
        constraints=DecisionConstraints(min_selections=1, max_selections=1),
        context=DecisionContext(),
    )
    first = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="hand:0"),),
        request_signature=request.request_signature,
    )
    second = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="hand:1"),),
        request_signature=request.request_signature,
    )

    assert first.action_id != second.action_id


def test_action_occurrence_id_distinguishes_repeated_execution_coordinates() -> None:
    request = _request()
    action = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="card-1"),),
        request_signature=request.request_signature,
    )
    first = ReplayEventV03a(
        step=0,
        request_signature=request.request_signature,
        action=action,
        state_hash_before="state_before_0",
        state_hash_after="state_after_0",
        turn=1,
        turn_action_index=0,
        chain_index=0,
    )
    repeated = ReplayEventV03a(
        step=1,
        request_signature=request.request_signature,
        action=action,
        state_hash_before="state_before_1",
        state_hash_after="state_after_1",
        turn=1,
        turn_action_index=1,
        chain_index=1,
    )

    assert first.action.action_id == repeated.action.action_id
    assert first.action_occurrence_id != repeated.action_occurrence_id
    assert first.to_dict()["action_occurrence_id"].startswith("aocc_")


@pytest.mark.parametrize(
    ("change", "value"),
    (("state_hash_before", "state_other"), ("turn", 2), ("turn_action_index", 4), ("chain_index", 2)),
)
def test_action_occurrence_id_covers_state_and_duel_order(change: str, value: object) -> None:
    coordinates = {
        "action_id": "act_stable",
        "step": 3,
        "state_hash_before": "state_before",
        "turn": 1,
        "turn_action_index": 3,
        "chain_index": 1,
    }
    baseline = build_action_occurrence_id(**coordinates)
    coordinates[change] = value

    assert build_action_occurrence_id(**coordinates) != baseline


def test_action_id_ignores_effect_display_label() -> None:
    request = _request()
    card_ref = CardRef(controller=0, owner=0, location="monster_zone", sequence=0)
    first_effect = EffectRef(card_ref=card_ref, effect_index=0, effect_label="Original label")
    renamed_effect = EffectRef(card_ref=card_ref, effect_index=0, effect_label="Renamed label")
    first = Action(
        kind=ActionKind.ACTIVATE_EFFECT,
        player=0,
        selections=(Selection(candidate_id="effect-1", effect_ref=first_effect),),
        effect_ref=first_effect,
        request_signature=request.request_signature,
    )
    second = Action(
        kind=ActionKind.ACTIVATE_EFFECT,
        player=0,
        selections=(Selection(candidate_id="effect-1", effect_ref=renamed_effect),),
        effect_ref=renamed_effect,
        request_signature=request.request_signature,
    )

    assert first.action_id == second.action_id
    assert first.to_dict()["effect_ref"]["effect_label"] == "Original label"
    assert second.to_dict()["effect_ref"]["effect_label"] == "Renamed label"


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


def test_action_granularity_follows_decision_request_boundaries() -> None:
    cost_request = _request(candidate_id="cost:card-1")
    target_request = _request(candidate_id="target:card-1")
    cost = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="cost:card-1"),),
        request_signature=cost_request.request_signature,
    )
    target = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="target:card-1"),),
        request_signature=target_request.request_signature,
    )

    assert cost.action_id != target.action_id
    assert cost.request_signature != target.request_signature

    multi_request = DecisionRequest(
        request_id="multi",
        request_type="select_card",
        player=0,
        candidates=(
            Candidate(candidate_id="card-1", kind="card"),
            Candidate(candidate_id="card-2", kind="card"),
        ),
        constraints=DecisionConstraints(min_selections=2, max_selections=2),
        context=DecisionContext(),
    )
    multi = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(
            Selection(candidate_id="card-1"),
            Selection(candidate_id="card-2"),
        ),
        request_signature=multi_request.request_signature,
    )
    assert len(multi.selections) == 2


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


def test_replay_reproduces_invalid_response_failure_record() -> None:
    request = _request()
    action = Action(
        kind=ActionKind.SELECT_CARD,
        player=0,
        selections=(Selection(candidate_id="card-1", order=0),),
        request_signature=request.request_signature,
    )
    failure = {
        "category": "invalid_response",
        "context": {
            "request": request.to_dict(),
            "response": {"selected_candidate_ids": ["unknown"]},
        },
        "disposition": "path_failure",
        "exception_type": "InvalidBridgeResponseError",
        "message": "response selected unknown candidates: ['unknown']",
        "recovery": "stop_path",
        "retryable": False,
    }
    replay = ReplayHistoryV03a(
        initial_snapshot={"state_hash": "state_before"},
        version_metadata={"project_version": "0.3a-test"},
        events=(
            ReplayEventV03a(
                step=0,
                request_signature=request.request_signature,
                action=action,
                request=request.to_dict(),
                failure=failure,
            ),
        ),
    )

    replay.assert_failure_matches(0, failure)
    changed = dict(failure)
    changed["message"] = "different failure"
    with pytest.raises(ReplaySignatureMismatchError) as captured:
        replay.assert_failure_matches(0, changed)
    assert captured.value.path == "failure.message"
