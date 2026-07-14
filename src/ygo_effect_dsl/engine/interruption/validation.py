from __future__ import annotations

from collections.abc import Mapping
import struct
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


OCGCORE_INTERRUPTION_VALIDATION_SCHEMA_VERSION = (
    "ocgcore-interruption-validation-v1"
)
OCGCORE_INTERRUPTION_VALIDATION_METHOD = "ocgcore-negation-timing-v1"

_MSG_MOVE = 50
_MSG_CHAINING = 70
_MSG_CHAINED = 71
_MSG_CHAIN_SOLVING = 72
_MSG_CHAIN_SOLVED = 73
_MSG_CHAIN_END = 74
_MSG_CHAIN_NEGATED = 75
_MSG_CHAIN_DISABLED = 76
_MSG_MISSED_EFFECT = 120
_REASON_COST = 0x80
_REASON_EFFECT = 0x40
_MOVE_PAYLOAD = struct.Struct("<IBBIIBBIII")
_MISSED_EFFECT_PAYLOAD = struct.Struct("<BBIII")
_MESSAGE_NAMES = {
    _MSG_MOVE: "MSG_MOVE",
    _MSG_CHAINING: "MSG_CHAINING",
    _MSG_CHAINED: "MSG_CHAINED",
    _MSG_CHAIN_SOLVING: "MSG_CHAIN_SOLVING",
    _MSG_CHAIN_SOLVED: "MSG_CHAIN_SOLVED",
    _MSG_CHAIN_END: "MSG_CHAIN_END",
    _MSG_CHAIN_NEGATED: "MSG_CHAIN_NEGATED",
    _MSG_CHAIN_DISABLED: "MSG_CHAIN_DISABLED",
    _MSG_MISSED_EFFECT: "MSG_MISSED_EFFECT",
}
_PAYLOAD_SIZES = {
    _MSG_MOVE: _MOVE_PAYLOAD.size,
    _MSG_CHAINING: 32,
    _MSG_CHAINED: 1,
    _MSG_CHAIN_SOLVING: 1,
    _MSG_CHAIN_SOLVED: 1,
    _MSG_CHAIN_END: 0,
    _MSG_CHAIN_NEGATED: 1,
    _MSG_CHAIN_DISABLED: 1,
    _MSG_MISSED_EFFECT: _MISSED_EFFECT_PAYLOAD.size,
}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _payload(frame: Mapping[str, Any], path: str) -> bytes:
    payload_hex = frame.get("payload_hex")
    if not isinstance(payload_hex, str):
        raise ValueError(f"{path}.payload_hex must be a string")
    try:
        return bytes.fromhex(payload_hex)
    except ValueError as error:
        raise ValueError(f"{path}.payload_hex must be valid hexadecimal") from error


def _move_record(
    payload: bytes, *, event_step: int, frame_index: int
) -> dict[str, Any]:
    (
        code,
        previous_controller,
        previous_location,
        previous_sequence,
        previous_position,
        current_controller,
        current_location,
        current_sequence,
        current_position,
        reason,
    ) = _MOVE_PAYLOAD.unpack(payload)
    return {
        "card_code": code,
        "current": {
            "controller": current_controller,
            "location": current_location,
            "position": current_position,
            "sequence": current_sequence,
        },
        "event_step": event_step,
        "frame_index": frame_index,
        "previous": {
            "controller": previous_controller,
            "location": previous_location,
            "position": previous_position,
            "sequence": previous_sequence,
        },
        "reason": reason,
        "reason_cost": bool(reason & _REASON_COST),
        "reason_effect": bool(reason & _REASON_EFFECT),
    }


def _missed_effect_record(
    payload: bytes, *, event_step: int, frame_index: int
) -> dict[str, Any]:
    controller, location, sequence, position, code = (
        _MISSED_EFFECT_PAYLOAD.unpack(payload)
    )
    return {
        "card_code": code,
        "controller": controller,
        "event_step": event_step,
        "frame_index": frame_index,
        "location": location,
        "position": position,
        "sequence": sequence,
    }


def derive_ocgcore_interruption_validation(
    replay: Mapping[str, Any],
) -> dict[str, Any]:
    replay = _mapping(replay, "replay")
    events = replay.get("events")
    if not isinstance(events, list):
        raise ValueError("replay.events must be a list")

    lifecycle_batches: list[dict[str, Any]] = []
    moves: list[dict[str, Any]] = []
    missed_effects: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    state_transitions: list[dict[str, Any]] = []
    for event_index, raw_event in enumerate(events):
        event = _mapping(raw_event, f"replay.events[{event_index}]")
        if event.get("step") != event_index:
            raise ValueError("replay event steps must be contiguous from 0")
        core_output = _mapping(
            event.get("core_output"),
            f"replay.events[{event_index}].core_output",
        )
        raw_frames = core_output.get("frames")
        if not isinstance(raw_frames, list):
            raise ValueError(
                f"replay.events[{event_index}].core_output.frames must be a list"
            )
        relevant_frames: list[dict[str, Any]] = []
        for raw_index, raw_frame in enumerate(raw_frames):
            path = f"replay.events[{event_index}].core_output.frames[{raw_index}]"
            frame = _mapping(raw_frame, path)
            message_type = frame.get("message_type")
            if message_type not in _MESSAGE_NAMES:
                continue
            frame_index = frame.get("frame_index")
            if frame_index != raw_index:
                raise ValueError(f"{path}.frame_index must match its list index")
            payload = _payload(frame, path)
            expected_size = _PAYLOAD_SIZES[message_type]
            if len(payload) != expected_size:
                raise ValueError(
                    f"{path} payload size must be {expected_size}, got {len(payload)}"
                )
            relevant_frames.append(
                {
                    "frame_index": frame_index,
                    "message_name": _MESSAGE_NAMES[message_type],
                    "message_type": message_type,
                    "payload_hex": payload.hex(),
                }
            )
            if message_type == _MSG_MOVE:
                moves.append(
                    _move_record(
                        payload,
                        event_step=event_index,
                        frame_index=frame_index,
                    )
                )
            elif message_type == _MSG_MISSED_EFFECT:
                missed_effects.append(
                    _missed_effect_record(
                        payload,
                        event_step=event_index,
                        frame_index=frame_index,
                    )
                )
        if relevant_frames:
            lifecycle_batches.append(
                {"event_step": event_index, "frames": relevant_frames}
            )

        request = _mapping(
            event.get("request"), f"replay.events[{event_index}].request"
        )
        if request.get("request_type") in {
            "select_chain",
            "select_effect_yes_no",
        }:
            raw_candidates = request.get("candidates")
            if not isinstance(raw_candidates, list):
                raise ValueError(
                    f"replay.events[{event_index}].request.candidates must be a list"
                )
            requests.append(
                {
                    "candidates": [
                        {
                            "candidate_id": candidate.get("candidate_id"),
                            "card_ref": candidate.get("card_ref"),
                            "kind": candidate.get("kind"),
                        }
                        for raw_candidate in raw_candidates
                        for candidate in [
                            _mapping(
                                raw_candidate,
                                f"replay.events[{event_index}]"
                                ".request.candidates[]",
                            )
                        ]
                    ],
                    "player": request.get("player"),
                    "request_signature": request.get("request_signature"),
                    "request_type": request.get("request_type"),
                    "step": event_index,
                }
            )

        action = _mapping(
            event.get("action"), f"replay.events[{event_index}].action"
        )
        actions.append(
            {
                "action_id": action.get("action_id"),
                "action_occurrence_id": event.get("action_occurrence_id"),
                "kind": action.get("kind"),
                "player": action.get("player"),
                "selections": action.get("selections"),
                "source": action.get("source"),
                "step": event_index,
            }
        )
        state_transitions.append(
            {
                "state_hash_after": event.get("state_hash_after"),
                "state_hash_before": event.get("state_hash_before"),
                "step": event_index,
            }
        )

    identity = to_canonical_data(
        {
            "actions": actions,
            "lifecycle_batches": lifecycle_batches,
            "method": OCGCORE_INTERRUPTION_VALIDATION_METHOD,
            "missed_effects": missed_effects,
            "moves": moves,
            "requests": requests,
            "schema_version": OCGCORE_INTERRUPTION_VALIDATION_SCHEMA_VERSION,
            "state_transitions": state_transitions,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="intvalidation_"),
    }
