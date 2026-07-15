from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import math
from statistics import NormalDist, fmean, stdev
from types import MappingProxyType
from typing import Any

from ygo_effect_dsl.engine.canonical import (
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.experiment.cross_validation import (
    STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION,
)
from ygo_effect_dsl.storage.query import (
    AnalyticsQueryRow,
    AnalyticsValue,
    AnalyticsValueState,
)


ANALYTICS_COMPARISON_CONTRACT_VERSION = "analytics-comparison-contract-v1"
ANALYTICS_COMPARISON_REQUEST_SCHEMA_VERSION = "analytics-comparison-request-v1"
ANALYTICS_COMPARISON_RESPONSE_SCHEMA_VERSION = "analytics-comparison-response-v1"
ANALYTICS_COMPARISON_OBSERVATION_SCHEMA_VERSION = (
    "analytics-comparison-observation-v1"
)
ANALYTICS_COMPARISON_CONTEXT_SCHEMA_VERSION = "analytics-comparison-context-v1"
ANALYTICS_COMPARISON_BUDGET_SCHEMA_VERSION = "analytics-comparison-budget-v1"
ANALYTICS_COMPARISON_LINEAGE_SCHEMA_VERSION = "analytics-comparison-lineage-v1"
ANALYTICS_COMPARISON_COMPATIBILITY_SCHEMA_VERSION = (
    "analytics-comparison-compatibility-v1"
)
ANALYTICS_COMPARISON_PAIR_SCHEMA_VERSION = "analytics-comparison-pair-v1"
ANALYTICS_COMPARISON_METRIC_SCHEMA_VERSION = "analytics-comparison-metric-v1"
ANALYTICS_COMPARISON_CONFIDENCE_SCHEMA_VERSION = (
    "analytics-comparison-confidence-v1"
)

MAX_COMPARISON_METRICS = 32
DEFAULT_CONFIDENCE_LEVEL = 0.95


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _finite(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be an integer >= 0")
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise ValueError(f"{name} must be a sequence")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(
            f"{name} fields must be exactly {sorted(expected)}; "
            f"observed {sorted(value)}"
        )


def _content_id(value: Any, prefix: str, name: str) -> str:
    parsed = _string(value, name)
    suffix = parsed.removeprefix(prefix)
    if (
        not parsed.startswith(prefix)
        or len(suffix) != 64
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError(f"{name} must be a {prefix!r} content ID")
    return parsed


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    canonical = to_canonical_data(value)

    def freeze(item: Any) -> Any:
        if isinstance(item, dict):
            return MappingProxyType(
                {key: freeze(child) for key, child in item.items()}
            )
        if isinstance(item, list):
            return tuple(freeze(child) for child in item)
        return item

    return freeze(canonical)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in sorted(value.items())}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


class ComparisonArm(str, Enum):
    BASELINE = "baseline"
    INTERRUPTED = "interrupted"
    RECOVERY = "recovery"


class ComparisonCompletion(str, Enum):
    COMPLETE = "complete"
    FRONTIER_EXHAUSTED = "frontier_exhausted"
    EARLY_STOP = "early_stop"
    TIMEOUT = "timeout"
    PRUNED = "pruned"
    PARTIAL_BUDGET = "partial_budget"
    FAILED = "failed"
    QUARANTINED = "quarantined"

    @property
    def censored(self) -> bool:
        return self not in {
            ComparisonCompletion.COMPLETE,
            ComparisonCompletion.FRONTIER_EXHAUSTED,
        }


class BudgetEvidenceStatus(str, Enum):
    OBSERVED = "observed"
    NOT_RECORDED = "not_recorded"


class ConfidenceMethod(str, Enum):
    NONE = "none"
    NORMAL_MEAN_V1 = "normal_mean_v1"


@dataclass(frozen=True)
class ValidatedComparisonLineage:
    evidence: Mapping[str, Any]
    schema_version: str = ANALYTICS_COMPARISON_LINEAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_COMPARISON_LINEAGE_SCHEMA_VERSION:
            raise ValueError("unsupported comparison lineage schema")
        document = _mapping(self.evidence, "lineage evidence")
        _exact_keys(
            document,
            {
                "baseline_semantic_id",
                "divergence",
                "divergence_id",
                "interrupted_semantic_id",
                "lineage_id",
                "recovery_action_count",
                "recovery_event_semantic_ids",
                "schema_version",
                "status",
                "trace_id",
            },
            "lineage evidence",
        )
        if document.get("schema_version") != (
            STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION
        ):
            raise ValueError("unsupported source lineage schema")
        if document.get("status") != "validated":
            raise ValueError("comparison lineage evidence must be validated")
        baseline_id = _content_id(
            document.get("baseline_semantic_id"),
            "strategyroute_",
            "baseline_semantic_id",
        )
        interrupted_id = _content_id(
            document.get("interrupted_semantic_id"),
            "strategyroute_",
            "interrupted_semantic_id",
        )
        divergence = _mapping(document.get("divergence"), "divergence")
        divergence_id = stable_digest(
            divergence, prefix="strategydivergence_"
        )
        if document.get("divergence_id") != divergence_id:
            raise ValueError("divergence_id does not match lineage evidence")
        recovery_ids = tuple(
            _content_id(
                item,
                "strategyrecoveryevent_",
                f"recovery_event_semantic_ids[{index}]",
            )
            for index, item in enumerate(
                _sequence(
                    document.get("recovery_event_semantic_ids"),
                    "recovery_event_semantic_ids",
                )
            )
        )
        if not recovery_ids:
            raise ValueError("validated lineage requires recovery evidence")
        if document.get("recovery_action_count") != len(recovery_ids):
            raise ValueError("recovery_action_count does not match lineage evidence")
        identity = {
            "baseline_semantic_id": baseline_id,
            "divergence": to_canonical_data(divergence),
            "interrupted_semantic_id": interrupted_id,
            "recovery_event_semantic_ids": list(recovery_ids),
            "schema_version": document["schema_version"],
            "trace_id": _string(document.get("trace_id"), "trace_id"),
        }
        lineage_id = stable_digest(identity, prefix="strategylineage_")
        if document.get("lineage_id") != lineage_id:
            raise ValueError("lineage_id does not match lineage evidence")
        object.__setattr__(self, "evidence", _frozen_mapping(document))

    @property
    def lineage_id(self) -> str:
        return str(self.evidence["lineage_id"])

    @property
    def baseline_semantic_id(self) -> str:
        return str(self.evidence["baseline_semantic_id"])

    @property
    def interrupted_semantic_id(self) -> str:
        return str(self.evidence["interrupted_semantic_id"])

    @property
    def recovery_semantic_id(self) -> str:
        return stable_digest(
            list(self.evidence["recovery_event_semantic_ids"]),
            prefix="strategyrecovery_",
        )

    def semantic_id_for(self, arm: ComparisonArm) -> str:
        if arm == ComparisonArm.BASELINE:
            return self.baseline_semantic_id
        if arm == ComparisonArm.INTERRUPTED:
            return self.interrupted_semantic_id
        return self.recovery_semantic_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": _thaw(self.evidence),
            "recovery_semantic_id": self.recovery_semantic_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ComparisonLineageKey:
    lineage: ValidatedComparisonLineage
    deck_id: str
    scenario_id: str
    opening_hand_id: str
    trial_id: str
    interruption_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.lineage, ValidatedComparisonLineage):
            raise ValueError("lineage must be validated comparison lineage")
        for name in (
            "deck_id",
            "scenario_id",
            "opening_hand_id",
            "trial_id",
            "interruption_id",
        ):
            _string(getattr(self, name), name)

    @property
    def key_id(self) -> str:
        return stable_digest(self.identity(), prefix="comparisonkey_")

    def identity(self) -> dict[str, Any]:
        return {
            "deck_id": self.deck_id,
            "interruption_id": self.interruption_id,
            "lineage_id": self.lineage.lineage_id,
            "opening_hand_id": self.opening_hand_id,
            "scenario_id": self.scenario_id,
            "trial_id": self.trial_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity(),
            "key_id": self.key_id,
            "lineage": self.lineage.to_dict(),
        }


@dataclass(frozen=True)
class ComparisonContext:
    evaluator_id: str
    evaluator_version: str
    evaluator_config_hash: str
    search_strategy_id: str
    search_strategy_version: str
    search_config_hash: str
    observation_schema_version: str
    search_schema_version: str
    schema_version: str = ANALYTICS_COMPARISON_CONTEXT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_COMPARISON_CONTEXT_SCHEMA_VERSION:
            raise ValueError("unsupported comparison context schema")
        for name in (
            "evaluator_id",
            "evaluator_version",
            "evaluator_config_hash",
            "search_strategy_id",
            "search_strategy_version",
            "search_config_hash",
            "observation_schema_version",
            "search_schema_version",
        ):
            _string(getattr(self, name), name)

    @property
    def context_id(self) -> str:
        return stable_digest(self.identity(), prefix="comparisoncontext_")

    def identity(self) -> dict[str, Any]:
        return {
            "evaluator_config_hash": self.evaluator_config_hash,
            "evaluator_id": self.evaluator_id,
            "evaluator_version": self.evaluator_version,
            "observation_schema_version": self.observation_schema_version,
            "schema_version": self.schema_version,
            "search_config_hash": self.search_config_hash,
            "search_schema_version": self.search_schema_version,
            "search_strategy_id": self.search_strategy_id,
            "search_strategy_version": self.search_strategy_version,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity(), "context_id": self.context_id}


@dataclass(frozen=True)
class ComparisonCompatibilityEvidence:
    left_context_id: str
    right_context_id: str
    evidence_id: str
    method: str
    status: str = "validated_semantic_equivalence"
    schema_version: str = ANALYTICS_COMPARISON_COMPATIBILITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_COMPARISON_COMPATIBILITY_SCHEMA_VERSION:
            raise ValueError("unsupported compatibility evidence schema")
        if self.status != "validated_semantic_equivalence":
            raise ValueError("compatibility evidence must be validated")
        for name in (
            "left_context_id",
            "right_context_id",
            "evidence_id",
            "method",
        ):
            _string(getattr(self, name), name)
        if self.left_context_id == self.right_context_id:
            raise ValueError("compatibility evidence is unnecessary for equal contexts")

    @property
    def context_pair(self) -> frozenset[str]:
        return frozenset((self.left_context_id, self.right_context_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "left_context_id": self.left_context_id,
            "method": self.method,
            "right_context_id": self.right_context_id,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True)
class ComparisonBudget:
    unit: str | None
    planned_units: int | None
    consumed_units: int | None
    status: BudgetEvidenceStatus = BudgetEvidenceStatus.OBSERVED
    schema_version: str = ANALYTICS_COMPARISON_BUDGET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_COMPARISON_BUDGET_SCHEMA_VERSION:
            raise ValueError("unsupported comparison budget schema")
        status = (
            self.status
            if isinstance(self.status, BudgetEvidenceStatus)
            else BudgetEvidenceStatus(self.status)
        )
        object.__setattr__(self, "status", status)
        if status == BudgetEvidenceStatus.NOT_RECORDED:
            if any(
                value is not None
                for value in (self.unit, self.planned_units, self.consumed_units)
            ):
                raise ValueError("unrecorded budget must not contain values")
            return
        _string(self.unit, "budget unit")
        planned = _integer(self.planned_units, "planned_units")
        consumed = _integer(self.consumed_units, "consumed_units")
        if planned < 1:
            raise ValueError("planned_units must be >= 1")
        if consumed > planned:
            raise ValueError("consumed_units must not exceed planned_units")

    @classmethod
    def not_recorded(cls) -> "ComparisonBudget":
        return cls(None, None, None, BudgetEvidenceStatus.NOT_RECORDED)

    @property
    def fraction(self) -> float | None:
        if self.status == BudgetEvidenceStatus.NOT_RECORDED:
            return None
        assert self.consumed_units is not None
        assert self.planned_units is not None
        return self.consumed_units / self.planned_units

    @property
    def partial(self) -> bool | None:
        fraction = self.fraction
        return None if fraction is None else fraction < 1.0

    def comparison_identity(self) -> tuple[str, int] | None:
        if self.status == BudgetEvidenceStatus.NOT_RECORDED:
            return None
        assert self.unit is not None and self.planned_units is not None
        return self.unit, self.planned_units

    def to_dict(self) -> dict[str, Any]:
        return {
            "consumed_units": self.consumed_units,
            "fraction": self.fraction,
            "partial": self.partial,
            "planned_units": self.planned_units,
            "schema_version": self.schema_version,
            "status": self.status.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class ComparisonObservation:
    query_snapshot_id: str
    lineage_key: ComparisonLineageKey
    arm: ComparisonArm
    semantic_id: str
    run_id: str
    route_id: str
    context: ComparisonContext
    completion: ComparisonCompletion
    budget: ComparisonBudget
    success: AnalyticsValue
    metrics: Mapping[str, AnalyticsValue]
    pruning_policy_version: str | None = None
    schema_version: str = ANALYTICS_COMPARISON_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_COMPARISON_OBSERVATION_SCHEMA_VERSION:
            raise ValueError("unsupported comparison observation schema")
        _string(self.query_snapshot_id, "query_snapshot_id")
        if not isinstance(self.lineage_key, ComparisonLineageKey):
            raise ValueError("lineage_key must be ComparisonLineageKey")
        arm = (
            self.arm
            if isinstance(self.arm, ComparisonArm)
            else ComparisonArm(self.arm)
        )
        completion = (
            self.completion
            if isinstance(self.completion, ComparisonCompletion)
            else ComparisonCompletion(self.completion)
        )
        object.__setattr__(self, "arm", arm)
        object.__setattr__(self, "completion", completion)
        expected_semantic_id = self.lineage_key.lineage.semantic_id_for(arm)
        if self.semantic_id != expected_semantic_id:
            raise ValueError(
                f"{arm.value} semantic_id does not match validated lineage"
            )
        _string(self.run_id, "run_id")
        _string(self.route_id, "route_id")
        if not isinstance(self.context, ComparisonContext):
            raise ValueError("context must be ComparisonContext")
        if not isinstance(self.budget, ComparisonBudget):
            raise ValueError("budget must be ComparisonBudget")
        success = (
            self.success
            if isinstance(self.success, AnalyticsValue)
            else AnalyticsValue.from_mapping(self.success)
        )
        if success.state == AnalyticsValueState.VALUE and not isinstance(
            success.value, bool
        ):
            raise ValueError("success value must be boolean")
        object.__setattr__(self, "success", success)
        parsed_metrics: dict[str, AnalyticsValue] = {}
        for name, raw_value in self.metrics.items():
            metric_name = _string(name, "metric name")
            if metric_name == "success":
                raise ValueError("success is reserved and must not be in metrics")
            value = (
                raw_value
                if isinstance(raw_value, AnalyticsValue)
                else AnalyticsValue.from_mapping(raw_value)
            )
            if value.state == AnalyticsValueState.VALUE:
                _finite(value.value, f"metric {metric_name}")
            parsed_metrics[metric_name] = value
        object.__setattr__(
            self, "metrics", MappingProxyType(dict(sorted(parsed_metrics.items())))
        )
        if completion == ComparisonCompletion.PRUNED:
            _string(self.pruning_policy_version, "pruning_policy_version")
        elif self.pruning_policy_version is not None:
            _string(self.pruning_policy_version, "pruning_policy_version")

    @property
    def observation_id(self) -> str:
        return stable_digest(self.identity(), prefix="comparisonobservation_")

    @property
    def censored(self) -> bool:
        return self.completion.censored

    @property
    def pruning_applied(self) -> bool:
        return self.pruning_policy_version is not None

    def value_for(self, metric: str) -> AnalyticsValue:
        if metric == "success":
            if self.success.state != AnalyticsValueState.VALUE:
                return self.success
            return AnalyticsValue.present(1.0 if self.success.value else 0.0)
        return self.metrics.get(metric, AnalyticsValue.missing())

    def identity(self) -> dict[str, Any]:
        return {
            "arm": self.arm.value,
            "budget": self.budget.to_dict(),
            "completion": self.completion.value,
            "context": self.context.to_dict(),
            "lineage_key_id": self.lineage_key.key_id,
            "metrics": {
                name: value.to_dict() for name, value in self.metrics.items()
            },
            "pruning_policy_version": self.pruning_policy_version,
            "query_snapshot_id": self.query_snapshot_id,
            "route_id": self.route_id,
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "semantic_id": self.semantic_id,
            "success": self.success.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity(),
            "censored": self.censored,
            "lineage_key": self.lineage_key.to_dict(),
            "observation_id": self.observation_id,
            "pruning_applied": self.pruning_applied,
        }


def comparison_observation_from_query_row(
    row: AnalyticsQueryRow,
    *,
    query_snapshot_id: str,
    lineage_key: ComparisonLineageKey,
    arm: ComparisonArm,
    semantic_id: str,
    context: ComparisonContext,
    completion: ComparisonCompletion,
    budget: ComparisonBudget,
    metric_fields: Sequence[str] = ("score", "resource_consumption"),
    pruning_policy_version: str | None = None,
) -> ComparisonObservation:
    if not isinstance(row, AnalyticsQueryRow):
        raise TypeError("row must be AnalyticsQueryRow")
    for required in ("run", "route"):
        value = row.values[required]
        if value.state != AnalyticsValueState.VALUE:
            raise ValueError(f"query row {required} must be an observed value")
    success = row.values["success"]
    metrics = {name: row.values[name] for name in metric_fields}
    return ComparisonObservation(
        query_snapshot_id=query_snapshot_id,
        lineage_key=lineage_key,
        arm=arm,
        semantic_id=semantic_id,
        run_id=str(row.values["run"].value),
        route_id=str(row.values["route"].value),
        context=context,
        completion=completion,
        budget=budget,
        success=success,
        metrics=metrics,
        pruning_policy_version=pruning_policy_version,
    )


@dataclass(frozen=True)
class AnalyticsComparisonRequest:
    query_snapshot_id: str
    metrics: tuple[str, ...]
    confidence_method: ConfidenceMethod = ConfidenceMethod.NORMAL_MEAN_V1
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL
    schema_version: str = ANALYTICS_COMPARISON_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_COMPARISON_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported comparison request schema")
        _string(self.query_snapshot_id, "query_snapshot_id")
        metrics = tuple(self.metrics)
        if not metrics or len(metrics) > MAX_COMPARISON_METRICS:
            raise ValueError(
                f"metrics must contain 1..{MAX_COMPARISON_METRICS} items"
            )
        for metric in metrics:
            _string(metric, "metric")
        if len(metrics) != len(set(metrics)):
            raise ValueError("comparison metrics must be unique")
        method = (
            self.confidence_method
            if isinstance(self.confidence_method, ConfidenceMethod)
            else ConfidenceMethod(self.confidence_method)
        )
        level = _finite(self.confidence_level, "confidence_level")
        if not 0.0 < level < 1.0:
            raise ValueError("confidence_level must be between 0 and 1")
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "confidence_method", method)
        object.__setattr__(self, "confidence_level", level)

    @property
    def request_id(self) -> str:
        return stable_digest(self.to_dict(), prefix="comparisonrequest_")

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence_level": self.confidence_level,
            "confidence_method": self.confidence_method.value,
            "metrics": list(self.metrics),
            "query_snapshot_id": self.query_snapshot_id,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_mapping(cls, value: Any) -> "AnalyticsComparisonRequest":
        document = _mapping(value, "comparison request")
        _exact_keys(
            document,
            {
                "confidence_level",
                "confidence_method",
                "metrics",
                "query_snapshot_id",
                "schema_version",
            },
            "comparison request",
        )
        return cls(
            query_snapshot_id=document.get("query_snapshot_id"),
            metrics=tuple(_sequence(document.get("metrics"), "metrics")),
            confidence_method=document.get("confidence_method"),
            confidence_level=document.get("confidence_level"),
            schema_version=document.get("schema_version"),
        )


def _unavailable_delta_state(
    status: str,
    before: AnalyticsValue,
    after: AnalyticsValue,
) -> AnalyticsValue:
    if status == "unavailable_missing_arm":
        return AnalyticsValue.missing()
    if status == "unavailable_censored":
        return AnalyticsValue.unknown()
    if status.startswith("unavailable_incomparable") or status == (
        "unavailable_unrecorded_budget"
    ):
        return AnalyticsValue.not_applicable()
    states = (before.state, after.state)
    for state, factory in (
        (AnalyticsValueState.QUARANTINED, AnalyticsValue.quarantined),
        (AnalyticsValueState.REDACTED, AnalyticsValue.redacted),
        (AnalyticsValueState.UNKNOWN, AnalyticsValue.unknown),
        (AnalyticsValueState.MISSING, AnalyticsValue.missing),
        (AnalyticsValueState.NOT_APPLICABLE, AnalyticsValue.not_applicable),
    ):
        if state in states:
            return factory()
    return AnalyticsValue.unknown()


def _context_compatibility(
    before: ComparisonObservation,
    after: ComparisonObservation,
    compatibility: Mapping[frozenset[str], ComparisonCompatibilityEvidence],
) -> tuple[bool, str | None]:
    if before.context.context_id == after.context.context_id:
        return True, None
    evidence = compatibility.get(
        frozenset((before.context.context_id, after.context.context_id))
    )
    return (evidence is not None, evidence.evidence_id if evidence else None)


def _comparison_status(
    before: ComparisonObservation | None,
    after: ComparisonObservation | None,
    compatibility: Mapping[frozenset[str], ComparisonCompatibilityEvidence],
) -> tuple[str, str | None]:
    if before is None or after is None:
        return "unavailable_missing_arm", None
    if before.censored or after.censored:
        return "unavailable_censored", None
    context_ok, evidence_id = _context_compatibility(
        before, after, compatibility
    )
    if not context_ok:
        return "unavailable_incomparable_context", None
    before_budget = before.budget.comparison_identity()
    after_budget = after.budget.comparison_identity()
    if before_budget is None or after_budget is None:
        return "unavailable_unrecorded_budget", evidence_id
    if before_budget != after_budget:
        return "unavailable_incomparable_budget", evidence_id
    return "available", evidence_id


def _metric_comparison(
    metric: str,
    before: ComparisonObservation | None,
    after: ComparisonObservation | None,
    compatibility: Mapping[frozenset[str], ComparisonCompatibilityEvidence],
) -> dict[str, Any]:
    before_value = (
        AnalyticsValue.missing() if before is None else before.value_for(metric)
    )
    after_value = (
        AnalyticsValue.missing() if after is None else after.value_for(metric)
    )
    status, compatibility_evidence_id = _comparison_status(
        before, after, compatibility
    )
    if status == "available" and (
        before_value.state != AnalyticsValueState.VALUE
        or after_value.state != AnalyticsValueState.VALUE
    ):
        status = "unavailable_value_state"
    if status == "available":
        before_number = _finite(before_value.value, "before metric")
        after_number = _finite(after_value.value, "after metric")
        absolute = AnalyticsValue.present(after_number - before_number)
        relative = (
            AnalyticsValue.not_applicable()
            if before_number == 0.0
            else AnalyticsValue.present(
                (after_number - before_number) / abs(before_number)
            )
        )
    else:
        absolute = _unavailable_delta_state(
            status, before_value, after_value
        )
        relative = _unavailable_delta_state(
            status, before_value, after_value
        )
    result = {
        "absolute_delta": absolute.to_dict(),
        "after": after_value.to_dict(),
        "before": before_value.to_dict(),
        "compatibility_evidence_id": compatibility_evidence_id,
        "metric": metric,
        "relative_delta": relative.to_dict(),
        "schema_version": ANALYTICS_COMPARISON_METRIC_SCHEMA_VERSION,
        "status": status,
    }
    return {
        **result,
        "metric_comparison_id": stable_digest(
            result, prefix="comparisonmetric_"
        ),
    }


_TRANSITIONS = (
    ("baseline_to_interrupted", ComparisonArm.BASELINE, ComparisonArm.INTERRUPTED),
    ("baseline_to_recovery", ComparisonArm.BASELINE, ComparisonArm.RECOVERY),
    (
        "interrupted_to_recovery",
        ComparisonArm.INTERRUPTED,
        ComparisonArm.RECOVERY,
    ),
)


def _pair_document(
    key: ComparisonLineageKey,
    arms: Mapping[ComparisonArm, ComparisonObservation],
    request: AnalyticsComparisonRequest,
    compatibility: Mapping[frozenset[str], ComparisonCompatibilityEvidence],
) -> dict[str, Any]:
    missing_arms = [arm.value for arm in ComparisonArm if arm not in arms]
    transition_documents: dict[str, Any] = {}
    statuses: set[str] = set()
    for transition, before_arm, after_arm in _TRANSITIONS:
        metrics = {
            metric: _metric_comparison(
                metric,
                arms.get(before_arm),
                arms.get(after_arm),
                compatibility,
            )
            for metric in request.metrics
        }
        transition_statuses = {item["status"] for item in metrics.values()}
        statuses.update(transition_statuses)
        transition_documents[transition] = {
            "after_arm": after_arm.value,
            "before_arm": before_arm.value,
            "metrics": metrics,
            "status": (
                "available"
                if transition_statuses == {"available"}
                else "partially_or_not_available"
            ),
        }
    if missing_arms:
        pair_status = "incomplete"
    elif any(observation.censored for observation in arms.values()):
        pair_status = "censored"
    elif any(status.startswith("unavailable_incomparable") for status in statuses):
        pair_status = "incomparable"
    elif "unavailable_unrecorded_budget" in statuses:
        pair_status = "incomparable"
    else:
        pair_status = "complete"
    budgets = {
        arm.value: arms[arm].budget.to_dict() if arm in arms else None
        for arm in ComparisonArm
    }
    pruning = sorted(
        {
            observation.pruning_policy_version
            for observation in arms.values()
            if observation.pruning_policy_version is not None
        }
    )
    identity = {
        "arms": {
            arm.value: arms[arm].to_dict() if arm in arms else None
            for arm in ComparisonArm
        },
        "budget": budgets,
        "censor_reasons": sorted(
            {
                observation.completion.value
                for observation in arms.values()
                if observation.censored
            }
        ),
        "lineage_key": key.to_dict(),
        "missing_arms": missing_arms,
        "pruning": {
            "affected": bool(pruning),
            "policy_versions": pruning,
        },
        "schema_version": ANALYTICS_COMPARISON_PAIR_SCHEMA_VERSION,
        "status": pair_status,
        "transitions": transition_documents,
    }
    return {**identity, "pair_id": stable_digest(identity, prefix="comparisonpair_")}


def _confidence(
    values: Sequence[float], request: AnalyticsComparisonRequest
) -> dict[str, Any]:
    sample_count = len(values)
    base = {
        "assumptions": [
            "independent_validated_lineages",
            "censored_and_incomparable_pairs_excluded",
        ],
        "confidence_level": request.confidence_level,
        "method": request.confidence_method.value,
        "sample_count": sample_count,
        "schema_version": ANALYTICS_COMPARISON_CONFIDENCE_SCHEMA_VERSION,
    }
    if request.confidence_method == ConfidenceMethod.NONE:
        return {**base, "lower": None, "status": "disabled", "upper": None}
    if sample_count < 2:
        return {
            **base,
            "lower": None,
            "status": "unavailable_insufficient_sample",
            "upper": None,
        }
    mean = fmean(values)
    standard_error = stdev(values) / math.sqrt(sample_count)
    critical = NormalDist().inv_cdf(0.5 + request.confidence_level / 2.0)
    return {
        **base,
        "assumptions": [
            *base["assumptions"],
            "normal_approximation_of_paired_mean",
        ],
        "lower": mean - critical * standard_error,
        "status": "available_provisional",
        "upper": mean + critical * standard_error,
    }


def _value_payload_number(value: Mapping[str, Any]) -> float | None:
    if value.get("state") != AnalyticsValueState.VALUE.value:
        return None
    return _finite(value.get("value"), "metric payload")


def _aggregate_metric_summaries(
    pairs: Sequence[Mapping[str, Any]],
    request: AnalyticsComparisonRequest,
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for transition, _, _ in _TRANSITIONS:
        metric_summaries: dict[str, Any] = {}
        for metric in request.metrics:
            entries = [
                pair["transitions"][transition]["metrics"][metric]
                for pair in pairs
            ]
            absolute_values = [
                value
                for entry in entries
                if (value := _value_payload_number(entry["absolute_delta"]))
                is not None
            ]
            relative_values = [
                value
                for entry in entries
                if (value := _value_payload_number(entry["relative_delta"]))
                is not None
            ]
            metric_summaries[metric] = {
                "absolute_delta_confidence": _confidence(
                    absolute_values, request
                ),
                "available_pair_count": len(absolute_values),
                "mean_absolute_delta": (
                    fmean(absolute_values) if absolute_values else None
                ),
                "mean_relative_delta": (
                    fmean(relative_values) if relative_values else None
                ),
                "relative_pair_count": len(relative_values),
                "unavailable_pair_count": len(entries) - len(absolute_values),
            }
        summaries[transition] = metric_summaries
    return summaries


def _arm_statistics(
    observations: Sequence[ComparisonObservation],
    request: AnalyticsComparisonRequest,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for arm in ComparisonArm:
        arm_observations = [
            item for item in observations if item.arm == arm and not item.censored
        ]
        metrics: dict[str, Any] = {}
        for metric in request.metrics:
            values = [
                _finite(value.value, metric)
                for item in arm_observations
                if (value := item.value_for(metric)).state
                == AnalyticsValueState.VALUE
            ]
            metrics[metric] = {
                "mean": fmean(values) if values else None,
                "observed_count": len(values),
            }
        result[arm.value] = {
            "metrics": metrics,
            "observation_count": len(arm_observations),
        }
    return result


def build_analytics_comparison_report(
    observations: Sequence[ComparisonObservation],
    request: AnalyticsComparisonRequest,
    *,
    compatibility_evidence: Sequence[ComparisonCompatibilityEvidence] = (),
) -> dict[str, Any]:
    if not isinstance(request, AnalyticsComparisonRequest):
        raise TypeError("request must be AnalyticsComparisonRequest")
    parsed = tuple(observations)
    if not parsed:
        raise ValueError("at least one comparison observation is required")
    if any(not isinstance(item, ComparisonObservation) for item in parsed):
        raise ValueError("observations must contain ComparisonObservation values")
    if any(item.query_snapshot_id != request.query_snapshot_id for item in parsed):
        raise ValueError("all observations must belong to the request snapshot")
    compatibility: dict[
        frozenset[str], ComparisonCompatibilityEvidence
    ] = {}
    for item in compatibility_evidence:
        if not isinstance(item, ComparisonCompatibilityEvidence):
            raise ValueError("invalid compatibility evidence")
        if item.context_pair in compatibility:
            raise ValueError("duplicate compatibility evidence for context pair")
        compatibility[item.context_pair] = item
    grouped: dict[str, list[ComparisonObservation]] = defaultdict(list)
    keys: dict[str, ComparisonLineageKey] = {}
    for observation in parsed:
        key_id = observation.lineage_key.key_id
        grouped[key_id].append(observation)
        keys[key_id] = observation.lineage_key
    pairs: list[dict[str, Any]] = []
    for key_id in sorted(grouped):
        arms: dict[ComparisonArm, ComparisonObservation] = {}
        for observation in grouped[key_id]:
            if observation.arm in arms:
                raise ValueError(
                    f"duplicate {observation.arm.value} observation for {key_id}"
                )
            arms[observation.arm] = observation
        pairs.append(
            _pair_document(keys[key_id], arms, request, compatibility)
        )
    pair_status_counts = {
        status: sum(pair["status"] == status for pair in pairs)
        for status in ("complete", "incomplete", "censored", "incomparable")
    }
    pruning_pairs = sum(pair["pruning"]["affected"] for pair in pairs)
    partial_budget_pairs = sum(
        any(
            budget is not None and budget["partial"] is True
            for budget in pair["budget"].values()
        )
        for pair in pairs
    )
    identity = {
        "arm_statistics": _arm_statistics(parsed, request),
        "compatibility_evidence": [
            compatibility[key].to_dict()
            for key in sorted(
                compatibility,
                key=lambda item: sorted(item),
            )
        ],
        "metric_summaries": _aggregate_metric_summaries(pairs, request),
        "pairs": pairs,
        "request": request.to_dict(),
        "request_id": request.request_id,
        "sample": {
            "pair_status_counts": pair_status_counts,
            "partial_budget_pair_count": partial_budget_pairs,
            "pruning_affected_pair_count": pruning_pairs,
            "total_lineage_count": len(pairs),
        },
        "schema_version": ANALYTICS_COMPARISON_RESPONSE_SCHEMA_VERSION,
        "uncertainty": {
            "censored_pairs_excluded_from_deltas": True,
            "confidence_method": request.confidence_method.value,
            "partial_budget_visible": True,
            "statistical_pruning_bias": (
                "present" if pruning_pairs else "not_observed"
            ),
        },
    }
    return {
        **identity,
        "comparison_report_id": stable_digest(
            identity, prefix="comparisonreport_"
        ),
    }


def analytics_comparison_contract_document() -> dict[str, Any]:
    return to_canonical_data(
        {
            "arms": [arm.value for arm in ComparisonArm],
            "compatibility": {
                "different_contexts_require": (
                    "analytics-comparison-compatibility-v1 with "
                    "validated_semantic_equivalence"
                ),
                "exact_context_fields": [
                    "evaluator_id/version/config_hash",
                    "search_strategy_id/version/config_hash",
                    "observation_schema_version",
                    "search_schema_version",
                ],
            },
            "confidence": {
                "method": ConfidenceMethod.NORMAL_MEAN_V1.value,
                "minimum_sample_count": 2,
                "status": "available_provisional",
            },
            "lineage": {
                "accepted_source_schema": (
                    STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION
                ),
                "requires_status": "validated",
                "tamper_checks": [
                    "divergence_id",
                    "lineage_id",
                    "recovery_action_count",
                    "arm_semantic_id",
                ],
            },
            "metrics": {
                "absolute_delta": "after - before",
                "missing_or_incomparable": "never coerced to zero or failure",
                "relative_delta": "(after - before) / abs(before)",
                "zero_before": "not_applicable",
            },
            "pairing": {
                "key_fields": [
                    "deck_id",
                    "scenario_id",
                    "opening_hand_id",
                    "trial_id",
                    "interruption_id",
                    "validated_lineage_id",
                ],
                "missing_arms": "explicit incomplete pair",
            },
            "schemas": {
                "budget": ANALYTICS_COMPARISON_BUDGET_SCHEMA_VERSION,
                "compatibility": (
                    ANALYTICS_COMPARISON_COMPATIBILITY_SCHEMA_VERSION
                ),
                "confidence": ANALYTICS_COMPARISON_CONFIDENCE_SCHEMA_VERSION,
                "context": ANALYTICS_COMPARISON_CONTEXT_SCHEMA_VERSION,
                "lineage": ANALYTICS_COMPARISON_LINEAGE_SCHEMA_VERSION,
                "metric": ANALYTICS_COMPARISON_METRIC_SCHEMA_VERSION,
                "observation": ANALYTICS_COMPARISON_OBSERVATION_SCHEMA_VERSION,
                "pair": ANALYTICS_COMPARISON_PAIR_SCHEMA_VERSION,
                "request": ANALYTICS_COMPARISON_REQUEST_SCHEMA_VERSION,
                "response": ANALYTICS_COMPARISON_RESPONSE_SCHEMA_VERSION,
            },
            "uncertainty": {
                "censored_completion_states": [
                    item.value for item in ComparisonCompletion if item.censored
                ],
                "partial_budget": "reported per arm and pair",
                "statistical_pruning": "reported as explicit potential bias",
            },
            "version": ANALYTICS_COMPARISON_CONTRACT_VERSION,
        }
    )
