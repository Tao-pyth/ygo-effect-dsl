from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
import math
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation import (
    RESOURCE_CONSUMPTION_METRIC,
    EvaluatorSpec,
    build_route_resource_consumption,
)
from ygo_effect_dsl.route_dsl.validator import assert_valid_route_document


ROUTE_NORMALIZATION_SCHEMA_VERSION = "route-normalization-v2"


class RouteTargetBoard(str, Enum):
    PEAK = "peak_board"
    TERMINAL = "terminal_board"


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _finite_number(value: Any, path: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{path} must be a finite number")
    return value


@dataclass(frozen=True)
class _RouteStep:
    key: str
    label: str
    atomic_steps: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "atomic_steps": list(self.atomic_steps),
            "key": self.key,
            "label": self.label,
        }


@dataclass(frozen=True)
class _RouteSummary:
    route_id: str
    target_state_id: str
    score: int | float
    success: bool
    action_count: int
    evaluation_context_id: str
    atomic_steps: tuple[_RouteStep, ...]
    composite_steps: tuple[_RouteStep, ...] | None
    resource_cost: int | float | None
    resource_report_id: str | None

    def steps(self, basis: str) -> tuple[_RouteStep, ...]:
        if basis == "composite_action":
            if self.composite_steps is None:
                raise ValueError("composite action comparison requires all presentations")
            return self.composite_steps
        return self.atomic_steps

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "action_count": self.action_count,
                "evaluation_context_id": self.evaluation_context_id,
                "resource_cost": self.resource_cost,
                "resource_report_id": self.resource_report_id,
                "route_id": self.route_id,
                "score": self.score,
                "success": self.success,
                "target_state_id": self.target_state_id,
            }
        )


def _evaluation_context_id(document: Mapping[str, Any]) -> str:
    experiment = _mapping(document.get("experiment"), "route.experiment")
    spec = EvaluatorSpec.from_mapping(experiment.get("evaluator"))
    identity = {
        "evaluate_at": experiment.get("evaluate_at"),
        "evaluator_config_hash": spec.config_hash,
        "evaluator_id": spec.evaluator_id,
        "evaluator_version": spec.version,
        "information_mode": experiment.get("information_mode"),
    }
    return stable_digest(identity, prefix="routeevalctx_")


def _atomic_route_steps(document: Mapping[str, Any]) -> tuple[_RouteStep, ...]:
    replay = _mapping(document.get("replay"), "route.replay")
    events = replay.get("events")
    if not isinstance(events, list):
        raise ValueError("route.replay.events must be a list")
    steps: list[_RouteStep] = []
    for index, raw_event in enumerate(events):
        event = _mapping(raw_event, f"route.replay.events[{index}]")
        action = _mapping(event.get("action"), f"route.replay.events[{index}].action")
        steps.append(
            _RouteStep(
                key=_non_empty_string(
                    action.get("action_id"),
                    f"route.replay.events[{index}].action.action_id",
                ),
                label=_non_empty_string(
                    action.get("kind"),
                    f"route.replay.events[{index}].action.kind",
                ),
                atomic_steps=(index,),
            )
        )
    return tuple(steps)


def _composite_route_steps(
    document: Mapping[str, Any],
) -> tuple[_RouteStep, ...] | None:
    presentation = document.get("presentation")
    if not isinstance(presentation, Mapping):
        return None
    aggregation = presentation.get("action_aggregation")
    if not isinstance(aggregation, Mapping):
        return None
    groups = aggregation.get("groups")
    if not isinstance(groups, list):
        return None
    steps: list[_RouteStep] = []
    for index, raw_group in enumerate(groups):
        group = _mapping(raw_group, f"route.presentation.action_aggregation.groups[{index}]")
        raw_atomic_steps = group.get("atomic_steps")
        if not isinstance(raw_atomic_steps, list) or any(
            not isinstance(step, int) or isinstance(step, bool) or step < 0
            for step in raw_atomic_steps
        ):
            raise ValueError(f"action aggregation group {index} has invalid atomic_steps")
        steps.append(
            _RouteStep(
                key=_non_empty_string(
                    group.get("comparison_key"),
                    f"action aggregation group {index}.comparison_key",
                ),
                label=_non_empty_string(
                    group.get("primary_kind"),
                    f"action aggregation group {index}.primary_kind",
                ),
                atomic_steps=tuple(raw_atomic_steps),
            )
        )
    return tuple(steps)


def _extract_summary(
    document: Mapping[str, Any],
    *,
    target_board: RouteTargetBoard,
    resource_cost: int | float | None,
    resource_report_id: str | None,
) -> _RouteSummary:
    assert_valid_route_document(document)
    route_id = _non_empty_string(document.get("route_id"), "route.route_id")
    result = _mapping(document.get("result"), "route.result")
    board = _mapping(result.get(target_board.value), f"route.result.{target_board.value}")
    if resource_cost is not None:
        resource_cost = _finite_number(resource_cost, f"resource_costs.{route_id}")
        if resource_cost < 0:
            raise ValueError(f"resource_costs.{route_id} must be non-negative")
    atomic_steps = _atomic_route_steps(document)
    return _RouteSummary(
        route_id=route_id,
        target_state_id=_non_empty_string(
            board.get("state_hash"), f"route.result.{target_board.value}.state_hash"
        ),
        score=_finite_number(
            board.get("score"), f"route.result.{target_board.value}.score"
        ),
        success=bool(result.get("success")),
        action_count=len(atomic_steps),
        evaluation_context_id=_evaluation_context_id(document),
        atomic_steps=atomic_steps,
        composite_steps=_composite_route_steps(document),
        resource_cost=resource_cost,
        resource_report_id=resource_report_id,
    )


def _minimum_ranking(
    summaries: Sequence[_RouteSummary],
    *,
    field: str,
    metric: str,
    missing_reason: str | None = None,
) -> dict[str, Any]:
    values = [(summary, getattr(summary, field)) for summary in summaries]
    missing = sorted(summary.route_id for summary, value in values if value is None)
    if missing:
        result = {
            "metric": metric,
            "missing_route_ids": missing,
            "status": "unavailable_missing_measurement",
        }
        if missing_reason is not None:
            result["reason"] = missing_reason
        return result
    minimum = min(value for _, value in values)
    winners = sorted(summary.route_id for summary, value in values if value == minimum)
    return {
        "metric": metric,
        "route_ids": winners,
        "selection_rule": "minimum",
        "status": "available",
        "value": minimum,
    }


def _highest_score_ranking(
    summaries: Sequence[_RouteSummary],
) -> dict[str, Any]:
    contexts = sorted({summary.evaluation_context_id for summary in summaries})
    if len(contexts) != 1:
        return {
            "evaluation_context_ids": contexts,
            "metric": "score",
            "status": "unavailable_incomparable_evaluation_contexts",
        }
    maximum = max(summary.score for summary in summaries)
    winners = sorted(
        summary.route_id for summary in summaries if summary.score == maximum
    )
    return {
        "evaluation_context_id": contexts[0],
        "metric": "score",
        "route_ids": winners,
        "selection_rule": "maximum",
        "status": "available",
        "value": maximum,
    }


def _diff_steps(
    base: _RouteSummary,
    alternative: _RouteSummary,
    *,
    basis: str,
) -> list[dict[str, Any]]:
    base_steps = base.steps(basis)
    alternative_steps = alternative.steps(basis)
    matcher = SequenceMatcher(
        a=[step.key for step in base_steps],
        b=[step.key for step in alternative_steps],
        autojunk=False,
    )
    differences: list[dict[str, Any]] = []
    for tag, base_start, base_end, alternative_start, alternative_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        identity = to_canonical_data(
            {
                "alternative_route_id": alternative.route_id,
                "alternative_span": [alternative_start, alternative_end],
                "base_route_id": base.route_id,
                "base_span": [base_start, base_end],
                "comparison_basis": basis,
                "operation": tag,
                "target_state_id": base.target_state_id,
            }
        )
        differences.append(
            {
                **identity,
                "alternative_actions": [
                    step.to_dict()
                    for step in alternative_steps[alternative_start:alternative_end]
                ],
                "base_actions": [
                    step.to_dict() for step in base_steps[base_start:base_end]
                ],
                "branch_id": stable_digest(identity, prefix="routebranch_"),
                "reconvergence": {
                    "kind": "exact_target_state",
                    "state_id": base.target_state_id,
                },
            }
        )
    return differences


def _assert_consistent_scores(summaries: Sequence[_RouteSummary]) -> None:
    scores_by_context: dict[str, set[int | float]] = {}
    for summary in summaries:
        scores_by_context.setdefault(summary.evaluation_context_id, set()).add(
            summary.score
        )
    inconsistent = {
        context: sorted(scores)
        for context, scores in scores_by_context.items()
        if len(scores) > 1
    }
    if inconsistent:
        raise ValueError(
            "same exact target State and evaluation context must have the same score: "
            f"{inconsistent}"
        )


def _group_report(
    summaries: Sequence[_RouteSummary],
    *,
    target_board: RouteTargetBoard,
    resource_metric: str,
    resource_missing_reason: str,
) -> dict[str, Any]:
    ordered = sorted(summaries, key=lambda summary: summary.route_id)
    _assert_consistent_scores(ordered)
    target_state_id = ordered[0].target_state_id
    basis = (
        "composite_action"
        if all(summary.composite_steps is not None for summary in ordered)
        else "atomic_action"
    )
    representative = min(
        ordered,
        key=lambda summary: (
            summary.action_count,
            summary.resource_cost is None,
            summary.resource_cost if summary.resource_cost is not None else math.inf,
            summary.route_id,
        ),
    )
    alternatives: list[dict[str, Any]] = []
    branch_points: list[dict[str, Any]] = []
    for summary in ordered:
        if summary.route_id == representative.route_id:
            continue
        differences = _diff_steps(representative, summary, basis=basis)
        branch_points.extend(differences)
        alternatives.append(
            {
                "action_count_delta": summary.action_count
                - representative.action_count,
                "compared_to_route_id": representative.route_id,
                "differences": differences,
                "resource_cost_delta": (
                    summary.resource_cost - representative.resource_cost
                    if summary.resource_cost is not None
                    and representative.resource_cost is not None
                    else None
                ),
                "route_id": summary.route_id,
                "score_comparable": (
                    summary.evaluation_context_id
                    == representative.evaluation_context_id
                ),
                "score_delta": (
                    summary.score - representative.score
                    if summary.evaluation_context_id
                    == representative.evaluation_context_id
                    else None
                ),
            }
        )
    group_identity = {
        "merge_reason": "exact_target_state",
        "target_board": target_board.value,
        "target_state_id": target_state_id,
    }
    return to_canonical_data(
        {
            "alternatives": alternatives,
            "branch_points": branch_points,
            "comparison_basis": basis,
            "group_id": stable_digest(group_identity, prefix="routegroup_"),
            "merge_reason": "exact_target_state",
            "rankings": {
                "minimum_consumption": _minimum_ranking(
                    ordered,
                    field="resource_cost",
                    metric=resource_metric,
                    missing_reason=resource_missing_reason,
                ),
                "shortest": _minimum_ranking(
                    ordered, field="action_count", metric="atomic_action_count"
                ),
            },
            "representative_route_id": representative.route_id,
            "representative_selection_rule": (
                "minimum atomic action count, then measured resource cost, then route_id"
            ),
            "route_ids": [summary.route_id for summary in ordered],
            "routes": [summary.to_dict() for summary in ordered],
            "target_state_id": target_state_id,
        }
    )


def normalize_and_explain_routes(
    documents: Sequence[Mapping[str, Any]],
    *,
    target_board: RouteTargetBoard = RouteTargetBoard.PEAK,
    resource_costs: Mapping[str, int | float] | None = None,
    resource_metric: str | None = None,
) -> dict[str, Any]:
    if not isinstance(target_board, RouteTargetBoard):
        target_board = RouteTargetBoard(target_board)
    if not isinstance(documents, Sequence) or isinstance(documents, (str, bytes)):
        raise ValueError("documents must be a sequence of Route mappings")
    if not documents:
        raise ValueError("at least one Route document is required")
    external_resource_costs = resource_costs is not None
    if external_resource_costs and not isinstance(resource_costs, Mapping):
        raise ValueError("resource_costs must be a mapping")
    resolved_resource_costs = resource_costs or {}

    route_ids: list[str] = []
    for index, document in enumerate(documents):
        mapping = _mapping(document, f"documents[{index}]")
        assert_valid_route_document(mapping)
        route_ids.append(
            _non_empty_string(
                mapping.get("route_id"), f"documents[{index}].route_id"
            )
        )
    duplicates = sorted(
        route_id for route_id in set(route_ids) if route_ids.count(route_id) > 1
    )
    if duplicates:
        raise ValueError(f"route_id must be unique: {duplicates}")
    unknown_costs = sorted(set(resolved_resource_costs) - set(route_ids))
    if unknown_costs:
        raise ValueError(f"resource_costs reference unknown routes: {unknown_costs}")

    resource_reports: dict[str, dict[str, Any]] = {}
    if external_resource_costs:
        resolved_resource_metric = _non_empty_string(
            resource_metric or "resource_consumption_v0_external",
            "resource_metric",
        )
        resource_missing_reason = "external_resource_cost_not_supplied"
        measurement_mode = "external"
    else:
        if resource_metric not in (None, RESOURCE_CONSUMPTION_METRIC):
            raise ValueError(
                "resource_metric cannot override the built-in metric without "
                "external resource_costs"
            )
        resolved_resource_metric = RESOURCE_CONSUMPTION_METRIC
        resource_missing_reason = "route_lacks_recalculable_resource_inputs"
        measurement_mode = "recalculated_from_route"
        for index, document in enumerate(documents):
            mapping = _mapping(document, f"documents[{index}]")
            replay = _mapping(mapping.get("replay"), f"documents[{index}].replay")
            snapshot = _mapping(
                replay.get("initial_snapshot"),
                f"documents[{index}].replay.initial_snapshot",
            )
            if not isinstance(snapshot.get("zones"), list) or not isinstance(
                snapshot.get("field_state"), Mapping
            ):
                continue
            report = build_route_resource_consumption(
                mapping, target_board=target_board.value
            )
            resource_reports[route_ids[index]] = report
            resolved_resource_costs[route_ids[index]] = report["scalar"]["total"]

    summaries = tuple(
        _extract_summary(
            _mapping(document, f"documents[{index}]"),
            target_board=target_board,
            resource_cost=resolved_resource_costs.get(route_ids[index]),
            resource_report_id=(
                resource_reports[route_ids[index]]["resource_report_id"]
                if route_ids[index] in resource_reports
                else None
            ),
        )
        for index, document in enumerate(documents)
    )
    grouped: dict[str, list[_RouteSummary]] = {}
    for summary in summaries:
        grouped.setdefault(summary.target_state_id, []).append(summary)
    groups = [
        _group_report(
            grouped[state_id],
            target_board=target_board,
            resource_metric=resolved_resource_metric,
            resource_missing_reason=resource_missing_reason,
        )
        for state_id in sorted(grouped)
    ]
    identity = to_canonical_data(
        {
            "groups": groups,
            "rankings": {
                "highest_score": _highest_score_ranking(summaries),
                "minimum_consumption": _minimum_ranking(
                    summaries,
                    field="resource_cost",
                    metric=resolved_resource_metric,
                    missing_reason=resource_missing_reason,
                ),
                "shortest": _minimum_ranking(
                    summaries, field="action_count", metric="atomic_action_count"
                ),
            },
            "resource_measurement_mode": measurement_mode,
            "resource_metric": resolved_resource_metric,
            "resource_reports": resource_reports,
            "route_count": len(summaries),
            "schema_version": ROUTE_NORMALIZATION_SCHEMA_VERSION,
            "target_board": target_board.value,
        }
    )
    return {**identity, "report_id": stable_digest(identity, prefix="routenorm_")}
