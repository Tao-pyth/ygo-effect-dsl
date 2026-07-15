from __future__ import annotations

from collections.abc import Mapping
from enum import IntEnum
from hashlib import sha256
import struct
from typing import Any

from ygo_effect_dsl.engine.bridge.errors import InvalidBridgeMessageError
from ygo_effect_dsl.engine.bridge.ocgcore.protocol import (
    DecodedMessageBatch,
    MessageFrame,
)
from ygo_effect_dsl.engine.bridge.ocgcore.random_trace import (
    extract_direct_random_draws,
    extract_direct_random_log_draws,
)
from ygo_effect_dsl.engine.bridge.ocgcore.state import (
    LOCATION_DECK,
    LOCATION_EXTRA,
    LOCATION_HAND,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


CORE_OUTPUT_TRACE_SCHEMA_VERSION = "ocgcore-output-trace-v2"
RANDOM_EVENT_TRACE_SCHEMA_VERSION = "ocgcore-random-event-v2"
PROGRESS_EVENT_TRACE_SCHEMA_VERSION = "ocgcore-progress-event-v1"
TERMINAL_EVENT_TRACE_SCHEMA_VERSION = "ocgcore-terminal-event-v1"
CROSS_CHANNEL_ORDERING_SCHEMA_VERSION = "ocgcore-cross-channel-ordering-v1"


class RandomMessageType(IntEnum):
    SHUFFLE_DECK = 32
    SHUFFLE_HAND = 33
    SHUFFLE_SET_CARD = 36
    SHUFFLE_EXTRA = 39
    RANDOM_SELECTED = 81
    TOSS_COIN = 130
    TOSS_DICE = 131


class ProgressMessageType(IntEnum):
    NEW_TURN = 40
    NEW_PHASE = 41


class TerminalMessageType(IntEnum):
    WIN = 5


PHASE_NAMES = {
    0x01: "draw",
    0x02: "standby",
    0x04: "main1",
    0x08: "battle_start",
    0x10: "battle_step",
    0x20: "damage",
    0x40: "damage_calculation",
    0x80: "battle",
    0x100: "main2",
    0x200: "end",
}


def build_cross_channel_ordering_evidence(
    random_events: list[Mapping[str, Any]],
    *,
    native_process_call_count: int,
) -> dict[str, Any]:
    if native_process_call_count != 1:
        raise ValueError(
            "cross-channel ordering evidence requires exactly one native process call"
        )
    script_events = [
        event for event in random_events if event.get("log_sequence") is not None
    ]
    frame_events = [
        event for event in random_events if event.get("frame_index") is not None
    ]
    if not script_events or not frame_events:
        raise ValueError("cross-channel ordering evidence requires both domains")
    identity = {
        "canonical_storage_order": [
            "script_log_callback_by_log_sequence",
            "core_message_buffer_by_frame_index",
        ],
        "cross_domain_chronology": "unavailable",
        "domains": [
            {
                "coordinate_field": "log_sequence",
                "coordinates": [event["log_sequence"] for event in script_events],
                "domain": "script_log_callback",
                "event_ids": [event["random_event_id"] for event in script_events],
            },
            {
                "coordinate_field": "frame_index",
                "coordinates": [event["frame_index"] for event in frame_events],
                "domain": "core_message_buffer",
                "event_ids": [event["random_event_id"] for event in frame_events],
            },
        ],
        "native_process_call_count": native_process_call_count,
        "scope": "single_ocg_duel_process_call",
        "schema_version": CROSS_CHANNEL_ORDERING_SCHEMA_VERSION,
        "semantics": "canonical_storage_order_is_not_observed_emission_order",
    }
    return {
        **to_canonical_data(identity),
        "ordering_id": stable_digest(identity, prefix="crossord_"),
    }


def assert_cross_channel_ordering_evidence(
    value: Mapping[str, Any],
    random_events: list[Mapping[str, Any]],
    *,
    native_process_call_count: int,
) -> None:
    expected = build_cross_channel_ordering_evidence(
        random_events,
        native_process_call_count=native_process_call_count,
    )
    if to_canonical_data(value) != expected:
        raise ValueError("cross-channel ordering evidence mismatch")


class _TraceReader:
    def __init__(self, frame: MessageFrame) -> None:
        self.frame = frame
        self.offset = 0

    def read(self, format_: str, label: str) -> int:
        size = struct.calcsize(format_)
        end = self.offset + size
        if end > len(self.frame.payload):
            raise InvalidBridgeMessageError(
                f"trace message {self.frame.message_type}.{label} is truncated "
                f"at byte {self.offset}"
            )
        value = struct.unpack_from(format_, self.frame.payload, self.offset)[0]
        self.offset = end
        return int(value)

    def u8(self, label: str) -> int:
        return self.read("<B", label)

    def u16(self, label: str) -> int:
        return self.read("<H", label)

    def u32(self, label: str) -> int:
        return self.read("<I", label)

    def location(self, label: str) -> dict[str, int]:
        return {
            "controller": self.u8(f"{label}.controller"),
            "location": self.u8(f"{label}.location"),
            "sequence": self.u32(f"{label}.sequence"),
            "position": self.u32(f"{label}.position"),
        }

    def finish(self) -> None:
        if self.offset != len(self.frame.payload):
            raise InvalidBridgeMessageError(
                f"trace message {self.frame.message_type} has "
                f"{len(self.frame.payload) - self.offset} trailing byte(s)"
            )


def _player(reader: _TraceReader, label: str = "player") -> int:
    value = reader.u8(label)
    if value not in (0, 1):
        raise InvalidBridgeMessageError(
            f"trace message {reader.frame.message_type}.{label} must be 0 or 1"
        )
    return value


def _zone_order(
    snapshot: Mapping[str, Any], controller: int, location: int
) -> list[Any]:
    zones = snapshot.get("zones", [])
    if not isinstance(zones, list):
        return []
    for zone in zones:
        if not isinstance(zone, Mapping):
            continue
        if zone.get("controller") == controller and zone.get("location") == location:
            cards = zone.get("cards", [])
            return to_canonical_data(cards) if isinstance(cards, list) else []
    return []


def _random_outcome(
    frame: MessageFrame,
    snapshot: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    reader = _TraceReader(frame)
    message_type = RandomMessageType(frame.message_type)
    if message_type == RandomMessageType.SHUFFLE_DECK:
        player = _player(reader)
        reader.finish()
        return "shuffle_deck", {
            "player": player,
            "zone_order": _zone_order(snapshot, player, LOCATION_DECK),
        }
    if message_type in {
        RandomMessageType.SHUFFLE_HAND,
        RandomMessageType.SHUFFLE_EXTRA,
    }:
        player = _player(reader)
        count = reader.u32("count")
        codes = [reader.u32(f"codes[{index}]") for index in range(count)]
        reader.finish()
        location = (
            LOCATION_HAND
            if message_type == RandomMessageType.SHUFFLE_HAND
            else LOCATION_EXTRA
        )
        return (
            "shuffle_hand"
            if message_type == RandomMessageType.SHUFFLE_HAND
            else "shuffle_extra"
        ), {
            "codes": codes,
            "player": player,
            "zone_order": _zone_order(snapshot, player, location),
        }
    if message_type == RandomMessageType.SHUFFLE_SET_CARD:
        location = reader.u8("location")
        count = reader.u8("count")
        before = [reader.location(f"before[{index}]") for index in range(count)]
        after = [reader.location(f"after[{index}]") for index in range(count)]
        reader.finish()
        return "shuffle_set_card", {
            "after": after,
            "before": before,
            "count": count,
            "location": location,
        }
    if message_type == RandomMessageType.RANDOM_SELECTED:
        player = _player(reader)
        count = reader.u32("count")
        selected = [reader.location(f"selected[{index}]") for index in range(count)]
        reader.finish()
        return "random_selected", {"player": player, "selected": selected}
    if message_type in {RandomMessageType.TOSS_COIN, RandomMessageType.TOSS_DICE}:
        player = _player(reader)
        count = reader.u8("count")
        results = [reader.u8(f"results[{index}]") for index in range(count)]
        reader.finish()
        if message_type == RandomMessageType.TOSS_COIN and any(
            result not in (0, 1) for result in results
        ):
            raise InvalidBridgeMessageError("coin result must be 0 or 1")
        if message_type == RandomMessageType.TOSS_DICE and any(
            not 1 <= result <= 6 for result in results
        ):
            raise InvalidBridgeMessageError("dice result must be between 1 and 6")
        return (
            "toss_coin"
            if message_type == RandomMessageType.TOSS_COIN
            else "toss_dice"
        ), {"player": player, "results": results}
    raise InvalidBridgeMessageError(
        f"unsupported random message type {frame.message_type}"
    )


def _progress_outcome(frame: MessageFrame) -> tuple[str, dict[str, Any]]:
    reader = _TraceReader(frame)
    message_type = ProgressMessageType(frame.message_type)
    if message_type == ProgressMessageType.NEW_TURN:
        turn_player = _player(reader, "turn_player")
        reader.finish()
        return "new_turn", {"turn_player": turn_player}
    phase = reader.u16("phase")
    reader.finish()
    phase_name = PHASE_NAMES.get(phase)
    if phase_name is None:
        raise InvalidBridgeMessageError(f"unknown phase value {phase:#x}")
    return "new_phase", {"phase": phase, "phase_name": phase_name}


def _terminal_outcome(frame: MessageFrame) -> dict[str, Any]:
    reader = _TraceReader(frame)
    winner = reader.u8("winner")
    reason_code = reader.u8("reason")
    reader.finish()
    if winner not in (0, 1, 2):
        raise InvalidBridgeMessageError(
            f"trace message {frame.message_type}.winner must be 0, 1, or 2"
        )
    return {
        "outcome": "draw" if winner == 2 else "win",
        "reason_category": {
            1: "life_points_zero",
            2: "deck_out",
        }.get(reason_code, "core_defined"),
        "reason_code": reason_code,
        "winner_player": None if winner == 2 else winner,
    }


def build_core_output_trace(
    batch: DecodedMessageBatch,
    *,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    state_hash = snapshot.get("state_hash")
    if not isinstance(state_hash, str) or not state_hash:
        raise ValueError("snapshot.state_hash must be a non-empty string")
    frames = [
        {
            "frame_index": index,
            "message_type": frame.message_type,
            "payload_hex": frame.payload.hex(),
            "payload_sha256": sha256(frame.payload).hexdigest(),
        }
        for index, frame in enumerate(batch.frames)
    ]
    logs = [
        {
            "log_index": index,
            "log_type": log.log_type.name.lower(),
            "message": log.message,
            "message_sha256": sha256(log.message.encode("utf-8")).hexdigest(),
            "sequence": log.sequence,
        }
        for index, log in enumerate(batch.logs)
    ]
    random_events: list[dict[str, Any]] = []
    progress_events: list[dict[str, Any]] = []
    terminal_events: list[dict[str, Any]] = []
    random_types = {int(value) for value in RandomMessageType}
    progress_types = {int(value) for value in ProgressMessageType}
    terminal_types = {int(value) for value in TerminalMessageType}
    legacy_direct_draws = extract_direct_random_draws(batch.frames)
    if legacy_direct_draws:
        raise InvalidBridgeMessageError(
            "legacy Hint direct random packets are forbidden in output trace v2"
        )
    for draw in extract_direct_random_log_draws(batch.logs):
        identity = {
            "kind": "direct_lua_random",
            "log_index": draw.log_index,
            "log_sequence": draw.log_sequence,
            "message_type": None,
            "outcome": draw.outcome_dict(),
            "resulting_state_hash": state_hash,
            "schema_version": RANDOM_EVENT_TRACE_SCHEMA_VERSION,
            "transport": "ocgcore_log_handler_from_script_v1",
        }
        random_events.append(
            {
                **to_canonical_data(identity),
                "random_event_id": stable_digest(identity, prefix="rnd_"),
            }
        )
    for frame_index, frame in enumerate(batch.frames):
        if frame.message_type in random_types:
            kind, outcome = _random_outcome(frame, snapshot)
            identity = {
                "frame_index": frame_index,
                "kind": kind,
                "message_type": frame.message_type,
                "outcome": outcome,
                "resulting_state_hash": state_hash,
                "schema_version": RANDOM_EVENT_TRACE_SCHEMA_VERSION,
            }
            random_events.append(
                {
                    **to_canonical_data(identity),
                    "random_event_id": stable_digest(identity, prefix="rnd_"),
                }
            )
        if frame.message_type in progress_types:
            kind, outcome = _progress_outcome(frame)
            identity = {
                "frame_index": frame_index,
                "kind": kind,
                "message_type": frame.message_type,
                "outcome": outcome,
                "resulting_state_hash": state_hash,
                "schema_version": PROGRESS_EVENT_TRACE_SCHEMA_VERSION,
            }
            progress_events.append(
                {
                    **to_canonical_data(identity),
                    "progress_event_id": stable_digest(identity, prefix="prog_"),
                }
            )
        if frame.message_type in terminal_types:
            outcome = _terminal_outcome(frame)
            identity = {
                "frame_index": frame_index,
                "message_type": frame.message_type,
                **outcome,
                "resulting_state_hash": state_hash,
                "schema_version": TERMINAL_EVENT_TRACE_SCHEMA_VERSION,
            }
            terminal_events.append(
                {
                    **to_canonical_data(identity),
                    "terminal_event_id": stable_digest(identity, prefix="terminal_"),
                }
            )
    identity = {
        "frames": frames,
        "logs": logs,
        "progress_events": progress_events,
        "random_events": random_events,
        "request_signature": (
            batch.request.request_signature if batch.request is not None else None
        ),
        "resulting_state_hash": state_hash,
        "schema_version": CORE_OUTPUT_TRACE_SCHEMA_VERSION,
    }
    if terminal_events:
        identity["terminal_events"] = terminal_events
    return {**to_canonical_data(identity), "batch_id": stable_digest(identity, prefix="batch_")}
