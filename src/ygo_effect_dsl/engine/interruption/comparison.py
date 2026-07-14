from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation import (
    EvaluationResult,
    EvaluatorSpec,
    compare_score_breakdowns,
)
from ygo_effect_dsl.engine.interruption.target import (
    InterruptionTarget,
    resolve_interruption_target,
)
from ygo_effect_dsl.route_dsl.analysis import RouteTargetBoard
from ygo_effect_dsl.route_dsl.validator import assert_valid_route_document


INTERRUPTION_COMPARISON_SCHEMA_VERSION = "interruption-comparison-v1"


class RecoveryStatus(str, Enum):
    ORIGINAL_TARGET_REACHED = "original_target_reached"
    ORIGINAL_ROUTE_REJOINED = "original_route_rejoined"
    GOAL_ONLY = "goal_only"
    NOT_RECOVERED = "not_recovered"
    GOAL_INCOMPARABLE = "goal_incomparable"


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _number(value: Any, path: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{path} must be a finite number")
    return value


@dataclass(frozen=True)
class _BoardView:
    state_id: str
    score: int | float
    evaluation: Mapping[str, Any]
    board_summary: Mapping[str, Any]
    evaluation_result: EvaluationResult | None


def _events(route: Mapping[str, Any], path: str) -> list[Mapping[str, Any]]:
    replay = _mapping(route.get("replay"), f"{path}.replay")
    raw_events = replay.get("events")
    if not isinstance(raw_events, list):
        raise ValueError(f"{path}.replay.events must be a list")
    return [_mapping(event, f"{path}.replay.events[{index}]") for index, event in enumerate(raw_events)]


def _board_view(
    route: Mapping[str, Any],
    target_board: RouteTargetBoard,
    path: str,
) -> _BoardView:
    result = _mapping(route.get("result"), f"{path}.result")
    board = _mapping(result.get(target_board.value), f"{path}.result.{target_board.value}")
    checkpoint_step = board.get("checkpoint_step")
    if not isinstance(checkpoint_step, int) or isinstance(checkpoint_step, bool):
        raise ValueError(f"{path}.result.{target_board.value}.checkpoint_step must be an integer")
    checkpoints = route.get("checkpoints")
    if not isinstance(checkpoints, list):
        raise ValueError(f"{path}.checkpoints must be a list")
    checkpoint = next(
        (
            _mapping(item, f"{path}.checkpoints")
            for item in checkpoints
            if isinstance(item, Mapping) and item.get("step") == checkpoint_step
        ),
        None,
    )
    if checkpoint is None:
        raise ValueError(f"{path} target board checkpoint was not found")
    raw_evaluation_result = board.get("evaluation_result")
    evaluation_result = (
        EvaluationResult.from_dict(raw_evaluation_result)
        if raw_evaluation_result is not None
        else None
    )
    return _BoardView(
        state_id=_string(board.get("state_hash"), f"{path}.result.{target_board.value}.state_hash"),
        score=_number(board.get("score"), f"{path}.result.{target_board.value}.score"),
        evaluation=_mapping(board.get("evaluation"), f"{path}.result.{target_board.value}.evaluation"),
        board_summary=_mapping(checkpoint.get("board_summary"), f"{path}.checkpoint.board_summary"),
        evaluation_result=evaluation_result,
    )


def _evaluator_context_id(route: Mapping[str, Any]) -> str:
    experiment = _mapping(route.get("experiment"), "route.experiment")
    spec = EvaluatorSpec.from_mapping(experiment.get("evaluator"))
    return stable_digest(
        {
            "evaluate_at": experiment.get("evaluate_at"),
            "evaluator_config_hash": spec.config_hash,
            "evaluator_id": spec.evaluator_id,
            "evaluator_version": spec.version,
            "information_mode": experiment.get("information_mode"),
        },
        prefix="intevalctx_",
    )


def _assert_evaluation_result_context(
    route: Mapping[str, Any], view: _BoardView, path: str
) -> None:
    if view.evaluation_result is None:
        return
    experiment = _mapping(route.get("experiment"), f"{path}.experiment")
    spec = EvaluatorSpec.from_mapping(experiment.get("evaluator"))
    result = view.evaluation_result
    if (
        result.evaluator_id != spec.evaluator_id
        or result.evaluator_version != spec.version
        or result.evaluator_config_hash != spec.config_hash
    ):
        raise ValueError(
            f"{path} evaluation_result evaluator metadata must match Experiment"
        )


def _success_context_id(route: Mapping[str, Any]) -> str:
    experiment = _mapping(route.get("experiment"), "route.experiment")
    predicate = _mapping(experiment.get("success_predicate"), "success_predicate")
    return stable_digest(
        {
            "evaluate_at": experiment.get("evaluate_at"),
            "information_mode": experiment.get("information_mode"),
            "success_predicate": predicate,
        },
        prefix="intsuccessctx_",
    )


def _numeric_metric(before: Any, after: Any) -> dict[str, Any]:
    if before is None or after is None:
        return {
            "after": after,
            "before": before,
            "delta": None,
            "status": "unavailable_missing_value",
        }
    try:
        before_number = _number(before, "before")
        after_number = _number(after, "after")
    except ValueError:
        return {
            "after": after,
            "before": before,
            "delta": None,
            "status": "unavailable_non_numeric",
        }
    return {
        "after": after_number,
        "before": before_number,
        "delta": after_number - before_number,
        "status": "available",
    }


def _evaluation_metrics(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    comparable: bool,
) -> dict[str, Any]:
    if not comparable:
        return {
            "metrics": {},
            "status": "unavailable_incomparable_evaluator_contexts",
        }
    metrics = {
        str(name): _numeric_metric(before.get(name), after.get(name))
        for name in sorted(before.keys() | after.keys(), key=str)
    }
    return {"metrics": metrics, "status": "available"}


def _perspective(route: Mapping[str, Any]) -> int:
    experiment = _mapping(route.get("experiment"), "route.experiment")
    player = _mapping(experiment.get("player"), "route.experiment.player")
    perspective = player.get("perspective")
    if not isinstance(perspective, int) or isinstance(perspective, bool) or perspective < 0:
        raise ValueError("route.experiment.player.perspective must be non-negative")
    return perspective


def _resource_view(board_summary: Mapping[str, Any], perspective: int) -> dict[str, Any]:
    resources: dict[str, Any] = {}
    zone_counts = board_summary.get("zone_counts")
    if isinstance(zone_counts, Mapping):
        player_zones = zone_counts.get(str(perspective), zone_counts.get(perspective))
        if isinstance(player_zones, Mapping):
            for name in (
                "banished",
                "deck",
                "extra_deck",
                "graveyard",
                "hand",
                "monster_zone",
                "spell_trap_zone",
            ):
                if name in player_zones:
                    resources[name] = player_zones[name]
            if "monster_zone" in resources and "spell_trap_zone" in resources:
                monster = resources["monster_zone"]
                spell_trap = resources["spell_trap_zone"]
                resources["field"] = (
                    monster + spell_trap
                    if isinstance(monster, (int, float))
                    and not isinstance(monster, bool)
                    and isinstance(spell_trap, (int, float))
                    and not isinstance(spell_trap, bool)
                    else None
                )
    life_points = board_summary.get("life_points")
    if isinstance(life_points, Mapping):
        player_lp = life_points.get(str(perspective), life_points.get(perspective))
        if player_lp is not None:
            resources["life_points"] = player_lp
    legacy_player = board_summary.get(f"player_{perspective}")
    if isinstance(legacy_player, Mapping):
        aliases = {
            "banished_count": "banished",
            "deck_count": "deck",
            "extra_deck_count": "extra_deck",
            "graveyard_count": "graveyard",
            "hand_count": "hand",
        }
        for source, target in aliases.items():
            if target not in resources and source in legacy_player:
                resources[target] = legacy_player[source]
        field = legacy_player.get("field")
        if "field" not in resources and isinstance(field, list):
            resources["field"] = len(field)
    return resources


def _resource_metrics(
    before: _BoardView,
    after: _BoardView,
    *,
    before_perspective: int,
    after_perspective: int,
) -> dict[str, Any]:
    if before_perspective != after_perspective:
        return {
            "metrics": {},
            "status": "unavailable_incomparable_perspectives",
        }
    before_resources = _resource_view(before.board_summary, before_perspective)
    after_resources = _resource_view(after.board_summary, after_perspective)
    return {
        "metrics": {
            name: _numeric_metric(before_resources.get(name), after_resources.get(name))
            for name in sorted(before_resources.keys() | after_resources.keys())
        },
        "perspective": before_perspective,
        "status": "available",
    }


def _additional_card_metric(
    evidence: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    if evidence is None:
        return {
            "cards": [],
            "status": "unavailable_not_attributed",
            "verification_issue": 100,
        }
    cards: list[dict[str, Any]] = []
    for index, raw_item in enumerate(evidence):
        item = _mapping(raw_item, f"additional_card_evidence[{index}]")
        card_id = _string(item.get("card_id"), f"additional_card_evidence[{index}].card_id")
        raw_proof = _mapping(item.get("evidence"), f"additional_card_evidence[{index}].evidence")
        if not raw_proof:
            raise ValueError(f"additional_card_evidence[{index}].evidence must not be empty")
        cards.append({"card_id": card_id, "evidence": to_canonical_data(raw_proof)})
    return {
        "cards": sorted(cards, key=lambda item: item["card_id"]),
        "status": "caller_supplied_provisional",
        "verification_issue": 100,
    }


def _event_prefix_identity(event: Mapping[str, Any]) -> dict[str, Any]:
    action = _mapping(event.get("action"), "event.action")
    return to_canonical_data(
        {
            "action_id": action.get("action_id"),
            "action_occurrence_id": event.get("action_occurrence_id"),
            "request_signature": event.get("request_signature"),
            "state_hash_after": event.get("state_hash_after"),
            "state_hash_before": event.get("state_hash_before"),
        }
    )


def _resolve_fork_target(
    base_route: Mapping[str, Any],
    interrupted_route: Mapping[str, Any],
    fork_step: int,
) -> tuple[str, dict[str, Any]]:
    interruptions = interrupted_route.get("interruptions")
    if not isinstance(interruptions, list):
        raise ValueError("interrupted_route.interruptions must be a list")
    candidates = [
        item
        for item in interruptions
        if isinstance(item, Mapping) and item.get("at_step") == fork_step
    ]
    if len(candidates) != 1:
        raise ValueError("interrupted Route requires exactly one interruption at fork_step")
    interruption = _mapping(candidates[0], "interrupted_route.interruptions[fork_step]")
    target = InterruptionTarget.from_dict(
        _mapping(interruption.get("target"), "interruption.target")
    )
    resolution = resolve_interruption_target(
        _mapping(base_route.get("replay"), "base_route.replay"), target
    )
    if resolution.replay_step != fork_step:
        raise ValueError("interruption target must resolve to lineage.fork_step")
    return (
        _string(interruption.get("interruption_id"), "interruption.interruption_id"),
        resolution.to_dict(),
    )


def _recovery_report(
    base_events: Sequence[Mapping[str, Any]],
    recovery_events: Sequence[Mapping[str, Any]],
    *,
    fork_step: int,
    original_target_state_id: str,
    goal_recovered: bool | None,
) -> dict[str, Any]:
    base_states: dict[str, int] = {}
    for index in range(fork_step, len(base_events)):
        state_id = _string(base_events[index].get("state_hash_after"), "base state")
        base_states.setdefault(state_id, index)
    rejoin: dict[str, Any] | None = None
    original_target_reached = False
    for index in range(fork_step, len(recovery_events)):
        state_id = _string(recovery_events[index].get("state_hash_after"), "recovery state")
        if state_id == original_target_state_id:
            original_target_reached = True
        if rejoin is None and state_id in base_states:
            rejoin = {
                "base_step": base_states[state_id],
                "recovery_step": index,
                "state_id": state_id,
            }
    if original_target_reached:
        status = RecoveryStatus.ORIGINAL_TARGET_REACHED
    elif rejoin is not None:
        status = RecoveryStatus.ORIGINAL_ROUTE_REJOINED
    elif goal_recovered is True:
        status = RecoveryStatus.GOAL_ONLY
    elif goal_recovered is None:
        status = RecoveryStatus.GOAL_INCOMPARABLE
    else:
        status = RecoveryStatus.NOT_RECOVERED
    identity = to_canonical_data(
        {
            "can_rejoin_original_route": rejoin is not None,
            "goal_recovered": goal_recovered,
            "original_target_reached": original_target_reached,
            "original_target_state_id": original_target_state_id,
            "rejoin": rejoin,
            "status": status.value,
        }
    )
    return {**identity, "recovery_id": stable_digest(identity, prefix="recovery_")}


def build_interruption_comparison(
    base_route: Mapping[str, Any],
    interrupted_route: Mapping[str, Any],
    *,
    target_board: RouteTargetBoard = RouteTargetBoard.PEAK,
    additional_card_evidence: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(target_board, RouteTargetBoard):
        target_board = RouteTargetBoard(target_board)
    assert_valid_route_document(base_route)
    assert_valid_route_document(interrupted_route)
    base_route_id = _string(base_route.get("route_id"), "base_route.route_id")
    interrupted_route_id = _string(
        interrupted_route.get("route_id"), "interrupted_route.route_id"
    )
    if base_route_id == interrupted_route_id:
        raise ValueError("base and interrupted Route IDs must differ")
    lineage = _mapping(interrupted_route.get("lineage"), "interrupted_route.lineage")
    if lineage.get("parent_route_id") != base_route_id:
        raise ValueError("interrupted Route lineage must reference base Route")
    fork_step = lineage.get("fork_step")
    if not isinstance(fork_step, int) or isinstance(fork_step, bool) or fork_step < 0:
        raise ValueError("interrupted Route lineage.fork_step must be non-negative")

    base_replay = _mapping(base_route.get("replay"), "base_route.replay")
    interrupted_replay = _mapping(
        interrupted_route.get("replay"), "interrupted_route.replay"
    )
    for name in ("initial_snapshot", "version_metadata", "seeds"):
        if to_canonical_data(base_replay.get(name)) != to_canonical_data(
            interrupted_replay.get(name)
        ):
            raise ValueError(f"base and interrupted Replay {name} must match")
    base_events = _events(base_route, "base_route")
    interrupted_events = _events(interrupted_route, "interrupted_route")
    if fork_step >= len(base_events) or fork_step >= len(interrupted_events):
        raise ValueError("lineage.fork_step must exist in both Replays")
    for index in range(fork_step):
        if _event_prefix_identity(base_events[index]) != _event_prefix_identity(
            interrupted_events[index]
        ):
            raise ValueError(f"Replay prefix differs before fork_step at step {index}")
    if base_events[fork_step].get("state_hash_before") != interrupted_events[
        fork_step
    ].get("state_hash_before"):
        raise ValueError("base and interrupted Replay must share the fork State")

    interruption_id, target_resolution = _resolve_fork_target(
        base_route, interrupted_route, fork_step
    )
    before = _board_view(base_route, target_board, "base_route")
    after = _board_view(interrupted_route, target_board, "interrupted_route")
    _assert_evaluation_result_context(base_route, before, "base_route")
    _assert_evaluation_result_context(interrupted_route, after, "interrupted_route")
    evaluator_context_before = _evaluator_context_id(base_route)
    evaluator_context_after = _evaluator_context_id(interrupted_route)
    evaluator_comparable = evaluator_context_before == evaluator_context_after
    if (
        evaluator_comparable
        and before.state_id == after.state_id
        and (
            before.score != after.score
            or to_canonical_data(before.evaluation)
            != to_canonical_data(after.evaluation)
        )
    ):
        raise ValueError(
            "same exact target State and evaluator context must have identical evaluation"
        )
    success_context_before = _success_context_id(base_route)
    success_context_after = _success_context_id(interrupted_route)
    success_comparable = success_context_before == success_context_after
    base_success = _mapping(base_route.get("result"), "base_route.result").get("success")
    interrupted_success = _mapping(
        interrupted_route.get("result"), "interrupted_route.result"
    ).get("success")
    goal_metric = (
        {
            "after": interrupted_success,
            "before": base_success,
            "recovered": interrupted_success is True,
            "retained": base_success is True and interrupted_success is True,
            "status": "available",
        }
        if success_comparable
        else {
            "after": interrupted_success,
            "before": base_success,
            "recovered": None,
            "retained": None,
            "status": "unavailable_incomparable_success_predicates",
        }
    )
    score_metric = (
        _numeric_metric(before.score, after.score)
        if evaluator_comparable
        else {
            "after": after.score,
            "before": before.score,
            "delta": None,
            "status": "unavailable_incomparable_evaluator_contexts",
        }
    )
    score_breakdown: dict[str, Any] | None = None
    if (
        evaluator_comparable
        and before.evaluation_result is not None
        and after.evaluation_result is not None
    ):
        score_breakdown = compare_score_breakdowns(
            before.evaluation_result.score_breakdown,
            after.evaluation_result.score_breakdown,
        )
    recovery = _recovery_report(
        base_events,
        interrupted_events,
        fork_step=fork_step,
        original_target_state_id=before.state_id,
        goal_recovered=(interrupted_success is True if success_comparable else None),
    )
    identity = to_canonical_data(
        {
            "base_route_id": base_route_id,
            "fork_step": fork_step,
            "interrupted_route_id": interrupted_route_id,
            "interruption": {
                "interruption_id": interruption_id,
                "target_resolution": target_resolution,
            },
            "metrics": {
                "additional_cards": _additional_card_metric(additional_card_evidence),
                "evaluation": _evaluation_metrics(
                    before.evaluation,
                    after.evaluation,
                    comparable=evaluator_comparable,
                ),
                "goal": goal_metric,
                "resources": _resource_metrics(
                    before,
                    after,
                    before_perspective=_perspective(base_route),
                    after_perspective=_perspective(interrupted_route),
                ),
                "route_length": _numeric_metric(len(base_events), len(interrupted_events)),
                "score": score_metric,
                "score_breakdown": score_breakdown,
            },
            "recovery": recovery,
            "schema_version": INTERRUPTION_COMPARISON_SCHEMA_VERSION,
            "target_board": target_board.value,
        }
    )
    return {
        **identity,
        "comparison_id": stable_digest(identity, prefix="intcompare_"),
    }
