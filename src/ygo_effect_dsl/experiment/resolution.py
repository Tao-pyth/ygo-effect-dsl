from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import to_canonical_data
from ygo_effect_dsl.engine.information import InformationAccessPolicy
from ygo_effect_dsl.engine.state import InformationMode
from ygo_effect_dsl.experiment.schema import (
    EXPERIMENT_SCHEMA_VERSION,
    LEGACY_EXPERIMENT_SCHEMA_VERSION,
    assert_current_experiment,
    assert_valid_experiment,
)


def resolve_experiment_overrides(
    experiment: Mapping[str, Any],
    *,
    max_nodes: int | None = None,
    max_seconds: float | None = None,
    evaluator_id: str | None = None,
    evaluator_version: str | None = None,
    interruption_mode: str | None = None,
) -> dict[str, Any]:
    resolved = deepcopy(dict(experiment))
    budget = resolved.setdefault("search", {}).setdefault("budget", {})
    if max_nodes is not None:
        budget["max_nodes"] = max_nodes
    if max_seconds is not None:
        budget["max_seconds"] = max_seconds
    evaluator = resolved.setdefault("evaluator", {})
    if evaluator_id is not None:
        evaluator["id"] = evaluator_id
    if evaluator_version is not None:
        evaluator["version"] = evaluator_version
    if interruption_mode is not None:
        resolved.setdefault("interruption", {})["mode"] = interruption_mode
    assert_current_experiment(resolved)
    return resolved


def migrate_experiment_v03a_to_v03b(
    experiment: Mapping[str, Any],
    *,
    deck_order: str,
    opening_hand: str,
    sampling_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Migrate only when every previously implicit policy dimension is supplied."""

    assert_valid_experiment(experiment)
    if experiment.get("schema_version") != LEGACY_EXPERIMENT_SCHEMA_VERSION:
        raise ValueError("migration source must be an Experiment 0.3a document")
    player = experiment.get("player")
    if not isinstance(player, Mapping):
        raise ValueError("Experiment player must be a mapping")
    mode = InformationMode(str(experiment.get("information_mode")))
    policy = InformationAccessPolicy(
        information_mode=mode,
        deck_order=deck_order,
        opening_hand=opening_hand,
        viewer=player.get("perspective") if mode == InformationMode.PLAYER_VIEW else None,
        sampling_reference=sampling_reference,
    )
    migrated = deepcopy(dict(experiment))
    migrated["schema_version"] = EXPERIMENT_SCHEMA_VERSION
    migrated["information_policy"] = policy.to_experiment_dict()
    assert_current_experiment(migrated)
    return migrated


def experiment_source_identity(experiment: Mapping[str, Any]) -> dict[str, Any]:
    identity = deepcopy(dict(experiment))
    identity.pop("prototype", None)
    return to_canonical_data(identity)


def assert_experiment_matches_route(
    experiment: Mapping[str, Any], route: Mapping[str, Any]
) -> None:
    route_experiment = route.get("experiment")
    if not isinstance(route_experiment, Mapping):
        raise ValueError("Route DSL is missing experiment")
    if experiment_source_identity(experiment) != experiment_source_identity(
        route_experiment
    ):
        raise ValueError("Experiment file does not match Route DSL experiment")
