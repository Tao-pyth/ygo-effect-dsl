from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.state import (
    ConstraintExpiration,
    ExpirationBoundary,
    StateCoordinate,
)


TEMPORARY_EFFECT_REPORT_SCHEMA_VERSION = "temporary-effect-evaluation-v1"


class ValuePermanence(str, Enum):
    PERSISTENT = "persistent"
    TEMPORARY = "temporary"


class BoundaryEvidence(str, Enum):
    OBSERVED_ACTIVE = "observed_active"
    OBSERVED_EXPIRED = "observed_expired"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class EvaluationValueComponent:
    component_id: str
    metric: str
    value: int | float
    permanence: ValuePermanence
    boundary_evidence: BoundaryEvidence = BoundaryEvidence.OBSERVED_ACTIVE
    expires_at: ConstraintExpiration | None = None
    source_ref: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.permanence, ValuePermanence):
            object.__setattr__(self, "permanence", ValuePermanence(self.permanence))
        if not isinstance(self.boundary_evidence, BoundaryEvidence):
            object.__setattr__(
                self,
                "boundary_evidence",
                BoundaryEvidence(self.boundary_evidence),
            )
        for name in ("component_id", "metric"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if (
            not isinstance(self.value, (int, float))
            or isinstance(self.value, bool)
            or not math.isfinite(self.value)
        ):
            raise ValueError("value must be a finite number")
        if self.source_ref is not None and not isinstance(self.source_ref, Mapping):
            raise ValueError("source_ref must be a mapping or None")
        if self.permanence == ValuePermanence.PERSISTENT:
            if self.expires_at is not None:
                raise ValueError("persistent value cannot have expires_at")
            if self.boundary_evidence != BoundaryEvidence.OBSERVED_ACTIVE:
                raise ValueError("persistent value must be observed_active")
        elif not isinstance(self.expires_at, ConstraintExpiration):
            raise ValueError("temporary value requires expires_at")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "boundary_evidence": self.boundary_evidence.value,
                "component_id": self.component_id,
                "expires_at": (
                    self.expires_at.to_dict() if self.expires_at is not None else None
                ),
                "metric": self.metric,
                "permanence": self.permanence.value,
                "source_ref": self.source_ref,
                "value": self.value,
            }
        )


def _inclusion(component: EvaluationValueComponent) -> tuple[bool, str | None]:
    if component.permanence == ValuePermanence.PERSISTENT:
        return True, None
    if component.boundary_evidence == BoundaryEvidence.OBSERVED_ACTIVE:
        return True, None
    if component.boundary_evidence == BoundaryEvidence.OBSERVED_EXPIRED:
        return False, "expired_before_evaluation_boundary"
    return False, "unverified_at_evaluation_boundary"


def build_temporary_effect_report(
    components: Sequence[EvaluationValueComponent],
    *,
    evaluation_boundary: StateCoordinate,
) -> dict[str, Any]:
    if not isinstance(evaluation_boundary, StateCoordinate):
        raise ValueError("evaluation_boundary must be a StateCoordinate")
    ordered = tuple(sorted(components, key=lambda item: item.component_id))
    if len({item.component_id for item in ordered}) != len(ordered):
        raise ValueError("component_id must be unique")
    values: dict[str, dict[str, int | float]] = {}
    component_payloads: list[dict[str, Any]] = []
    explanations: list[dict[str, Any]] = []
    excluded_ids: list[str] = []
    unverified_ids: list[str] = []
    for component in ordered:
        included, reason = _inclusion(component)
        metric_values = values.setdefault(
            component.metric,
            {"durable": 0, "excluded_temporary": 0, "raw": 0},
        )
        metric_values["raw"] += component.value
        if included:
            metric_values["durable"] += component.value
        else:
            metric_values["excluded_temporary"] += component.value
            excluded_ids.append(component.component_id)
            if component.boundary_evidence == BoundaryEvidence.UNVERIFIED:
                unverified_ids.append(component.component_id)
            explanations.append(
                {
                    "code": reason,
                    "component_id": component.component_id,
                    "message": (
                        "Temporary value was excluded from durable evaluation "
                        f"because it was {reason.replace('_', ' ')}."
                    ),
                    "metric": component.metric,
                    "value": component.value,
                }
            )
        component_payloads.append(
            {
                **component.to_dict(),
                "exclusion_reason": reason,
                "included_in_durable_value": included,
            }
        )
    prevented_metrics = sorted(
        metric
        for metric, totals in values.items()
        if totals["excluded_temporary"] > 0
    )
    identity = to_canonical_data(
        {
            "components": component_payloads,
            "evaluation_boundary": evaluation_boundary.to_dict(),
            "explanations": explanations,
            "overvaluation_prevention": {
                "applied": bool(excluded_ids),
                "excluded_component_ids": excluded_ids,
                "metrics_with_prevented_overvaluation": prevented_metrics,
                "unverified_component_ids": unverified_ids,
            },
            "schema_version": TEMPORARY_EFFECT_REPORT_SCHEMA_VERSION,
            "values": values,
        }
    )
    return {
        **identity,
        "report_id": stable_digest(identity, prefix="teval_"),
    }


def _expiration_from_dict(value: Any) -> ConstraintExpiration | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("expires_at must be a mapping or None")
    return ConstraintExpiration(
        boundary=ExpirationBoundary(str(value.get("boundary"))),
        turn=value.get("turn"),
        phase=value.get("phase"),
        chain_index=value.get("chain_index"),
        turn_action_index=value.get("turn_action_index"),
    )


def assert_valid_temporary_effect_report(report: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping):
        raise ValueError("temporary effect report must be a mapping")
    if report.get("schema_version") != TEMPORARY_EFFECT_REPORT_SCHEMA_VERSION:
        raise ValueError("unsupported temporary effect report schema")
    boundary = report.get("evaluation_boundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("evaluation_boundary must be a mapping")
    coordinate = StateCoordinate(
        turn=boundary.get("turn"),
        phase=boundary.get("phase"),
        chain_index=boundary.get("chain_index", 0),
        turn_action_index=boundary.get("turn_action_index", 0),
    )
    raw_components = report.get("components")
    if not isinstance(raw_components, list):
        raise ValueError("components must be a list")
    components: list[EvaluationValueComponent] = []
    for raw_component in raw_components:
        if not isinstance(raw_component, Mapping):
            raise ValueError("components entries must be mappings")
        components.append(
            EvaluationValueComponent(
                component_id=raw_component.get("component_id"),
                metric=raw_component.get("metric"),
                value=raw_component.get("value"),
                permanence=ValuePermanence(str(raw_component.get("permanence"))),
                boundary_evidence=BoundaryEvidence(
                    str(raw_component.get("boundary_evidence"))
                ),
                expires_at=_expiration_from_dict(raw_component.get("expires_at")),
                source_ref=raw_component.get("source_ref"),
            )
        )
    expected = build_temporary_effect_report(
        components,
        evaluation_boundary=coordinate,
    )
    if to_canonical_data(report) != expected:
        raise ValueError("temporary effect report does not match its components")
