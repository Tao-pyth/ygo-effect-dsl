from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.peak import (
    DURABLE_EVALUATION_TIMING,
    TEMPORARY_EVALUATION_TIMING,
    build_durability_report,
)


def _checkpoint(
    *, step: int, turn: int, score: int, field_count: int, state_hash: str
) -> dict[str, object]:
    return {
        "evaluation": {"field_count": field_count, "hand_count": 0},
        "phase": "main1",
        "score": score,
        "state_hash": state_hash,
        "step": step,
        "success": field_count > 0,
        "turn": turn,
    }


def test_durability_report_compares_temporary_and_next_turn_board() -> None:
    report = build_durability_report(
        _checkpoint(
            step=5, turn=1, score=20, field_count=2, state_hash="state_before"
        ),
        _checkpoint(
            step=9, turn=2, score=10, field_count=1, state_hash="state_after"
        ),
    )

    assert report["evaluation_timing"] == {
        "after": DURABLE_EVALUATION_TIMING,
        "before": TEMPORARY_EVALUATION_TIMING,
    }
    assert report["delta"] == {
        "evaluation": {"field_count": -1, "hand_count": 0},
        "score": -10,
    }
    assert report["state_changed"] is True
    assert report["success_retained"] is True


def test_durability_report_requires_a_later_turn() -> None:
    checkpoint = _checkpoint(
        step=5, turn=1, score=10, field_count=1, state_hash="state"
    )

    with pytest.raises(ValueError, match="later turn"):
        build_durability_report(checkpoint, checkpoint)
