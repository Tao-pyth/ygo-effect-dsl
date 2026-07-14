from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.search import (
    SearchBudget,
    SearchTerminationMonitor,
    TerminationReason,
)


def test_depth_node_and_replay_budgets_stop_with_distinct_reasons() -> None:
    depth = SearchTerminationMonitor(SearchBudget(max_depth=2))
    assert depth.check_before_expand(depth=1) is None
    assert depth.check_before_expand(depth=2).reason == TerminationReason.MAX_DEPTH

    nodes = SearchTerminationMonitor(SearchBudget(max_nodes=2))
    assert nodes.observe_node(depth=0, score=0, success=False) is None
    assert nodes.observe_node(depth=1, score=1, success=False).reason == (
        TerminationReason.MAX_NODES
    )

    replays = SearchTerminationMonitor(SearchBudget(max_replays=3))
    assert replays.observe_node(
        depth=0, score=0, success=False, replay_count=2
    ) is None
    assert replays.observe_node(
        depth=1, score=0, success=False, replay_count=1
    ).reason == TerminationReason.MAX_REPLAYS


def test_goal_score_and_success_stop_before_resource_budget() -> None:
    target = SearchTerminationMonitor(SearchBudget(max_nodes=100, target_score=10))
    success = SearchTerminationMonitor(
        SearchBudget(max_nodes=100, stop_on_success=True)
    )

    assert target.observe_node(depth=2, score=10, success=False).reason == (
        TerminationReason.GOAL_REACHED
    )
    assert success.observe_node(depth=1, score=0, success=True).reason == (
        TerminationReason.GOAL_REACHED
    )


def test_stagnation_counts_nodes_without_strict_improvement() -> None:
    monitor = SearchTerminationMonitor(
        SearchBudget(max_nodes=100, stagnation_nodes=2)
    )

    assert monitor.observe_node(depth=0, score=5, success=False) is None
    assert monitor.observe_node(depth=1, score=5, success=False) is None
    decision = monitor.observe_node(depth=2, score=4, success=False)

    assert decision.reason == TerminationReason.STAGNATION
    assert decision.detail == {"nodes_since_improvement": 2}


def test_repeated_transition_detects_loop_without_blocking_same_action_elsewhere() -> None:
    monitor = SearchTerminationMonitor(
        SearchBudget(max_nodes=100, max_transition_repetitions=3)
    )
    repeated = ("state_a", "act_loop", "state_b")

    assert monitor.observe_node(
        depth=0,
        score=0,
        success=False,
        transition=repeated,
    ) is None
    assert monitor.observe_node(
        depth=1,
        score=0,
        success=False,
        transition=("state_c", "act_loop", "state_d"),
    ) is None
    assert monitor.observe_node(
        depth=2,
        score=0,
        success=False,
        transition=repeated,
    ) is None
    decision = monitor.observe_node(
        depth=3,
        score=0,
        success=False,
        transition=repeated,
    )

    assert decision.reason == TerminationReason.REPEATED_TRANSITION
    assert decision.detail["visits"] == 3


def test_time_budget_uses_injected_monotonic_clock() -> None:
    current = [100.0]
    monitor = SearchTerminationMonitor(
        SearchBudget(max_seconds=5), clock=lambda: current[0]
    )
    current[0] = 104.9
    assert monitor.check_before_expand(depth=0) is None
    current[0] = 105.0

    decision = monitor.check_before_expand(depth=0)

    assert decision.reason == TerminationReason.MAX_SECONDS
    assert decision.elapsed_seconds == 5.0


def test_first_termination_decision_is_sticky_and_hash_identified() -> None:
    monitor = SearchTerminationMonitor(SearchBudget(max_nodes=1, max_depth=1))
    first = monitor.observe_node(depth=0, score=1, success=False)
    second = monitor.check_before_expand(depth=1)

    assert first is second
    assert second.reason == TerminationReason.MAX_NODES
    assert second.to_dict()["decision_id"].startswith("stop_")
    assert second.to_dict()["schema_version"] == "search-termination-v1"


def test_budget_parser_rejects_unknown_or_empty_configuration() -> None:
    with pytest.raises(ValueError, match="at least one"):
        SearchBudget()
    with pytest.raises(ValueError, match="unknown search termination"):
        SearchBudget.from_mapping({"max_nodes": 10, "typo_limit": 2})


def test_budget_is_resolved_from_existing_experiment_search_boundaries() -> None:
    budget = SearchBudget.from_experiment(
        {
            "search": {
                "budget": {"max_nodes": 100, "max_seconds": 30},
                "parameters": {
                    "termination": {
                        "max_depth": 12,
                        "max_replays": 40,
                        "stagnation_nodes": 20,
                    }
                },
            }
        }
    )

    assert budget.max_nodes == 100
    assert budget.max_seconds == 30
    assert budget.max_depth == 12
    assert budget.max_replays == 40
    assert budget.stagnation_nodes == 20
