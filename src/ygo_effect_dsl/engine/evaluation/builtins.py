from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ygo_effect_dsl.engine.evaluation.api import (
    EvaluationContext,
    EvaluationInput,
    EvaluationOutput,
    EvaluatorRegistry,
)
from ygo_effect_dsl.engine.evaluation.scoring import (
    MissingValuePolicy,
    build_weighted_score_breakdown,
)


class BoardCountEvaluator:
    evaluator_id = "real_core_board_count"
    version = "1"

    def evaluate(
        self,
        state: EvaluationInput,
        context: EvaluationContext,
    ) -> EvaluationOutput:
        player = context.evaluator_config.get("player", 0)
        if player not in (0, 1):
            raise ValueError("board count evaluator player must be 0 or 1")
        zone_counts = state.board_summary.get("zone_counts")
        if not isinstance(zone_counts, Mapping):
            raise ValueError("board_summary.zone_counts must be a mapping")
        player_counts = zone_counts.get(str(player))
        if not isinstance(player_counts, Mapping):
            raise ValueError(f"board_summary has no zone counts for player {player}")
        monster_count = _optional_non_negative_count(
            player_counts.get("monster_zone"), "monster_zone"
        )
        hand_count = _optional_non_negative_count(player_counts.get("hand"), "hand")
        monster_weight = _weight(
            context.evaluator_config.get("monster_weight", 10), "monster_weight"
        )
        hand_weight = _weight(
            context.evaluator_config.get("hand_weight", 1), "hand_weight"
        )
        raw_values = {"field_count": monster_count, "hand_count": hand_count}
        raw_defaults = context.evaluator_config.get("missing_defaults", {})
        if not isinstance(raw_defaults, Mapping):
            raise ValueError("missing_defaults must be a mapping")
        breakdown = build_weighted_score_breakdown(
            raw_values,
            {"field_count": monster_weight, "hand_count": hand_weight},
            missing_policy=MissingValuePolicy(
                str(context.evaluator_config.get("missing_value_policy", "error"))
            ),
            defaults=raw_defaults,
        )
        vector = {term.metric: term.resolved_value for term in breakdown.terms}
        return EvaluationOutput(
            vector=vector,
            score_breakdown=breakdown,
        )


def _optional_non_negative_count(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer or None")
    return value


def _weight(value: Any, name: str) -> int | float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    return value


def build_default_evaluator_registry() -> EvaluatorRegistry:
    registry = EvaluatorRegistry()
    registry.register(BoardCountEvaluator())
    return registry
