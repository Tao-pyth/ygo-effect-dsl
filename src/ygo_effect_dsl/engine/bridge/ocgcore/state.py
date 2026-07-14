from __future__ import annotations

from dataclasses import dataclass, field
import struct
from typing import Any, Iterable, Mapping

from ygo_effect_dsl.engine.bridge import DecisionRequest
from ygo_effect_dsl.engine.bridge.ocgcore.errors import OcgcoreSnapshotError
from ygo_effect_dsl.engine.bridge.ocgcore.types import DuelState, Query
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.state import (
    CanonicalState,
    InformationMode,
    StateIdentityCompleteness,
)


SNAPSHOT_SCHEMA_VERSION = "ocgcore-query-v1"
CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION = "ocgcore-card-instance-snapshot-v2"
IDENTITY_COMPLETENESS = "query_api_projection"
MISSING_IDENTITY_FIELDS = (
    "effect_usage_history",
    "lua_global_state",
    "remaining_normal_summon_constraints",
    "temporary_rule_constraints_not_exposed_by_query_api",
)

LOCATION_DECK = 0x01
LOCATION_HAND = 0x02
LOCATION_MZONE = 0x04
LOCATION_SZONE = 0x08
LOCATION_GRAVE = 0x10
LOCATION_REMOVED = 0x20
LOCATION_EXTRA = 0x40
LOCATION_ORDER = (
    LOCATION_DECK,
    LOCATION_HAND,
    LOCATION_MZONE,
    LOCATION_SZONE,
    LOCATION_GRAVE,
    LOCATION_REMOVED,
    LOCATION_EXTRA,
)
LOCATION_NAMES = {
    LOCATION_DECK: "deck",
    LOCATION_HAND: "hand",
    LOCATION_MZONE: "monster_zone",
    LOCATION_SZONE: "spell_trap_zone",
    LOCATION_GRAVE: "graveyard",
    LOCATION_REMOVED: "banished",
    LOCATION_EXTRA: "extra_deck",
}

QUERY_CODE = 0x1
QUERY_POSITION = 0x2
QUERY_ALIAS = 0x4
QUERY_TYPE = 0x8
QUERY_LEVEL = 0x10
QUERY_RANK = 0x20
QUERY_ATTRIBUTE = 0x40
QUERY_RACE = 0x80
QUERY_ATTACK = 0x100
QUERY_DEFENSE = 0x200
QUERY_BASE_ATTACK = 0x400
QUERY_BASE_DEFENSE = 0x800
QUERY_REASON = 0x1000
QUERY_REASON_CARD = 0x2000
QUERY_EQUIP_CARD = 0x4000
QUERY_TARGET_CARD = 0x8000
QUERY_OVERLAY_CARD = 0x10000
QUERY_COUNTERS = 0x20000
QUERY_OWNER = 0x40000
QUERY_STATUS = 0x80000
QUERY_IS_PUBLIC = 0x100000
QUERY_LSCALE = 0x200000
QUERY_RSCALE = 0x400000
QUERY_LINK = 0x800000
QUERY_IS_HIDDEN = 0x1000000
QUERY_COVER = 0x2000000
QUERY_END = 0x80000000
QUERY_SNAPSHOT_FLAGS = 0x03FFFFFF

QUERY_NAMES = {
    QUERY_CODE: "code",
    QUERY_POSITION: "position",
    QUERY_ALIAS: "alias",
    QUERY_TYPE: "type",
    QUERY_LEVEL: "level",
    QUERY_RANK: "rank",
    QUERY_ATTRIBUTE: "attribute",
    QUERY_RACE: "race",
    QUERY_ATTACK: "attack",
    QUERY_DEFENSE: "defense",
    QUERY_BASE_ATTACK: "base_attack",
    QUERY_BASE_DEFENSE: "base_defense",
    QUERY_REASON: "reason",
    QUERY_REASON_CARD: "reason_card",
    QUERY_EQUIP_CARD: "equip_card",
    QUERY_TARGET_CARD: "target_cards",
    QUERY_OVERLAY_CARD: "overlay_cards",
    QUERY_COUNTERS: "counters",
    QUERY_OWNER: "owner",
    QUERY_STATUS: "status",
    QUERY_IS_PUBLIC: "is_public",
    QUERY_LSCALE: "left_scale",
    QUERY_RSCALE: "right_scale",
    QUERY_LINK: "link",
    QUERY_IS_HIDDEN: "is_hidden",
    QUERY_COVER: "cover",
    QUERY_END: "end",
}


class _Reader:
    def __init__(self, data: bytes, label: str) -> None:
        self.data = data
        self.label = label
        self.offset = 0

    def read(self, format_: str, field_name: str) -> int:
        size = struct.calcsize(format_)
        end = self.offset + size
        if end > len(self.data):
            raise OcgcoreSnapshotError(
                f"{self.label}.{field_name} is truncated at byte {self.offset}"
            )
        value = struct.unpack_from(format_, self.data, self.offset)[0]
        self.offset = end
        return int(value)

    def take(self, size: int, field_name: str) -> bytes:
        end = self.offset + size
        if size < 0 or end > len(self.data):
            raise OcgcoreSnapshotError(
                f"{self.label}.{field_name} is truncated at byte {self.offset}"
            )
        value = self.data[self.offset:end]
        self.offset = end
        return value

    def finish(self) -> None:
        if self.offset != len(self.data):
            raise OcgcoreSnapshotError(
                f"{self.label} has {len(self.data) - self.offset} trailing byte(s)"
            )


def _location_value(data: bytes) -> dict[str, int]:
    if len(data) != 10:
        raise OcgcoreSnapshotError("query location reference must contain 10 bytes")
    controller, location, sequence, position = struct.unpack("<BBII", data)
    return {
        "controller": controller,
        "location": location,
        "position": position,
        "sequence": sequence,
    }


def _counted_u32(data: bytes, label: str) -> list[int]:
    if len(data) < 4:
        raise OcgcoreSnapshotError(f"{label} count is truncated")
    count = struct.unpack_from("<I", data)[0]
    if len(data) != 4 + count * 4:
        raise OcgcoreSnapshotError(f"{label} payload length does not match its count")
    return list(struct.unpack_from(f"<{count}I", data, 4)) if count else []


def _decode_query_value(flag: int, payload: bytes) -> Any:
    if flag == QUERY_END:
        if payload:
            raise OcgcoreSnapshotError("QUERY_END must not contain a value")
        return None
    if flag in {QUERY_OWNER, QUERY_IS_PUBLIC, QUERY_IS_HIDDEN}:
        if len(payload) != 1:
            raise OcgcoreSnapshotError(f"query flag {flag:#x} must contain uint8")
        return payload[0]
    if flag == QUERY_RACE:
        if len(payload) != 8:
            raise OcgcoreSnapshotError("QUERY_RACE must contain uint64")
        return struct.unpack("<Q", payload)[0]
    if flag in {QUERY_ATTACK, QUERY_DEFENSE, QUERY_BASE_ATTACK, QUERY_BASE_DEFENSE}:
        if len(payload) != 4:
            raise OcgcoreSnapshotError(f"query flag {flag:#x} must contain int32")
        return struct.unpack("<i", payload)[0]
    if flag in {
        QUERY_CODE,
        QUERY_POSITION,
        QUERY_ALIAS,
        QUERY_TYPE,
        QUERY_LEVEL,
        QUERY_RANK,
        QUERY_ATTRIBUTE,
        QUERY_REASON,
        QUERY_STATUS,
        QUERY_LSCALE,
        QUERY_RSCALE,
        QUERY_COVER,
    }:
        if len(payload) != 4:
            raise OcgcoreSnapshotError(f"query flag {flag:#x} must contain uint32")
        return struct.unpack("<I", payload)[0]
    if flag in {QUERY_REASON_CARD, QUERY_EQUIP_CARD}:
        return _location_value(payload)
    if flag == QUERY_TARGET_CARD:
        if len(payload) < 4:
            raise OcgcoreSnapshotError("QUERY_TARGET_CARD count is truncated")
        count = struct.unpack_from("<I", payload)[0]
        if len(payload) != 4 + count * 10:
            raise OcgcoreSnapshotError(
                "QUERY_TARGET_CARD payload length does not match its count"
            )
        return [
            _location_value(payload[4 + index * 10 : 14 + index * 10])
            for index in range(count)
        ]
    if flag == QUERY_OVERLAY_CARD:
        return _counted_u32(payload, "QUERY_OVERLAY_CARD")
    if flag == QUERY_COUNTERS:
        values = _counted_u32(payload, "QUERY_COUNTERS")
        return [
            {"count": value >> 16, "counter_type": value & 0xFFFF}
            for value in values
        ]
    if flag == QUERY_LINK:
        if len(payload) != 8:
            raise OcgcoreSnapshotError("QUERY_LINK must contain two uint32 values")
        rating, markers = struct.unpack("<II", payload)
        return {"markers": markers, "rating": rating}
    return {"hex": payload.hex()}


def decode_query_location(
    data: bytes, *, controller: int, location: int
) -> tuple[dict[str, Any] | None, ...]:
    reader = _Reader(data, f"query_location[{controller},{location:#x}]")
    declared = reader.read("<I", "payload_length")
    if declared != len(data) - 4:
        raise OcgcoreSnapshotError(
            "query location payload length does not match its header"
        )
    cards: list[dict[str, Any] | None] = []
    fields: list[dict[str, Any]] = []
    while reader.offset < len(data):
        segment_length = reader.read("<H", "segment_length")
        if segment_length == 0:
            if fields:
                raise OcgcoreSnapshotError("empty query slot appeared inside a card record")
            cards.append(None)
            continue
        if segment_length < 4:
            raise OcgcoreSnapshotError("query segment must include a uint32 flag")
        segment = _Reader(reader.take(segment_length, "segment"), "query_segment")
        flag = segment.read("<I", "flag")
        payload = segment.take(segment_length - 4, "value")
        segment.finish()
        if flag == QUERY_END:
            _decode_query_value(flag, payload)
            cards.append(
                {
                    "controller": controller,
                    "fields": sorted(fields, key=lambda item: int(item["flag"])),
                    "instance_key": f"{controller}:{location}:{len(cards)}",
                    "location": location,
                    "slot": len(cards),
                }
            )
            fields = []
            continue
        if any(item["flag"] == flag for item in fields):
            raise OcgcoreSnapshotError(f"query card repeats flag {flag:#x}")
        fields.append(
            {
                "flag": flag,
                "name": QUERY_NAMES.get(flag, f"unknown_{flag:#x}"),
                "value": _decode_query_value(flag, payload),
            }
        )
    if fields:
        raise OcgcoreSnapshotError("query card record is missing QUERY_END")
    reader.finish()
    return tuple(cards)


def _decode_field_slots(reader: _Reader, count: int, label: str) -> list[dict[str, int] | None]:
    slots: list[dict[str, int] | None] = []
    for index in range(count):
        occupied = reader.read("<B", f"{label}[{index}].occupied")
        if occupied == 0:
            slots.append(None)
            continue
        if occupied != 1:
            raise OcgcoreSnapshotError(f"{label}[{index}].occupied must be 0 or 1")
        position = reader.read("<B", f"{label}[{index}].position")
        overlay_count = reader.read("<I", f"{label}[{index}].overlay_count")
        slots.append(
            {
                "overlay_count": overlay_count,
                "position": position,
            }
        )
    return slots


def decode_query_field(data: bytes) -> dict[str, Any]:
    reader = _Reader(data, "query_field")
    duel_options = reader.read("<I", "duel_options")
    players: list[dict[str, Any]] = []
    for player in range(2):
        life_points = reader.read("<I", f"players[{player}].life_points")
        monster_zones = _decode_field_slots(reader, 7, f"players[{player}].monster_zones")
        spell_trap_zones = _decode_field_slots(
            reader, 8, f"players[{player}].spell_trap_zones"
        )
        counts = {
            name: reader.read("<I", f"players[{player}].{name}")
            for name in (
                "deck_count",
                "hand_count",
                "graveyard_count",
                "banished_count",
                "extra_deck_count",
                "face_up_extra_count",
            )
        }
        players.append(
            {
                **counts,
                "life_points": life_points,
                "monster_zones": monster_zones,
                "player": player,
                "spell_trap_zones": spell_trap_zones,
            }
        )
    chain_count = reader.read("<I", "chain_count")
    chain: list[dict[str, Any]] = []
    for index in range(chain_count):
        handler_code = reader.read("<I", f"chain[{index}].handler.code")
        handler_controller = reader.read("<B", f"chain[{index}].handler.controller")
        handler_location = reader.read("<B", f"chain[{index}].handler.location")
        handler_sequence = reader.read("<I", f"chain[{index}].handler.sequence")
        handler_position = reader.read("<I", f"chain[{index}].handler.position")
        triggering_controller = reader.read(
            "<B", f"chain[{index}].triggering_controller"
        )
        triggering_location = reader.read(
            "<B", f"chain[{index}].triggering_location"
        )
        triggering_sequence = reader.read(
            "<I", f"chain[{index}].triggering_sequence"
        )
        description = reader.read("<Q", f"chain[{index}].description")
        chain.append(
            {
                "description": description,
                "handler": {
                    "code": handler_code,
                    "controller": handler_controller,
                    "location": handler_location,
                    "position": handler_position,
                    "sequence": handler_sequence,
                },
                "triggering_controller": triggering_controller,
                "triggering_location": triggering_location,
                "triggering_sequence": triggering_sequence,
            }
        )
    reader.finish()
    return {
        "chain": chain,
        "chain_count": chain_count,
        "duel_options": duel_options,
        "players": players,
    }


def _field_value(card: Mapping[str, Any], name: str) -> Any:
    for item in card.get("fields", []):
        if item.get("name") == name:
            return item.get("value")
    return None


@dataclass(frozen=True)
class CompleteSnapshot:
    environment: Mapping[str, Any]
    field_state: Mapping[str, Any]
    zones: tuple[Mapping[str, Any], ...]
    process_state: str
    pending_request: Mapping[str, Any] | None
    identity_completeness: str = IDENTITY_COMPLETENESS
    missing_identity_fields: tuple[str, ...] = MISSING_IDENTITY_FIELDS
    display_metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)
    information_mode: InformationMode = InformationMode.COMPLETE_INFORMATION
    sampling_reference: Mapping[str, Any] | None = None
    card_instance_schema_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.information_mode, InformationMode):
            object.__setattr__(
                self, "information_mode", InformationMode(self.information_mode)
            )
        if self.sampling_reference is not None and not isinstance(
            self.sampling_reference, Mapping
        ):
            raise ValueError("sampling_reference must be a mapping or None")
        if (
            self.information_mode == InformationMode.SAMPLED_PRIVATE_STATE
            and self.sampling_reference is None
        ):
            raise ValueError("sampled_private_state requires sampling_reference")
        if self.card_instance_schema_version not in {
            None,
            CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported card instance snapshot schema")

    def to_state_identity(self) -> CanonicalState:
        engine_state = {
            "environment": self.environment,
            "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        }
        if self.card_instance_schema_version is not None:
            engine_state["card_instance_schema_version"] = (
                self.card_instance_schema_version
            )
        return CanonicalState(
            public_state={
                "field_state": self.field_state,
                "process_state": self.process_state,
            },
            private_state={"zones": self.zones},
            constraints={
                "observation_status": "unavailable_from_ocgcore_query_api",
            },
            history={
                "chain": self.field_state.get("chain", []),
                "effect_usage_observation_status": (
                    "unavailable_from_ocgcore_query_api"
                ),
            },
            pending_request=self.pending_request,
            engine_state=engine_state,
            information_mode=self.information_mode,
            sampling_reference=self.sampling_reference,
            completeness=StateIdentityCompleteness(self.identity_completeness),
            missing_fields=self.missing_identity_fields,
        )

    def to_identity_dict(self) -> dict[str, Any]:
        return self.to_state_identity().to_identity_dict()

    @property
    def state_hash(self) -> str:
        return stable_digest(self.to_identity_dict(), prefix="state_")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "environment": to_canonical_data(self.environment),
            "field_state": to_canonical_data(self.field_state),
            "identity_completeness": self.identity_completeness,
            "missing_identity_fields": list(self.missing_identity_fields),
            "pending_request": to_canonical_data(self.pending_request),
            "process_state": self.process_state,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "state_identity": self.to_state_identity().to_dict(),
            "zones": to_canonical_data(self.zones),
            "display_metadata": to_canonical_data(self.display_metadata),
            "state_hash": self.state_hash,
        }
        if self.card_instance_schema_version is not None:
            result["card_instance_schema_version"] = (
                self.card_instance_schema_version
            )
        return result


@dataclass(frozen=True)
class VisibleSnapshot:
    viewer: int
    data: Mapping[str, Any]

    @property
    def visible_hash(self) -> str:
        return stable_digest(
            {
                "data": self.data,
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "viewer": self.viewer,
            },
            prefix="visible_",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": to_canonical_data(self.data),
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "viewer": self.viewer,
            "visible_hash": self.visible_hash,
        }


@dataclass(frozen=True)
class SearchProjection:
    information_mode: str
    data: Mapping[str, Any]
    exact_equivalence: bool = False

    @property
    def projection_hash(self) -> str:
        return stable_digest(
            {
                "data": self.data,
                "exact_equivalence": self.exact_equivalence,
                "information_mode": self.information_mode,
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
            },
            prefix="search_",
        )


@dataclass(frozen=True)
class BoardSummary:
    data: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(self.data)


@dataclass(frozen=True)
class LegalStopDecision:
    can_stop: bool
    reason: str
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_stop": self.can_stop,
            "evidence": to_canonical_data(self.evidence),
            "reason": self.reason,
        }


class OcgcoreStateAdapter:
    def capture(
        self,
        duel: Any,
        *,
        pending_request: DecisionRequest | None,
        environment: Mapping[str, Any],
        locations: Iterable[int] = LOCATION_ORDER,
        display_metadata: Mapping[str, Any] | None = None,
        information_mode: InformationMode | str = InformationMode.COMPLETE_INFORMATION,
        sampling_reference: Mapping[str, Any] | None = None,
    ) -> CompleteSnapshot:
        requested_locations = tuple(locations)
        if len(requested_locations) != len(set(requested_locations)) or set(
            requested_locations
        ) != set(LOCATION_ORDER):
            raise OcgcoreSnapshotError(
                "complete snapshot requires every canonical location exactly once"
            )
        field_state = decode_query_field(duel.query_field())
        zones: list[dict[str, Any]] = []
        for controller in (0, 1):
            for location in requested_locations:
                cards = decode_query_location(
                    duel.query_location(
                        Query(flags=QUERY_SNAPSHOT_FLAGS, controller=controller, location=location)
                    ),
                    controller=controller,
                    location=location,
                )
                expected_slots = {
                    LOCATION_MZONE: 7,
                    LOCATION_SZONE: 8,
                }.get(location)
                if expected_slots is not None and len(cards) != expected_slots:
                    raise OcgcoreSnapshotError(
                        f"query location for player={controller} location={location:#x} "
                        f"returned {len(cards)} slots; expected {expected_slots}"
                    )
                observed_count = sum(card is not None for card in cards)
                native_count = duel.query_count(controller, location)
                if observed_count != native_count:
                    raise OcgcoreSnapshotError(
                        f"query count mismatch for player={controller} location={location:#x}: "
                        f"location returned {observed_count}, count returned {native_count}"
                    )
                zones.append(
                    {
                        "cards": cards,
                        "controller": controller,
                        "location": location,
                        "location_name": LOCATION_NAMES[location],
                    }
                )
        zones.sort(key=lambda zone: (int(zone["controller"]), int(zone["location"])))
        pending = None
        if pending_request is not None:
            pending = {
                "candidate_action_kinds": [
                    candidate.payload.get("action_kind")
                    for candidate in pending_request.candidates
                ],
                "candidate_ids": [
                    candidate.candidate_id for candidate in pending_request.candidates
                ],
                "forced": pending_request.context.extra.get("forced") is True,
                "player": pending_request.player,
                "request_signature": pending_request.request_signature,
                "request_type": pending_request.request_type,
            }
        return CompleteSnapshot(
            environment=dict(environment),
            field_state=field_state,
            zones=tuple(zones),
            process_state=duel.state.value,
            pending_request=pending,
            information_mode=InformationMode(information_mode),
            sampling_reference=sampling_reference,
            display_metadata=dict(display_metadata or {}),
        )


def project_visible(snapshot: CompleteSnapshot, *, viewer: int) -> VisibleSnapshot:
    if viewer not in (0, 1):
        raise ValueError("viewer must be 0 or 1")
    zones: list[dict[str, Any]] = []
    for zone in snapshot.zones:
        controller = int(zone["controller"])
        location = int(zone["location"])
        projected_cards: list[dict[str, Any] | None] = []
        for card in zone["cards"]:
            if card is None:
                projected_cards.append(None)
                continue
            is_visible = (
                _field_value(card, "is_hidden") != 1
                and location != LOCATION_DECK
                and (controller == viewer or _field_value(card, "is_public") == 1)
            )
            if is_visible:
                projected = dict(card)
                player_view_ids = projected.pop("player_view_instance_ids", None)
                if controller != viewer and "persistent_instance_id" in projected:
                    if not isinstance(player_view_ids, Mapping):
                        raise OcgcoreSnapshotError(
                            "opponent card identity requires viewer-scoped projection"
                        )
                    viewer_instance_id = player_view_ids.get(str(viewer))
                    if not isinstance(viewer_instance_id, str):
                        raise OcgcoreSnapshotError(
                            "visible opponent card has no viewer-scoped identity"
                        )
                    projected.pop("persistent_instance_id", None)
                    projected["viewer_instance_id"] = viewer_instance_id
                projected_cards.append(projected)
            else:
                projected_cards.append({"hidden": True, "slot": card["slot"]})
        zones.append(
            {
                "cards": projected_cards,
                "controller": controller,
                "location": location,
                "location_name": zone["location_name"],
            }
        )
    pending_request = None
    if (
        snapshot.pending_request is not None
        and snapshot.pending_request.get("player") == viewer
    ):
        pending_request = dict(snapshot.pending_request)
        if snapshot.card_instance_schema_version is not None:
            request_observation_id = pending_request.get("request_observation_id")
            if not isinstance(request_observation_id, str):
                raise OcgcoreSnapshotError(
                    "card instance v2 PlayerView requires request_observation_id"
                )
            pending_request.pop("request_signature", None)
    return VisibleSnapshot(
        viewer=viewer,
        data={
            "field_state": snapshot.field_state,
            "pending_request": pending_request,
            "process_state": snapshot.process_state,
            "zones": zones,
        },
    )


def build_search_projection(
    snapshot: CompleteSnapshot,
    *,
    information_mode: str,
    viewer: int = 0,
) -> SearchProjection:
    if information_mode == "complete_information":
        data = snapshot.to_identity_dict()
    elif information_mode == "visible_information":
        data = project_visible(snapshot, viewer=viewer).to_dict()
    else:
        raise ValueError("information_mode must be complete_information or visible_information")
    return SearchProjection(
        information_mode=information_mode,
        data=data,
        exact_equivalence=False,
    )


def build_board_summary(snapshot: CompleteSnapshot, *, viewer: int = 0) -> BoardSummary:
    visible = project_visible(snapshot, viewer=viewer)
    public_cards: list[dict[str, Any]] = []
    zone_counts: dict[str, dict[str, int]] = {"0": {}, "1": {}}
    for zone in visible.data["zones"]:
        cards = [card for card in zone["cards"] if card is not None]
        zone_counts[str(zone["controller"])][str(zone["location_name"])] = len(cards)
        for card in cards:
            if card.get("hidden"):
                continue
            public_cards.append(
                {
                    "code": _field_value(card, "code"),
                    "controller": zone["controller"],
                    "location": zone["location"],
                    "position": _field_value(card, "position"),
                    "slot": card["slot"],
                }
            )
    return BoardSummary(
        data={
            "life_points": {
                str(player["player"]): player["life_points"]
                for player in snapshot.field_state["players"]
            },
            "public_cards": public_cards,
            "state_hash": snapshot.state_hash,
            "zone_counts": zone_counts,
        }
    )


def evaluate_legal_stop(snapshot: CompleteSnapshot) -> LegalStopDecision:
    evidence = {
        "chain_count": snapshot.field_state["chain_count"],
        "pending_request_type": (
            snapshot.pending_request.get("request_type")
            if snapshot.pending_request
            else None
        ),
        "process_state": snapshot.process_state,
        "state_hash": snapshot.state_hash,
    }
    if snapshot.field_state["chain_count"]:
        return LegalStopDecision(False, "chain_active", evidence)
    if snapshot.process_state == DuelState.ENDED.value:
        return LegalStopDecision(True, "terminal", evidence)
    if snapshot.process_state != DuelState.AWAITING_RESPONSE.value:
        return LegalStopDecision(False, "mandatory_processing", evidence)
    pending = snapshot.pending_request
    if pending is None:
        return LegalStopDecision(False, "pending_request_missing", evidence)
    if pending.get("forced"):
        return LegalStopDecision(False, "mandatory_request", evidence)
    if pending.get("request_type") != "select_idle_command":
        return LegalStopDecision(False, "pending_request", evidence)
    if "control:end_turn" not in pending.get("candidate_ids", []):
        return LegalStopDecision(False, "end_turn_unavailable", evidence)
    return LegalStopDecision(
        True,
        "core_end_turn_available",
        {
            **evidence,
            "core_control_candidate": "control:end_turn",
            "stop_action_kind": "STOP_LINE",
        },
    )
