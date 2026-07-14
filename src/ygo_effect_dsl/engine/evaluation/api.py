from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any, Protocol, runtime_checkable

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation.scoring import ScoreBreakdown


EVALUATION_RESULT_SCHEMA_VERSION = "evaluation-result-v1"


def _finite_number(value: Any, path: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{path} must be a finite number")
    return value


@dataclass(frozen=True)
class EvaluationInput:
    state_hash: str
    board_summary: Mapping[str, Any]
    turn: int
    phase: str
    information_mode: str

    def __post_init__(self) -> None:
        for name in ("state_hash", "phase", "information_mode"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.board_summary, Mapping):
            raise ValueError("board_summary must be a mapping")
        if not isinstance(self.turn, int) or isinstance(self.turn, bool) or self.turn < 1:
            raise ValueError("turn must be an integer >= 1")


@dataclass(frozen=True)
class EvaluatorSpec:
    evaluator_id: str
    version: str
    config: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in ("evaluator_id", "version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.config, Mapping):
            raise ValueError("evaluator config must be a mapping")

    @property
    def config_hash(self) -> str:
        return stable_digest(
            {
                "config": self.config,
                "evaluator_id": self.evaluator_id,
                "version": self.version,
            },
            prefix="evalcfg_",
        )

    @classmethod
    def from_mapping(cls, value: Any) -> "EvaluatorSpec":
        if not isinstance(value, Mapping):
            raise ValueError("experiment.evaluator must be a mapping")
        return cls(
            evaluator_id=value.get("id"),
            version=value.get("version"),
            config=value.get("config", {}),
        )


@dataclass(frozen=True)
class EvaluationContext:
    experiment_id: str
    evaluate_at: str
    evaluator_config: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in ("experiment_id", "evaluate_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.evaluator_config, Mapping):
            raise ValueError("evaluator_config must be a mapping")


@dataclass(frozen=True)
class EvaluationOutput:
    vector: Mapping[str, int | float]
    score_breakdown: ScoreBreakdown
    explanations: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.vector, Mapping) or not self.vector:
            raise ValueError("evaluation vector must be a non-empty mapping")
        for name, value in self.vector.items():
            if not isinstance(name, str) or not name:
                raise ValueError("evaluation vector keys must be non-empty strings")
            _finite_number(value, f"evaluation vector {name!r}")
        if not isinstance(self.score_breakdown, ScoreBreakdown):
            raise ValueError("score_breakdown must be a ScoreBreakdown")
        resolved_vector = {
            term.metric: term.resolved_value for term in self.score_breakdown.terms
        }
        if to_canonical_data(self.vector) != to_canonical_data(resolved_vector):
            raise ValueError(
                "evaluation vector must match score breakdown resolved values"
            )
        if not isinstance(self.explanations, tuple) or any(
            not isinstance(item, Mapping) for item in self.explanations
        ):
            raise ValueError("explanations must be a tuple of mappings")

    @property
    def total_score(self) -> int | float:
        return self.score_breakdown.total_score


@dataclass(frozen=True)
class EvaluationResult:
    evaluator_id: str
    evaluator_version: str
    evaluator_config_hash: str
    vector: Mapping[str, int | float]
    score_breakdown: ScoreBreakdown
    explanations: tuple[Mapping[str, Any], ...] = ()
    schema_version: str = EVALUATION_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EVALUATION_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported evaluation result schema")
        EvaluationOutput(self.vector, self.score_breakdown, self.explanations)
        for name in (
            "evaluator_id",
            "evaluator_version",
            "evaluator_config_hash",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "evaluator_config_hash": self.evaluator_config_hash,
                "evaluator_id": self.evaluator_id,
                "evaluator_version": self.evaluator_version,
                "explanations": list(self.explanations),
                "schema_version": self.schema_version,
                "score_breakdown": self.score_breakdown.to_dict(),
                "total_score": self.total_score,
                "vector": self.vector,
            }
        )

    @classmethod
    def from_dict(cls, value: Any) -> "EvaluationResult":
        if not isinstance(value, Mapping):
            raise ValueError("evaluation result must be a mapping")
        raw_explanations = value.get("explanations")
        if not isinstance(raw_explanations, list) or any(
            not isinstance(item, Mapping) for item in raw_explanations
        ):
            raise ValueError("evaluation result explanations must be a list of mappings")
        result = cls(
            evaluator_id=value.get("evaluator_id"),
            evaluator_version=value.get("evaluator_version"),
            evaluator_config_hash=value.get("evaluator_config_hash"),
            vector=value.get("vector"),
            score_breakdown=ScoreBreakdown.from_dict(value.get("score_breakdown")),
            explanations=tuple(raw_explanations),
            schema_version=value.get("schema_version"),
        )
        if result.to_dict() != to_canonical_data(value):
            raise ValueError("evaluation result does not match its score breakdown")
        return result

    @property
    def total_score(self) -> int | float:
        return self.score_breakdown.total_score


@runtime_checkable
class Evaluator(Protocol):
    evaluator_id: str
    version: str

    def evaluate(
        self,
        state: EvaluationInput,
        context: EvaluationContext,
    ) -> EvaluationOutput: ...


class EvaluatorRegistry:
    def __init__(self) -> None:
        self._evaluators: dict[tuple[str, str], Evaluator] = {}

    def register(self, evaluator: Evaluator) -> None:
        if not isinstance(evaluator, Evaluator):
            raise ValueError("evaluator must implement the Evaluator protocol")
        key = (evaluator.evaluator_id, evaluator.version)
        if key in self._evaluators:
            raise ValueError(f"evaluator {key[0]!r} version {key[1]!r} is registered")
        self._evaluators[key] = evaluator

    def resolve(self, evaluator_id: str, version: str) -> Evaluator:
        try:
            return self._evaluators[(evaluator_id, version)]
        except KeyError as exc:
            raise ValueError(
                f"unknown evaluator {evaluator_id!r} version {version!r}"
            ) from exc

    def evaluate(
        self,
        spec: EvaluatorSpec,
        state: EvaluationInput,
        context: EvaluationContext,
    ) -> EvaluationResult:
        if to_canonical_data(context.evaluator_config) != to_canonical_data(spec.config):
            raise ValueError("evaluation context config does not match evaluator spec")
        evaluator = self.resolve(spec.evaluator_id, spec.version)
        output = evaluator.evaluate(state, context)
        if not isinstance(output, EvaluationOutput):
            raise ValueError("evaluator must return EvaluationOutput")
        return EvaluationResult(
            evaluator_id=spec.evaluator_id,
            evaluator_version=spec.version,
            evaluator_config_hash=spec.config_hash,
            vector=output.vector,
            score_breakdown=output.score_breakdown,
            explanations=output.explanations,
        )

    def evaluate_experiment(
        self,
        experiment: Mapping[str, Any],
        state: EvaluationInput,
    ) -> EvaluationResult:
        if not isinstance(experiment, Mapping):
            raise ValueError("experiment must be a mapping")
        spec = EvaluatorSpec.from_mapping(experiment.get("evaluator"))
        information_mode = experiment.get("information_mode")
        if information_mode != state.information_mode:
            raise ValueError("experiment information_mode does not match evaluation input")
        context = EvaluationContext(
            experiment_id=experiment.get("experiment_id"),
            evaluate_at=experiment.get("evaluate_at"),
            evaluator_config=spec.config,
        )
        return self.evaluate(spec, state, context)
