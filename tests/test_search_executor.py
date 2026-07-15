from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    FailureRecord,
    FailureRecordError,
    RecoveryAction,
)
from ygo_effect_dsl.engine.search import (
    BeamSearchStrategyV1,
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
    state_completeness: str = "exact",
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
        state_completeness=state_completeness,
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


def _beam_experiment(beam_width: int = 1, seed: int = 17) -> dict:
    return {
        "experiment_id": "beam_search_executor_test",
        "search": {
            "strategy": "beam_search_v1",
            "budget": {"max_nodes": 20},
            "parameters": {"beam_width": beam_width, "seed": seed},
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
    assert first.executor_schema_version == "search-executor-v5"
    assert first.experiment_digest.startswith("experiment_")
    assert first.frontier_schema_version == "search-frontier-v2"
    assert first.schema_version == "search-run-result-v5"
    assert first.strategy_schema_version == "random-search-strategy-v1"
    assert first.strategy_parameters == {"seed": 41}
    assert first.strategy_evidence["evidence_id"].startswith("strategyevidence_")
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


def test_query_api_projection_never_deduplicates_search_branches() -> None:
    left = _action("left")
    right = _action("right")
    child = _action("child")
    adapter = FakeFrontierAdapter(
        {
            (): _frontier(
                "projected-root",
                state_completeness="query_api_projection",
                actions=(left, right),
            ),
            ("left",): _frontier(
                "same-projection",
                state_completeness="query_api_projection",
                actions=(child,),
                legal=True,
            ),
            ("right",): _frontier(
                "same-projection",
                state_completeness="query_api_projection",
                actions=(child,),
                legal=True,
            ),
            ("left", "child"): _frontier(
                "left-child",
                state_completeness="query_api_projection",
                legal=True,
            ),
            ("right", "child"): _frontier(
                "right-child",
                state_completeness="query_api_projection",
                legal=True,
            ),
        }
    )

    result = SearchExecutor(
        adapter,
        RandomSearchStrategyV1(3),
        SearchBudget(max_nodes=10),
        clock=lambda: 0.0,
    ).run(_experiment())

    assert result.exact_state_duplicates == 0
    assert len([prefix for prefix in adapter.prefixes if len(prefix) == 2]) == 2
    assert len([route for route in result.routes if route.action_count == 2]) == 2


def test_search_frontier_rejects_an_old_schema_version() -> None:
    with pytest.raises(ValueError, match="unsupported SearchFrontier schema"):
        SearchFrontier(
            state_id="state",
            state_completeness="exact",
            request={"request_signature": "req_fixture"},
            actions=(),
            score=0,
            peak_score=0,
            success=False,
            legal_stop=False,
            legal_stop_reason="pending_request",
            schema_version="search-frontier-v1",
        )


@pytest.mark.parametrize(
    ("field_name", "old_version"),
    [
        ("executor_schema_version", "search-executor-v2"),
        ("frontier_schema_version", "search-frontier-v1"),
        ("schema_version", "search-run-result-v2"),
    ],
)
def test_search_run_rejects_old_or_mixed_version_provenance(
    field_name: str, old_version: str
) -> None:
    result = SearchExecutor(
        FakeFrontierAdapter({(): _frontier("root")}),
        RandomSearchStrategyV1(1),
        SearchBudget(max_nodes=1),
        clock=lambda: 0.0,
    ).run(_experiment())

    with pytest.raises(ValueError, match="version provenance"):
        replace(result, **{field_name: old_version})


def test_search_run_rejects_an_invalid_experiment_digest() -> None:
    result = SearchExecutor(
        FakeFrontierAdapter({(): _frontier("root")}),
        RandomSearchStrategyV1(1),
        SearchBudget(max_nodes=1),
        clock=lambda: 0.0,
    ).run(_experiment())

    with pytest.raises(ValueError, match="experiment_digest"):
        replace(result, experiment_digest="experiment_tampered")


def test_beam_strategy_is_constructed_and_mcts_remains_unimplemented() -> None:
    experiment = _experiment()
    experiment["search"]["strategy"] = "beam_search_v1"
    experiment["search"]["parameters"] = {
        "beam_width": 2,
        "max_frontier_actions": 128,
        "seed": 17,
        "termination": {"stop_on_success": True},
    }

    strategy = strategy_from_experiment(experiment)

    assert isinstance(strategy, BeamSearchStrategyV1)
    assert strategy.parameters == {"beam_width": 2, "seed": 17}

    experiment["search"]["strategy"] = "mcts_v1"
    experiment["search"]["parameters"] = {
        "reward_ceiling": 100,
        "reward_floor": 0,
        "seed": 17,
        "simulations": 4,
    }
    with pytest.raises(UnsupportedSearchStrategyError, match="not implemented"):
        strategy_from_experiment(experiment)


def test_beam_width_one_is_greedy_by_complete_layer_score() -> None:
    left = _action("left")
    right = _action("right")
    left_finish = _action("left_finish")
    right_finish = _action("right_finish")
    adapter = FakeFrontierAdapter(
        {
            (): _frontier("root", actions=(right, left)),
            ("left",): _frontier(
                "left", actions=(left_finish,), score=20, legal=True
            ),
            ("right",): _frontier(
                "right", actions=(right_finish,), score=10, legal=True
            ),
            ("left", "left_finish"): _frontier(
                "left-finish", score=1, legal=True
            ),
            ("right", "right_finish"): _frontier(
                "right-finish", score=100, success=True, legal=True
            ),
        }
    )

    result = SearchExecutor(
        adapter,
        BeamSearchStrategyV1(beam_width=1, seed=5),
        SearchBudget(max_nodes=20),
        clock=lambda: 0.0,
    ).run(_beam_experiment(beam_width=1, seed=5))

    assert {prefix for prefix in adapter.prefixes if len(prefix) == 1} == {
        ("left",),
        ("right",),
    }
    assert [prefix for prefix in adapter.prefixes if len(prefix) == 2] == [
        ("left", "left_finish")
    ]
    assert result.best_route is not None
    assert result.best_route.route_id == "route_left"
    assert result.strategy_schema_version == "beam-search-strategy-v1"
    assert result.strategy_parameters == {"beam_width": 1, "seed": 5}


def test_beam_success_precedes_a_higher_failure_score() -> None:
    successful = _action("successful")
    high_score = _action("high_score")
    success_child = _action("success_child")
    score_child = _action("score_child")
    adapter = FakeFrontierAdapter(
        {
            (): _frontier("root", actions=(successful, high_score)),
            ("successful",): _frontier(
                "successful",
                actions=(success_child,),
                score=0,
                success=True,
                legal=True,
            ),
            ("high_score",): _frontier(
                "high-score", actions=(score_child,), score=100, legal=True
            ),
            ("successful", "success_child"): _frontier(
                "success-child", score=0, success=True, legal=True
            ),
            ("high_score", "score_child"): _frontier(
                "score-child", score=200, legal=True
            ),
        }
    )

    result = SearchExecutor(
        adapter,
        BeamSearchStrategyV1(beam_width=1),
        SearchBudget(max_nodes=20),
        clock=lambda: 0.0,
    ).run(_beam_experiment())

    assert [prefix for prefix in adapter.prefixes if len(prefix) == 2] == [
        ("successful", "success_child")
    ]
    assert result.best_route is not None
    assert result.best_route.success is True


def test_beam_does_not_select_from_a_budget_truncated_layer() -> None:
    actions = tuple(_action(name) for name in ("a", "b", "c"))
    child = _action("child")
    frontiers = {(): _frontier("root", actions=actions)}
    frontiers.update(
        {
            (name,): _frontier(name, actions=(child,), score=index)
            for index, name in enumerate(("a", "b", "c"))
        }
    )
    adapter = FakeFrontierAdapter(frontiers)

    result = SearchExecutor(
        adapter,
        BeamSearchStrategyV1(beam_width=2, seed=19),
        SearchBudget(max_nodes=3),
        clock=lambda: 0.0,
    ).run(_beam_experiment(beam_width=2, seed=19))

    assert result.termination_reason == "max_nodes"
    assert len([prefix for prefix in adapter.prefixes if len(prefix) == 1]) == 2
    assert not [prefix for prefix in adapter.prefixes if len(prefix) == 2]
    layer = result.strategy_evidence["logical_updates"][-1]
    assert layer["complete"] is False
    assert layer["selected_prefix_ids"] == []


@pytest.mark.parametrize(
    ("state_completeness", "expected_duplicates", "expected_depth_two"),
    [("exact", 1, 1), ("query_api_projection", 0, 2)],
)
def test_beam_deduplicates_only_exact_state_identity(
    state_completeness: str,
    expected_duplicates: int,
    expected_depth_two: int,
) -> None:
    left = _action("left")
    right = _action("right")
    child = _action("child")
    adapter = FakeFrontierAdapter(
        {
            (): _frontier("root", actions=(left, right)),
            ("left",): _frontier(
                "same",
                state_completeness=state_completeness,
                actions=(child,),
            ),
            ("right",): _frontier(
                "same",
                state_completeness=state_completeness,
                actions=(child,),
            ),
            ("left", "child"): _frontier("left-child", legal=True),
            ("right", "child"): _frontier("right-child", legal=True),
        }
    )

    result = SearchExecutor(
        adapter,
        BeamSearchStrategyV1(beam_width=2, seed=3),
        SearchBudget(max_nodes=10),
        clock=lambda: 0.0,
    ).run(_beam_experiment(beam_width=2, seed=3))

    assert result.exact_state_duplicates == expected_duplicates
    assert len([prefix for prefix in adapter.prefixes if len(prefix) == 2]) == (
        expected_depth_two
    )


def test_search_run_rejects_tampered_strategy_evidence() -> None:
    result = SearchExecutor(
        FakeFrontierAdapter({(): _frontier("root")}),
        RandomSearchStrategyV1(1),
        SearchBudget(max_nodes=1),
        clock=lambda: 0.0,
    ).run(_experiment(seed=1))
    tampered = dict(result.strategy_evidence)
    tampered["parameters"] = {"seed": 999}

    with pytest.raises(ValueError, match="content ID"):
        replace(result, strategy_evidence=tampered)


def test_beam_worker_failure_keeps_healthy_siblings_searchable() -> None:
    failing = _action("failing")
    healthy = _action("healthy")

    class PathFailureAdapter(FakeFrontierAdapter):
        def replay(
            self, experiment: Mapping, action_prefix: Sequence[Action]
        ) -> SearchFrontier:
            key = tuple(
                action.selections[0].candidate_id for action in action_prefix
            )
            if key == ("failing",):
                raise RuntimeError("worker crashed")
            return super().replay(experiment, action_prefix)

    adapter = PathFailureAdapter(
        {
            (): _frontier("root", actions=(failing, healthy)),
            ("healthy",): _frontier("healthy", score=4, legal=True),
        }
    )

    result = SearchExecutor(
        adapter,
        BeamSearchStrategyV1(beam_width=2, seed=9),
        SearchBudget(max_nodes=10),
        clock=lambda: 0.0,
    ).run(_beam_experiment(beam_width=2, seed=9))

    assert result.best_route is not None
    assert result.best_route.route_id == "route_healthy"
    assert len(result.path_failures) == 1
    assert result.path_failures[0]["status"] == "path_failure"


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


def test_worker_failure_record_is_preserved_in_search_run() -> None:
    failing = _action("failing")
    healthy = _action("healthy")
    failure = FailureRecord(
        category="worker_timeout",
        disposition=FailureDisposition.PATH_FAILURE,
        recovery=RecoveryAction.REPLACE_WORKER,
        retryable=True,
        message="worker deadline exceeded",
        exception_type="OcgcoreWorkerTimeoutError",
        context={"attempt_ids": ["frontierattempt_fixture"]},
    )

    class StructuredFailureAdapter(FakeFrontierAdapter):
        def replay(self, experiment: Mapping, action_prefix: Sequence[Action]) -> SearchFrontier:
            key = tuple(action.selections[0].candidate_id for action in action_prefix)
            if key == ("failing",):
                raise FailureRecordError(failure)
            return super().replay(experiment, action_prefix)

    result = SearchExecutor(
        StructuredFailureAdapter(
            {
                (): _frontier("root", actions=(failing, healthy)),
                ("healthy",): _frontier("healthy", score=4, legal=True),
            }
        ),
        RandomSearchStrategyV1(9),
        SearchBudget(max_nodes=10),
        clock=lambda: 0.0,
    ).run(_experiment())

    assert result.best_route is not None
    assert result.path_failures[0]["failure"] == failure.to_dict()
