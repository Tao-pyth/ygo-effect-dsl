from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.replay.errors import ReplayFormatError
from ygo_effect_dsl.engine.bridge.errors import InvalidBridgeMessageError
from ygo_effect_dsl.engine.bridge.ocgcore.protocol import MessageFrame
from ygo_effect_dsl.engine.bridge.ocgcore.random_trace import (
    extract_direct_random_draws,
    extract_direct_random_log_draws,
)
from ygo_effect_dsl.engine.bridge.ocgcore.types import CoreLog, LogType


def build_scripted_output_trace(
    *,
    state_hash: str,
    request_signature: str | None,
) -> dict[str, Any]:
    identity = {
        "frames": [],
        "progress_events": [],
        "random_events": [],
        "request_signature": request_signature,
        "resulting_state_hash": state_hash,
        "schema_version": "scripted-output-trace-v1",
    }
    return {**identity, "batch_id": stable_digest(identity, prefix="batch_")}


def _output_trace(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReplayFormatError(f"{path} must be a mapping")
    for field in (
        "batch_id",
        "frames",
        "random_events",
        "resulting_state_hash",
        "schema_version",
    ):
        if field not in value:
            raise ReplayFormatError(f"{path}.{field} is required")
    if not isinstance(value["frames"], list):
        raise ReplayFormatError(f"{path}.frames must be a list")
    if not isinstance(value["random_events"], list):
        raise ReplayFormatError(f"{path}.random_events must be a list")
    progress_events = value.get("progress_events", [])
    if not isinstance(progress_events, list):
        raise ReplayFormatError(f"{path}.progress_events must be a list")
    frame_indices: set[int] = set()
    decoded_frames: list[MessageFrame] = []
    for index, frame in enumerate(value["frames"]):
        if not isinstance(frame, Mapping):
            raise ReplayFormatError(f"{path}.frames[{index}] must be a mapping")
        if frame.get("frame_index") != index:
            raise ReplayFormatError(f"{path}.frames[{index}].frame_index must be {index}")
        frame_indices.add(index)
        payload_hex = frame.get("payload_hex")
        if not isinstance(payload_hex, str):
            raise ReplayFormatError(f"{path}.frames[{index}].payload_hex must be a string")
        try:
            payload = bytes.fromhex(payload_hex)
        except ValueError as exc:
            raise ReplayFormatError(
                f"{path}.frames[{index}].payload_hex is invalid"
            ) from exc
        if frame.get("payload_sha256") != sha256(payload).hexdigest():
            raise ReplayFormatError(f"{path}.frames[{index}] payload hash mismatch")
        message_type = frame.get("message_type")
        if not isinstance(message_type, int) or isinstance(message_type, bool):
            raise ReplayFormatError(
                f"{path}.frames[{index}].message_type must be an integer"
            )
        decoded_frames.append(MessageFrame(message_type=message_type, payload=payload))
    raw_logs = value.get("logs", [])
    if not isinstance(raw_logs, list):
        raise ReplayFormatError(f"{path}.logs must be a list")
    decoded_logs: list[CoreLog] = []
    log_indices: set[int] = set()
    previous_sequence = -1
    for index, log in enumerate(raw_logs):
        if not isinstance(log, Mapping):
            raise ReplayFormatError(f"{path}.logs[{index}] must be a mapping")
        if log.get("log_index") != index:
            raise ReplayFormatError(f"{path}.logs[{index}].log_index must be {index}")
        log_indices.add(index)
        message = log.get("message")
        if not isinstance(message, str):
            raise ReplayFormatError(f"{path}.logs[{index}].message must be a string")
        if log.get("message_sha256") != sha256(message.encode("utf-8")).hexdigest():
            raise ReplayFormatError(f"{path}.logs[{index}] message hash mismatch")
        sequence = log.get("sequence")
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or sequence <= previous_sequence
        ):
            raise ReplayFormatError(
                f"{path}.logs[{index}].sequence must be a strictly increasing integer"
            )
        previous_sequence = sequence
        raw_log_type = log.get("log_type")
        try:
            log_type = LogType[str(raw_log_type).upper()]
        except KeyError as exc:
            raise ReplayFormatError(
                f"{path}.logs[{index}].log_type is unsupported"
            ) from exc
        decoded_logs.append(CoreLog(sequence, log_type, message))
    if any(
        frame.get("message_type") in {40, 41} for frame in value["frames"]
    ) and "progress_events" not in value:
        raise ReplayFormatError(
            f"{path}.progress_events is required for turn or phase frames"
        )
    for index, random_event in enumerate(value["random_events"]):
        if not isinstance(random_event, Mapping):
            raise ReplayFormatError(f"{path}.random_events[{index}] must be a mapping")
        if random_event.get("kind") == "direct_lua_random":
            if random_event.get("transport") == "ocgcore_log_handler_from_script_v1":
                if random_event.get("log_index") not in log_indices:
                    raise ReplayFormatError(
                        f"{path}.random_events[{index}].log_index does not reference a log"
                    )
            elif random_event.get("frame_index") not in frame_indices:
                raise ReplayFormatError(
                    f"{path}.random_events[{index}].frame_index does not reference a frame"
                )
        elif random_event.get("frame_index") not in frame_indices:
            raise ReplayFormatError(
                f"{path}.random_events[{index}].frame_index does not reference a frame"
            )
        for field in ("kind", "message_type", "outcome", "random_event_id"):
            if field not in random_event:
                raise ReplayFormatError(
                    f"{path}.random_events[{index}].{field} is required"
                )
        random_identity = {
            key: item for key, item in random_event.items() if key != "random_event_id"
        }
        if random_event.get("random_event_id") != stable_digest(
            random_identity, prefix="rnd_"
        ):
            raise ReplayFormatError(
                f"{path}.random_events[{index}].random_event_id mismatch"
            )
        if random_event.get("resulting_state_hash") != value.get(
            "resulting_state_hash"
        ):
            raise ReplayFormatError(
                f"{path}.random_events[{index}] state hash mismatch"
            )
    schema_version = value.get("schema_version")
    try:
        direct_draws = extract_direct_random_draws(decoded_frames)
        direct_log_draws = extract_direct_random_log_draws(decoded_logs)
    except InvalidBridgeMessageError as exc:
        raise ReplayFormatError(f"{path} has invalid direct random trace: {exc}") from exc
    if schema_version == "ocgcore-output-trace-v2":
        if direct_draws:
            raise ReplayFormatError(f"{path} v2 forbids legacy Hint trace packets")
        expected_direct = [
            {
                "frame_index": None,
                "frame_indices": None,
                "kind": "direct_lua_random",
                "log_index": draw.log_index,
                "log_sequence": draw.log_sequence,
                "message_type": None,
                "outcome": draw.outcome_dict(),
                "transport": "ocgcore_log_handler_from_script_v1",
            }
            for draw in direct_log_draws
        ]
    else:
        if direct_log_draws:
            raise ReplayFormatError(f"{path} v1 forbids log transport records")
        expected_direct = [
            {
                "frame_index": draw.frame_index,
                "frame_indices": list(draw.frame_indices),
                "kind": "direct_lua_random",
                "log_index": None,
                "log_sequence": None,
                "message_type": 2,
                "outcome": draw.outcome_dict(),
                "transport": None,
            }
            for draw in direct_draws
        ]
    actual_direct = [
        {
            "frame_index": event.get("frame_index"),
            "frame_indices": event.get("frame_indices"),
            "kind": event.get("kind"),
            "log_index": event.get("log_index"),
            "log_sequence": event.get("log_sequence"),
            "message_type": event.get("message_type"),
            "outcome": event.get("outcome"),
            "transport": event.get("transport"),
        }
        for event in value["random_events"]
        if isinstance(event, Mapping) and event.get("kind") == "direct_lua_random"
    ]
    if actual_direct != expected_direct:
        raise ReplayFormatError(
            f"{path}.random_events direct Lua random trace does not match frames"
        )
    for index, progress_event in enumerate(progress_events):
        if not isinstance(progress_event, Mapping):
            raise ReplayFormatError(
                f"{path}.progress_events[{index}] must be a mapping"
            )
        if progress_event.get("frame_index") not in frame_indices:
            raise ReplayFormatError(
                f"{path}.progress_events[{index}].frame_index does not reference a frame"
            )
        for field in ("kind", "message_type", "outcome", "progress_event_id"):
            if field not in progress_event:
                raise ReplayFormatError(
                    f"{path}.progress_events[{index}].{field} is required"
                )
        progress_identity = {
            key: item
            for key, item in progress_event.items()
            if key != "progress_event_id"
        }
        if progress_event.get("progress_event_id") != stable_digest(
            progress_identity, prefix="prog_"
        ):
            raise ReplayFormatError(
                f"{path}.progress_events[{index}].progress_event_id mismatch"
            )
        if progress_event.get("resulting_state_hash") != value.get(
            "resulting_state_hash"
        ):
            raise ReplayFormatError(
                f"{path}.progress_events[{index}] state hash mismatch"
            )
    batch_identity = {key: item for key, item in value.items() if key != "batch_id"}
    if value.get("batch_id") != stable_digest(batch_identity, prefix="batch_"):
        raise ReplayFormatError(f"{path}.batch_id mismatch")
    return value


def assert_complete_io_trace(replay: Mapping[str, Any]) -> None:
    initial_output = _output_trace(
        replay.get("initial_core_output"), "replay.initial_core_output"
    )
    events = replay.get("events")
    if not isinstance(events, list):
        raise ReplayFormatError("replay.events must be a list")
    seen_random_event_ids: set[str] = set()
    next_direct_draw_index = 1

    def collect_random_ids(output: Mapping[str, Any], path: str) -> None:
        nonlocal next_direct_draw_index
        for index, random_event in enumerate(output["random_events"]):
            random_event_id = random_event.get("random_event_id")
            if not isinstance(random_event_id, str) or not random_event_id:
                raise ReplayFormatError(
                    f"{path}.random_events[{index}].random_event_id must be non-empty"
                )
            if random_event_id in seen_random_event_ids:
                raise ReplayFormatError(f"duplicate random event id {random_event_id}")
            seen_random_event_ids.add(random_event_id)
            if random_event.get("kind") == "direct_lua_random":
                outcome = random_event.get("outcome")
                draw_index = (
                    outcome.get("draw_index") if isinstance(outcome, Mapping) else None
                )
                if draw_index != next_direct_draw_index:
                    raise ReplayFormatError(
                        f"{path}.random_events[{index}] direct random draw index "
                        f"must be {next_direct_draw_index}"
                    )
                next_direct_draw_index += 1

    collect_random_ids(initial_output, "replay.initial_core_output")
    expected_random_trace: list[dict[str, Any]] = [
        {"after_response_step": None, **event}
        for event in initial_output["random_events"]
    ]
    for index, raw_event in enumerate(events):
        if not isinstance(raw_event, Mapping):
            raise ReplayFormatError(f"replay.events[{index}] must be a mapping")
        if raw_event.get("step") != index:
            raise ReplayFormatError(f"replay.events[{index}].step must be {index}")
        response = raw_event.get("core_response")
        if not isinstance(response, Mapping):
            raise ReplayFormatError(
                f"replay.events[{index}].core_response must be a mapping"
            )
        if response.get("request_signature") != raw_event.get("request_signature"):
            raise ReplayFormatError(
                f"replay.events[{index}].core_response request signature mismatch"
            )
        selected_candidate_ids = response.get("selected_candidate_ids")
        action = raw_event.get("action")
        if isinstance(selected_candidate_ids, list) and isinstance(action, Mapping):
            selections = action.get("selections")
            if isinstance(selections, list):
                action_candidate_ids = [
                    selection.get("candidate_id")
                    for selection in selections
                    if isinstance(selection, Mapping)
                ]
                if selected_candidate_ids != action_candidate_ids:
                    raise ReplayFormatError(
                        f"replay.events[{index}].core_response selection mismatch"
                    )
        response_hex = response.get("response_hex")
        if response_hex is not None:
            try:
                response_bytes = bytes.fromhex(str(response_hex))
            except ValueError as exc:
                raise ReplayFormatError(
                    f"replay.events[{index}].core_response.response_hex is invalid"
                ) from exc
            if response.get("response_length") != len(response_bytes):
                raise ReplayFormatError(
                    f"replay.events[{index}].core_response response length mismatch"
                )
            if response.get("response_sha256") != sha256(response_bytes).hexdigest():
                raise ReplayFormatError(
                    f"replay.events[{index}].core_response response hash mismatch"
                )
        core_input_ref = raw_event.get("core_input_ref")
        if core_input_ref != stable_digest(response, prefix="input_"):
            raise ReplayFormatError(
                f"replay.events[{index}].core_input_ref does not match core_response"
            )
        output = _output_trace(
            raw_event.get("core_output"), f"replay.events[{index}].core_output"
        )
        if output.get("resulting_state_hash") != raw_event.get("state_hash_after"):
            raise ReplayFormatError(
                f"replay.events[{index}].core_output state hash mismatch"
            )
        collect_random_ids(output, f"replay.events[{index}].core_output")
        expected_random_trace.extend(
            {"after_response_step": index, **event}
            for event in output["random_events"]
        )
    if replay.get("random_events") != expected_random_trace:
        raise ReplayFormatError(
            "replay.random_events must be the ordered index of all core output random events"
        )
