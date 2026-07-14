from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.engine.search import (
    RandomSearchStrategyV1,
    SearchBudget,
    SearchExecutor,
    SearchFrontier,
    UnsupportedSearchStrategyError,
    strategy_from_experiment,
)


def _action(name: str, kind: ActionKind = ActionKind.NORMAL_SUMMON) -> Action:
    return Action(
        kind=kind,
        player=0,
        selections=(Selection(candidate_id=name),),
        request_signature="req_fixture",
    )


class FakeFrontierAdapter:
    def __init__(self, frontiers: Mapping[tuple[str, ...], SearchFrontier]) -> None:
        self.frontiers = frontiers
        self.prefixes: list[tuple[str, ...]] = []

    def replay(
        self, _experiment: Mapping, action_prefix: Sequence[Action]
    ) -> SearchFrontier:
        key = tuple(action.selections[0].candidate_id for action in action_prefix)
        self.prefixes.append(key)
        return self.frontiers[key]


def _frontier(
    state: str,
    *,
    actions: tuple[Action, ...] = (),
    score: int = 0,
    peak: int | None = None,
    success: bool = False,
    legal: bool = False,
) -> SearchFrontier:
    route = (
        {
            "route_id": f"route_{state}",
            "result": {"success": success},
        }
        if legal
        else None
    )
    return SearchFrontier(
        state_id=state,
        request={"request_signature": "req_fixture"},
        actions=actions,
        score=score,
        peak_score=score if peak is None else peak,
        success=success,
        legal_stop=legal,
        legal_stop_reason="core_end_turn_available" if legal else "pending_request",
        route_document=route,
    )


def _experiment(seed: int = 17) -> dict:
    return {
        "experiment_id": "search_executor_test",
        "search": {
            "strategy": "random_search_v1",
            "budget": {"max_nodes": 20},
            "parameters": {"seed": seed},
        },
    }


def test_random_search_is_semantically_deterministic() -> None:
    left = _action("left")
    right = _action("right")
    frontiers = {
        (): _frontier("root", actions=(left, right)),
        ("left",): _frontier("left", score=5, peak=12, legal=True),
        ("right",): _frontier("right", score=9, peak=9, success=True, legal=True),
    }

    first = SearchExecutor(
        FakeFrontierAdapter(frontiers),
        RandomSearchStrategyV1(41),
        SearchBudget(max_nodes=20),
        clock=lambda: 0.0,
    ).run(_experiment())
    second = SearchExecutor(
        FakeFrontierAdapter(frontiers),
        RandomSearchStrategyV1(41),
        SearchBudget(max_nodes=20),
        clock=lambda: 0.0,
    ).run(_experiment())

    assert first.semantic_dict() == second.semantic_dict()
    assert first.run_id == second.run_id
    assert first.best_route is not None
    assert first.best_route.route_id == "route_right"
    assert [route.route_id for route in first.routes] == ["route_right", "route_left"]


def test_seed_changes_budget_limited_exploration_order() -> None:
    actions = tuple(_action(name) for name in ("a", "b", "c", "d"))
    frontiers = {(): _frontier("root", actions=actions)}
    frontiers.update(
        {(name,): _frontier(name, score=index, legal=True) for index, name in enumerate(("a", "b", "c", "d"))}
    )

    observed = set()
    for seed in range(10):
        adapter = FakeFrontierAdapter(frontiers)
        SearchExecutor(
            adapter,
            RandomSearchStrategyV1(seed),
            SearchBudget(max_nodes=2),
            clock=lambda: 0.0,
        ).run(_experiment(seed))
        observed.add(adapter.prefixes[1])

    assert len(observed) > 1


def test_stop_line_is_terminal_and_end_turn_remains_a_core_action() -> None:
    end_turn = _action("control:end_turn", ActionKind.END_TURN)
    summon = _action("summon")
    adapter = FakeFrontierAdapter(
        {
            (): _frontier("root", actions=(summon,)),
            ("summon",): _frontier(
                "summoned", actions=(end_turn,), score=10, legal=True
            ),
            ("summon", "control:end_turn"): _frontier(
                "next_turn", score=8, legal=True
            ),
        }
    )

    result = SearchExecutor(
        adapter,
        RandomSearchStrategyV1(1),
        SearchBudget(max_nodes=10, max_depth=2),
        clock=lambda: 0.0,
    ).run(_experiment())

    assert ("summon",) in adapter.prefixes
    assert ("summon", "control:end_turn") in adapter.prefixes
    assert {route.action_count for route in result.routes} == {1, 2}


def test_exact_state_identity_deduplicates_only_after_recording_routes() -> None:
    left = _action("left")
    right = _action("right")
    child = _action("child")
    adapter = FakeFrontierAdapter(
        {
            (): _frontier("root", actions=(left, right)),
            ("left",): _frontier("same", actions=(child,), legal=True),
            ("right",): _frontier("same", actions=(child,), legal=True),
            ("left", "child"): _frontier("left-child", legal=True),
            ("right", "child"): _frontier("right-child", legal=True),
        }
    )

    result = SearchExecutor(
        adapter,
        RandomSearchStrategyV1(3),
        SearchBudget(max_nodes=10),
        clock=lambda: 0.0,
    ).run(_experiment())

    assert result.exact_state_duplicates == 1
    assert len([prefix for prefix in adapter.prefixes if len(prefix) == 2]) == 1
    assert len([route for route in result.routes if route.action_count == 1]) == 2


def test_beam_and_mcts_are_explicitly_unimplemented() -> None:
    for strategy in ("beam_search_v1", "mcts_v1"):
        experiment = _experiment()
        experiment["search"]["strategy"] = strategy
        with pytest.raises(UnsupportedSearchStrategyError, match="not implemented"):
            strategy_from_experiment(experiment)


def test_worker_error_stops_only_the_affected_path() -> None:
    failing = _action("failing")
    healthy = _action("healthy")

    class PathFailureAdapter(FakeFrontierAdapter):
        def replay(self, experiment: Mapping, action_prefix: Sequence[Action]) -> SearchFrontier:
            key = tuple(action.selections[0].candidate_id for action in action_prefix)
            if key == ("failing",):
                raise RuntimeError("ambiguous interruption response")
            return super().replay(experiment, action_prefix)

    adapter = PathFailureAdapter(
        {
            (): _frontier("root", actions=(failing, healthy)),
            ("healthy",): _frontier("healthy", score=4, legal=True),
        }
    )
    result = SearchExecutor(
        adapter,
        RandomSearchStrategyV1(9),
        SearchBudget(max_nodes=10),
        clock=lambda: 0.0,
    ).run(_experiment())

    assert result.best_route is not None
    assert len(result.path_failures) == 1
    assert result.path_failures[0]["status"] == "path_failure"
