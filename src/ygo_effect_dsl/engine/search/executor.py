from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

from ygo_effect_dsl.engine.action import Action
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.failures import FailureRecord
from ygo_effect_dsl.engine.evaluation import (
    RouteRankingPolicy,
    TerminalPreferenceProfile,
    build_terminal_board_projection,
    build_route_randomness_summary,
    evaluate_terminal_preferences,
    rank_route_candidates,
)
from ygo_effect_dsl.engine.search.lifecycle import MultiTurnLifecycleDecision
from ygo_effect_dsl.engine.search.parallel import (
    ParallelSearchPolicy,
    build_search_node_id,
)
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
SEARCH_CANDIDATE_EVIDENCE_SCHEMA_VERSION = "search-candidate-evidence-v1"
SEARCH_COVERAGE_SCHEMA_VERSION = "search-coverage-v1"

_COVERAGE_CAPABLE_MODES = frozenset({"depth_first", "beam"})
_CENSORING_TERMINATIONS = frozenset(
    {
        TerminationReason.GOAL_REACHED,
        TerminationReason.MAX_DEPTH,
        TerminationReason.MAX_NODES,
        TerminationReason.MAX_REPLAYS,
        TerminationReason.MAX_SECONDS,
        TerminationReason.REPEATED_TRANSITION,
        TerminationReason.STAGNATION,
    }
)


@dataclass(frozen=True)
class SearchFrontier:
    state_id: str
    state_completeness: str
    request: Mapping[str, Any] | None
    actions: tuple[Action, ...]
    score: int | float
    peak_score: int | float
    success: bool
    legal_stop: bool
    legal_stop_reason: str
    route_document: Mapping[str, Any] | None = None
    replay_count: int = 1
    terminal_observation: Mapping[str, Any] | None = None
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
        if self.request is None and self.terminal_observation is None:
            raise ValueError(
                "SearchFrontier requires a request or terminal_observation"
            )
        if self.request is not None and self.terminal_observation is not None:
            raise ValueError(
                "SearchFrontier request and terminal_observation are mutually exclusive"
            )
        if self.terminal_observation is not None:
            if not isinstance(self.terminal_observation, Mapping):
                raise ValueError("terminal_observation must be a mapping or None")
            if self.actions:
                raise ValueError("a terminal SearchFrontier cannot expose Actions")
            if not self.legal_stop:
                raise ValueError("a terminal SearchFrontier must be a legal stop")
        if self.route_document is not None and not self.legal_stop:
            raise ValueError("route_document requires a legal stop")
        if self.legal_stop and self.route_document is None:
            raise ValueError("a legal stop requires a replayable route_document")
        if not isinstance(self.replay_count, int) or self.replay_count < 1:
            raise ValueError("replay_count must be an integer >= 1")
        if self.request is not None and "turn_lifecycle" in self.request:
            lifecycle = MultiTurnLifecycleDecision.from_dict(
                self.request["turn_lifecycle"]
            )
            object.__setattr__(
                self,
                "request",
                {**self.request, "turn_lifecycle": lifecycle.to_dict()},
            )
        if self.terminal_observation is not None:
            lifecycle = MultiTurnLifecycleDecision.from_dict(
                self.terminal_observation.get("turn_lifecycle")
            )
            if not lifecycle.duel_ended:
                raise ValueError(
                    "terminal_observation requires a duel-ended lifecycle"
                )
            object.__setattr__(
                self,
                "terminal_observation",
                {
                    **self.terminal_observation,
                    "turn_lifecycle": lifecycle.to_dict(),
                },
            )


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
    lifecycle_boundary: Mapping[str, Any] | None = None
    randomness_summary: Mapping[str, Any] | None = None
    terminal_preference_evaluation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.randomness_summary is None:
            object.__setattr__(
                self,
                "randomness_summary",
                build_route_randomness_summary(self.route_document),
            )
        elif not isinstance(self.randomness_summary, Mapping):
            raise ValueError("randomness_summary must be a mapping")
        if (
            self.terminal_preference_evaluation is not None
            and not isinstance(self.terminal_preference_evaluation, Mapping)
        ):
            raise ValueError("terminal_preference_evaluation must be a mapping")
        if self.lifecycle_boundary is not None:
            decision = MultiTurnLifecycleDecision.from_dict(
                self.lifecycle_boundary
            )
            if not decision.legal_stop:
                raise ValueError("route lifecycle_boundary must be a legal stop")
            object.__setattr__(self, "lifecycle_boundary", decision.to_dict())

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
            "randomness_summary": to_canonical_data(self.randomness_summary),
            "route_id": self.route_id,
            "success": self.success,
            "terminal_score": self.terminal_score,
        }
        if self.terminal_preference_evaluation is not None:
            payload["terminal_preference_evaluation"] = to_canonical_data(
                self.terminal_preference_evaluation
            )
        if self.lifecycle_boundary is not None:
            payload["lifecycle_boundary"] = to_canonical_data(
                self.lifecycle_boundary
            )
        if include_document:
            payload["route_document"] = to_canonical_data(self.route_document)
        return payload


def _build_research_route_ranking(
    routes: Sequence[SearchRouteSummary],
) -> dict[str, Any]:
    policy = RouteRankingPolicy()
    unique_routes: list[SearchRouteSummary] = []
    seen_route_ids: set[str] = set()
    for route in routes:
        if route.route_id in seen_route_ids:
            continue
        seen_route_ids.add(route.route_id)
        unique_routes.append(route)
    if not unique_routes:
        identity = to_canonical_data(
            {
                "best_route_id": None,
                "excluded_routes": [],
                "policy": policy.to_dict(),
                "ranked_routes": [],
                "schema_version": "route-ranking-v1",
            }
        )
        return {**identity, "ranking_id": stable_digest(identity, prefix="routerank_")}
    return rank_route_candidates(
        [
            {
                "action_count": route.action_count,
                "peak_score": route.peak_score,
                "randomness_summary": route.randomness_summary,
                "route_id": route.route_id,
                "success": route.success,
                "terminal_composite_score": route.terminal_score,
            }
            for route in unique_routes
        ],
        policy=policy,
    )


def _candidate_counts(candidates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {
        "censored": 0,
        "explored": 0,
        "failed": 0,
        "pruned": 0,
        "total": len(candidates),
        "unexplored": 0,
    }
    for candidate in candidates:
        status = candidate.get("status")
        if status in counts and status != "total":
            counts[status] += 1
    return counts


def _build_search_evidence(
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    canonical_candidates = sorted(
        (to_canonical_data(candidate) for candidate in candidates),
        key=lambda candidate: (
            candidate.get("depth"),
            candidate.get("parent_prefix_id"),
            candidate.get("action_id"),
            candidate.get("prefix_id"),
        ),
    )
    identity = to_canonical_data(
        {
            "candidate_counts": _candidate_counts(canonical_candidates),
            "candidates": canonical_candidates,
            "schema_version": SEARCH_CANDIDATE_EVIDENCE_SCHEMA_VERSION,
        }
    )
    return {**identity, "evidence_id": stable_digest(identity, prefix="searchev_")}


def _build_empty_search_evidence() -> dict[str, Any]:
    return _build_search_evidence(())


def _build_coverage_certificate(
    *,
    termination: TerminationReason,
    execution_mode: str,
    search_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = search_evidence.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(
        candidates, (str, bytes, bytearray)
    ):
        candidates = ()
    counts = _candidate_counts(
        [candidate for candidate in candidates if isinstance(candidate, Mapping)]
    )
    frontier_exhausted = (
        termination == TerminationReason.EXHAUSTED
        and execution_mode in _COVERAGE_CAPABLE_MODES
        and counts["unexplored"] == 0
        and counts["censored"] == 0
        and counts["pruned"] == 0
    )
    identity = to_canonical_data(
        {
            "candidate_accounting_complete": True,
            "candidate_counts": counts,
            "coverage_status": (
                "frontier_exhausted" if frontier_exhausted else "best_observed"
            ),
            "frontier_exhausted": frontier_exhausted,
            "pending_frontier_count": counts["unexplored"],
            "schema_version": SEARCH_COVERAGE_SCHEMA_VERSION,
            "termination_reason": termination.value,
            "unknown_candidate_count": 0,
        }
    )
    return {
        **identity,
        "coverage_id": stable_digest(identity, prefix="searchcoverage_"),
    }


def _terminal_board_projection_source(
    route_document: Mapping[str, Any],
    terminal_board: Mapping[str, Any],
) -> Mapping[str, Any]:
    embedded_summary = terminal_board.get("board_summary")
    if isinstance(embedded_summary, Mapping):
        return embedded_summary
    if "public_cards" in terminal_board:
        return terminal_board
    checkpoint_step = terminal_board.get("checkpoint_step")
    checkpoints = route_document.get("checkpoints")
    if isinstance(checkpoint_step, int) and isinstance(checkpoints, Sequence):
        for checkpoint in checkpoints:
            if not isinstance(checkpoint, Mapping):
                continue
            if checkpoint.get("step") != checkpoint_step:
                continue
            board_summary = checkpoint.get("board_summary")
            if isinstance(board_summary, Mapping):
                return board_summary
    raise ValueError(
        "terminal preference evaluation requires terminal board public_cards"
    )


def _terminal_preference_evaluation(
    experiment: Mapping[str, Any],
    route_document: Mapping[str, Any],
    *,
    base_score: int | float,
) -> dict[str, Any] | None:
    raw_profile = experiment.get("terminal_preference_profile")
    if not isinstance(raw_profile, Mapping):
        return None
    profile = TerminalPreferenceProfile.from_mapping(
        {
            "name": raw_profile.get("name"),
            "rules": raw_profile.get("rules"),
            "schema_version": raw_profile.get("schema_version"),
        }
    )
    if not profile.rules:
        return None
    result = route_document.get("result")
    terminal_board = (
        result.get("terminal_board")
        if isinstance(result, Mapping) and isinstance(result.get("terminal_board"), Mapping)
        else None
    )
    if terminal_board is None:
        raise ValueError("terminal preference evaluation requires result.terminal_board")
    projection_source = _terminal_board_projection_source(
        route_document,
        terminal_board,
    )
    projection = build_terminal_board_projection(projection_source)
    return evaluate_terminal_preferences(
        projection,
        profile,
        base_score=base_score,
        randomness_penalty=0,
    )


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
    route_ranking: Mapping[str, Any] | None = None
    search_evidence: Mapping[str, Any] | None = None
    coverage: Mapping[str, Any] | None = None
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
        if self.route_ranking is None:
            object.__setattr__(
                self,
                "route_ranking",
                _build_research_route_ranking(self.routes),
            )
        elif not isinstance(self.route_ranking, Mapping):
            raise ValueError("route_ranking must be a mapping")
        expected_ranking = _build_research_route_ranking(self.routes)
        if to_canonical_data(self.route_ranking) != expected_ranking:
            raise ValueError("route_ranking does not match routes and policy")
        if self.search_evidence is None:
            object.__setattr__(
                self,
                "search_evidence",
                _build_empty_search_evidence(),
            )
        elif not isinstance(self.search_evidence, Mapping):
            raise ValueError("search_evidence must be a mapping")
        if self.coverage is None:
            object.__setattr__(
                self,
                "coverage",
                _build_coverage_certificate(
                    termination=TerminationReason(self.termination_reason),
                    execution_mode=str(self.strategy_evidence.get("execution_mode")),
                    search_evidence=self.search_evidence,
                ),
            )
        elif not isinstance(self.coverage, Mapping):
            raise ValueError("coverage must be a mapping")

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "best_route": self.best_route.to_dict() if self.best_route else None,
            "coverage": to_canonical_data(self.coverage),
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
            "route_ranking": to_canonical_data(self.route_ranking),
            "routes": [route.to_dict() for route in self.routes],
            "schema_version": self.schema_version,
            "search_evidence": to_canonical_data(self.search_evidence),
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
    parallel_policy: ParallelSearchPolicy | None = None
    cache: dict[tuple[str, ...], SearchFrontier] = field(default_factory=dict)
    prefetched: dict[tuple[str, ...], SearchFrontier | Exception] = field(
        default_factory=dict
    )
    node_ids: dict[tuple[str, ...], str] = field(default_factory=dict)
    seen_states: set[str] = field(default_factory=set)
    candidate_evidence: dict[tuple[str, ...], dict[str, Any]] = field(
        default_factory=dict
    )
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

    def _ensure_candidate(
        self,
        runtime: _SearchRuntime,
        prefix: tuple[Action, ...],
    ) -> dict[str, Any] | None:
        if not prefix:
            return None
        key = self._key(prefix)
        candidate = runtime.candidate_evidence.get(key)
        if candidate is None:
            candidate = {
                "action_id": prefix[-1].action_id,
                "action_ids": list(key),
                "depth": len(prefix),
                "parent_prefix_id": self._prefix_id(
                    runtime.experiment_id,
                    key[:-1],
                ),
                "prefix_id": self._prefix_id(runtime.experiment_id, key),
                "status": "unexplored",
            }
            runtime.candidate_evidence[key] = candidate
        return candidate

    def _mark_candidate(
        self,
        runtime: _SearchRuntime,
        prefix: tuple[Action, ...],
        *,
        status: str,
        **details: Any,
    ) -> None:
        candidate = self._ensure_candidate(runtime, prefix)
        if candidate is None:
            return
        candidate.update(
            {
                key: to_canonical_data(value)
                for key, value in details.items()
                if value is not None
            }
        )
        candidate["status"] = status

    @staticmethod
    def _mark_candidate_key(
        runtime: _SearchRuntime,
        key: Sequence[str],
        *,
        status: str,
        **details: Any,
    ) -> None:
        candidate = runtime.candidate_evidence.get(tuple(key))
        if candidate is None:
            return
        candidate.update(
            {
                detail_key: to_canonical_data(value)
                for detail_key, value in details.items()
                if value is not None
            }
        )
        candidate["status"] = status

    def _search_evidence(self, runtime: _SearchRuntime) -> dict[str, Any]:
        candidates: list[Mapping[str, Any]] = []
        for candidate in runtime.candidate_evidence.values():
            candidate_record = dict(candidate)
            if (
                runtime.termination in _CENSORING_TERMINATIONS
                and candidate_record.get("status") == "unexplored"
            ):
                candidate_record["status"] = "censored"
                candidate_record["censor_reason"] = runtime.termination.value
            candidates.append(candidate_record)
        return _build_search_evidence(candidates)

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
            boundary_source = (
                frontier.terminal_observation
                if frontier.terminal_observation is not None
                else frontier.request
            )
            lifecycle_boundary = (
                boundary_source.get("turn_lifecycle")
                if isinstance(boundary_source, Mapping)
                else None
            )
            terminal_preference = _terminal_preference_evaluation(
                runtime.experiment,
                frontier.route_document,
                base_score=frontier.score,
            )
            terminal_score = (
                terminal_preference["terminal_composite_score"]
                if terminal_preference is not None
                else frontier.score
            )
            runtime.route_prefixes.add(key)
            runtime.routes.append(
                SearchRouteSummary(
                    route_id=route_id,
                    success=frontier.success,
                    peak_score=frontier.peak_score,
                    terminal_score=terminal_score,
                    action_count=len(prefix),
                    action_ids=key,
                    route_document=frontier.route_document,
                    terminal_preference_evaluation=terminal_preference,
                    lifecycle_boundary=(
                        lifecycle_boundary
                        if isinstance(lifecycle_boundary, Mapping)
                        else None
                    ),
                )
            )
        if frontier.success and self.budget.stop_on_success:
            runtime.termination = TerminationReason.GOAL_REACHED
        if (
            self.budget.target_score is not None
            and frontier.score >= self.budget.target_score
        ):
            runtime.termination = TerminationReason.GOAL_REACHED

    def _record_path_failure(
        self,
        runtime: _SearchRuntime,
        prefix: tuple[Action, ...],
        exc: Exception,
    ) -> None:
        key = self._key(prefix)
        path_failure: dict[str, Any] = {
            "action_ids": list(key),
            "depth": len(prefix),
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "status": "path_failure",
        }
        failure = getattr(exc, "failure", None)
        if isinstance(failure, FailureRecord):
            path_failure["failure"] = failure.to_dict()
        runtime.path_failures.append(path_failure)
        self._mark_candidate(
            runtime,
            prefix,
            exception_type=type(exc).__name__,
            failure_category=(
                failure.category if isinstance(failure, FailureRecord) else None
            ),
            status="failed",
        )

    def _commit_frontier(
        self,
        runtime: _SearchRuntime,
        prefix: tuple[Action, ...],
        frontier: SearchFrontier,
        *,
        cache_hit: bool,
    ) -> _ObservedNode:
        depth = len(prefix)
        key = self._key(prefix)
        if cache_hit:
            runtime.cache_hits += 1
        else:
            runtime.cache[key] = frontier
            runtime.replays += frontier.replay_count
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
        self._mark_candidate(
            runtime,
            prefix,
            duplicate=duplicate,
            legal_stop=frontier.legal_stop,
            node_id=node_id,
            route_id=(
                frontier.route_document.get("route_id")
                if frontier.legal_stop
                and isinstance(frontier.route_document, Mapping)
                else None
            ),
            state_completeness=frontier.state_completeness,
            state_id=frontier.state_id,
            status="explored",
            success=frontier.success,
        )
        return _ObservedNode(
            prefix=prefix,
            prefix_id=self._prefix_id(runtime.experiment_id, key),
            node_id=node_id,
            frontier=frontier,
            duplicate=duplicate,
        )

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
            prefetched = runtime.prefetched.pop(key, None)
            if prefetched is None:
                try:
                    frontier = self.adapter.replay(runtime.experiment, prefix)
                except Exception as exc:
                    if not prefix:
                        raise
                    runtime.nodes += 1
                    runtime.replays += 1
                    self._record_path_failure(runtime, prefix, exc)
                    return None
            elif isinstance(prefetched, Exception):
                if not prefix:
                    raise prefetched
                runtime.nodes += 1
                runtime.replays += 1
                self._record_path_failure(runtime, prefix, prefetched)
                return None
            else:
                frontier = prefetched
            return self._commit_frontier(
                runtime,
                prefix,
                frontier,
                cache_hit=False,
            )
        return self._commit_frontier(
            runtime,
            prefix,
            frontier,
            cache_hit=True,
        )

    def _prefetch_prefixes_parallel(
        self,
        runtime: _SearchRuntime,
        prefixes: Sequence[tuple[Action, ...]],
    ) -> None:
        policy = runtime.parallel_policy
        if policy is None or policy.pool_size <= 1 or len(prefixes) <= 1:
            return
        slots = self._remaining_node_slots(runtime)
        window = policy.pool_size if slots is None else min(policy.pool_size, slots)
        if window <= 1:
            return
        dispatch: list[tuple[Action, ...]] = []
        for prefix in prefixes[:window]:
            key = self._key(prefix)
            if key in runtime.cache or key in runtime.prefetched:
                continue
            self._ensure_candidate(runtime, prefix)
            dispatch.append(prefix)
        if len(dispatch) <= 1:
            return
        with ThreadPoolExecutor(max_workers=policy.pool_size) as pool:
            future_by_key = {
                pool.submit(self.adapter.replay, runtime.experiment, prefix): (
                    self._key(prefix),
                    prefix,
                )
                for prefix in dispatch
            }
            for future, (key, _prefix) in future_by_key.items():
                try:
                    runtime.prefetched[key] = future.result()
                except Exception as exc:  # pragma: no cover - consumed by callers
                    runtime.prefetched[key] = exc

    def _replay_prefixes_parallel(
        self,
        runtime: _SearchRuntime,
        prefixes: Sequence[tuple[Action, ...]],
    ) -> list[_ObservedNode | None]:
        policy = runtime.parallel_policy
        if policy is None or policy.pool_size <= 1 or len(prefixes) <= 1:
            return [self._replay_prefix(runtime, prefix) for prefix in prefixes]
        results: dict[tuple[str, ...], SearchFrontier | Exception] = {}
        uncached: list[tuple[Action, ...]] = []
        for prefix in prefixes:
            runtime.max_depth_reached = max(
                runtime.max_depth_reached,
                len(prefix),
            )
            key = self._key(prefix)
            cached = runtime.cache.get(key)
            if cached is None:
                self._ensure_candidate(runtime, prefix)
                uncached.append(prefix)
            else:
                self._ensure_candidate(runtime, prefix)
                results[key] = cached
        if uncached:
            with ThreadPoolExecutor(max_workers=policy.pool_size) as pool:
                future_by_key = {
                    pool.submit(self.adapter.replay, runtime.experiment, prefix): (
                        self._key(prefix),
                        prefix,
                    )
                    for prefix in uncached
                }
                for future, (key, _prefix) in future_by_key.items():
                    try:
                        results[key] = future.result()
                    except Exception as exc:  # pragma: no cover - exercised via callers
                        results[key] = exc
        observed: list[_ObservedNode | None] = []
        for prefix in prefixes:
            key = self._key(prefix)
            result = results[key]
            if isinstance(result, Exception):
                runtime.nodes += 1
                runtime.replays += 1
                self._record_path_failure(runtime, prefix, result)
                observed.append(None)
                continue
            observed.append(
                self._commit_frontier(
                    runtime,
                    prefix,
                    result,
                    cache_hit=key in runtime.cache,
                )
            )
        return observed

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
            self._prefetch_prefixes_parallel(
                runtime,
                [(*prefix, action) for action in ordered],
            )
            for action in reversed(ordered):
                self._ensure_candidate(runtime, (*prefix, action))
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

    def _remaining_node_slots(self, runtime: _SearchRuntime) -> int | None:
        slots: list[int] = []
        if self.budget.max_nodes is not None:
            slots.append(self.budget.max_nodes - runtime.nodes)
        if self.budget.max_replays is not None:
            slots.append(self.budget.max_replays - runtime.replays)
        if not slots:
            return None
        return max(0, min(slots))

    def _plan_beam_child_prefixes(
        self,
        runtime: _SearchRuntime,
        current: Sequence[_ObservedNode],
    ) -> tuple[list[tuple[Action, ...]], bool, bool, TerminationReason | None]:
        child_prefixes: list[tuple[Action, ...]] = []
        layer_complete = True
        depth_limited = False
        stop_reason: TerminationReason | None = None
        remaining_slots = self._remaining_node_slots(runtime)
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
                    return child_prefixes, False, depth_limited, reason
                if remaining_slots is not None and remaining_slots <= 0:
                    stop_reason = (
                        TerminationReason.MAX_NODES
                        if self.budget.max_nodes is not None
                        and runtime.nodes + len(child_prefixes)
                        >= self.budget.max_nodes
                        else TerminationReason.MAX_REPLAYS
                    )
                    layer_complete = False
                    return child_prefixes, layer_complete, depth_limited, stop_reason
                child_prefixes.append((*parent.prefix, action))
                self._ensure_candidate(runtime, child_prefixes[-1])
                if remaining_slots is not None:
                    remaining_slots -= 1
        return child_prefixes, layer_complete, depth_limited, stop_reason

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
            layer_depth = len(current[0].prefix) + 1
            (
                child_prefixes,
                layer_complete,
                depth_limited,
                stop_reason,
            ) = self._plan_beam_child_prefixes(runtime, current)
            for prefix, child in zip(
                child_prefixes,
                self._replay_prefixes_parallel(runtime, child_prefixes),
            ):
                if child is None:
                    key = self._key(prefix)
                    child_records.append(
                        {
                            "action_ids": list(key),
                            "prefix_id": self._prefix_id(runtime.experiment_id, key),
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
                    stop_reason = runtime.termination
                    break
            if stop_reason is not None and runtime.termination != (
                TerminationReason.GOAL_REACHED
            ):
                runtime.termination = stop_reason
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
            for record in child_records:
                if (
                    record.get("status") == "observed"
                    and record.get("expandable") is True
                    and record["prefix_id"] not in selected_ids
                ):
                    action_ids = record.get("action_ids")
                    if isinstance(action_ids, list):
                        self._mark_candidate_key(
                            runtime,
                            [str(item) for item in action_ids],
                            status="pruned",
                        )
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
                self._prefetch_prefixes_parallel(
                    runtime,
                    [
                        (*node.observed.prefix, candidate)
                        for candidate in node.untried_actions
                    ],
                )
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
        search_evidence = self._search_evidence(runtime)
        coverage = _build_coverage_certificate(
            termination=runtime.termination,
            execution_mode=self.strategy.execution_mode,
            search_evidence=search_evidence,
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
            search_evidence=search_evidence,
            coverage=coverage,
            elapsed_seconds=max(0.0, self.clock() - runtime.started),
        )

    def run(self, experiment: Mapping[str, Any]) -> SearchRunResult:
        experiment_id = str(experiment.get("experiment_id", ""))
        if not experiment_id:
            raise ValueError("experiment_id must be a non-empty string")
        parallel_policy = None
        search = experiment.get("search")
        if isinstance(search, Mapping):
            parameters = search.get("parameters")
            if isinstance(parameters, Mapping) and isinstance(
                parameters.get("parallel"),
                Mapping,
            ):
                parallel_policy = ParallelSearchPolicy.from_experiment(experiment)
        runtime = _SearchRuntime(
            experiment=experiment,
            experiment_id=experiment_id,
            parallel_policy=parallel_policy,
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
