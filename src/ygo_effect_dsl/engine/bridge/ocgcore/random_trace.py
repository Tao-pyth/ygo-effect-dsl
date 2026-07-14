from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
import struct
from typing import Sequence

from ygo_effect_dsl.engine.bridge.errors import InvalidBridgeMessageError
from ygo_effect_dsl.engine.bridge.ocgcore.protocol import MessageFrame
from ygo_effect_dsl.engine.bridge.ocgcore.types import CoreLog, LogType
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


DIRECT_RANDOM_TRACE_SCHEMA_VERSION = "ocgcore-direct-random-trace-v2"
DIRECT_RANDOM_TRACE_SCRIPT_NAME = "ygo_effect_dsl_direct_random_trace.lua"
DIRECT_RANDOM_TRACE_TRANSPORT = "ocgcore_log_handler_from_script_v1"
DIRECT_RANDOM_TRACE_LOG_PREFIX = "YGO_EFFECT_DSL_RNG_V2"
DIRECT_RANDOM_TRACE_HINT_TYPE = 199
DIRECT_RANDOM_TRACE_MARKER = 0x59474F524E475631
DIRECT_RANDOM_TRACE_PACKET_COUNT = 5
_UINT32_MAX = (1 << 32) - 1

DIRECT_RANDOM_TRACE_LUA_SOURCE = b"""local original_get_random_number = Duel.GetRandomNumber
local trace_prefix = "YGO_EFFECT_DSL_RNG_V2"
local draw_index = 0

Duel.GetRandomNumber = function(...)
    local argument_count = select("#", ...)
    local minimum
    local maximum
    if argument_count == 1 then
        minimum = 0
        maximum = select(1, ...)
    else
        minimum = select(1, ...)
        maximum = select(2, ...)
    end
    local result = original_get_random_number(...)
    draw_index = draw_index + 1
    Debug.Message(table.concat({
        trace_prefix,
        tostring(draw_index),
        tostring(minimum),
        tostring(maximum),
        tostring(result)
    }, "|"))
    return result
end
"""
DIRECT_RANDOM_TRACE_SCRIPT_SHA256 = sha256(DIRECT_RANDOM_TRACE_LUA_SOURCE).hexdigest()
_LOG_PATTERN = re.compile(
    rf"^{DIRECT_RANDOM_TRACE_LOG_PREFIX}\|([1-9][0-9]*)\|"
    r"(-?[0-9]+)\|(-?[0-9]+)\|(-?[0-9]+)$"
)
_INT32_MIN = -(1 << 31)
_INT32_MAX = (1 << 31) - 1


@dataclass(frozen=True)
class DirectRandomDraw:
    draw_index: int
    frame_indices: tuple[int, ...]
    minimum: int
    maximum: int
    result: int

    @property
    def frame_index(self) -> int:
        return self.frame_indices[0]

    def outcome_dict(self) -> dict[str, int]:
        return {
            "draw_index": self.draw_index,
            "maximum": self.maximum,
            "minimum": self.minimum,
            "result": self.result,
        }


@dataclass(frozen=True)
class DirectRandomLogDraw:
    draw_index: int
    log_index: int
    log_sequence: int
    minimum: int
    maximum: int
    result: int

    def outcome_dict(self) -> dict[str, int]:
        return {
            "draw_index": self.draw_index,
            "maximum": self.maximum,
            "minimum": self.minimum,
            "result": self.result,
        }


def direct_random_trace_metadata(*, enabled: bool) -> dict[str, object]:
    identity = {
        "enabled": enabled,
        "record_format": "prefix|draw_index|minimum|maximum|result",
        "schema_version": DIRECT_RANDOM_TRACE_SCHEMA_VERSION,
        "script_name": DIRECT_RANDOM_TRACE_SCRIPT_NAME,
        "script_sha256": DIRECT_RANDOM_TRACE_SCRIPT_SHA256,
        "transport": DIRECT_RANDOM_TRACE_TRANSPORT,
    }
    return {
        **to_canonical_data(identity),
        "instrumentation_id": stable_digest(identity, prefix="rnginst_"),
    }


def _trace_packet(frame: MessageFrame, frame_index: int) -> int | None:
    if frame.message_type != 2:
        return None
    if not frame.payload or frame.payload[0] != DIRECT_RANDOM_TRACE_HINT_TYPE:
        return None
    if len(frame.payload) != 10:
        raise InvalidBridgeMessageError(
            f"direct random trace frame {frame_index} must have a 10-byte payload"
        )
    hint_type, player, value = struct.unpack("<BBQ", frame.payload)
    assert hint_type == DIRECT_RANDOM_TRACE_HINT_TYPE
    if player != 0:
        raise InvalidBridgeMessageError(
            f"direct random trace frame {frame_index} must use player 0"
        )
    return int(value)


def _signed_int32(value: int) -> int:
    return value if value < (1 << 31) else value - (1 << 32)


def extract_direct_random_draws(
    frames: Sequence[MessageFrame],
) -> tuple[DirectRandomDraw, ...]:
    draws: list[DirectRandomDraw] = []
    index = 0
    while index < len(frames):
        packet = _trace_packet(frames[index], index)
        if packet is None:
            index += 1
            continue
        if packet != DIRECT_RANDOM_TRACE_MARKER:
            raise InvalidBridgeMessageError(
                f"orphan direct random trace packet at frame {index}"
            )
        end = index + DIRECT_RANDOM_TRACE_PACKET_COUNT
        if end > len(frames):
            raise InvalidBridgeMessageError(
                f"direct random trace beginning at frame {index} is truncated"
            )
        packets: list[int] = []
        for packet_index in range(index, end):
            value = _trace_packet(frames[packet_index], packet_index)
            if value is None:
                raise InvalidBridgeMessageError(
                    "direct random trace packets must be contiguous; "
                    f"frame {packet_index} is not a trace packet"
                )
            packets.append(value)
        _, draw_index, raw_minimum, raw_maximum, raw_result = packets
        if draw_index <= 0:
            raise InvalidBridgeMessageError("direct random draw index must be positive")
        if draws and draw_index != draws[-1].draw_index + 1:
            raise InvalidBridgeMessageError(
                "direct random draw indices within a batch must be contiguous"
            )
        if any(
            value > _UINT32_MAX
            for value in (raw_minimum, raw_maximum, raw_result)
        ):
            raise InvalidBridgeMessageError(
                "direct random trace range and result packets must fit uint32"
            )
        minimum = _signed_int32(raw_minimum)
        maximum = _signed_int32(raw_maximum)
        result = _signed_int32(raw_result)
        if minimum > maximum or not minimum <= result <= maximum:
            raise InvalidBridgeMessageError(
                "direct random trace result must be within its inclusive range"
            )
        draws.append(
            DirectRandomDraw(
                draw_index=draw_index,
                frame_indices=tuple(range(index, end)),
                minimum=minimum,
                maximum=maximum,
                result=result,
            )
        )
        index = end
    return tuple(draws)


def extract_direct_random_log_draws(
    logs: Sequence[CoreLog],
) -> tuple[DirectRandomLogDraw, ...]:
    draws: list[DirectRandomLogDraw] = []
    for log_index, log in enumerate(logs):
        if not isinstance(log, CoreLog):
            raise InvalidBridgeMessageError(
                f"direct random trace log {log_index} must be CoreLog"
            )
        if log.log_type != LogType.FROM_SCRIPT:
            continue
        if not log.message.startswith(DIRECT_RANDOM_TRACE_LOG_PREFIX):
            continue
        match = _LOG_PATTERN.fullmatch(log.message)
        if match is None:
            raise InvalidBridgeMessageError(
                f"direct random trace log {log_index} has an invalid record"
            )
        draw_index, minimum, maximum, result = (
            int(value) for value in match.groups()
        )
        if any(
            value < _INT32_MIN or value > _INT32_MAX
            for value in (minimum, maximum, result)
        ):
            raise InvalidBridgeMessageError(
                f"direct random trace log {log_index} values must fit int32"
            )
        if draws and draw_index != draws[-1].draw_index + 1:
            raise InvalidBridgeMessageError(
                "direct random draw indices within a batch must be contiguous"
            )
        if minimum > maximum or not minimum <= result <= maximum:
            raise InvalidBridgeMessageError(
                "direct random trace result must be within its inclusive range"
            )
        draws.append(
            DirectRandomLogDraw(
                draw_index=draw_index,
                log_index=log_index,
                log_sequence=log.sequence,
                minimum=minimum,
                maximum=maximum,
                result=result,
            )
        )
    return tuple(draws)
