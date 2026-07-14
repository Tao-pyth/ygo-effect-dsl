from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.state import ConstraintExpiration, ExpirationBoundary


TEMPORARY_MODIFIER_OBSERVATION_SCHEMA_VERSION = (
    "ocgcore-temporary-modifier-observation-v1"
)


def build_temporary_modifier_observation(
    *,
    component_id: str,
    modifier_kind: str,
    metric: str,
    baseline: Mapping[str, Any],
    active: Mapping[str, Any],
    expired: Mapping[str, Any],
    expiration: ConstraintExpiration,
    source_ref: Mapping[str, Any],
) -> dict[str, Any]:
    for name, value in (
        ("component_id", component_id),
        ("modifier_kind", modifier_kind),
        ("metric", metric),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
    for name, point in (
        ("baseline", baseline),
        ("active", active),
        ("expired", expired),
    ):
        if not isinstance(point, Mapping):
            raise ValueError(f"{name} must be a mapping")
        value = point.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{name}.value must be numeric")
        if not isinstance(point.get("state_hash"), str):
            raise ValueError(f"{name}.state_hash must be a string")
    if not isinstance(expiration, ConstraintExpiration):
        raise ValueError("expiration must be ConstraintExpiration")
    if not isinstance(source_ref, Mapping):
        raise ValueError("source_ref must be a mapping")
    baseline_value = baseline["value"]
    active_value = active["value"]
    expired_value = expired["value"]
    activated = active_value != baseline_value
    returned_to_baseline = expired_value == baseline_value
    observation_status = (
        "observed_expired"
        if activated and returned_to_baseline
        else "unverified"
    )
    identity = to_canonical_data(
        {
            "boundary_evidence": observation_status,
            "component_id": component_id,
            "expiration": expiration.to_dict(),
            "metric": metric,
            "modifier_kind": modifier_kind,
            "points": {
                "active": active,
                "baseline": baseline,
                "expired": expired,
            },
            "schema_version": TEMPORARY_MODIFIER_OBSERVATION_SCHEMA_VERSION,
            "source_ref": source_ref,
            "transition": {
                "activated": activated,
                "active_delta": active_value - baseline_value,
                "expired_delta": expired_value - baseline_value,
                "returned_to_baseline": returned_to_baseline,
            },
        }
    )
    return {
        **identity,
        "observation_id": stable_digest(identity, prefix="tempobs_"),
    }


def assert_valid_temporary_modifier_observation(
    observation: Mapping[str, Any],
) -> None:
    if not isinstance(observation, Mapping):
        raise ValueError("temporary modifier observation must be a mapping")
    expiration = observation.get("expiration")
    if not isinstance(expiration, Mapping):
        raise ValueError("temporary modifier expiration must be a mapping")
    points = observation.get("points")
    if not isinstance(points, Mapping):
        raise ValueError("temporary modifier points must be a mapping")
    expected = build_temporary_modifier_observation(
        component_id=observation.get("component_id"),
        modifier_kind=observation.get("modifier_kind"),
        metric=observation.get("metric"),
        baseline=points.get("baseline"),
        active=points.get("active"),
        expired=points.get("expired"),
        expiration=ConstraintExpiration(
            boundary=ExpirationBoundary(str(expiration.get("boundary"))),
            turn=expiration.get("turn"),
            phase=expiration.get("phase"),
            chain_index=expiration.get("chain_index"),
            turn_action_index=expiration.get("turn_action_index"),
        ),
        source_ref=observation.get("source_ref"),
    )
    if to_canonical_data(observation) != expected:
        raise ValueError("temporary modifier observation does not match its points")
