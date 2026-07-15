from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from ygo_effect_dsl.engine.action import Action
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.failures import FailureRecord
from ygo_effect_dsl.engine.search.parallel import build_search_node_id
from ygo_effect_dsl.engine.search.strategy import (
    RANDOM_SEARCH_STRATEGY_SCHEMA_VERSION,
    RandomSearchStrategyV1,
    SearchStrategy,
    UnsupportedSearchStrategyError,
    strategy_from_experiment,
)
from ygo_effect_dsl.engine.search.termination import SearchBudget, TerminationReason


SEARCH_EXECUTOR_SCHEMA_VERSION = "search-executor-v4"
SEARCH_FRONTIER_SCHEMA_VERSION = "search-frontier-v2"
SEARCH_RUN_RESULT_SCHEMA_VERSION = "search-run-result-v4"
SEARCH_RUN_REPORT_SCHEMA_VERSION = "search-run-report-v1"
SEARCH_RUN_FAILURE_SCHEMA_VERSION = "search-run-failure-v2"
SEARCH_ARTIFACT_COMMIT_SCHEMA_VERSION = "search-artifact-commit-v1"


@dataclass(frozen=True)
class SearchFrontier:
    state_id: str
    state_completeness: str
    request: Mapping[str, Any]
    actions: tuple[Action, ...]
    score: int | float
    peak_score: int | float
    success: bool
    legal_stop: bool
    legal_stop_reason: str
    route_document: Mapping[str, Any] | None = None
    replay_count: int = 1
    schema_version: str = SEARCH_FRONTIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SEARCH_FRONTIER_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported SearchFrontier schema {self.schema_version!r}"
            )
        if self.state_completeness not in {"exact", "query_api_projection"}:
            raise ValueError(
                "state_completeness must be 'exact' or 'query_api_projection'"
            )
        if not isinstance(self.actions, tuple):
            object.__setattr__(self, "actions", tuple(self.actions))
        if self.route_document is not None and not self.legal_stop:
            raise ValueError("route_document requires a legal stop")
        if self.legal_stop and self.route_document is None:
            raise ValueError("a legal stop requires a replayable route_document")
        if not isinstance(self.replay_count, int) or self.replay_count < 1:
            raise ValueError("replay_count must be an integer >= 1")


class FrontierAdapter(Protocol):
    def replay(
        self,
        experiment: Mapping[str, Any],
        action_prefix: Sequence[Action],
    ) -> SearchFrontier: ...


@dataclass(frozen=True)
class SearchRouteSummary:
    route_id: str
    success: bool
    peak_score: int | float
    terminal_score: int | float
    action_count: int
    action_ids: tuple[str, ...]
    route_document: Mapping[str, Any]

    @property
    def rank_key(self) -> tuple[Any, ...]:
        return (
            -int(self.success),
            -self.peak_score,
            -self.terminal_score,
            self.action_count,
            self.route_id,
        )

    def to_dict(self, *, include_document: bool = False) -> dict[str, Any]:
        payload = {
            "action_count": self.action_count,
            "action_ids": list(self.action_ids),
            "peak_score": self.peak_score,
            "route_id": self.route_id,
            "success": self.success,
            "terminal_score": self.terminal_score,
        }
        if include_document:
            payload["route_document"] = to_canonical_data(self.route_document)
        return payload


@dataclass(frozen=True)
class SearchRunResult:
    experiment_id: str
    experiment_digest: str
    strategy_id: str
    termination_reason: str
    nodes: int
    replays: int
    max_depth_reached: int
    exact_state_duplicates: int
    prefix_cache_hits: int
    prefix_cache_entries: int
    path_failures: tuple[Mapping[str, Any], ...]
    routes: tuple[SearchRouteSummary, ...]
    best_route: SearchRouteSummary | None
    elapsed_seconds: float
    executor_schema_version: str = SEARCH_EXECUTOR_SCHEMA_VERSION
    frontier_schema_version: str = SEARCH_FRONTIER_SCHEMA_VERSION
    schema_version: str = SEARCH_RUN_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        observed = (
            self.executor_schema_version,
            self.frontier_schema_version,
            self.schema_version,
        )
        expected = (
            SEARCH_EXECUTOR_SCHEMA_VERSION,
            SEARCH_FRONTIER_SCHEMA_VERSION,
            SEARCH_RUN_RESULT_SCHEMA_VERSION,
        )
        if observed != expected:
            raise ValueError(
                "unsupported SearchRunResult version provenance: "
                f"observed={observed!r}, expected={expected!r}"
            )
        if not isinstance(self.experiment_digest, str):
            raise ValueError("experiment_digest must be an experiment_ content ID")
        digest = self.experiment_digest.removeprefix("experiment_")
        if (
            not self.experiment_digest.startswith("experiment_")
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("experiment_digest must be an experiment_ content ID")

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "best_route": self.best_route.to_dict() if self.best_route else None,
            "exact_state_duplicates": self.exact_state_duplicates,
            "executor_schema_version": self.executor_schema_version,
            "experiment_digest": self.experiment_digest,
            "experiment_id": self.experiment_id,
            "frontier_schema_version": self.frontier_schema_version,
            "max_depth_reached": self.max_depth_reached,
            "nodes": self.nodes,
            "path_failures": [to_canonical_data(item) for item in self.path_failures],
            "prefix_cache_entries": self.prefix_cache_entries,
            "prefix_cache_hits": self.prefix_cache_hits,
            "replays": self.replays,
            "routes": [route.to_dict() for route in self.routes],
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "termination_reason": self.termination_reason,
        }

    @property
    def run_id(self) -> str:
        return stable_digest(self.semantic_dict(), prefix="searchrun_")

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_dict(),
            "elapsed_seconds": self.elapsed_seconds,
            "run_id": self.run_id,
        }


class SearchExecutor:
    schema_version = SEARCH_EXECUTOR_SCHEMA_VERSION

    def __init__(
        self,
        adapter: FrontierAdapter,
        strategy: SearchStrategy,
        budget: SearchBudget,
        *,
        clock: Any = time.monotonic,
    ) -> None:
        self.adapter = adapter
        self.strategy = strategy
        self.budget = budget
        self.clock = clock

    def run(self, experiment: Mapping[str, Any]) -> SearchRunResult:
        experiment_id = str(experiment.get("experiment_id", ""))
        if not experiment_id:
            raise ValueError("experiment_id must be a non-empty string")
        started = self.clock()
        pending: list[tuple[Action, ...]] = [()]
        cache: dict[tuple[str, ...], SearchFrontier] = {}
        node_ids: dict[tuple[str, ...], str] = {}
        seen_states: set[str] = set()
        routes: list[SearchRouteSummary] = []
        nodes = 0
        replays = 0
        cache_hits = 0
        duplicates = 0
        path_failures: list[Mapping[str, Any]] = []
        max_depth_reached = 0
        termination = TerminationReason.EXHAUSTED
        while pending:
            elapsed = self.clock() - started
            if self.budget.max_seconds is not None and elapsed >= self.budget.max_seconds:
                termination = TerminationReason.MAX_SECONDS
                break
            if self.budget.max_nodes is not None and nodes >= self.budget.max_nodes:
                termination = TerminationReason.MAX_NODES
                break
            if self.budget.max_replays is not None and replays >= self.budget.max_replays:
                termination = TerminationReason.MAX_REPLAYS
                break
            prefix = pending.pop()
            depth = len(prefix)
            max_depth_reached = max(max_depth_reached, depth)
            key = tuple(action.action_id for action in prefix)
            frontier = cache.get(key)
            if frontier is None:
                try:
                    frontier = self.adapter.replay(experiment, prefix)
                except Exception as exc:
                    if not prefix:
                        raise
                    nodes += 1
                    replays += 1
                    path_failure = {
                        "action_ids": list(key),
                        "depth": depth,
                        "exception_type": type(exc).__name__,
                        "message": str(exc),
                        "status": "path_failure",
                    }
                    failure = getattr(exc, "failure", None)
                    if isinstance(failure, FailureRecord):
                        path_failure["failure"] = failure.to_dict()
                    path_failures.append(path_failure)
                    continue
                cache[key] = frontier
                replays += frontier.replay_count
            else:
                cache_hits += 1
            nodes += 1
            if frontier.legal_stop and prefix:
                assert frontier.route_document is not None
                route_id = str(frontier.route_document.get("route_id", ""))
                if not route_id:
                    route_id = stable_digest(
                        {
                            "experiment_id": experiment_id,
                            "prefix": list(key),
                            "state_id": frontier.state_id,
                        },
                        prefix="route_",
                    )
                routes.append(
                    SearchRouteSummary(
                        route_id=route_id,
                        success=frontier.success,
                        peak_score=frontier.peak_score,
                        terminal_score=frontier.score,
                        action_count=depth,
                        action_ids=key,
                        route_document=frontier.route_document,
                    )
                )
                if frontier.success and self.budget.stop_on_success:
                    termination = TerminationReason.GOAL_REACHED
                    break
                if (
                    self.budget.target_score is not None
                    and frontier.score >= self.budget.target_score
                ):
                    termination = TerminationReason.GOAL_REACHED
                    break
            if frontier.state_completeness == "exact":
                if frontier.state_id in seen_states:
                    duplicates += 1
                    continue
                seen_states.add(frontier.state_id)
            if self.budget.max_depth is not None and depth >= self.budget.max_depth:
                termination = TerminationReason.MAX_DEPTH
                continue
            node_id = build_search_node_id(
                experiment_id=experiment_id,
                state_id=frontier.state_id,
                depth=depth,
                parent_node_id=(
                    node_ids[key[:-1]]
                    if depth
                    else None
                ),
                action_id=prefix[-1].action_id if depth else None,
            )
            node_ids[key] = node_id
            ordered = self.strategy.order_actions(node_id=node_id, actions=frontier.actions)
            for action in reversed(ordered):
                pending.append((*prefix, action))
        ordered_routes = tuple(sorted(routes, key=lambda route: route.rank_key))
        best = ordered_routes[0] if ordered_routes else None
        elapsed_seconds = max(0.0, self.clock() - started)
        return SearchRunResult(
            experiment_digest=stable_digest(experiment, prefix="experiment_"),
            experiment_id=experiment_id,
            strategy_id=self.strategy.strategy_id,
            termination_reason=termination.value,
            nodes=nodes,
            replays=replays,
            max_depth_reached=max_depth_reached,
            exact_state_duplicates=duplicates,
            prefix_cache_hits=cache_hits,
            prefix_cache_entries=len(cache),
            path_failures=tuple(path_failures),
            routes=ordered_routes,
            best_route=best,
            elapsed_seconds=elapsed_seconds,
        )
