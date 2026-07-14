from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


SEARCH_TERMINATION_SCHEMA_VERSION = "search-termination-v1"


class TerminationReason(str, Enum):
    GOAL_REACHED = "goal_reached"
    MAX_DEPTH = "max_depth"
    MAX_NODES = "max_nodes"
    MAX_REPLAYS = "max_replays"
    MAX_SECONDS = "max_seconds"
    STAGNATION = "stagnation"
    REPEATED_TRANSITION = "repeated_transition"
    EXHAUSTED = "exhausted"


def _positive_integer(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be an integer >= 1 or None")
    return value


@dataclass(frozen=True)
class SearchBudget:
    max_depth: int | None = None
    max_nodes: int | None = None
    max_replays: int | None = None
    max_seconds: float | None = None
    stagnation_nodes: int | None = None
    max_transition_repetitions: int | None = None
    target_score: int | float | None = None
    stop_on_success: bool = False

    def __post_init__(self) -> None:
        for name in (
            "max_depth",
            "max_nodes",
            "max_replays",
            "stagnation_nodes",
            "max_transition_repetitions",
        ):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        if self.max_seconds is not None and (
            not isinstance(self.max_seconds, (int, float))
            or isinstance(self.max_seconds, bool)
            or not math.isfinite(self.max_seconds)
            or self.max_seconds <= 0
        ):
            raise ValueError("max_seconds must be a finite number > 0 or None")
        if self.target_score is not None and (
            not isinstance(self.target_score, (int, float))
            or isinstance(self.target_score, bool)
            or not math.isfinite(self.target_score)
        ):
            raise ValueError("target_score must be a finite number or None")
        if not isinstance(self.stop_on_success, bool):
            raise ValueError("stop_on_success must be boolean")
        if all(
            getattr(self, name) is None
            for name in (
                "max_depth",
                "max_nodes",
                "max_replays",
                "max_seconds",
                "stagnation_nodes",
                "max_transition_repetitions",
                "target_score",
            )
        ) and not self.stop_on_success:
            raise ValueError("SearchBudget requires at least one termination condition")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SearchBudget":
        if not isinstance(value, Mapping):
            raise ValueError("search termination config must be a mapping")
        known = {
            "max_depth",
            "max_nodes",
            "max_replays",
            "max_seconds",
            "stagnation_nodes",
            "max_transition_repetitions",
            "target_score",
            "stop_on_success",
        }
        unknown = sorted(set(value) - known)
        if unknown:
            raise ValueError(f"unknown search termination fields: {unknown}")
        return cls(**dict(value))

    @classmethod
    def from_experiment(cls, experiment: Mapping[str, Any]) -> "SearchBudget":
        search = experiment.get("search")
        if not isinstance(search, Mapping):
            raise ValueError("experiment.search must be a mapping")
        raw_budget = search.get("budget")
        parameters = search.get("parameters", {})
        if not isinstance(raw_budget, Mapping) or not isinstance(parameters, Mapping):
            raise ValueError("search budget and parameters must be mappings")
        raw_termination = parameters.get("termination", {})
        if not isinstance(raw_termination, Mapping):
            raise ValueError("search.parameters.termination must be a mapping")
        budget_fields = {"max_depth", "max_nodes", "max_replays", "max_seconds"}
        duplicates = sorted(set(raw_termination) & set(raw_budget) & budget_fields)
        if duplicates:
            raise ValueError(
                "core budget fields must not be duplicated across budget and termination: "
                f"{duplicates}"
            )
        merged = {
            **dict(raw_termination),
            **{
                name: raw_budget[name]
                for name in sorted(budget_fields)
                if name in raw_budget
            },
        }
        return cls.from_mapping(merged)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_depth": self.max_depth,
            "max_nodes": self.max_nodes,
            "max_replays": self.max_replays,
            "max_seconds": self.max_seconds,
            "max_transition_repetitions": self.max_transition_repetitions,
            "stagnation_nodes": self.stagnation_nodes,
            "stop_on_success": self.stop_on_success,
            "target_score": self.target_score,
        }


@dataclass(frozen=True)
class TerminationDecision:
    reason: TerminationReason
    depth: int
    nodes: int
    replays: int
    elapsed_seconds: float
    best_score: int | float | None
    detail: Mapping[str, Any]
    schema_version: str = SEARCH_TERMINATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "best_score": self.best_score,
                "depth": self.depth,
                "detail": self.detail,
                "elapsed_seconds": self.elapsed_seconds,
                "nodes": self.nodes,
                "reason": self.reason.value,
                "replays": self.replays,
                "schema_version": self.schema_version,
            }
        )
        return {
            **identity,
            "decision_id": stable_digest(identity, prefix="stop_"),
        }


class SearchTerminationMonitor:
    def __init__(
        self,
        budget: SearchBudget,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.budget = budget
        self._clock = clock
        self._started_at = clock()
        self.nodes = 0
        self.replays = 0
        self.best_score: int | float | None = None
        self.nodes_since_improvement = 0
        self._transition_visits: dict[tuple[str, str, str], int] = {}
        self.decision: TerminationDecision | None = None

    def _elapsed(self) -> float:
        return max(0.0, self._clock() - self._started_at)

    def _stop(
        self,
        reason: TerminationReason,
        *,
        depth: int,
        detail: Mapping[str, Any],
    ) -> TerminationDecision:
        if self.decision is None:
            self.decision = TerminationDecision(
                reason=reason,
                depth=depth,
                nodes=self.nodes,
                replays=self.replays,
                elapsed_seconds=self._elapsed(),
                best_score=self.best_score,
                detail=detail,
            )
        return self.decision

    def check_before_expand(self, *, depth: int) -> TerminationDecision | None:
        if self.decision is not None:
            return self.decision
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            raise ValueError("depth must be a non-negative integer")
        if self.budget.max_depth is not None and depth >= self.budget.max_depth:
            return self._stop(
                TerminationReason.MAX_DEPTH,
                depth=depth,
                detail={"limit": self.budget.max_depth},
            )
        if self.budget.max_seconds is not None and self._elapsed() >= self.budget.max_seconds:
            return self._stop(
                TerminationReason.MAX_SECONDS,
                depth=depth,
                detail={"limit": self.budget.max_seconds},
            )
        return None

    def observe_node(
        self,
        *,
        depth: int,
        score: int | float,
        success: bool,
        replay_count: int = 0,
        transition: tuple[str, str, str] | None = None,
    ) -> TerminationDecision | None:
        if self.decision is not None:
            return self.decision
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            raise ValueError("depth must be a non-negative integer")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
            raise ValueError("score must be a finite number")
        if not isinstance(success, bool):
            raise ValueError("success must be boolean")
        if not isinstance(replay_count, int) or isinstance(replay_count, bool) or replay_count < 0:
            raise ValueError("replay_count must be a non-negative integer")
        self.nodes += 1
        self.replays += replay_count
        if self.best_score is None or score > self.best_score:
            self.best_score = score
            self.nodes_since_improvement = 0
        else:
            self.nodes_since_improvement += 1
        if success and self.budget.stop_on_success:
            return self._stop(TerminationReason.GOAL_REACHED, depth=depth, detail={"success": True})
        if self.budget.target_score is not None and score >= self.budget.target_score:
            return self._stop(
                TerminationReason.GOAL_REACHED,
                depth=depth,
                detail={"score": score, "target_score": self.budget.target_score},
            )
        if transition is not None:
            if (
                not isinstance(transition, tuple)
                or len(transition) != 3
                or any(not isinstance(item, str) or not item for item in transition)
            ):
                raise ValueError("transition must be (state_before, action_id, state_after)")
            visits = self._transition_visits.get(transition, 0) + 1
            self._transition_visits[transition] = visits
            if (
                self.budget.max_transition_repetitions is not None
                and visits >= self.budget.max_transition_repetitions
            ):
                return self._stop(
                    TerminationReason.REPEATED_TRANSITION,
                    depth=depth,
                    detail={"transition": list(transition), "visits": visits},
                )
        if self.budget.max_nodes is not None and self.nodes >= self.budget.max_nodes:
            return self._stop(
                TerminationReason.MAX_NODES,
                depth=depth,
                detail={"limit": self.budget.max_nodes},
            )
        if self.budget.max_replays is not None and self.replays >= self.budget.max_replays:
            return self._stop(
                TerminationReason.MAX_REPLAYS,
                depth=depth,
                detail={"limit": self.budget.max_replays},
            )
        if (
            self.budget.stagnation_nodes is not None
            and self.nodes_since_improvement >= self.budget.stagnation_nodes
        ):
            return self._stop(
                TerminationReason.STAGNATION,
                depth=depth,
                detail={"nodes_since_improvement": self.nodes_since_improvement},
            )
        if self.budget.max_seconds is not None and self._elapsed() >= self.budget.max_seconds:
            return self._stop(
                TerminationReason.MAX_SECONDS,
                depth=depth,
                detail={"limit": self.budget.max_seconds},
            )
        return None

    def mark_exhausted(self, *, depth: int = 0) -> TerminationDecision:
        return self._stop(TerminationReason.EXHAUSTED, depth=depth, detail={})
