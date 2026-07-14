from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation import EvaluatorSpec
from ygo_effect_dsl.engine.evaluation.scoring import SCORE_BREAKDOWN_SCHEMA_VERSION
from ygo_effect_dsl.engine.state.identity import STATE_ID_SCHEMA_VERSION


PRUNING_POLICY_SCHEMA_VERSION = "pruning-guardrail-policy-v2"
PRUNING_DATA_SCHEMA_VERSION = "pruning-data-identity-v1"
PRUNING_DECISION_SCHEMA_VERSION = "pruning-decision-v2"
EXPLORATION_DECISION_SCHEMA_VERSION = "unexplored-action-decision-v1"
PRUNING_AUDIT_SCHEMA_VERSION = "pruning-audit-v2"
PRUNING_BOUND_METHOD = "independent_cluster_hoeffding_v1"
LEGACY_PRUNING_BOUND_METHOD = "bounded_hoeffding_v0"
SUPPORTED_PRUNING_BOUND_METHODS = frozenset(
    {PRUNING_BOUND_METHOD, LEGACY_PRUNING_BOUND_METHOD}
)


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _finite_number(value: Any, name: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    return value


class PruningDisposition(str, Enum):
    KEEP = "keep"
    PRUNE = "prune"
    INVALIDATE = "invalidate"


class PruningReason(str, Enum):
    DATA_IDENTITY_MISMATCH = "data_identity_mismatch"
    MANDATORY_MINIMUM_VISITS = "mandatory_minimum_visits"
    INCUMBENT_UNDER_SAMPLED = "incumbent_under_sampled"
    INDEPENDENCE_UNVERIFIED = "independence_unverified"
    CONFIDENCE_OVERLAP = "confidence_overlap"
    OPTIMISTIC_BOUND_DOMINATED = "optimistic_bound_dominated"


class ExplorationReason(str, Enum):
    NO_UNEXPLORED_ACTIONS = "no_unexplored_actions"
    PROBABILITY_SELECTED_UNEXPLORED = "probability_selected_unexplored"
    PROBABILITY_SELECTED_EXPLORED = "probability_selected_explored"


@dataclass(frozen=True)
class PruningGuardrailPolicy:
    minimum_action_visits: int
    unexplored_action_probability: float
    confidence_delta: float
    score_lower_bound: int | float
    score_upper_bound: int | float
    prune_margin: int | float = 0
    bound_method: str = PRUNING_BOUND_METHOD
    schema_version: str = PRUNING_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.minimum_action_visits, int)
            or isinstance(self.minimum_action_visits, bool)
            or self.minimum_action_visits < 1
        ):
            raise ValueError("minimum_action_visits must be an integer >= 1")
        for name in ("unexplored_action_probability", "confidence_delta"):
            value = _finite_number(getattr(self, name), name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be greater than 0 and at most 1")
        lower = _finite_number(self.score_lower_bound, "score_lower_bound")
        upper = _finite_number(self.score_upper_bound, "score_upper_bound")
        if lower >= upper:
            raise ValueError("score_lower_bound must be less than score_upper_bound")
        if _finite_number(self.prune_margin, "prune_margin") < 0:
            raise ValueError("prune_margin must be greater than or equal to 0")
        if self.bound_method not in SUPPORTED_PRUNING_BOUND_METHODS:
            raise ValueError(
                "bound_method must be one of "
                f"{sorted(SUPPORTED_PRUNING_BOUND_METHODS)!r}"
            )
        if self.schema_version != PRUNING_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported pruning policy schema")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PruningGuardrailPolicy":
        if not isinstance(value, Mapping):
            raise ValueError("search pruning config must be a mapping")
        known = {
            "minimum_action_visits",
            "unexplored_action_probability",
            "confidence_delta",
            "score_lower_bound",
            "score_upper_bound",
            "prune_margin",
            "bound_method",
        }
        unknown = sorted(set(value) - known)
        if unknown:
            raise ValueError(f"unknown search pruning fields: {unknown}")
        required = known - {"prune_margin", "bound_method"}
        missing = sorted(required - set(value))
        if missing:
            raise ValueError(f"missing search pruning fields: {missing}")
        return cls(**dict(value))

    @classmethod
    def from_experiment(cls, experiment: Mapping[str, Any]) -> "PruningGuardrailPolicy":
        search = experiment.get("search")
        if not isinstance(search, Mapping):
            raise ValueError("experiment.search must be a mapping")
        parameters = search.get("parameters")
        if not isinstance(parameters, Mapping):
            raise ValueError("search.parameters must be a mapping")
        pruning = parameters.get("pruning")
        if not isinstance(pruning, Mapping):
            raise ValueError("search.parameters.pruning must be a mapping")
        return cls.from_mapping(pruning)

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "bound_method": self.bound_method,
                "confidence_delta": self.confidence_delta,
                "minimum_action_visits": self.minimum_action_visits,
                "prune_margin": self.prune_margin,
                "schema_version": self.schema_version,
                "score_lower_bound": self.score_lower_bound,
                "score_upper_bound": self.score_upper_bound,
                "unexplored_action_probability": self.unexplored_action_probability,
            }
        )
        return {**identity, "policy_id": stable_digest(identity, prefix="prunepol_")}


@dataclass(frozen=True)
class PruningDataIdentity:
    evaluator_id: str
    evaluator_version: str
    evaluator_config_hash: str
    information_mode: str
    evaluate_at: str
    environment_hash: str
    state_id_schema_version: str = STATE_ID_SCHEMA_VERSION
    score_schema_version: str = SCORE_BREAKDOWN_SCHEMA_VERSION
    schema_version: str = PRUNING_DATA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "evaluator_id",
            "evaluator_version",
            "evaluator_config_hash",
            "information_mode",
            "evaluate_at",
            "environment_hash",
            "state_id_schema_version",
            "score_schema_version",
        ):
            _non_empty_string(getattr(self, name), name)
        if self.schema_version != PRUNING_DATA_SCHEMA_VERSION:
            raise ValueError("unsupported pruning data identity schema")

    @classmethod
    def from_experiment(cls, experiment: Mapping[str, Any]) -> "PruningDataIdentity":
        if not isinstance(experiment, Mapping):
            raise ValueError("experiment must be a mapping")
        spec = EvaluatorSpec.from_mapping(experiment.get("evaluator"))
        information_mode = _non_empty_string(
            experiment.get("information_mode"), "information_mode"
        )
        evaluate_at = _non_empty_string(experiment.get("evaluate_at"), "evaluate_at")
        environment = {
            name: experiment.get(name)
            for name in (
                "deck",
                "player",
                "turn_limit",
                "information_mode",
                "evaluate_at",
                "success_predicate",
                "interruption",
                "replay",
            )
        }
        return cls(
            evaluator_id=spec.evaluator_id,
            evaluator_version=spec.version,
            evaluator_config_hash=spec.config_hash,
            information_mode=information_mode,
            evaluate_at=evaluate_at,
            environment_hash=stable_digest(environment, prefix="searchenv_"),
        )

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "environment_hash": self.environment_hash,
                "evaluate_at": self.evaluate_at,
                "evaluator_config_hash": self.evaluator_config_hash,
                "evaluator_id": self.evaluator_id,
                "evaluator_version": self.evaluator_version,
                "information_mode": self.information_mode,
                "schema_version": self.schema_version,
                "score_schema_version": self.score_schema_version,
                "state_id_schema_version": self.state_id_schema_version,
            }
        )
        return {**identity, "dataset_id": stable_digest(identity, prefix="prunedata_")}

    @property
    def dataset_id(self) -> str:
        return str(self.to_dict()["dataset_id"])


@dataclass(frozen=True)
class ActionEvidence:
    parent_state_id: str
    action_id: str
    dataset_id: str
    scores: tuple[int | float, ...]
    sampling_unit_ids: tuple[str, ...] | None = None
    independence_basis: str | None = None

    def __post_init__(self) -> None:
        for name in ("parent_state_id", "action_id", "dataset_id"):
            _non_empty_string(getattr(self, name), name)
        if not isinstance(self.scores, tuple):
            raise ValueError("scores must be a tuple")
        for index, score in enumerate(self.scores):
            _finite_number(score, f"scores[{index}]")
        if self.sampling_unit_ids is None:
            if self.independence_basis is not None:
                raise ValueError(
                    "independence_basis requires sampling_unit_ids"
                )
        else:
            if not isinstance(self.sampling_unit_ids, tuple):
                raise ValueError("sampling_unit_ids must be a tuple")
            if len(self.sampling_unit_ids) != len(self.scores):
                raise ValueError(
                    "sampling_unit_ids must contain one ID for each score"
                )
            for index, unit_id in enumerate(self.sampling_unit_ids):
                _non_empty_string(unit_id, f"sampling_unit_ids[{index}]")
            _non_empty_string(self.independence_basis, "independence_basis")

    @property
    def visits(self) -> int:
        return len(self.scores)

    @property
    def mean_score(self) -> float | None:
        if not self.scores:
            return None
        return math.fsum(self.scores) / self.visits

    @property
    def independent_unit_count(self) -> int | None:
        if self.sampling_unit_ids is None:
            return None
        return len(set(self.sampling_unit_ids))

    def independent_unit_scores(self) -> tuple[float, ...]:
        if self.sampling_unit_ids is None:
            raise ValueError("independent sampling units are not identified")
        grouped: dict[str, list[int | float]] = {}
        for unit_id, score in zip(
            self.sampling_unit_ids, self.scores, strict=True
        ):
            grouped.setdefault(unit_id, []).append(score)
        return tuple(
            math.fsum(scores) / len(scores) for scores in grouped.values()
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "dataset_id": self.dataset_id,
            "independence_basis": self.independence_basis,
            "independent_unit_count": self.independent_unit_count,
            "mean_score": self.mean_score,
            "parent_state_id": self.parent_state_id,
            "visits": self.visits,
        }


@dataclass(frozen=True)
class ScoreInterval:
    lower: float
    upper: float
    mean: float
    radius: float
    sample_count: int
    raw_sample_count: int
    method: str = PRUNING_BOUND_METHOD

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "lower": self.lower,
                "mean": self.mean,
                "method": self.method,
                "radius": self.radius,
                "raw_sample_count": self.raw_sample_count,
                "sample_count": self.sample_count,
                "upper": self.upper,
            }
        )


@dataclass(frozen=True)
class PruningDecision:
    disposition: PruningDisposition
    reason: PruningReason
    candidate: Mapping[str, Any]
    incumbent: Mapping[str, Any]
    candidate_interval: ScoreInterval | None
    incumbent_interval: ScoreInterval | None
    detail: Mapping[str, Any]
    schema_version: str = PRUNING_DECISION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "candidate": self.candidate,
                "candidate_interval": (
                    self.candidate_interval.to_dict()
                    if self.candidate_interval is not None
                    else None
                ),
                "detail": self.detail,
                "disposition": self.disposition.value,
                "incumbent": self.incumbent,
                "incumbent_interval": (
                    self.incumbent_interval.to_dict()
                    if self.incumbent_interval is not None
                    else None
                ),
                "reason": self.reason.value,
                "schema_version": self.schema_version,
            }
        )
        return {**identity, "decision_id": stable_digest(identity, prefix="prune_")}


@dataclass(frozen=True)
class ExplorationDecision:
    has_unexplored_actions: bool
    draw: float
    probability: float
    select_unexplored: bool
    reason: ExplorationReason
    schema_version: str = EXPLORATION_DECISION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "draw": self.draw,
                "has_unexplored_actions": self.has_unexplored_actions,
                "probability": self.probability,
                "reason": self.reason.value,
                "schema_version": self.schema_version,
                "select_unexplored": self.select_unexplored,
            }
        )
        return {**identity, "decision_id": stable_digest(identity, prefix="explore_")}


class SearchPruningGuardrails:
    def __init__(
        self,
        policy: PruningGuardrailPolicy,
        data_identity: PruningDataIdentity,
    ) -> None:
        self.policy = policy
        self.data_identity = data_identity
        self._records: list[dict[str, Any]] = []

    def _record(self, payload: Mapping[str, Any]) -> None:
        self._records.append(to_canonical_data(payload))

    def choose_unexplored(
        self,
        *,
        has_unexplored_actions: bool,
        draw: float,
    ) -> ExplorationDecision:
        if not isinstance(has_unexplored_actions, bool):
            raise ValueError("has_unexplored_actions must be boolean")
        draw = float(_finite_number(draw, "draw"))
        if not 0 <= draw < 1:
            raise ValueError("draw must be greater than or equal to 0 and less than 1")
        if not has_unexplored_actions:
            selected = False
            reason = ExplorationReason.NO_UNEXPLORED_ACTIONS
        elif draw < self.policy.unexplored_action_probability:
            selected = True
            reason = ExplorationReason.PROBABILITY_SELECTED_UNEXPLORED
        else:
            selected = False
            reason = ExplorationReason.PROBABILITY_SELECTED_EXPLORED
        decision = ExplorationDecision(
            has_unexplored_actions=has_unexplored_actions,
            draw=draw,
            probability=self.policy.unexplored_action_probability,
            select_unexplored=selected,
            reason=reason,
        )
        self._record(decision.to_dict())
        return decision

    def _interval(self, evidence: ActionEvidence) -> ScoreInterval:
        if not evidence.scores:
            raise ValueError("cannot calculate an interval without scores")
        for score in evidence.scores:
            if not self.policy.score_lower_bound <= score <= self.policy.score_upper_bound:
                raise ValueError(
                    f"score {score!r} is outside the configured score bounds"
                )
        if self.policy.bound_method == PRUNING_BOUND_METHOD:
            interval_scores = evidence.independent_unit_scores()
            # confidence_delta is the family-wise error budget for both Actions.
            log_term = math.log(4 / self.policy.confidence_delta)
        else:
            interval_scores = tuple(float(score) for score in evidence.scores)
            log_term = math.log(2 / self.policy.confidence_delta)
        sample_count = len(interval_scores)
        score_range = self.policy.score_upper_bound - self.policy.score_lower_bound
        radius = score_range * math.sqrt(
            log_term / (2 * sample_count)
        )
        mean = math.fsum(interval_scores) / sample_count
        return ScoreInterval(
            lower=max(float(self.policy.score_lower_bound), mean - radius),
            upper=min(float(self.policy.score_upper_bound), mean + radius),
            mean=mean,
            radius=radius,
            sample_count=sample_count,
            raw_sample_count=evidence.visits,
            method=self.policy.bound_method,
        )

    def assess(
        self,
        candidate: ActionEvidence,
        incumbent: ActionEvidence,
    ) -> PruningDecision:
        if candidate.parent_state_id != incumbent.parent_state_id:
            raise ValueError("pruning comparison requires the same exact parent_state_id")
        if candidate.action_id == incumbent.action_id:
            raise ValueError("candidate and incumbent action_id must differ")
        expected_dataset_id = self.data_identity.dataset_id
        mismatches = [
            role
            for role, evidence in (("candidate", candidate), ("incumbent", incumbent))
            if evidence.dataset_id != expected_dataset_id
        ]
        candidate_interval: ScoreInterval | None = None
        incumbent_interval: ScoreInterval | None = None
        if mismatches:
            disposition = PruningDisposition.INVALIDATE
            reason = PruningReason.DATA_IDENTITY_MISMATCH
            detail: Mapping[str, Any] = {
                "expected_dataset_id": expected_dataset_id,
                "mismatched_evidence": mismatches,
                "required_action": "discard_and_resample",
            }
        elif self.policy.bound_method == PRUNING_BOUND_METHOD and (
            candidate.independent_unit_count is None
            or incumbent.independent_unit_count is None
        ):
            disposition = PruningDisposition.KEEP
            reason = PruningReason.INDEPENDENCE_UNVERIFIED
            detail = {
                "bound_method": self.policy.bound_method,
                "candidate_independent_unit_count": (
                    candidate.independent_unit_count
                ),
                "incumbent_independent_unit_count": (
                    incumbent.independent_unit_count
                ),
                "required_action": (
                    "identify_independently_seeded_sampling_units_or_keep"
                ),
            }
        else:
            candidate_sample_count = (
                candidate.independent_unit_count
                if self.policy.bound_method == PRUNING_BOUND_METHOD
                else candidate.visits
            )
            incumbent_sample_count = (
                incumbent.independent_unit_count
                if self.policy.bound_method == PRUNING_BOUND_METHOD
                else incumbent.visits
            )
            assert candidate_sample_count is not None
            assert incumbent_sample_count is not None
            decision_values = self._assess_sampled_evidence(
                candidate,
                incumbent,
                candidate_sample_count=candidate_sample_count,
                incumbent_sample_count=incumbent_sample_count,
            )
            (
                disposition,
                reason,
                candidate_interval,
                incumbent_interval,
                detail,
            ) = decision_values
        decision = PruningDecision(
            disposition=disposition,
            reason=reason,
            candidate=candidate.to_summary(),
            incumbent=incumbent.to_summary(),
            candidate_interval=candidate_interval,
            incumbent_interval=incumbent_interval,
            detail=detail,
        )
        self._record(decision.to_dict())
        return decision

    def _assess_sampled_evidence(
        self,
        candidate: ActionEvidence,
        incumbent: ActionEvidence,
        *,
        candidate_sample_count: int,
        incumbent_sample_count: int,
    ) -> tuple[
        PruningDisposition,
        PruningReason,
        ScoreInterval | None,
        ScoreInterval | None,
        Mapping[str, Any],
    ]:
        candidate_interval: ScoreInterval | None = None
        incumbent_interval: ScoreInterval | None = None
        sample_count_name = (
            "independent_unit_count"
            if self.policy.bound_method == PRUNING_BOUND_METHOD
            else "raw_score_count"
        )
        if candidate_sample_count < self.policy.minimum_action_visits:
            disposition = PruningDisposition.KEEP
            reason = PruningReason.MANDATORY_MINIMUM_VISITS
            detail = {
                "minimum_action_visits": self.policy.minimum_action_visits,
                "remaining_visits": (
                    self.policy.minimum_action_visits - candidate_sample_count
                ),
                "sample_count_kind": sample_count_name,
            }
        elif incumbent_sample_count < self.policy.minimum_action_visits:
            disposition = PruningDisposition.KEEP
            reason = PruningReason.INCUMBENT_UNDER_SAMPLED
            detail = {
                "minimum_action_visits": self.policy.minimum_action_visits,
                "remaining_visits": (
                    self.policy.minimum_action_visits - incumbent_sample_count
                ),
                "sample_count_kind": sample_count_name,
            }
        else:
            candidate_interval = self._interval(candidate)
            incumbent_interval = self._interval(incumbent)
            dominated = (
                candidate_interval.upper + self.policy.prune_margin
                < incumbent_interval.lower
            )
            if dominated:
                disposition = PruningDisposition.PRUNE
                reason = PruningReason.OPTIMISTIC_BOUND_DOMINATED
            else:
                disposition = PruningDisposition.KEEP
                reason = PruningReason.CONFIDENCE_OVERLAP
            detail = {
                "bound_method_status": (
                    "deprecated_iid_compatibility"
                    if self.policy.bound_method == LEGACY_PRUNING_BOUND_METHOD
                    else "correlation_guarded"
                ),
                "candidate_optimistic_upper_bound": candidate_interval.upper,
                "incumbent_pessimistic_lower_bound": incumbent_interval.lower,
                "prune_margin": self.policy.prune_margin,
            }
        return (
            disposition,
            reason,
            candidate_interval,
            incumbent_interval,
            detail,
        )

    def export_audit_log(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "dataset_id": self.data_identity.dataset_id,
                "policy_id": self.policy.to_dict()["policy_id"],
                "records": self._records,
                "schema_version": PRUNING_AUDIT_SCHEMA_VERSION,
            }
        )
        return {**identity, "audit_id": stable_digest(identity, prefix="pruneaudit_")}
