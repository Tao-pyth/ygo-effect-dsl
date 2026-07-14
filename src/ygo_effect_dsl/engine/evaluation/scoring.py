from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


SCORE_BREAKDOWN_SCHEMA_VERSION = "score-breakdown-v1"
SCORE_COMPARISON_SCHEMA_VERSION = "score-comparison-v1"


class MissingValuePolicy(str, Enum):
    ERROR = "error"
    ZERO = "zero"
    CONFIGURED_DEFAULT = "configured_default"


class ValueResolution(str, Enum):
    OBSERVED = "observed"
    ZERO = "zero"
    CONFIGURED_DEFAULT = "configured_default"


def _number(value: Any, path: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{path} must be a finite number")
    return value


@dataclass(frozen=True)
class ScoreTerm:
    metric: str
    raw_value: int | float | None
    resolved_value: int | float
    weight: int | float
    resolution: ValueResolution

    def __post_init__(self) -> None:
        if not isinstance(self.metric, str) or not self.metric:
            raise ValueError("metric must be a non-empty string")
        if not isinstance(self.resolution, ValueResolution):
            object.__setattr__(self, "resolution", ValueResolution(self.resolution))
        if self.raw_value is not None:
            _number(self.raw_value, "raw_value")
        _number(self.resolved_value, "resolved_value")
        _number(self.weight, "weight")
        if self.resolution == ValueResolution.OBSERVED:
            if self.raw_value is None or self.raw_value != self.resolved_value:
                raise ValueError("observed term must preserve its raw value")
        elif self.raw_value is not None:
            raise ValueError("resolved missing term must have raw_value=None")
        if self.resolution == ValueResolution.ZERO and self.resolved_value != 0:
            raise ValueError("zero-resolved term must resolve to 0")

    @property
    def contribution(self) -> int | float:
        return self.resolved_value * self.weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "contribution": self.contribution,
            "metric": self.metric,
            "raw_value": self.raw_value,
            "resolution": self.resolution.value,
            "resolved_value": self.resolved_value,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class ScoreBreakdown:
    terms: tuple[ScoreTerm, ...]
    schema_version: str = SCORE_BREAKDOWN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCORE_BREAKDOWN_SCHEMA_VERSION:
            raise ValueError("unsupported score breakdown schema")
        ordered = tuple(sorted(self.terms, key=lambda item: item.metric))
        if len({item.metric for item in ordered}) != len(ordered):
            raise ValueError("score breakdown metrics must be unique")
        if not ordered:
            raise ValueError("score breakdown requires at least one term")
        object.__setattr__(self, "terms", ordered)

    @property
    def total_score(self) -> int | float:
        return sum((term.contribution for term in self.terms), start=0)

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "missing_metrics": [
                    term.metric for term in self.terms if term.raw_value is None
                ],
                "schema_version": self.schema_version,
                "terms": [term.to_dict() for term in self.terms],
                "total_score": self.total_score,
            }
        )
        return {
            **identity,
            "breakdown_id": stable_digest(identity, prefix="score_"),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ScoreBreakdown":
        if not isinstance(value, Mapping):
            raise ValueError("score breakdown must be a mapping")
        if value.get("schema_version") != SCORE_BREAKDOWN_SCHEMA_VERSION:
            raise ValueError("unsupported score breakdown schema")
        raw_terms = value.get("terms")
        if not isinstance(raw_terms, list):
            raise ValueError("score breakdown terms must be a list")
        terms: list[ScoreTerm] = []
        for raw_term in raw_terms:
            if not isinstance(raw_term, Mapping):
                raise ValueError("score breakdown term must be a mapping")
            terms.append(
                ScoreTerm(
                    metric=raw_term.get("metric"),
                    raw_value=raw_term.get("raw_value"),
                    resolved_value=raw_term.get("resolved_value"),
                    weight=raw_term.get("weight"),
                    resolution=ValueResolution(str(raw_term.get("resolution"))),
                )
            )
        breakdown = cls(tuple(terms))
        if breakdown.to_dict() != to_canonical_data(value):
            raise ValueError("score breakdown does not match its terms")
        return breakdown


def build_weighted_score_breakdown(
    values: Mapping[str, int | float | None],
    weights: Mapping[str, int | float],
    *,
    missing_policy: MissingValuePolicy = MissingValuePolicy.ERROR,
    defaults: Mapping[str, int | float] | None = None,
) -> ScoreBreakdown:
    if not isinstance(values, Mapping) or not isinstance(weights, Mapping):
        raise ValueError("values and weights must be mappings")
    if not isinstance(missing_policy, MissingValuePolicy):
        missing_policy = MissingValuePolicy(missing_policy)
    defaults = defaults or {}
    unweighted = sorted(set(values) - set(weights))
    if unweighted:
        raise ValueError(f"metrics have no weights: {unweighted}")
    terms: list[ScoreTerm] = []
    for metric in sorted(weights):
        if not isinstance(metric, str) or not metric:
            raise ValueError("weight metric must be a non-empty string")
        weight = _number(weights[metric], f"weights.{metric}")
        raw_value = values.get(metric)
        if raw_value is not None:
            resolved_value = _number(raw_value, f"values.{metric}")
            resolution = ValueResolution.OBSERVED
        elif missing_policy == MissingValuePolicy.ERROR:
            raise ValueError(f"missing evaluation value for metric {metric!r}")
        elif missing_policy == MissingValuePolicy.ZERO:
            resolved_value = 0
            resolution = ValueResolution.ZERO
        else:
            if metric not in defaults:
                raise ValueError(f"missing configured default for metric {metric!r}")
            resolved_value = _number(defaults[metric], f"defaults.{metric}")
            resolution = ValueResolution.CONFIGURED_DEFAULT
        terms.append(
            ScoreTerm(
                metric=metric,
                raw_value=raw_value,
                resolved_value=resolved_value,
                weight=weight,
                resolution=resolution,
            )
        )
    return ScoreBreakdown(tuple(terms))


def compare_score_breakdowns(
    before: ScoreBreakdown,
    after: ScoreBreakdown,
) -> dict[str, Any]:
    before_terms = {term.metric: term for term in before.terms}
    after_terms = {term.metric: term for term in after.terms}
    metrics = sorted(before_terms.keys() | after_terms.keys())
    terms = []
    for metric in metrics:
        before_term = before_terms.get(metric)
        after_term = after_terms.get(metric)
        before_contribution = (
            before_term.contribution if before_term is not None else 0
        )
        after_contribution = after_term.contribution if after_term is not None else 0
        terms.append(
            {
                "after_contribution": after_contribution,
                "after_resolved_value": (
                    after_term.resolved_value if after_term is not None else None
                ),
                "after_weight": after_term.weight if after_term is not None else None,
                "before_contribution": before_contribution,
                "before_resolved_value": (
                    before_term.resolved_value if before_term is not None else None
                ),
                "before_weight": before_term.weight if before_term is not None else None,
                "contribution_delta": after_contribution - before_contribution,
                "metric": metric,
            }
        )
    identity = to_canonical_data(
        {
            "after_breakdown_id": after.to_dict()["breakdown_id"],
            "before_breakdown_id": before.to_dict()["breakdown_id"],
            "schema_version": SCORE_COMPARISON_SCHEMA_VERSION,
            "terms": terms,
            "total_score_delta": after.total_score - before.total_score,
        }
    )
    return {
        **identity,
        "comparison_id": stable_digest(identity, prefix="scorecmp_"),
    }
