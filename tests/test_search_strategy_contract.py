from __future__ import annotations

import math

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.engine.search import (
    BeamSearchParametersV1,
    MctsSearchParametersV1,
    RandomSearchStrategyV1,
    beam_rank_key,
    build_strategy_conformance_report,
    deterministic_decision_key,
    mcts_uct_score,
    normalize_mcts_reward,
)


def _action(candidate_id: str) -> Action:
    return Action(
        kind=ActionKind.NORMAL_SUMMON,
        player=0,
        selections=(Selection(candidate_id=candidate_id),),
        request_signature="req_strategy_contract",
    )


def test_random_v1_satisfies_the_common_strategy_contract() -> None:
    strategy = RandomSearchStrategyV1(seed=71)
    actions = tuple(_action(name) for name in ("left", "middle", "right"))

    first = build_strategy_conformance_report(
        strategy, node_id="node_fixture", actions=actions
    )
    second = build_strategy_conformance_report(
        strategy, node_id="node_fixture", actions=tuple(reversed(actions))
    )

    assert first == second
    assert first["strategy_conformance_schema_version"] == (
        "search-strategy-conformance-v1"
    )
    assert first["execution_mode"] == "depth_first"
    assert first["conformance_id"].startswith("strategyconf_")


def test_deterministic_decision_key_is_purpose_and_seed_scoped() -> None:
    base = {
        "strategy_id": "fixture",
        "strategy_version": "fixture-v1",
        "node_id": "node_a",
        "purpose": "selection",
        "candidate_id": "candidate_a",
    }
    assert deterministic_decision_key(seed=3, **base) == deterministic_decision_key(
        seed=3, **base
    )
    assert deterministic_decision_key(seed=3, **base) != deterministic_decision_key(
        seed=4, **base
    )
    assert deterministic_decision_key(seed=3, **base) != deterministic_decision_key(
        seed=3, **{**base, "purpose": "rollout"}
    )


def test_beam_v1_parameters_and_rank_vectors() -> None:
    parameters = BeamSearchParametersV1.from_mapping(
        {"beam_width": 2, "seed": 11}
    )
    candidates = [
        ("failed_high", False, 100, 100, 1),
        ("success_lower", True, 10, 9, 2),
        ("success_tie_b", True, 10, 9, 2),
        ("success_tie_a", True, 10, 9, 2),
    ]
    ranked = sorted(
        candidates,
        key=lambda item: beam_rank_key(
            success=item[1],
            peak_score=item[2],
            terminal_score=item[3],
            action_count=item[4],
            semantic_prefix_id=item[0],
        ),
    )

    assert parameters.to_dict() == {"beam_width": 2, "seed": 11}
    assert [item[0] for item in ranked[: parameters.beam_width]] == [
        "success_lower",
        "success_tie_a",
    ]
    with pytest.raises(ValueError, match="unknown strategy parameters"):
        BeamSearchParametersV1.from_mapping({"beam_width": 2, "workers": 4})


def test_mcts_v1_reward_and_uct_vectors() -> None:
    parameters = MctsSearchParametersV1.from_mapping(
        {
            "simulations": 8,
            "reward_floor": -10,
            "reward_ceiling": 20,
            "exploration_constant": 1.25,
            "seed": 5,
        }
    )

    failed_max = normalize_mcts_reward(
        success=False,
        terminal_score=20,
        reward_floor=-10,
        reward_ceiling=20,
    )
    success_min = normalize_mcts_reward(
        success=True,
        terminal_score=-10,
        reward_floor=-10,
        reward_ceiling=20,
    )
    assert failed_max == pytest.approx(1 / 3)
    assert success_min == pytest.approx(2 / 3)
    assert success_min > failed_max
    assert math.isinf(
        mcts_uct_score(
            parent_visits=4,
            child_visits=0,
            child_value_sum=0,
            exploration_constant=parameters.exploration_constant,
        )
    )
    assert mcts_uct_score(
        parent_visits=4,
        child_visits=2,
        child_value_sum=1,
        exploration_constant=0,
    ) == pytest.approx(0.5)


@pytest.mark.parametrize(
    "parameters",
    [
        {"simulations": 0, "reward_floor": 0, "reward_ceiling": 1},
        {"simulations": 1, "reward_floor": 1, "reward_ceiling": 1},
        {
            "simulations": 1,
            "reward_floor": 0,
            "reward_ceiling": 1,
            "resume_from": "checkpoint",
        },
    ],
)
def test_mcts_v1_rejects_invalid_or_resume_parameters(parameters: dict) -> None:
    with pytest.raises(ValueError):
        MctsSearchParametersV1.from_mapping(parameters)
