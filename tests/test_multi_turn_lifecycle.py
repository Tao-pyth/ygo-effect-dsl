from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    RecoveryAction,
    classify_failure,
)
from ygo_effect_dsl.engine.search import (
    MULTI_TURN_LIFECYCLE_SCHEMA_VERSION,
    SEARCH_BUDGET_OWNERSHIP_SCHEMA_VERSION,
    SEARCH_BUDGET_PRIORITY,
    MultiTurnLifecycleDecision,
    MultiTurnLifecycleError,
    apply_turn_lifecycle,
    search_budget_ownership_contract,
)


def _action(kind: ActionKind) -> Action:
    return Action(
        kind=kind,
        player=0,
        selections=(),
        request_signature="req_lifecycle_fixture",
    )


def test_budget_ownership_contract_is_versioned_and_content_identified() -> None:
    first = search_budget_ownership_contract()
    second = search_budget_ownership_contract()

    assert first == second
    assert first["schema_version"] == SEARCH_BUDGET_OWNERSHIP_SCHEMA_VERSION
    assert tuple(first["priority"]) == SEARCH_BUDGET_PRIORITY
    assert first["core_owned"] == ["phase", "draw", "turn_counter", "duel_end"]
    assert first["scenario_adapter_owned"] == ["turn_limit"]
    assert first["contract_id"].startswith("budgetownership_")


def test_final_turn_suppresses_end_turn_and_records_legal_boundary() -> None:
    actions, decision = apply_turn_lifecycle(
        (_action(ActionKind.PASS), _action(ActionKind.END_TURN)),
        turn=3,
        phase="main1",
        turn_limit=3,
        request_type="select_idle_command",
        process_state="awaiting_response",
        chain_count=0,
        legal_stop=True,
        forced_response=False,
    )

    assert [action.kind for action in actions] == [ActionKind.PASS]
    assert decision.schema_version == MULTI_TURN_LIFECYCLE_SCHEMA_VERSION
    assert decision.core_end_turn_offered is True
    assert decision.end_turn_allowed is False
    assert decision.turn_limit_reached is True
    assert decision.boundary_reason == "turn_limit"
    assert MultiTurnLifecycleDecision.from_dict(decision.to_dict()) == decision


@pytest.mark.parametrize(
    ("chain_count", "forced_response", "reason"),
    [(1, False, "pending_chain"), (0, True, "mandatory_response")],
)
def test_pending_chain_or_forced_response_cannot_be_a_legal_stop(
    chain_count: int, forced_response: bool, reason: str
) -> None:
    _, decision = apply_turn_lifecycle(
        (_action(ActionKind.PASS),),
        turn=1,
        phase="main1",
        turn_limit=2,
        request_type="select_chain",
        process_state="awaiting_response",
        chain_count=chain_count,
        legal_stop=False,
        forced_response=forced_response,
    )

    assert decision.mandatory_response_pending is True
    assert decision.boundary_reason == reason


def test_turn_limit_overflow_is_a_non_retryable_path_failure() -> None:
    with pytest.raises(MultiTurnLifecycleError) as raised:
        apply_turn_lifecycle(
            (),
            turn=2,
            phase="draw",
            turn_limit=1,
            request_type="select_idle_command",
            process_state="awaiting_response",
            chain_count=0,
            legal_stop=False,
            forced_response=False,
        )

    failure = classify_failure(raised.value)
    assert failure.category == "multi_turn_lifecycle"
    assert failure.disposition == FailureDisposition.PATH_FAILURE
    assert failure.recovery == RecoveryAction.STOP_PATH
    assert failure.retryable is False
    assert failure.context == {"code": "turn_limit_exceeded", "turn": 2, "turn_limit": 1}


def test_core_duel_end_has_a_unique_terminal_reason() -> None:
    actions, decision = apply_turn_lifecycle(
        (),
        turn=2,
        phase="main1",
        turn_limit=3,
        request_type="duel_end",
        process_state="ended",
        chain_count=0,
        legal_stop=True,
        forced_response=False,
    )

    assert actions == ()
    assert decision.duel_ended is True
    assert decision.boundary_reason == "duel_end"
    assert decision.end_turn_allowed is False


def test_lifecycle_parser_rejects_tampered_content_id_and_inconsistent_flags() -> None:
    _, decision = apply_turn_lifecycle(
        (),
        turn=1,
        phase="main1",
        turn_limit=2,
        request_type="select_idle_command",
        process_state="awaiting_response",
        chain_count=0,
        legal_stop=True,
        forced_response=False,
    )
    tampered_id = {**decision.to_dict(), "phase": "battle"}
    inconsistent = {**decision.to_dict(), "turn_limit_reached": True}

    with pytest.raises(ValueError, match="ID mismatch"):
        MultiTurnLifecycleDecision.from_dict(tampered_id)
    with pytest.raises(ValueError, match="does not match"):
        MultiTurnLifecycleDecision.from_dict(inconsistent)
