from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ygo_effect_dsl.engine.bridge.ocgcore.state import (
    CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION,
    LOCATION_DECK,
    LOCATION_EXTRA,
    LOCATION_GRAVE,
    LOCATION_HAND,
    LOCATION_MZONE,
    LOCATION_NAMES,
    LOCATION_ORDER,
    LOCATION_REMOVED,
    LOCATION_SZONE,
    CompleteSnapshot,
)
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data
from ygo_effect_dsl.engine.replay.v03a import ReplayEventV03a


PLAYER_VIEW_REPLAY_SCHEMA_VERSION = "player-view-replay-v1"
PLAYER_VIEW_MANIFEST_SCHEMA_VERSION = "player-view-manifest-v1"
PLAYER_VIEW_OBSERVATION_SCHEMA_VERSION = "player-view-observation-v1"
PLAYER_VIEW_EVENT_SCHEMA_VERSION = "player-view-event-v1"
PLAYER_VIEW_PROJECTOR_ID = "ocgcore-player-view-projector-v1"

_CARD_TOP_LEVEL_FIELDS = frozenset(
    {
        "controller",
        "fields",
        "instance_key",
        "location",
        "persistent_instance_id",
        "player_view_instance_ids",
        "slot",
    }
)
_KNOWN_QUERY_FIELDS = frozenset(
    {
        "alias",
        "attack",
        "attribute",
        "base_attack",
        "base_defense",
        "code",
        "counters",
        "cover",
        "defense",
        "end",
        "equip_card",
        "is_hidden",
        "is_public",
        "left_scale",
        "level",
        "link",
        "overlay_cards",
        "owner",
        "position",
        "race",
        "rank",
        "reason",
        "reason_card",
        "right_scale",
        "status",
        "target_cards",
        "type",
    }
)
_PUBLIC_CARD_FIELDS = (
    "alias",
    "attack",
    "attribute",
    "base_attack",
    "base_defense",
    "code",
    "defense",
    "is_public",
    "left_scale",
    "level",
    "link",
    "owner",
    "position",
    "race",
    "rank",
    "right_scale",
    "status",
    "type",
)
_KNOWN_REQUEST_TYPES = frozenset(
    {
        "announce_attribute",
        "announce_card",
        "announce_number",
        "announce_race",
        "rock_paper_scissors",
        "select_battle_command",
        "select_card",
        "select_chain",
        "select_counter",
        "select_disfield",
        "select_effect_yes_no",
        "select_idle_command",
        "select_option",
        "select_place",
        "select_position",
        "select_sum",
        "select_tribute",
        "select_unselect_card",
        "select_yes_no",
        "sort_card",
        "sort_chain",
    }
)
_KNOWN_PROCESS_STATES = frozenset(
    {
        "awaiting_response",
        "cards_loaded",
        "duel_created",
        "ended",
        "failed",
        "processing",
        "started",
        "version_checked",
    }
)
_FIELD_STATE_FIELDS = frozenset({"chain", "chain_count", "duel_options", "players"})
_PLAYER_FIELD_FIELDS = frozenset(
    {
        "banished_count",
        "deck_count",
        "extra_deck_count",
        "face_up_extra_count",
        "graveyard_count",
        "hand_count",
        "life_points",
        "monster_zones",
        "player",
        "spell_trap_zones",
    }
)
_CHAIN_FIELDS = frozenset(
    {
        "description",
        "handler",
        "triggering_controller",
        "triggering_location",
        "triggering_sequence",
    }
)
_CHAIN_HANDLER_FIELDS = frozenset(
    {"code", "controller", "location", "position", "sequence"}
)


class PlayerViewProjectionError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code} at {path}: {message}")


@dataclass(frozen=True)
class PlayerViewProjectionInput:
    source_route: Mapping[str, Any]
    initial_snapshot: CompleteSnapshot
    initial_turn: int
    initial_phase: str
    checkpoint_snapshots: Sequence[tuple[CompleteSnapshot, int, str]]
    events: Sequence[ReplayEventV03a]
    viewer: int
    parent_player_view_id: str | None = None
    fork_step: int | None = None


def _reject(code: str, path: str, message: str) -> None:
    raise PlayerViewProjectionError(code, path, message)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _reject("unprojectable_shape", path, "expected a mapping")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        _reject("unprojectable_shape", path, f"expected an integer >= {minimum}")
    return value


def _exact_fields(value: Mapping[str, Any], expected: frozenset[str], path: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown or missing:
        _reject(
            "unprojectable_shape",
            path,
            f"field mismatch; unknown={unknown}, missing={missing}",
        )


def _card_fields(card: Mapping[str, Any], path: str) -> dict[str, Any]:
    unknown = sorted(set(card) - _CARD_TOP_LEVEL_FIELDS)
    required = {"controller", "fields", "instance_key", "location", "slot"}
    missing = sorted(required - set(card))
    if unknown or missing:
        _reject(
            "unprojectable_shape",
            path,
            f"card field mismatch; unknown={unknown}, missing={missing}",
        )
    raw_fields = card["fields"]
    if not isinstance(raw_fields, (list, tuple)):
        _reject("unprojectable_shape", f"{path}.fields", "expected a sequence")
    fields: dict[str, Any] = {}
    for index, raw_field in enumerate(raw_fields):
        field = _mapping(raw_field, f"{path}.fields[{index}]")
        _exact_fields(field, frozenset({"flag", "name", "value"}), f"{path}.fields[{index}]")
        name = field["name"]
        if not isinstance(name, str) or name not in _KNOWN_QUERY_FIELDS:
            _reject(
                "unprojectable_shape",
                f"{path}.fields[{index}].name",
                f"unsupported query field {name!r}",
            )
        if name in fields:
            _reject("unprojectable_shape", f"{path}.fields", f"duplicate field {name!r}")
        fields[name] = field["value"]
    return fields


def _viewer_alias(
    snapshot: CompleteSnapshot,
    card: Mapping[str, Any],
    *,
    viewer: int,
    path: str,
) -> str | None:
    aliases = card.get("player_view_instance_ids")
    if snapshot.card_instance_schema_version is None:
        if aliases is not None or "persistent_instance_id" in card:
            _reject("unprojectable_shape", path, "v1 snapshot contains v2 identity fields")
        return None
    if snapshot.card_instance_schema_version != CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION:
        _reject("unprojectable_shape", path, "unsupported card instance schema")
    if not isinstance(aliases, Mapping):
        _reject("missing_viewer_alias", path, "visible card has no viewer alias mapping")
    alias = aliases.get(str(viewer))
    if not isinstance(alias, str) or not alias.startswith("viewcard_"):
        _reject("missing_viewer_alias", path, "visible card has no valid viewer alias")
    return alias


def _public_card(
    snapshot: CompleteSnapshot,
    card: Mapping[str, Any],
    fields: Mapping[str, Any],
    *,
    viewer: int,
    include_sequence: bool,
    path: str,
) -> dict[str, Any]:
    if "code" not in fields:
        _reject("unprojectable_shape", path, "visible card has no card code")
    projected = {
        name: to_canonical_data(fields[name])
        for name in _PUBLIC_CARD_FIELDS
        if name in fields
    }
    projected["controller"] = _integer(card["controller"], f"{path}.controller")
    projected["location"] = _integer(card["location"], f"{path}.location")
    if include_sequence:
        projected["sequence"] = _integer(card["slot"], f"{path}.slot")
    alias = _viewer_alias(snapshot, card, viewer=viewer, path=path)
    if alias is not None:
        projected["viewer_instance_alias"] = alias
    return projected


def _is_hidden(fields: Mapping[str, Any]) -> bool:
    position = fields.get("position")
    face_down = isinstance(position, int) and bool(position & 0x0A)
    return fields.get("is_hidden") == 1 or face_down


def _project_field_state(snapshot: CompleteSnapshot) -> dict[str, Any]:
    field_state = _mapping(snapshot.field_state, "field_state")
    _exact_fields(field_state, _FIELD_STATE_FIELDS, "field_state")
    raw_players = field_state["players"]
    if not isinstance(raw_players, (list, tuple)) or len(raw_players) != 2:
        _reject("unprojectable_shape", "field_state.players", "expected two players")
    life_points: dict[str, int] = {}
    occupied_zones: dict[str, dict[str, list[dict[str, int]]]] = {}
    for index, raw_player in enumerate(raw_players):
        player = _mapping(raw_player, f"field_state.players[{index}]")
        _exact_fields(player, _PLAYER_FIELD_FIELDS, f"field_state.players[{index}]")
        player_id = _integer(player["player"], f"field_state.players[{index}].player")
        if player_id != index:
            _reject("unprojectable_shape", f"field_state.players[{index}].player", "unexpected player order")
        life_points[str(player_id)] = _integer(
            player["life_points"], f"field_state.players[{index}].life_points"
        )
        occupied: dict[str, list[dict[str, int]]] = {}
        for zone_name, expected_size in (("monster_zones", 7), ("spell_trap_zones", 8)):
            slots = player[zone_name]
            if not isinstance(slots, (list, tuple)) or len(slots) != expected_size:
                _reject(
                    "unprojectable_shape",
                    f"field_state.players[{index}].{zone_name}",
                    f"expected {expected_size} slots",
                )
            visible_slots: list[dict[str, int]] = []
            for sequence, raw_slot in enumerate(slots):
                if raw_slot is None:
                    continue
                slot = _mapping(raw_slot, f"field_state.players[{index}].{zone_name}[{sequence}]")
                _exact_fields(
                    slot,
                    frozenset({"overlay_count", "position"}),
                    f"field_state.players[{index}].{zone_name}[{sequence}]",
                )
                visible_slots.append(
                    {
                        "overlay_count": _integer(slot["overlay_count"], f"field_state.players[{index}].{zone_name}[{sequence}].overlay_count"),
                        "position": _integer(slot["position"], f"field_state.players[{index}].{zone_name}[{sequence}].position"),
                        "sequence": sequence,
                    }
                )
            occupied[zone_name] = visible_slots
        occupied_zones[str(player_id)] = occupied
    raw_chain = field_state["chain"]
    if not isinstance(raw_chain, (list, tuple)):
        _reject("unprojectable_shape", "field_state.chain", "expected a sequence")
    chain: list[dict[str, Any]] = []
    for index, raw_link in enumerate(raw_chain):
        link = _mapping(raw_link, f"field_state.chain[{index}]")
        _exact_fields(link, _CHAIN_FIELDS, f"field_state.chain[{index}]")
        handler = _mapping(link["handler"], f"field_state.chain[{index}].handler")
        _exact_fields(handler, _CHAIN_HANDLER_FIELDS, f"field_state.chain[{index}].handler")
        chain.append(
            {
                "handler": {
                    key: _integer(value, f"field_state.chain[{index}].handler.{key}")
                    for key, value in handler.items()
                },
                "triggering_controller": _integer(link["triggering_controller"], f"field_state.chain[{index}].triggering_controller"),
                "triggering_location": _integer(link["triggering_location"], f"field_state.chain[{index}].triggering_location"),
                "triggering_sequence": _integer(link["triggering_sequence"], f"field_state.chain[{index}].triggering_sequence"),
            }
        )
    chain_count = _integer(field_state["chain_count"], "field_state.chain_count")
    if chain_count != len(chain):
        _reject("unprojectable_shape", "field_state.chain_count", "does not match chain length")
    return {
        "chain": chain,
        "chain_count": chain_count,
        "life_points": life_points,
        "occupied_zones": occupied_zones,
    }


def _project_pending_request(snapshot: CompleteSnapshot, *, viewer: int) -> dict[str, Any] | None:
    if snapshot.pending_request is None:
        return None
    request = _mapping(snapshot.pending_request, "pending_request")
    allowed = frozenset(
        {
            "candidate_action_kinds",
            "candidate_ids",
            "forced",
            "player",
            "request_observation_id",
            "request_signature",
            "request_type",
        }
    )
    unknown = sorted(set(request) - allowed)
    required = {"candidate_action_kinds", "candidate_ids", "forced", "player", "request_signature", "request_type"}
    missing = sorted(required - set(request))
    if unknown or missing:
        _reject(
            "unprojectable_shape",
            "pending_request",
            f"field mismatch; unknown={unknown}, missing={missing}",
        )
    player = _integer(request["player"], "pending_request.player")
    if player != viewer:
        return None
    request_type = request["request_type"]
    if not isinstance(request_type, str) or request_type not in _KNOWN_REQUEST_TYPES:
        _reject("unprojectable_shape", "pending_request.request_type", f"unsupported request type {request_type!r}")
    action_kinds = request["candidate_action_kinds"]
    if not isinstance(action_kinds, (list, tuple)):
        _reject(
            "unprojectable_shape",
            "pending_request.candidate_action_kinds",
            "expected a sequence",
        )
    normalized_action_kinds = []
    for index, kind in enumerate(action_kinds):
        if kind is None:
            normalized_action_kinds.append("UNSPECIFIED")
            continue
        if not isinstance(kind, str) or not kind:
            _reject(
                "unprojectable_shape",
                f"pending_request.candidate_action_kinds[{index}]",
                "expected a non-empty string or legacy null",
            )
        normalized_action_kinds.append(kind)
    if not isinstance(request["forced"], bool):
        _reject("unprojectable_shape", "pending_request.forced", "expected a boolean")
    return {
        "action_categories": sorted(set(normalized_action_kinds)),
        "forced": request["forced"],
        "player": player,
        "request_type": request_type,
    }


def project_player_view_observation(
    snapshot: CompleteSnapshot,
    *,
    viewer: int,
    turn: int,
    phase: str,
) -> dict[str, Any]:
    if viewer not in (0, 1):
        raise ValueError("viewer must be 0 or 1")
    _integer(turn, "turn", minimum=1)
    if not isinstance(phase, str) or not phase:
        _reject("unprojectable_shape", "phase", "expected a non-empty string")
    if snapshot.process_state not in _KNOWN_PROCESS_STATES:
        _reject("unprojectable_shape", "process_state", "unsupported process state")
    if len(snapshot.zones) != len(LOCATION_ORDER) * 2:
        _reject("unprojectable_shape", "zones", "complete canonical zone set is required")
    field_state = _project_field_state(snapshot)
    pending_request = _project_pending_request(snapshot, viewer=viewer)
    zones: list[dict[str, Any]] = []
    observed_keys: set[tuple[int, int]] = set()
    for zone_index, raw_zone in enumerate(snapshot.zones):
        path = f"zones[{zone_index}]"
        zone = _mapping(raw_zone, path)
        _exact_fields(zone, frozenset({"cards", "controller", "location", "location_name"}), path)
        controller = _integer(zone["controller"], f"{path}.controller")
        location = _integer(zone["location"], f"{path}.location")
        if controller not in (0, 1) or location not in LOCATION_ORDER:
            _reject("unprojectable_shape", path, "unknown controller or location")
        key = (controller, location)
        if key in observed_keys:
            _reject("unprojectable_shape", path, "duplicate zone")
        observed_keys.add(key)
        if zone["location_name"] != LOCATION_NAMES[location]:
            _reject("unprojectable_shape", f"{path}.location_name", "location name mismatch")
        raw_cards = zone["cards"]
        if not isinstance(raw_cards, (list, tuple)):
            _reject("unprojectable_shape", f"{path}.cards", "expected a sequence")
        cards = [card for card in raw_cards if card is not None]
        projected_zone: dict[str, Any] = {
            "controller": controller,
            "count": len(cards),
            "location": location,
            "location_name": LOCATION_NAMES[location],
        }
        private_count_only = location == LOCATION_DECK or (
            controller != viewer and location in {LOCATION_HAND, LOCATION_EXTRA}
        )
        if not private_count_only:
            projected_cards: list[dict[str, Any]] = []
            hidden_count = 0
            for card_index, raw_card in enumerate(cards):
                card_path = f"{path}.cards[{card_index}]"
                card = _mapping(raw_card, card_path)
                fields = _card_fields(card, card_path)
                card_controller = _integer(card["controller"], f"{card_path}.controller")
                card_location = _integer(card["location"], f"{card_path}.location")
                if card_controller != controller or card_location != location:
                    _reject("unprojectable_shape", card_path, "card coordinate disagrees with zone")
                hidden = controller != viewer and _is_hidden(fields)
                sequence = _integer(card["slot"], f"{card_path}.slot")
                if hidden:
                    if location not in {LOCATION_MZONE, LOCATION_SZONE}:
                        hidden_count += 1
                        continue
                    projected_cards.append(
                        {
                            "controller": controller,
                            "hidden": True,
                            "location": location,
                            "position": fields["position"],
                            "sequence": sequence,
                        }
                    )
                    continue
                projected_cards.append(
                    _public_card(
                        snapshot,
                        card,
                        fields,
                        viewer=viewer,
                        include_sequence=location in {LOCATION_MZONE, LOCATION_SZONE},
                        path=card_path,
                    )
                )
            if location not in {LOCATION_MZONE, LOCATION_SZONE}:
                projected_cards.sort(key=canonical_json)
            projected_zone["cards"] = projected_cards
            if hidden_count:
                projected_zone["hidden_count"] = hidden_count
        zones.append(projected_zone)
    expected_keys = {(controller, location) for controller in (0, 1) for location in LOCATION_ORDER}
    if observed_keys != expected_keys:
        _reject("unprojectable_shape", "zones", "canonical zone coverage is incomplete")
    zones.sort(key=lambda zone: (zone["controller"], zone["location"]))
    base_payload = {
        "field_state": field_state,
        "pending_request": pending_request,
        "phase": phase,
        "process_category": snapshot.process_state,
        "schema_version": PLAYER_VIEW_OBSERVATION_SCHEMA_VERSION,
        "turn": turn,
        "viewer": viewer,
        "zones": zones,
    }
    marker_scope = stable_digest(base_payload, prefix="obsscope_")
    for zone in zones:
        for card in zone.get("cards", []):
            if card.get("hidden") is not True:
                continue
            coordinate = (
                card["controller"],
                card["location"],
                card["sequence"],
            )
            card["hidden_marker"] = stable_digest(
                {"coordinate": coordinate, "scope": marker_scope, "viewer": viewer},
                prefix="hidden_",
            )
    observation_id = stable_digest(base_payload, prefix="observation_")
    return {"observation_id": observation_id, **to_canonical_data(base_payload)}


def _event_request(event: ReplayEventV03a, viewer: int) -> dict[str, Any] | None:
    if event.action.player != viewer:
        return None
    request = _mapping(event.request, f"events[{event.step}].request")
    request_type = request.get("request_type")
    if not isinstance(request_type, str) or request_type not in _KNOWN_REQUEST_TYPES:
        _reject(
            "unprojectable_shape",
            f"events[{event.step}].request.request_type",
            f"unsupported request type {request_type!r}",
        )
    constraints = _mapping(request.get("constraints"), f"events[{event.step}].request.constraints")
    required = frozenset(
        {"allow_duplicates", "max_selections", "min_selections", "ordered", "required"}
    )
    _exact_fields(constraints, required, f"events[{event.step}].request.constraints")
    for name in ("allow_duplicates", "ordered", "required"):
        if not isinstance(constraints[name], bool):
            _reject(
                "unprojectable_shape",
                f"events[{event.step}].request.constraints.{name}",
                "expected a boolean",
            )
    return {
        "constraints": {
            "allow_duplicates": constraints["allow_duplicates"],
            "max_selections": _integer(constraints["max_selections"], f"events[{event.step}].request.constraints.max_selections"),
            "min_selections": _integer(constraints["min_selections"], f"events[{event.step}].request.constraints.min_selections"),
            "ordered": constraints["ordered"],
            "required": constraints["required"],
        },
        "request_type": request_type,
    }


def project_player_view_event(
    event: ReplayEventV03a,
    *,
    viewer: int,
    before_observation_id: str,
    after_observation_id: str,
    phase: str,
) -> dict[str, Any]:
    if viewer not in (0, 1):
        raise ValueError("viewer must be 0 or 1")
    if event.turn is None:
        _reject("unprojectable_shape", f"events[{event.step}].turn", "turn is required")
    actor = event.action.player
    if actor not in (0, 1):
        _reject("unprojectable_shape", f"events[{event.step}].actor", "unknown actor")
    action_category = event.action.kind.value if actor == viewer else "OPPONENT_ACTION"
    payload = {
        "action_category": action_category,
        "actor": actor,
        "after_observation_id": after_observation_id,
        "before_observation_id": before_observation_id,
        "chain_index": event.chain_index,
        "phase": phase,
        "request": _event_request(event, viewer),
        "response": {"submitted": True} if actor == viewer else None,
        "schema_version": PLAYER_VIEW_EVENT_SCHEMA_VERSION,
        "step": event.step,
        "turn": event.turn,
    }
    return {
        "event_id": stable_digest(payload, prefix="playerviewevent_"),
        **to_canonical_data(payload),
    }


def _manifest(source_route: Mapping[str, Any]) -> dict[str, Any]:
    replay = _mapping(source_route.get("replay"), "source_route.replay")
    source_manifest = _mapping(replay.get("manifest"), "source_route.replay.manifest")
    environment = _mapping(source_manifest.get("environment"), "source_route.replay.manifest.environment")
    project = _mapping(environment.get("project"), "source_route.replay.manifest.environment.project")
    core = _mapping(environment.get("core"), "source_route.replay.manifest.environment.core")
    assets = _mapping(environment.get("assets"), "source_route.replay.manifest.environment.assets")
    for value, path in (
        (project.get("replay_schema"), "project.replay_schema"),
        (project.get("snapshot_schema"), "project.snapshot_schema"),
        (core.get("api"), "core.api"),
        (core.get("lock_id"), "core.lock_id"),
        (assets.get("lock_id"), "assets.lock_id"),
    ):
        if not isinstance(value, (str, int, list, tuple)) or value == "":
            _reject("unprojectable_shape", f"source_route.replay.manifest.environment.{path}", "missing public version metadata")
    return to_canonical_data(
        {
            "asset_lock_id": assets["lock_id"],
            "core_api": core["api"],
            "core_lock_id": core["lock_id"],
            "projector_id": PLAYER_VIEW_PROJECTOR_ID,
            "schema_version": PLAYER_VIEW_MANIFEST_SCHEMA_VERSION,
            "source_replay_schema_version": replay.get("schema_version"),
            "source_route_schema_version": source_route.get("schema_version"),
            "source_snapshot_schema_version": project["snapshot_schema"],
        }
    )


def _result(source_route: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(source_route.get("result"), "source_route.result")
    terminal = _mapping(result.get("terminal_board"), "source_route.result.terminal_board")
    peak = _mapping(result.get("peak_board"), "source_route.result.peak_board")
    required = ("phase", "score", "stop_reason", "success", "turn")
    for name in required:
        if name not in terminal or name not in peak:
            _reject("unprojectable_shape", "source_route.result", f"missing public result field {name!r}")
    return to_canonical_data(
        {
            "peak": {name: peak[name] for name in required},
            "success": bool(result.get("success")),
            "terminal": {name: terminal[name] for name in required},
        }
    )


def build_player_view_replay(data: PlayerViewProjectionInput) -> dict[str, Any]:
    if data.viewer not in (0, 1):
        raise ValueError("viewer must be 0 or 1")
    if len(data.events) != len(data.checkpoint_snapshots):
        _reject("unprojectable_shape", "events", "event and checkpoint counts differ")
    observations = [
        project_player_view_observation(
            data.initial_snapshot,
            viewer=data.viewer,
            turn=data.initial_turn,
            phase=data.initial_phase,
        )
    ]
    for snapshot, turn, phase in data.checkpoint_snapshots:
        observations.append(
            project_player_view_observation(
                snapshot,
                viewer=data.viewer,
                turn=turn,
                phase=phase,
            )
        )
    events = []
    for index, event in enumerate(data.events):
        if event.step != index:
            _reject("unprojectable_shape", f"events[{index}].step", "event steps must be contiguous")
        events.append(
            project_player_view_event(
                event,
                viewer=data.viewer,
                before_observation_id=observations[index]["observation_id"],
                after_observation_id=observations[index + 1]["observation_id"],
                phase=observations[index]["phase"],
            )
        )
    payload = {
        "events": events,
        "initial_observation": observations[0],
        "lineage": {
            "fork_step": data.fork_step,
            "parent_player_view_id": data.parent_player_view_id,
        },
        "manifest": _manifest(data.source_route),
        "result": _result(data.source_route),
        "schema_version": PLAYER_VIEW_REPLAY_SCHEMA_VERSION,
        "viewer": data.viewer,
    }
    return {
        "player_view_id": stable_digest(payload, prefix="playerview_"),
        **to_canonical_data(payload),
    }


def assert_valid_player_view_replay(document: Mapping[str, Any]) -> None:
    expected = frozenset(
        {
            "events",
            "initial_observation",
            "lineage",
            "manifest",
            "player_view_id",
            "result",
            "schema_version",
            "viewer",
        }
    )
    _exact_fields(document, expected, "player_view")
    if document["schema_version"] != PLAYER_VIEW_REPLAY_SCHEMA_VERSION:
        _reject("unprojectable_shape", "player_view.schema_version", "unsupported schema")
    identity = dict(document)
    supplied_id = identity.pop("player_view_id")
    expected_id = stable_digest(identity, prefix="playerview_")
    if supplied_id != expected_id:
        _reject("identity_mismatch", "player_view.player_view_id", "digest mismatch")
