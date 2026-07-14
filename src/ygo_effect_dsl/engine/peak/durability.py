from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ygo_effect_dsl.engine.canonical import to_canonical_data
from ygo_effect_dsl.engine.evaluation import (
    EvaluationResult,
    compare_score_breakdowns,
)


DURABILITY_SCHEMA_VERSION = "peak-durability-v1"
TEMPORARY_EVALUATION_TIMING = "legal_stop_before_end_turn"
DURABLE_EVALUATION_TIMING = (
    "opponent_main1_after_end_phase_and_turn_start_processing"
)


def _number(value: Any, path: str) -> int | float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be a number")
    return value


def _checkpoint_view(checkpoint: Mapping[str, Any], path: str) -> dict[str, Any]:
    step = checkpoint.get("step")
    turn = checkpoint.get("turn")
    phase = checkpoint.get("phase")
    state_hash = checkpoint.get("state_hash")
    evaluation = checkpoint.get("evaluation")
    success = checkpoint.get("success")
    if not isinstance(step, int) or isinstance(step, bool) or step < 0:
        raise ValueError(f"{path}.step must be a non-negative integer")
    if not isinstance(turn, int) or isinstance(turn, bool) or turn < 1:
        raise ValueError(f"{path}.turn must be a positive integer")
    if not isinstance(phase, str) or not phase:
        raise ValueError(f"{path}.phase must be a non-empty string")
    if not isinstance(state_hash, str) or not state_hash:
        raise ValueError(f"{path}.state_hash must be a non-empty string")
    if not isinstance(evaluation, Mapping):
        raise ValueError(f"{path}.evaluation must be a mapping")
    if not isinstance(success, bool):
        raise ValueError(f"{path}.success must be a boolean")
    view = {
        "checkpoint_step": step,
        "evaluation": to_canonical_data(evaluation),
        "phase": phase,
        "score": _number(checkpoint.get("score"), f"{path}.score"),
        "state_hash": state_hash,
        "success": success,
        "turn": turn,
    }
    evaluation_result = checkpoint.get("evaluation_result")
    if evaluation_result is not None:
        parsed = EvaluationResult.from_dict(evaluation_result)
        if parsed.vector != evaluation or parsed.total_score != view["score"]:
            raise ValueError(
                f"{path}.evaluation_result must match evaluation and score"
            )
        view["evaluation_result"] = parsed.to_dict()
    return view


def _evaluation_delta(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, int | float]:
    delta: dict[str, int | float] = {}
    for key in sorted(before.keys() & after.keys()):
        before_value = before[key]
        after_value = after[key]
        if (
            isinstance(before_value, (int, float))
            and not isinstance(before_value, bool)
            and isinstance(after_value, (int, float))
            and not isinstance(after_value, bool)
        ):
            delta[str(key)] = after_value - before_value
    return delta


def build_durability_report(
    before_checkpoint: Mapping[str, Any],
    after_checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    before = _checkpoint_view(before_checkpoint, "before_checkpoint")
    after = _checkpoint_view(after_checkpoint, "after_checkpoint")
    if after["turn"] <= before["turn"]:
        raise ValueError("after_checkpoint must be from a later turn")
    delta: dict[str, Any] = {
        "evaluation": _evaluation_delta(
            before["evaluation"], after["evaluation"]
        ),
        "score": after["score"] - before["score"],
    }
    before_result = before.get("evaluation_result")
    after_result = after.get("evaluation_result")
    if isinstance(before_result, Mapping) and isinstance(after_result, Mapping):
        delta["score_breakdown"] = compare_score_breakdowns(
            EvaluationResult.from_dict(before_result).score_breakdown,
            EvaluationResult.from_dict(after_result).score_breakdown,
        )
    return {
        "after": after,
        "before": before,
        "delta": delta,
        "evaluation_timing": {
            "after": DURABLE_EVALUATION_TIMING,
            "before": TEMPORARY_EVALUATION_TIMING,
        },
        "schema_version": DURABILITY_SCHEMA_VERSION,
        "state_changed": before["state_hash"] != after["state_hash"],
        "success_retained": before["success"] and after["success"],
    }
