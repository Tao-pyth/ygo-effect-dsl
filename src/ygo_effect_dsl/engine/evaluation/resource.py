from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


RESOURCE_CONSUMPTION_SCHEMA_VERSION = "route-resource-consumption-v1"
RESOURCE_CONSUMPTION_EVALUATOR_ID = "route_resource_consumption"
RESOURCE_CONSUMPTION_EVALUATOR_VERSION = "1"
RESOURCE_CONSUMPTION_METRIC = "resource_consumption_v1"
RESOURCE_CONSUMPTION_DEFAULT_CONFIG = {
    "weights": {
        "extra_deck_net_decrease": 1,
        "hand_net_decrease": 1,
        "life_point_loss": 0.001,
        "normal_summon_uses": 1,
    }
}

_LOCATION_NAMES = {
    0x01: "deck",
    0x02: "hand",
    0x04: "monster_zone",
    0x08: "spell_trap_zone",
    0x10: "graveyard",
    0x20: "banished",
    0x40: "extra_deck",
}
_STOCK_LOCATIONS = (
    "deck",
    "hand",
    "monster_zone",
    "spell_trap_zone",
    "graveyard",
    "banished",
    "extra_deck",
)
_SCALAR_DIMENSIONS = tuple(RESOURCE_CONSUMPTION_DEFAULT_CONFIG["weights"])


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _non_negative_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{path} must be an integer >= 0")
    return value


def _non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _finite_non_negative(value: Any, path: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{path} must be a finite number >= 0")
    return value


def _config(value: Mapping[str, Any] | None) -> dict[str, Any]:
    resolved = to_canonical_data(
        RESOURCE_CONSUMPTION_DEFAULT_CONFIG if value is None else value
    )
    weights = _mapping(resolved.get("weights"), "resource config.weights")
    if set(weights) != set(_SCALAR_DIMENSIONS):
        raise ValueError(
            "resource config.weights must contain exactly "
            f"{sorted(_SCALAR_DIMENSIONS)}"
        )
    for dimension, weight in weights.items():
        _finite_non_negative(weight, f"resource config.weights.{dimension}")
    return resolved


def _initial_zone_counts(snapshot: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    counts = {str(player): {name: 0 for name in _STOCK_LOCATIONS} for player in (0, 1)}
    for index, raw_zone in enumerate(_list(snapshot.get("zones"), "initial_snapshot.zones")):
        zone = _mapping(raw_zone, f"initial_snapshot.zones[{index}]")
        controller = _non_negative_int(
            zone.get("controller"), f"initial_snapshot.zones[{index}].controller"
        )
        if controller not in (0, 1):
            raise ValueError("initial snapshot zone controller must be 0 or 1")
        location = _non_negative_int(
            zone.get("location"), f"initial_snapshot.zones[{index}].location"
        )
        location_name = _LOCATION_NAMES.get(location)
        if location_name is None:
            continue
        cards = _list(zone.get("cards"), f"initial_snapshot.zones[{index}].cards")
        counts[str(controller)][location_name] += sum(
            card is not None for card in cards
        )
    return counts


def _initial_life_points(snapshot: Mapping[str, Any]) -> dict[str, int]:
    field_state = _mapping(snapshot.get("field_state"), "initial_snapshot.field_state")
    players = _list(field_state.get("players"), "initial_snapshot.field_state.players")
    result: dict[str, int] = {}
    for index, raw_player in enumerate(players):
        player = _mapping(raw_player, f"initial_snapshot.field_state.players[{index}]")
        player_id = _non_negative_int(player.get("player"), f"players[{index}].player")
        if player_id not in (0, 1):
            raise ValueError("initial snapshot player must be 0 or 1")
        result[str(player_id)] = _non_negative_int(
            player.get("life_points"), f"players[{index}].life_points"
        )
    if set(result) != {"0", "1"}:
        raise ValueError("initial snapshot must contain both players")
    return result


def _target_checkpoint(
    document: Mapping[str, Any], target_board: str
) -> tuple[int, Mapping[str, Any], Mapping[str, Any]]:
    if target_board not in {"peak_board", "terminal_board"}:
        raise ValueError("target_board must be peak_board or terminal_board")
    result = _mapping(document.get("result"), "route.result")
    board = _mapping(result.get(target_board), f"route.result.{target_board}")
    checkpoint_step = _non_negative_int(
        board.get("checkpoint_step"), f"route.result.{target_board}.checkpoint_step"
    )
    checkpoints = _list(document.get("checkpoints"), "route.checkpoints")
    checkpoint = next(
        (
            _mapping(item, f"route.checkpoints[{index}]")
            for index, item in enumerate(checkpoints)
            if isinstance(item, Mapping) and item.get("step") == checkpoint_step
        ),
        None,
    )
    if checkpoint is None:
        raise ValueError(f"route has no checkpoint for step {checkpoint_step}")
    if checkpoint.get("state_hash") != board.get("state_hash"):
        raise ValueError("target board and checkpoint state hashes must match")
    summary = _mapping(checkpoint.get("board_summary"), "checkpoint.board_summary")
    return checkpoint_step, checkpoint, summary


def _action_usage(
    document: Mapping[str, Any], checkpoint_step: int
) -> dict[str, dict[str, int]]:
    replay = _mapping(document.get("replay"), "route.replay")
    events = _list(replay.get("events"), "route.replay.events")
    usage = {
        str(player): {"normal_summon_uses": 0, "special_summon_actions": 0}
        for player in (0, 1)
    }
    for index, raw_event in enumerate(events):
        event = _mapping(raw_event, f"route.replay.events[{index}]")
        step = _non_negative_int(event.get("step"), f"events[{index}].step")
        if step > checkpoint_step:
            continue
        action = _mapping(event.get("action"), f"events[{index}].action")
        player = _non_negative_int(action.get("player"), f"events[{index}].action.player")
        if player not in (0, 1):
            raise ValueError("action player must be 0 or 1")
        kind = action.get("kind")
        if kind == "NORMAL_SUMMON":
            usage[str(player)]["normal_summon_uses"] += 1
        elif kind == "SPECIAL_SUMMON":
            usage[str(player)]["special_summon_actions"] += 1
    return usage


def _cost_evidence(
    document: Mapping[str, Any], checkpoint_step: int
) -> tuple[dict[str, dict[str, int]], list[dict[str, Any]], str | None]:
    counts = {
        str(player): {name: 0 for name in _STOCK_LOCATIONS}
        for player in (0, 1)
    }
    records: list[dict[str, Any]] = []
    presentation = document.get("presentation")
    if not isinstance(presentation, Mapping):
        return counts, records, None
    aggregation = presentation.get("action_aggregation")
    evidence = presentation.get("action_aggregation_evidence")
    if not isinstance(aggregation, Mapping):
        return counts, records, None
    for group_index, raw_group in enumerate(
        _list(aggregation.get("groups"), "action_aggregation.groups")
    ):
        group = _mapping(raw_group, f"action_aggregation.groups[{group_index}]")
        for part_index, raw_part in enumerate(
            _list(group.get("parts"), f"action_aggregation.groups[{group_index}].parts")
        ):
            part = _mapping(
                raw_part,
                f"action_aggregation.groups[{group_index}].parts[{part_index}]",
            )
            if part.get("role") != "cost":
                continue
            step = _non_negative_int(part.get("step"), "cost part.step")
            if step > checkpoint_step:
                continue
            for selection_index, raw_selection in enumerate(
                _list(part.get("selections"), "cost part.selections")
            ):
                selection = _mapping(raw_selection, "cost selection")
                card_ref = selection.get("card_ref")
                if not isinstance(card_ref, Mapping):
                    continue
                player = _non_negative_int(
                    card_ref.get("controller"), "cost selection.card_ref.controller"
                )
                location = _non_negative_int(
                    card_ref.get("location"), "cost selection.card_ref.location"
                )
                location_name = _LOCATION_NAMES.get(location, f"core_location_{location}")
                if player in (0, 1) and location_name in counts[str(player)]:
                    counts[str(player)][location_name] += 1
                records.append(
                    to_canonical_data(
                        {
                            "action_occurrence_id": part.get("action_occurrence_id"),
                            "candidate_id": selection.get("candidate_id"),
                            "controller": player,
                            "location": location,
                            "location_name": location_name,
                            "public_card_id": card_ref.get("public_card_id"),
                            "step": step,
                        }
                    )
                )
    evidence_id = (
        evidence.get("evidence_id") if isinstance(evidence, Mapping) else None
    )
    return counts, records, evidence_id if isinstance(evidence_id, str) else None


def build_route_resource_consumption(
    document: Mapping[str, Any],
    *,
    target_board: str = "peak_board",
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    document = _mapping(document, "route")
    route_id = document.get("route_id")
    if not isinstance(route_id, str) or not route_id:
        raise ValueError("route.route_id must be a non-empty string")
    experiment = _mapping(document.get("experiment"), "route.experiment")
    player_config = _mapping(experiment.get("player"), "route.experiment.player")
    perspective = _non_negative_int(
        player_config.get("perspective"), "route.experiment.player.perspective"
    )
    if perspective not in (0, 1):
        raise ValueError("route perspective must be 0 or 1")
    replay = _mapping(document.get("replay"), "route.replay")
    initial_snapshot = _mapping(
        replay.get("initial_snapshot"), "route.replay.initial_snapshot"
    )
    initial_state_hash = _non_empty_string(
        initial_snapshot.get("state_hash"), "route.replay.initial_snapshot.state_hash"
    )
    checkpoint_step, checkpoint, target_summary = _target_checkpoint(
        document, target_board
    )
    target_state_hash = _non_empty_string(
        checkpoint.get("state_hash"), "checkpoint.state_hash"
    )
    initial_counts = _initial_zone_counts(initial_snapshot)
    initial_lp = _initial_life_points(initial_snapshot)
    target_counts = _mapping(target_summary.get("zone_counts"), "board_summary.zone_counts")
    target_lp = _mapping(target_summary.get("life_points"), "board_summary.life_points")
    action_usage = _action_usage(document, checkpoint_step)
    cost_counts, cost_records, aggregation_evidence_id = _cost_evidence(
        document, checkpoint_step
    )

    players: dict[str, Any] = {}
    for player in (0, 1):
        player_key = str(player)
        player_target_counts = _mapping(
            target_counts.get(player_key), f"board_summary.zone_counts.{player_key}"
        )
        target_zone_counts = {
            name: _non_negative_int(
                player_target_counts.get(name),
                f"board_summary.zone_counts.{player_key}.{name}",
            )
            for name in _STOCK_LOCATIONS
        }
        target_life_points = _non_negative_int(
            target_lp.get(player_key), f"board_summary.life_points.{player_key}"
        )
        net_decreases = {
            f"{name}_net_decrease": max(
                initial_counts[player_key][name] - target_zone_counts[name], 0
            )
            for name in ("deck", "hand", "monster_zone", "spell_trap_zone", "extra_deck")
        }
        dimensions = {
            **net_decreases,
            "banished_net_increase": max(
                target_zone_counts["banished"] - initial_counts[player_key]["banished"],
                0,
            ),
            "explicit_cost_cards": sum(cost_counts[player_key].values()),
            "graveyard_net_increase": max(
                target_zone_counts["graveyard"]
                - initial_counts[player_key]["graveyard"],
                0,
            ),
            "life_point_loss": max(
                initial_lp[player_key] - target_life_points, 0
            ),
            **action_usage[player_key],
        }
        players[player_key] = {
            "dimensions": dimensions,
            "explicit_cost_cards_by_origin": cost_counts[player_key],
            "initial": {
                "life_points": initial_lp[player_key],
                "zone_counts": initial_counts[player_key],
            },
            "target": {
                "life_points": target_life_points,
                "zone_counts": target_zone_counts,
            },
        }

    resolved_config = _config(config)
    perspective_dimensions = players[str(perspective)]["dimensions"]
    terms = []
    for dimension, weight in resolved_config["weights"].items():
        value = perspective_dimensions[dimension]
        terms.append(
            {
                "contribution": value * weight,
                "dimension": dimension,
                "value": value,
                "weight": weight,
            }
        )
    total = sum(term["contribution"] for term in terms)
    config_identity = {
        "config": resolved_config,
        "evaluator_id": RESOURCE_CONSUMPTION_EVALUATOR_ID,
        "evaluator_version": RESOURCE_CONSUMPTION_EVALUATOR_VERSION,
    }
    identity = to_canonical_data(
        {
            "checkpoint_step": checkpoint_step,
            "config": resolved_config,
            "config_hash": stable_digest(config_identity, prefix="resourcecfg_"),
            "evaluator_id": RESOURCE_CONSUMPTION_EVALUATOR_ID,
            "evaluator_version": RESOURCE_CONSUMPTION_EVALUATOR_VERSION,
            "explicit_cost_evidence": {
                "action_aggregation_evidence_id": aggregation_evidence_id,
                "records": cost_records,
                "truth_source": "validated_action_aggregation_roles",
            },
            "metric": RESOURCE_CONSUMPTION_METRIC,
            "perspective": perspective,
            "players": players,
            "route_id": route_id,
            "scalar": {
                "terms": terms,
                "total": total,
                "truth_source": "initial_to_checkpoint_net_state_delta_plus_action_usage",
            },
            "schema_version": RESOURCE_CONSUMPTION_SCHEMA_VERSION,
            "source_state_hashes": {
                "initial": initial_state_hash,
                "target": target_state_hash,
            },
            "target_board": target_board,
            "unavailable_dimensions": [
                {
                    "dimension": "normal_summon_remaining",
                    "reason": "unavailable_from_ocgcore_query_api",
                },
                {
                    "dimension": "once_per_turn_remaining",
                    "reason": "unavailable_from_ocgcore_query_api",
                },
                {
                    "dimension": "public_information_disclosure_cost",
                    "reason": "no_calibrated_value_model",
                },
            ],
        }
    )
    return {
        **identity,
        "resource_report_id": stable_digest(identity, prefix="resourceeval_"),
    }
