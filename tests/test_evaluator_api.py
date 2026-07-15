from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.evaluation import (
    EvaluationContext,
    EvaluationInput,
    EvaluationOutput,
    EvaluatorRegistry,
    EvaluatorSpec,
    build_default_evaluator_registry,
    build_weighted_score_breakdown,
)


def _state() -> EvaluationInput:
    return EvaluationInput(
        state_hash="state_fixture",
        board_summary={
            "zone_counts": {
                "0": {"hand": 2, "monster_zone": 1},
                "1": {"hand": 0, "monster_zone": 0},
            }
        },
        turn=1,
        phase="main1",
        information_mode="complete_information",
    )


def _experiment(*, monster_weight: int = 10) -> dict[str, object]:
    return {
        "experiment_id": "evaluation_fixture",
        "evaluate_at": "legal_stop",
        "information_mode": "complete_information",
        "evaluator": {
            "id": "real_core_board_count",
            "version": "1",
            "config": {"hand_weight": 1, "monster_weight": monster_weight},
        },
    }


def test_registry_selects_evaluator_from_experiment_config() -> None:
    registry = build_default_evaluator_registry()

    normal = registry.evaluate_experiment(_experiment(monster_weight=10), _state())
    field_heavy = registry.evaluate_experiment(
        _experiment(monster_weight=100), _state()
    )

    assert normal.vector == {"field_count": 1, "hand_count": 2}
    assert normal.total_score == 12
    assert field_heavy.total_score == 102
    assert normal.evaluator_id == "real_core_board_count"
    assert normal.evaluator_version == "1"
    assert normal.evaluator_config_hash != field_heavy.evaluator_config_hash


def test_registry_requires_exact_evaluator_version() -> None:
    registry = build_default_evaluator_registry()
    experiment = _experiment()
    experiment["evaluator"]["version"] = "2"

    with pytest.raises(ValueError, match="unknown evaluator"):
        registry.evaluate_experiment(experiment, _state())


def test_registry_supports_custom_evaluator() -> None:
    class ConstantEvaluator:
        evaluator_id = "constant"
        version = "1"

        def evaluate(
            self, state: EvaluationInput, context: EvaluationContext
        ) -> EvaluationOutput:
            return EvaluationOutput(
                vector={"constant": 1},
                score_breakdown=build_weighted_score_breakdown(
                    {"constant": 1}, {"constant": 7}
                ),
            )

    registry = EvaluatorRegistry()
    registry.register(ConstantEvaluator())
    spec = EvaluatorSpec("constant", "1", {})
    result = registry.evaluate(
        spec,
        _state(),
        EvaluationContext("fixture", "legal_stop", {}),
    )

    assert result.vector == {"constant": 1}
    assert result.total_score == 7


def test_registry_rejects_duplicate_registration() -> None:
    registry = build_default_evaluator_registry()

    with pytest.raises(ValueError, match="is registered"):
        registry.register(registry.resolve("real_core_board_count", "1"))


def test_experiment_information_mode_must_match_input() -> None:
    experiment = _experiment()
    experiment["information_mode"] = "player_view"

    with pytest.raises(ValueError, match="information_mode"):
        build_default_evaluator_registry().evaluate_experiment(experiment, _state())


def test_board_count_evaluator_applies_missing_value_policy() -> None:
    state = _state()
    state = EvaluationInput(
        state_hash=state.state_hash,
        board_summary={
            "zone_counts": {
                "0": {"monster_zone": 1},
                "1": {"hand": 0, "monster_zone": 0},
            }
        },
        turn=state.turn,
        phase=state.phase,
        information_mode=state.information_mode,
    )
    experiment = _experiment()
    experiment["evaluator"]["config"]["missing_value_policy"] = "zero"

    result = build_default_evaluator_registry().evaluate_experiment(
        experiment, state
    )

    assert result.vector == {"field_count": 1, "hand_count": 0}
    assert result.score_breakdown.to_dict()["missing_metrics"] == ["hand_count"]
    assert result.score_breakdown.to_dict()["terms"][1]["resolution"] == "zero"


def test_board_break_evaluator_scores_observed_public_zones() -> None:
    state = EvaluationInput(
        state_hash="state_board_break",
        board_summary={
            "zone_counts": {
                "0": {"hand": 3, "monster_zone": 1},
                "1": {
                    "banished": 1,
                    "graveyard": 0,
                    "monster_zone": 0,
                    "spell_trap_zone": 1,
                },
            }
        },
        turn=1,
        phase="main1",
        information_mode="complete_information",
    )
    experiment = {
        "experiment_id": "board_break_evaluation_fixture",
        "evaluate_at": "legal_stop",
        "information_mode": "complete_information",
        "evaluator": {
            "id": "real_core_board_break",
            "version": "1",
            "config": {
                "actor_player": 0,
                "weights": {
                    "opponent_banished_count": 5,
                    "opponent_monster_count": -10,
                    "opponent_spell_trap_count": -6,
                },
            },
        },
    }

    result = build_default_evaluator_registry().evaluate_experiment(
        experiment, state
    )

    assert result.vector == {
        "opponent_banished_count": 1,
        "opponent_monster_count": 0,
        "opponent_spell_trap_count": 1,
    }
    assert result.total_score == -1
    assert result.explanations == (
        {
            "actor_player": 0,
            "opponent_player": 1,
            "schema_version": "board-break-evaluation-v1",
        },
    )


def test_board_break_evaluator_rejects_unknown_config() -> None:
    experiment = {
        "experiment_id": "invalid_board_break_evaluation_fixture",
        "evaluate_at": "legal_stop",
        "information_mode": "complete_information",
        "evaluator": {
            "id": "real_core_board_break",
            "version": "1",
            "config": {"actor_player": 0, "inferred_card_power": 10},
        },
    }

    with pytest.raises(ValueError, match="unknown config keys"):
        build_default_evaluator_registry().evaluate_experiment(
            experiment,
            EvaluationInput(
                state_hash="state_invalid_board_break",
                board_summary={"zone_counts": {"0": {}, "1": {}}},
                turn=1,
                phase="main1",
                information_mode="complete_information",
            ),
        )
