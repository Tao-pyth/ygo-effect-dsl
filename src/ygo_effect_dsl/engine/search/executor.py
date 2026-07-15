from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from ygo_effect_dsl.engine.action import Action
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.failures import FailureRecord
from ygo_effect_dsl.engine.search.parallel import build_search_node_id
from ygo_effect_dsl.engine.search.strategy import (
    RANDOM_SEARCH_STRATEGY_SCHEMA_VERSION,
    SEARCH_STRATEGY_EVIDENCE_SCHEMA_VERSION,
    MctsSearchStrategyV1,
    RandomSearchStrategyV1,
    SearchStrategy,
    UnsupportedSearchStrategyError,
    beam_rank_key,
    build_strategy_evidence,
    mcts_uct_score,
    normalize_mcts_reward,
    strategy_from_experiment,
)
from ygo_effect_dsl.engine.search.termination import SearchBudget, TerminationReason


SEARCH_EXECUTOR_SCHEMA_VERSION = "search-executor-v5"
SEARCH_FRONTIER_SCHEMA_VERSION = "search-frontier-v2"
SEARCH_RUN_RESULT_SCHEMA_VERSION = "search-run-result-v5"
LEGACY_SEARCH_RUN_RESULT_SCHEMA_VERSIONS = ("search-run-result-v4",)
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
    strategy_schema_version: str
    strategy_parameters: Mapping[str, Any]
    strategy_evidence: Mapping[str, Any]
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
        if (
            not isinstance(self.strategy_schema_version, str)
            or not self.strategy_schema_version
        ):
            raise ValueError("strategy_schema_version must be a non-empty string")
        if not isinstance(self.strategy_parameters, Mapping):
            raise ValueError("strategy_parameters must be a mapping")
        if not isinstance(self.strategy_evidence, Mapping):
            raise ValueError("strategy_evidence must be a mapping")
        expected_evidence_fields = {
            "evidence_id",
            "execution_mode",
            "logical_updates",
            "parameters",
            "schema_version",
            "strategy_id",
            "strategy_schema_version",
        }
        if set(self.strategy_evidence) != expected_evidence_fields:
            raise ValueError("strategy_evidence fields do not match v1")
        if (
            self.strategy_evidence.get("schema_version")
            != SEARCH_STRATEGY_EVIDENCE_SCHEMA_VERSION
        ):
            raise ValueError("unsupported strategy_evidence schema")
        evidence_identity = {
            key: value
            for key, value in self.strategy_evidence.items()
            if key != "evidence_id"
        }
        if self.strategy_evidence.get("evidence_id") != stable_digest(
            evidence_identity, prefix="strategyevidence_"
        ):
            raise ValueError("strategy_evidence content ID does not match its payload")
        if (
            self.strategy_evidence.get("strategy_id") != self.strategy_id
            or self.strategy_evidence.get("strategy_schema_version")
            != self.strategy_schema_version
            or self.strategy_evidence.get("parameters")
            != to_canonical_data(self.strategy_parameters)
        ):
            raise ValueError("strategy_evidence provenance does not match the result")

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
            "strategy_evidence": to_canonical_data(self.strategy_evidence),
            "strategy_id": self.strategy_id,
            "strategy_parameters": to_canonical_data(self.strategy_parameters),
            "strategy_schema_version": self.strategy_schema_version,
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


@dataclass
class _SearchRuntime:
    experiment: Mapping[str, Any]
    experiment_id: str
    started: float
    cache: dict[tuple[str, ...], SearchFrontier] = field(default_factory=dict)
    node_ids: dict[tuple[str, ...], str] = field(default_factory=dict)
    seen_states: set[str] = field(default_factory=set)
    routes: list[SearchRouteSummary] = field(default_factory=list)
    route_prefixes: set[tuple[str, ...]] = field(default_factory=set)
    path_failures: list[Mapping[str, Any]] = field(default_factory=list)
    logical_updates: list[Mapping[str, Any]] = field(default_factory=list)
    nodes: int = 0
    replays: int = 0
    cache_hits: int = 0
    duplicates: int = 0
    max_depth_reached: int = 0
    termination: TerminationReason = TerminationReason.EXHAUSTED


@dataclass(frozen=True)
class _ObservedNode:
    prefix: tuple[Action, ...]
    prefix_id: str
    node_id: str
    frontier: SearchFrontier
    duplicate: bool


@dataclass
class _MctsTreeNode:
    observed: _ObservedNode
    incoming_action_id: str | None
    untried_actions: list[Action]
    children: dict[str, _MctsTreeNode] = field(default_factory=dict)
    visits: int = 0
    value_sum: float = 0.0


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

    @staticmethod
    def _key(prefix: Sequence[Action]) -> tuple[str, ...]:
        return tuple(action.action_id for action in prefix)

    @staticmethod
    def _prefix_id(experiment_id: str, key: Sequence[str]) -> str:
        return stable_digest(
            {"action_ids": list(key), "experiment_id": experiment_id},
            prefix="searchprefix_",
        )

    def _hard_budget_reason(
        self, runtime: _SearchRuntime
    ) -> TerminationReason | None:
        elapsed = self.clock() - runtime.started
        if self.budget.max_seconds is not None and elapsed >= self.budget.max_seconds:
            return TerminationReason.MAX_SECONDS
        if self.budget.max_nodes is not None and runtime.nodes >= self.budget.max_nodes:
            return TerminationReason.MAX_NODES
        if (
            self.budget.max_replays is not None
            and runtime.replays >= self.budget.max_replays
        ):
            return TerminationReason.MAX_REPLAYS
        return None

    def _record_route(
        self,
        runtime: _SearchRuntime,
        prefix: tuple[Action, ...],
        frontier: SearchFrontier,
    ) -> None:
        if not frontier.legal_stop or not prefix:
            return
        assert frontier.route_document is not None
        key = self._key(prefix)
        route_id = str(frontier.route_document.get("route_id", ""))
        if not route_id:
            route_id = stable_digest(
                {
                    "experiment_id": runtime.experiment_id,
                    "prefix": list(key),
                    "state_id": frontier.state_id,
                },
                prefix="route_",
            )
        if key not in runtime.route_prefixes:
            runtime.route_prefixes.add(key)
            runtime.routes.append(
                SearchRouteSummary(
                    route_id=route_id,
                    success=frontier.success,
                    peak_score=frontier.peak_score,
                    terminal_score=frontier.score,
                    action_count=len(prefix),
                    action_ids=key,
                    route_document=frontier.route_document,
                )
            )
        if frontier.success and self.budget.stop_on_success:
            runtime.termination = TerminationReason.GOAL_REACHED
        if (
            self.budget.target_score is not None
            and frontier.score >= self.budget.target_score
        ):
            runtime.termination = TerminationReason.GOAL_REACHED

    def _replay_prefix(
        self,
        runtime: _SearchRuntime,
        prefix: tuple[Action, ...],
    ) -> _ObservedNode | None:
        depth = len(prefix)
        runtime.max_depth_reached = max(runtime.max_depth_reached, depth)
        key = self._key(prefix)
        frontier = runtime.cache.get(key)
        if frontier is None:
            try:
                frontier = self.adapter.replay(runtime.experiment, prefix)
            except Exception as exc:
                if not prefix:
                    raise
                runtime.nodes += 1
                runtime.replays += 1
                path_failure: dict[str, Any] = {
                    "action_ids": list(key),
                    "depth": depth,
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "status": "path_failure",
                }
                failure = getattr(exc, "failure", None)
                if isinstance(failure, FailureRecord):
                    path_failure["failure"] = failure.to_dict()
                runtime.path_failures.append(path_failure)
                return None
            runtime.cache[key] = frontier
            runtime.replays += frontier.replay_count
        else:
            runtime.cache_hits += 1
        runtime.nodes += 1
        self._record_route(runtime, prefix, frontier)
        duplicate = False
        if frontier.state_completeness == "exact":
            if frontier.state_id in runtime.seen_states:
                runtime.duplicates += 1
                duplicate = True
            else:
                runtime.seen_states.add(frontier.state_id)
        node_id = build_search_node_id(
            experiment_id=runtime.experiment_id,
            state_id=frontier.state_id,
            depth=depth,
            parent_node_id=runtime.node_ids.get(key[:-1]) if depth else None,
            action_id=prefix[-1].action_id if depth else None,
        )
        runtime.node_ids[key] = node_id
        return _ObservedNode(
            prefix=prefix,
            prefix_id=self._prefix_id(runtime.experiment_id, key),
            node_id=node_id,
            frontier=frontier,
            duplicate=duplicate,
        )

    def _run_depth_first(self, runtime: _SearchRuntime) -> None:
        pending: list[tuple[Action, ...]] = [()]
        while pending:
            reason = self._hard_budget_reason(runtime)
            if reason is not None:
                runtime.termination = reason
                break
            prefix = pending.pop()
            observed = self._replay_prefix(runtime, prefix)
            if observed is None:
                continue
            if runtime.termination == TerminationReason.GOAL_REACHED:
                break
            if observed.duplicate:
                continue
            depth = len(prefix)
            if self.budget.max_depth is not None and depth >= self.budget.max_depth:
                runtime.termination = TerminationReason.MAX_DEPTH
                continue
            ordered = self.strategy.order_actions(
                node_id=observed.node_id,
                actions=observed.frontier.actions,
            )
            runtime.logical_updates.append(
                {
                    "action_ids": list(self._key(prefix)),
                    "node_id": observed.node_id,
                    "ordered_action_ids": [action.action_id for action in ordered],
                    "prefix_id": observed.prefix_id,
                    "update_type": "depth_first_expansion",
                }
            )
            for action in reversed(ordered):
                pending.append((*prefix, action))

    @staticmethod
    def _beam_sort_key(observed: _ObservedNode) -> tuple[Any, ...]:
        return beam_rank_key(
            success=observed.frontier.success,
            peak_score=observed.frontier.peak_score,
            terminal_score=observed.frontier.score,
            action_count=len(observed.prefix),
            semantic_prefix_id=observed.prefix_id,
        )

    def _run_beam(self, runtime: _SearchRuntime) -> None:
        beam_width = self.strategy.parameters.get("beam_width")
        if (
            not isinstance(beam_width, int)
            or isinstance(beam_width, bool)
            or beam_width < 1
        ):
            raise ValueError("beam strategy requires an integer beam_width >= 1")
        reason = self._hard_budget_reason(runtime)
        if reason is not None:
            runtime.termination = reason
            return
        root = self._replay_prefix(runtime, ())
        if root is None:
            return
        current = [] if root.duplicate else [root]
        while current and runtime.termination != TerminationReason.GOAL_REACHED:
            child_nodes: list[_ObservedNode] = []
            child_records: list[dict[str, Any]] = []
            layer_complete = True
            depth_limited = False
            layer_depth = len(current[0].prefix) + 1
            for parent in current:
                parent_depth = len(parent.prefix)
                if (
                    self.budget.max_depth is not None
                    and parent_depth >= self.budget.max_depth
                ):
                    depth_limited = True
                    continue
                ordered = self.strategy.order_actions(
                    node_id=parent.node_id,
                    actions=parent.frontier.actions,
                )
                for action in ordered:
                    reason = self._hard_budget_reason(runtime)
                    if reason is not None:
                        runtime.termination = reason
                        layer_complete = False
                        break
                    prefix = (*parent.prefix, action)
                    child = self._replay_prefix(runtime, prefix)
                    if child is None:
                        key = self._key(prefix)
                        child_records.append(
                            {
                                "action_ids": list(key),
                                "prefix_id": self._prefix_id(
                                    runtime.experiment_id, key
                                ),
                                "selected": False,
                                "status": "path_failure",
                            }
                        )
                        continue
                    child_at_depth_limit = (
                        self.budget.max_depth is not None
                        and len(prefix) >= self.budget.max_depth
                    )
                    if child_at_depth_limit:
                        depth_limited = True
                    expandable = bool(child.frontier.actions) and not (
                        child.duplicate or child_at_depth_limit
                    )
                    child_records.append(
                        {
                            "action_ids": list(self._key(prefix)),
                            "duplicate": child.duplicate,
                            "expandable": expandable,
                            "peak_score": child.frontier.peak_score,
                            "prefix_id": child.prefix_id,
                            "score": child.frontier.score,
                            "selected": False,
                            "state_completeness": child.frontier.state_completeness,
                            "state_id": child.frontier.state_id,
                            "status": "observed",
                            "success": child.frontier.success,
                        }
                    )
                    if expandable:
                        child_nodes.append(child)
                    if runtime.termination == TerminationReason.GOAL_REACHED:
                        layer_complete = False
                        break
                if not layer_complete:
                    break
            selected: list[_ObservedNode] = []
            if layer_complete:
                selected = sorted(child_nodes, key=self._beam_sort_key)[:beam_width]
            selected_ids = {node.prefix_id for node in selected}
            child_records = [
                {
                    **record,
                    "selected": record["prefix_id"] in selected_ids,
                }
                for record in child_records
            ]
            runtime.logical_updates.append(
                {
                    "complete": layer_complete,
                    "depth": layer_depth,
                    "observed_children": child_records,
                    "parent_prefix_ids": [parent.prefix_id for parent in current],
                    "selected_prefix_ids": [node.prefix_id for node in selected],
                    "termination_reason": (
                        runtime.termination.value if not layer_complete else None
                    ),
                    "update_type": "beam_layer",
                }
            )
            if not layer_complete:
                break
            current = selected
            if not current:
                if depth_limited:
                    runtime.termination = TerminationReason.MAX_DEPTH
                break

    def _mcts_strategy(self) -> MctsSearchStrategyV1:
        if not isinstance(self.strategy, MctsSearchStrategyV1):
            raise ValueError("mcts execution requires MctsSearchStrategyV1")
        return self.strategy

    def _mcts_tree_node(
        self,
        observed: _ObservedNode,
        *,
        incoming_action_id: str | None,
    ) -> _MctsTreeNode:
        strategy = self._mcts_strategy()
        ordered = strategy.order_actions_for_purpose(
            node_id=observed.node_id,
            actions=observed.frontier.actions,
            purpose="mcts_expansion",
        )
        return _MctsTreeNode(
            observed=observed,
            incoming_action_id=incoming_action_id,
            untried_actions=list(ordered),
        )

    def _mcts_boundary(self, observed: _ObservedNode) -> str | None:
        if observed.frontier.legal_stop:
            return "legal_stop"
        if observed.duplicate:
            return "exact_state_duplicate"
        if (
            self.budget.max_depth is not None
            and len(observed.prefix) >= self.budget.max_depth
        ):
            return "max_depth"
        if not observed.frontier.actions:
            return "frontier_exhausted"
        return None

    def _select_mcts_child(
        self, node: _MctsTreeNode
    ) -> tuple[_MctsTreeNode, float]:
        strategy = self._mcts_strategy()
        ranked: list[tuple[tuple[Any, ...], _MctsTreeNode, float]] = []
        for child in node.children.values():
            assert child.incoming_action_id is not None
            score = mcts_uct_score(
                parent_visits=max(1, node.visits),
                child_visits=child.visits,
                child_value_sum=child.value_sum,
                exploration_constant=strategy.exploration_constant,
            )
            ranked.append(
                (
                    (
                        -score,
                        strategy.decision_key(
                            node_id=node.observed.node_id,
                            purpose="mcts_selection",
                            candidate_id=child.incoming_action_id,
                        ),
                        child.incoming_action_id,
                    ),
                    child,
                    score,
                )
            )
        if not ranked:
            raise ValueError("MCTS selection requires at least one child")
        _, selected, score = min(ranked, key=lambda item: item[0])
        return selected, score

    @staticmethod
    def _mcts_incomplete_update(
        *,
        ordinal: int,
        status: str,
        selections: Sequence[Mapping[str, Any]],
        expansion: Mapping[str, Any] | None,
        rollout: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return {
            "backpropagation": [],
            "completed": False,
            "discarded_from_statistics": True,
            "expansion": expansion,
            "ordinal": ordinal,
            "reward": None,
            "rollout": list(rollout),
            "selection": list(selections),
            "status": status,
            "update_type": "mcts_simulation",
        }

    def _run_mcts(self, runtime: _SearchRuntime) -> None:
        strategy = self._mcts_strategy()
        reason = self._hard_budget_reason(runtime)
        if reason is not None:
            runtime.termination = reason
            return
        root_observed = self._replay_prefix(runtime, ())
        if root_observed is None:
            return
        root = self._mcts_tree_node(root_observed, incoming_action_id=None)
        completed_simulations = 0
        for ordinal in range(1, strategy.simulations + 1):
            reason = self._hard_budget_reason(runtime)
            if reason is not None:
                runtime.termination = reason
                runtime.logical_updates.append(
                    self._mcts_incomplete_update(
                        ordinal=ordinal,
                        status=f"hard_budget:{reason.value}",
                        selections=(),
                        expansion=None,
                        rollout=(),
                    )
                )
                break
            node = root
            tree_path = [root]
            selections: list[Mapping[str, Any]] = []
            expansion: Mapping[str, Any] | None = None
            rollout: list[Mapping[str, Any]] = []
            boundary = self._mcts_boundary(node.observed)
            while boundary is None and not node.untried_actions and node.children:
                child, uct_score = self._select_mcts_child(node)
                selections.append(
                    {
                        "action_id": child.incoming_action_id,
                        "child_prefix_id": child.observed.prefix_id,
                        "child_value_sum": child.value_sum,
                        "child_visits": child.visits,
                        "parent_prefix_id": node.observed.prefix_id,
                        "parent_visits": node.visits,
                        "uct_score": None if uct_score == float("inf") else uct_score,
                        "unvisited": uct_score == float("inf"),
                    }
                )
                node = child
                tree_path.append(node)
                boundary = self._mcts_boundary(node.observed)

            hard_stop = False
            path_failure = False
            if boundary is None and node.untried_actions:
                reason = self._hard_budget_reason(runtime)
                if reason is not None:
                    runtime.termination = reason
                    hard_stop = True
                else:
                    action = node.untried_actions.pop(0)
                    prefix = (*node.observed.prefix, action)
                    child_observed = self._replay_prefix(runtime, prefix)
                    expansion = {
                        "action_id": action.action_id,
                        "parent_prefix_id": node.observed.prefix_id,
                        "prefix_id": self._prefix_id(
                            runtime.experiment_id, self._key(prefix)
                        ),
                        "status": (
                            "observed" if child_observed is not None else "path_failure"
                        ),
                    }
                    if child_observed is None:
                        path_failure = True
                    else:
                        child_node = self._mcts_tree_node(
                            child_observed,
                            incoming_action_id=action.action_id,
                        )
                        node.children[action.action_id] = child_node
                        node = child_node
                        tree_path.append(node)
                        boundary = self._mcts_boundary(node.observed)

            terminal = node.observed
            while not hard_stop and not path_failure and boundary is None:
                ordered = strategy.order_actions_for_purpose(
                    node_id=terminal.node_id,
                    actions=terminal.frontier.actions,
                    purpose="mcts_rollout",
                )
                if not ordered:
                    boundary = "frontier_exhausted"
                    break
                reason = self._hard_budget_reason(runtime)
                if reason is not None:
                    runtime.termination = reason
                    hard_stop = True
                    break
                action = ordered[0]
                prefix = (*terminal.prefix, action)
                next_observed = self._replay_prefix(runtime, prefix)
                rollout.append(
                    {
                        "action_id": action.action_id,
                        "parent_prefix_id": terminal.prefix_id,
                        "prefix_id": self._prefix_id(
                            runtime.experiment_id, self._key(prefix)
                        ),
                        "status": (
                            "observed" if next_observed is not None else "path_failure"
                        ),
                    }
                )
                if next_observed is None:
                    path_failure = True
                    break
                terminal = next_observed
                boundary = self._mcts_boundary(terminal)

            if hard_stop:
                assert runtime.termination in {
                    TerminationReason.MAX_NODES,
                    TerminationReason.MAX_REPLAYS,
                    TerminationReason.MAX_SECONDS,
                }
                runtime.logical_updates.append(
                    self._mcts_incomplete_update(
                        ordinal=ordinal,
                        status=f"hard_budget:{runtime.termination.value}",
                        selections=selections,
                        expansion=expansion,
                        rollout=rollout,
                    )
                )
                break
            if path_failure:
                runtime.logical_updates.append(
                    self._mcts_incomplete_update(
                        ordinal=ordinal,
                        status="path_failure",
                        selections=selections,
                        expansion=expansion,
                        rollout=rollout,
                    )
                )
                continue

            reward = normalize_mcts_reward(
                success=terminal.frontier.success,
                terminal_score=terminal.frontier.score,
                reward_floor=strategy.reward_floor,
                reward_ceiling=strategy.reward_ceiling,
            )
            backpropagation = []
            for visited_node in reversed(tree_path):
                visited_node.visits += 1
                visited_node.value_sum += reward
                backpropagation.append(
                    {
                        "prefix_id": visited_node.observed.prefix_id,
                        "value_sum": visited_node.value_sum,
                        "visits": visited_node.visits,
                    }
                )
            completed_simulations += 1
            runtime.logical_updates.append(
                {
                    "backpropagation": backpropagation,
                    "boundary": boundary,
                    "completed": True,
                    "discarded_from_statistics": False,
                    "expansion": expansion,
                    "ordinal": ordinal,
                    "reward": reward,
                    "rollout": rollout,
                    "selection": selections,
                    "status": "complete",
                    "terminal": {
                        "peak_score": terminal.frontier.peak_score,
                        "prefix_id": terminal.prefix_id,
                        "score": terminal.frontier.score,
                        "success": terminal.frontier.success,
                    },
                    "update_type": "mcts_simulation",
                }
            )
            if runtime.termination == TerminationReason.GOAL_REACHED:
                break
        runtime.logical_updates.append(
            {
                "completed_simulations": completed_simulations,
                "requested_simulations": strategy.simulations,
                "root_value_sum": root.value_sum,
                "root_visits": root.visits,
                "update_type": "mcts_summary",
            }
        )

    def _result(self, runtime: _SearchRuntime) -> SearchRunResult:
        ordered_routes = tuple(
            sorted(runtime.routes, key=lambda route: route.rank_key)
        )
        evidence = build_strategy_evidence(
            self.strategy,
            logical_updates=runtime.logical_updates,
        )
        return SearchRunResult(
            experiment_digest=stable_digest(
                runtime.experiment, prefix="experiment_"
            ),
            experiment_id=runtime.experiment_id,
            strategy_id=self.strategy.strategy_id,
            strategy_schema_version=self.strategy.schema_version,
            strategy_parameters=dict(self.strategy.parameters),
            strategy_evidence=evidence,
            termination_reason=runtime.termination.value,
            nodes=runtime.nodes,
            replays=runtime.replays,
            max_depth_reached=runtime.max_depth_reached,
            exact_state_duplicates=runtime.duplicates,
            prefix_cache_hits=runtime.cache_hits,
            prefix_cache_entries=len(runtime.cache),
            path_failures=tuple(runtime.path_failures),
            routes=ordered_routes,
            best_route=ordered_routes[0] if ordered_routes else None,
            elapsed_seconds=max(0.0, self.clock() - runtime.started),
        )

    def run(self, experiment: Mapping[str, Any]) -> SearchRunResult:
        experiment_id = str(experiment.get("experiment_id", ""))
        if not experiment_id:
            raise ValueError("experiment_id must be a non-empty string")
        runtime = _SearchRuntime(
            experiment=experiment,
            experiment_id=experiment_id,
            started=self.clock(),
        )
        if self.strategy.execution_mode == "depth_first":
            self._run_depth_first(runtime)
        elif self.strategy.execution_mode == "beam":
            self._run_beam(runtime)
        elif self.strategy.execution_mode == "mcts":
            self._run_mcts(runtime)
        else:
            raise UnsupportedSearchStrategyError(
                f"unsupported search execution mode {self.strategy.execution_mode!r}"
            )
        return self._result(runtime)
