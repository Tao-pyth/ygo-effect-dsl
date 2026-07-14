from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import stable_digest


@dataclass(frozen=True)
class PrototypeEvaluation:
    vector: dict[str, int]
    total_score: float
    success: bool
    config_hash: str

    @property
    def tie_vector(self) -> tuple[int, ...]:
        return tuple(self.vector.values())


class PrototypePathEvaluator:
    """Temporary list-count evaluator configured entirely by the scenario."""

    evaluator_id = "prototype-path-count"
    version = "0"

    def __init__(self, config: Mapping[str, Any], success_config: Mapping[str, Any]) -> None:
        self._config = dict(config)
        self._success_config = dict(success_config)
        self.config_hash = stable_digest(
            {"evaluator": self._config, "success": self._success_config},
            prefix="config_",
        )

    def evaluate(self, state: Mapping[str, Any]) -> PrototypeEvaluation:
        vector: dict[str, int] = {}
        total_score = 0.0
        metrics = self._config.get("metrics", [])
        if not isinstance(metrics, list) or not metrics:
            raise ValueError("experiment.evaluator.config.metrics must be a non-empty list")
        for index, raw_metric in enumerate(metrics):
            if not isinstance(raw_metric, Mapping):
                raise ValueError(f"experiment.evaluator.config.metrics[{index}] must be a mapping")
            name = str(raw_metric.get("name", ""))
            path = str(raw_metric.get("path", ""))
            if not name or not path:
                raise ValueError(f"experiment.evaluator.config.metrics[{index}] requires name and path")
            value = _count_value(_resolve_path(state, path))
            vector[name] = value
            total_score += value * float(raw_metric.get("weight", 1.0))

        success_path = str(self._success_config.get("path", ""))
        if not success_path:
            raise ValueError("experiment.success_predicate.config.path is required")
        success_count = _count_value(_resolve_path(state, success_path))
        success = success_count >= int(self._success_config.get("min_count", 1))
        return PrototypeEvaluation(
            vector=vector,
            total_score=total_score,
            success=success,
            config_hash=self.config_hash,
        )


def _resolve_path(root: Mapping[str, Any], dotted_path: str) -> Any:
    current: Any = root
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError(f"prototype evaluator path does not exist: {dotted_path}")
        current = current[part]
    return current


def _count_value(value: Any) -> int:
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    raise ValueError(f"prototype evaluator can only count collections, bools, or integers; got {type(value).__name__}")
