from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.engine.state import (
    CanonicalState,
    ConstraintExpiration,
    EffectUsage,
    ExpirationBoundary,
    InformationMode,
    PlayerSummonState,
    RuleState,
    StateCoordinate,
    StateIdentityCompleteness,
    TimedConstraint,
    VisibilityState,
)


def _rule_state(*, normal_summons_remaining: int = 1, usage_key: str = "effect:1") -> RuleState:
    return RuleState(
        summon_states=(
            PlayerSummonState(
                player=0,
                normal_summons_remaining=normal_summons_remaining,
                special_summon_allowed=True,
            ),
            PlayerSummonState(
                player=1,
                normal_summons_remaining=1,
                special_summon_allowed=True,
            ),
        ),
        effect_usages=(
            EffectUsage(
                usage_key=usage_key,
                player=0,
                uses=1,
                limit=1,
                reset_at=ConstraintExpiration(
                    ExpirationBoundary.END_OF_TURN,
                    turn=1,
                ),
            ),
        ),
        constraints=(
            TimedConstraint(
                constraint_id="lock:dragon-only",
                kind="special_summon_filter",
                player=0,
                payload={"allowed_race": "dragon"},
                starts_at=StateCoordinate(turn=1, phase="main1", turn_action_index=2),
                expires_at=ConstraintExpiration(
                    ExpirationBoundary.END_OF_PHASE,
                    turn=1,
                    phase="main1",
                ),
            ),
        ),
    )


def _canonical(rule_state: RuleState) -> CanonicalState:
    return CanonicalState(
        public_state={"turn": 1, "phase": "main1"},
        private_state={},
        constraints=rule_state.to_constraints_dict(),
        history=rule_state.to_history_dict(),
        pending_request=None,
        engine_state={"core": "fixture"},
        information_mode=InformationMode.COMPLETE_INFORMATION,
        completeness=StateIdentityCompleteness.EXACT,
    )


def test_state_hash_changes_when_normal_summon_right_changes() -> None:
    available = _canonical(_rule_state(normal_summons_remaining=1))
    consumed = _canonical(_rule_state(normal_summons_remaining=0))

    assert available.state_id != consumed.state_id


def test_state_hash_changes_when_once_per_turn_key_changes() -> None:
    first = _canonical(_rule_state(usage_key="effect:1"))
    second = _canonical(_rule_state(usage_key="effect:2"))

    assert first.state_id != second.state_id


def test_constraint_expiration_preserves_start_and_end_boundaries() -> None:
    constraint = _rule_state().constraints[0].to_dict()

    assert constraint["starts_at"] == {
        "chain_index": 0,
        "phase": "main1",
        "turn": 1,
        "turn_action_index": 2,
    }
    assert constraint["expires_at"] == {
        "boundary": "end_of_phase",
        "chain_index": None,
        "phase": "main1",
        "turn": 1,
        "turn_action_index": None,
    }


def test_visibility_state_enforces_information_mode_boundaries() -> None:
    complete = VisibilityState(
        information_mode=InformationMode.COMPLETE_INFORMATION,
        known_private_by_player={"0": {"hand": [1]}, "1": {"hand": [2]}},
        unknown_private_by_player={},
    )
    player_view = VisibilityState(
        information_mode=InformationMode.PLAYER_VIEW,
        viewer=0,
        known_private_by_player={"0": {"hand": [1]}},
        unknown_private_by_player={"1": {"hand_count": 1}},
    )
    sampled = VisibilityState(
        information_mode=InformationMode.SAMPLED_PRIVATE_STATE,
        known_private_by_player={"0": {"hand": [1]}, "1": {"hand": [2]}},
        unknown_private_by_player={},
        sampling_reference={"seed": 7, "sampler": "fixture-v1"},
    )

    assert complete.to_private_state_dict()["known_private_by_player"]["1"]["hand"] == [2]
    assert player_view.to_private_state_dict()["unknown_private_by_player"]["1"] == {
        "hand_count": 1
    }
    assert sampled.sampling_reference == {"seed": 7, "sampler": "fixture-v1"}
    assert sampled.to_dict()["information_mode"] == "sampled_private_state"
    assert sampled.to_dict()["sampling_reference"]["seed"] == 7

    with pytest.raises(ValueError, match="another player's private state"):
        VisibilityState(
            information_mode=InformationMode.PLAYER_VIEW,
            viewer=0,
            known_private_by_player={"1": {"hand": [2]}},
            unknown_private_by_player={},
        )
