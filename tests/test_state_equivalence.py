from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.engine.state import (
    ApproximationPolicy,
    CanonicalState,
    StateEquivalenceError,
    StateKeyPurpose,
    build_state_key,
    exact_state_equivalent,
)


FIXTURE = Path(__file__).parent / "fixtures" / "state" / "minimal_complete_state.json"


def _state(*, deck_order: list[int] | None = None) -> CanonicalState:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if deck_order is not None:
        payload["private_state"]["deck_order"] = deck_order
    return CanonicalState.from_dict(payload)


def _policy(*, version: str = "1") -> ApproximationPolicy:
    return ApproximationPolicy(
        policy_id="ignore-private-deck-order",
        version=version,
        drop_paths=(("private_state", "deck_order"),),
        allowed_purposes=(
            StateKeyPurpose.TRANSPOSITION_HINT,
            StateKeyPurpose.EVALUATION_CACHE,
            StateKeyPurpose.SEARCH_ORDERING,
        ),
        risk_notes=(
            "future draws can differ",
            "never prune without exact confirmation",
        ),
    )


def test_exact_equivalence_is_necessary_and_sufficient_for_same_identity() -> None:
    first = _state()
    same = _state()
    changed = _state(deck_order=[200, 100])

    assert exact_state_equivalent(first, same) is True
    assert exact_state_equivalent(first, changed) is False
    key = build_state_key(first, purpose=StateKeyPurpose.REPLAY_VALIDATION)
    assert key.key == first.state_id
    assert key.exact is True


def test_exact_equivalence_rejects_incomplete_or_cross_mode_state() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["completeness"] = "query_api_projection"
    payload["missing_fields"] = ["effect_usage_history"]
    incomplete = CanonicalState.from_dict(payload)

    with pytest.raises(StateEquivalenceError, match="not exact"):
        exact_state_equivalent(incomplete, incomplete)
    with pytest.raises(StateEquivalenceError, match="requires exact"):
        build_state_key(incomplete, purpose=StateKeyPurpose.LEGALITY_CACHE)

    player_payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    player_payload["information_mode"] = "player_view"
    player_payload["viewer"] = 0
    player_view = CanonicalState.from_dict(player_payload)
    with pytest.raises(StateEquivalenceError, match="information_mode"):
        exact_state_equivalent(_state(), player_view)


def test_approximate_key_can_group_private_order_but_requires_confirmation() -> None:
    first = _state(deck_order=[100, 200])
    reordered = _state(deck_order=[200, 100])
    policy = _policy()

    first_key = build_state_key(
        first,
        purpose=StateKeyPurpose.TRANSPOSITION_HINT,
        approximation=policy,
    )
    reordered_key = build_state_key(
        reordered,
        purpose=StateKeyPurpose.TRANSPOSITION_HINT,
        approximation=policy,
    )

    assert first_key.key == reordered_key.key
    assert first_key.exact is False
    assert first_key.requires_exact_confirmation is True
    assert first_key.policy_hash == policy.policy_hash


def test_approximation_never_drops_constraints_or_enables_direct_pruning() -> None:
    with pytest.raises(StateEquivalenceError, match="private_state"):
        ApproximationPolicy(
            policy_id="unsafe",
            version="1",
            drop_paths=(("constraints", "summon_states"),),
            allowed_purposes=(StateKeyPurpose.TRANSPOSITION_HINT,),
            risk_notes=("unsafe",),
        )

    with pytest.raises(StateEquivalenceError, match="does not allow"):
        build_state_key(
            _state(),
            purpose=StateKeyPurpose.BRANCH_PRUNING,
            approximation=_policy(),
        )

    changed_payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    changed_payload["constraints"]["normal_summon_available"] = False
    changed = CanonicalState.from_dict(changed_payload)
    original_key = build_state_key(
        _state(),
        purpose=StateKeyPurpose.EVALUATION_CACHE,
        approximation=_policy(),
    )
    changed_key = build_state_key(
        changed,
        purpose=StateKeyPurpose.EVALUATION_CACHE,
        approximation=_policy(),
    )
    assert original_key.key != changed_key.key


def test_approximation_policy_version_invalidates_cache_key() -> None:
    state = _state()
    first = build_state_key(
        state,
        purpose=StateKeyPurpose.EVALUATION_CACHE,
        approximation=_policy(version="1"),
    )
    second = build_state_key(
        state,
        purpose=StateKeyPurpose.EVALUATION_CACHE,
        approximation=_policy(version="2"),
    )

    assert first.key != second.key
    assert first.policy_hash != second.policy_hash
