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


BOARD_BREAK_EVALUATOR_ID = "real_core_board_break"
BOARD_BREAK_EVALUATOR_VERSION = "1"
BOARD_BREAK_EVALUATION_SCHEMA_VERSION = "board-break-evaluation-v1"
BOARD_BREAK_DEFAULT_WEIGHTS = {
    "actor_hand_count": 1,
    "actor_monster_count": 4,
    "opponent_banished_count": 3,
    "opponent_graveyard_count": -1,
    "opponent_monster_count": -10,
    "opponent_spell_trap_count": -6,
}


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


class BoardBreakEvaluator:
    evaluator_id = BOARD_BREAK_EVALUATOR_ID
    version = BOARD_BREAK_EVALUATOR_VERSION

    def evaluate(
        self,
        state: EvaluationInput,
        context: EvaluationContext,
    ) -> EvaluationOutput:
        config = context.evaluator_config
        unknown_config = sorted(set(config) - {"actor_player", "weights"})
        if unknown_config:
            raise ValueError(
                f"board-break evaluator has unknown config keys: {unknown_config}"
            )
        actor = config.get("actor_player", 0)
        if (
            not isinstance(actor, int)
            or isinstance(actor, bool)
            or actor not in (0, 1)
        ):
            raise ValueError("board-break evaluator actor_player must be 0 or 1")
        opponent = 1 - actor
        zone_counts = state.board_summary.get("zone_counts")
        if not isinstance(zone_counts, Mapping):
            raise ValueError("board_summary.zone_counts must be a mapping")
        actor_counts = zone_counts.get(str(actor))
        opponent_counts = zone_counts.get(str(opponent))
        if not isinstance(actor_counts, Mapping) or not isinstance(
            opponent_counts, Mapping
        ):
            raise ValueError("board_summary is missing actor or opponent zone counts")
        observed = {
            "actor_hand_count": _zone_count(actor_counts, "hand"),
            "actor_monster_count": _zone_count(actor_counts, "monster_zone"),
            "opponent_banished_count": _zone_count(opponent_counts, "banished"),
            "opponent_graveyard_count": _zone_count(opponent_counts, "graveyard"),
            "opponent_monster_count": _zone_count(
                opponent_counts, "monster_zone"
            ),
            "opponent_spell_trap_count": _zone_count(
                opponent_counts, "spell_trap_zone"
            ),
        }
        raw_weights = config.get("weights", BOARD_BREAK_DEFAULT_WEIGHTS)
        if not isinstance(raw_weights, Mapping) or not raw_weights:
            raise ValueError("board-break evaluator weights must be a mapping")
        unknown = sorted(set(raw_weights) - set(observed))
        if unknown:
            raise ValueError(f"board-break evaluator has unknown weights: {unknown}")
        weights = {
            str(metric): _weight(weight, f"weights.{metric}")
            for metric, weight in raw_weights.items()
        }
        values = {metric: observed[metric] for metric in weights}
        breakdown = build_weighted_score_breakdown(values, weights)
        vector = {term.metric: term.resolved_value for term in breakdown.terms}
        return EvaluationOutput(
            vector=vector,
            score_breakdown=breakdown,
            explanations=(
                {
                    "actor_player": actor,
                    "opponent_player": opponent,
                    "schema_version": BOARD_BREAK_EVALUATION_SCHEMA_VERSION,
                },
            ),
        )


def _optional_non_negative_count(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer or None")
    return value


def _zone_count(counts: Mapping[str, Any], zone: str) -> int:
    value = counts.get(zone, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{zone} must be a non-negative integer")
    return value


def _weight(value: Any, name: str) -> int | float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    return value


def build_default_evaluator_registry() -> EvaluatorRegistry:
    registry = EvaluatorRegistry()
    registry.register(BoardCountEvaluator())
    registry.register(BoardBreakEvaluator())
    return registry
