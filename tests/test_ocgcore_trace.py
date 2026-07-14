from __future__ import annotations

from pathlib import Path
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.engine.bridge import InvalidBridgeMessageError
from ygo_effect_dsl.engine.bridge.ocgcore import (
    DIRECT_RANDOM_TRACE_LOG_PREFIX,
    DIRECT_RANDOM_TRACE_HINT_TYPE,
    DIRECT_RANDOM_TRACE_MARKER,
    CoreLog,
    DecodedMessageBatch,
    MessageFrame,
    ProgressMessageType,
    RandomMessageType,
    build_core_output_trace,
    extract_direct_random_draws,
)
from ygo_effect_dsl.engine.bridge.ocgcore.types import LogType
from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.replay import (
    ReplayEventV03a,
    ReplayHistoryV03a,
    assert_complete_io_trace,
    build_scripted_output_trace,
)
from ygo_effect_dsl.engine.replay.errors import ReplayFormatError


def _location(controller: int, location: int, sequence: int, position: int) -> bytes:
    return struct.pack("<BBII", controller, location, sequence, position)


def _snapshot() -> dict[str, object]:
    return {
        "state_hash": "state_after_randomness",
        "zones": [
            {
                "controller": 0,
                "location": 0x01,
                "cards": [
                    {"slot": 0, "code": 100},
                    {"slot": 1, "code": 200},
                ],
            },
            {
                "controller": 0,
                "location": 0x02,
                "cards": [{"slot": 0, "code": 300}],
            },
            {
                "controller": 1,
                "location": 0x40,
                "cards": [{"slot": 0, "code": 400}],
            },
        ],
    }


def _direct_random_packet(value: int) -> MessageFrame:
    return MessageFrame(
        2,
        struct.pack("<BBQ", DIRECT_RANDOM_TRACE_HINT_TYPE, 0, value),
    )


def _direct_random_frames(
    *, draw_index: int = 1, minimum: int = 1, maximum: int = 6, result: int = 4
) -> tuple[MessageFrame, ...]:
    return tuple(
        _direct_random_packet(value)
        for value in (
            DIRECT_RANDOM_TRACE_MARKER,
            draw_index,
            minimum & 0xFFFFFFFF,
            maximum & 0xFFFFFFFF,
            result & 0xFFFFFFFF,
        )
    )


def _direct_random_log(
    *,
    sequence: int = 0,
    draw_index: int = 1,
    minimum: int = 1,
    maximum: int = 6,
    result: int = 4,
) -> CoreLog:
    return CoreLog(
        sequence=sequence,
        log_type=LogType.FROM_SCRIPT,
        message=(
            f"{DIRECT_RANDOM_TRACE_LOG_PREFIX}|{draw_index}|"
            f"{minimum}|{maximum}|{result}"
        ),
    )


def test_core_output_trace_records_all_random_outcome_types_in_order() -> None:
    assert int(RandomMessageType.SHUFFLE_EXTRA) == 39
    before = _location(0, 0x08, 0, 0x08)
    after = _location(0, 0x08, 1, 0x08)
    selected = _location(1, 0x04, 2, 0x01)
    frames = (
        MessageFrame(RandomMessageType.SHUFFLE_DECK, b"\x00"),
        MessageFrame(
            RandomMessageType.SHUFFLE_HAND,
            struct.pack("<BI", 0, 1) + struct.pack("<I", 300),
        ),
        MessageFrame(
            RandomMessageType.SHUFFLE_EXTRA,
            struct.pack("<BI", 1, 1) + struct.pack("<I", 400),
        ),
        MessageFrame(
            RandomMessageType.SHUFFLE_SET_CARD,
            struct.pack("<BB", 0x08, 1) + before + after,
        ),
        MessageFrame(
            RandomMessageType.RANDOM_SELECTED,
            struct.pack("<BI", 0, 1) + selected,
        ),
        MessageFrame(RandomMessageType.TOSS_COIN, bytes((0, 2, 1, 0))),
        MessageFrame(RandomMessageType.TOSS_DICE, bytes((1, 3, 1, 4, 6))),
    )

    trace = build_core_output_trace(
        DecodedMessageBatch(frames=frames, request=None),
        snapshot=_snapshot(),
    )

    assert [event["kind"] for event in trace["random_events"]] == [
        "shuffle_deck",
        "shuffle_hand",
        "shuffle_extra",
        "shuffle_set_card",
        "random_selected",
        "toss_coin",
        "toss_dice",
    ]
    assert trace["random_events"][0]["outcome"]["zone_order"][0]["code"] == 100
    assert trace["random_events"][1]["outcome"]["codes"] == [300]
    assert trace["random_events"][4]["outcome"]["selected"][0]["sequence"] == 2
    assert trace["random_events"][5]["outcome"]["results"] == [1, 0]
    assert trace["random_events"][6]["outcome"]["results"] == [1, 4, 6]
    assert [frame["frame_index"] for frame in trace["frames"]] == list(range(7))
    assert len({event["random_event_id"] for event in trace["random_events"]}) == 7


def test_core_output_trace_records_direct_lua_random_range_result_and_order() -> None:
    logs = (
        _direct_random_log(minimum=-2, maximum=2, result=-1),
        _direct_random_log(
            sequence=1,
            draw_index=2,
            minimum=10,
            maximum=20,
            result=17,
        ),
    )

    trace = build_core_output_trace(
        DecodedMessageBatch(
            frames=(MessageFrame(ProgressMessageType.NEW_TURN, b"\x00"),),
            request=None,
            logs=logs,
        ),
        snapshot=_snapshot(),
    )

    direct = [
        event
        for event in trace["random_events"]
        if event["kind"] == "direct_lua_random"
    ]
    assert [event["outcome"]["draw_index"] for event in direct] == [1, 2]
    assert direct[0]["outcome"] == {
        "draw_index": 1,
        "maximum": 2,
        "minimum": -2,
        "result": -1,
    }
    assert direct[0]["log_index"] == 0
    assert direct[0]["log_sequence"] == 0
    assert direct[0]["message_type"] is None
    assert direct[0]["transport"] == "ocgcore_log_handler_from_script_v1"
    assert direct[1]["outcome"]["result"] == 17
    assert [log["log_index"] for log in trace["logs"]] == [0, 1]


def test_core_output_trace_rejects_malformed_direct_lua_random_log() -> None:
    malformed = CoreLog(
        sequence=0,
        log_type=LogType.FROM_SCRIPT,
        message=f"{DIRECT_RANDOM_TRACE_LOG_PREFIX}|1|1|6",
    )

    with pytest.raises(InvalidBridgeMessageError, match="invalid record"):
        build_core_output_trace(
            DecodedMessageBatch(frames=(), request=None, logs=(malformed,)),
            snapshot=_snapshot(),
        )


def test_core_output_trace_rejects_invalid_direct_lua_random_sequence() -> None:
    skipped_draw = (
        _direct_random_log(),
        _direct_random_log(sequence=1, draw_index=3),
    )

    with pytest.raises(InvalidBridgeMessageError, match="must be contiguous"):
        build_core_output_trace(
            DecodedMessageBatch(frames=(), request=None, logs=skipped_draw),
            snapshot=_snapshot(),
        )


def test_legacy_direct_random_hint_parser_remains_available_for_v1_replay() -> None:
    draws = extract_direct_random_draws(
        _direct_random_frames(minimum=-2, maximum=2, result=-1)
    )

    assert len(draws) == 1
    assert draws[0].outcome_dict() == {
        "draw_index": 1,
        "maximum": 2,
        "minimum": -2,
        "result": -1,
    }


def test_core_output_trace_records_turn_and_phase_progress_in_order() -> None:
    trace = build_core_output_trace(
        DecodedMessageBatch(
            frames=(
                MessageFrame(ProgressMessageType.NEW_TURN, b"\x01"),
                MessageFrame(
                    ProgressMessageType.NEW_PHASE, struct.pack("<H", 0x200)
                ),
                MessageFrame(
                    ProgressMessageType.NEW_PHASE, struct.pack("<H", 0x04)
                ),
            ),
            request=None,
        ),
        snapshot=_snapshot(),
    )

    assert [event["kind"] for event in trace["progress_events"]] == [
        "new_turn",
        "new_phase",
        "new_phase",
    ]
    assert trace["progress_events"][0]["outcome"] == {"turn_player": 1}
    assert trace["progress_events"][1]["outcome"] == {
        "phase": 0x200,
        "phase_name": "end",
    }
    assert trace["progress_events"][2]["outcome"]["phase_name"] == "main1"
    assert len(
        {event["progress_event_id"] for event in trace["progress_events"]}
    ) == 3


def test_core_output_trace_rejects_unknown_phase() -> None:
    with pytest.raises(InvalidBridgeMessageError, match="unknown phase"):
        build_core_output_trace(
            DecodedMessageBatch(
                frames=(
                    MessageFrame(
                        ProgressMessageType.NEW_PHASE, struct.pack("<H", 0xFFFF)
                    ),
                ),
                request=None,
            ),
            snapshot=_snapshot(),
        )


@pytest.mark.parametrize(
    "frame",
    (
        MessageFrame(RandomMessageType.TOSS_COIN, bytes((0, 1, 2))),
        MessageFrame(RandomMessageType.TOSS_DICE, bytes((0, 1, 0))),
        MessageFrame(RandomMessageType.SHUFFLE_HAND, struct.pack("<BI", 0, 2)),
    ),
)
def test_core_output_trace_rejects_invalid_random_payload(frame: MessageFrame) -> None:
    with pytest.raises(InvalidBridgeMessageError):
        build_core_output_trace(
            DecodedMessageBatch(frames=(frame,), request=None),
            snapshot=_snapshot(),
        )


def test_replay_smoke_validates_ordered_responses_and_random_index() -> None:
    output = build_core_output_trace(
        DecodedMessageBatch(
            frames=(MessageFrame(RandomMessageType.TOSS_COIN, bytes((0, 1, 1))),),
            request=None,
        ),
        snapshot={"state_hash": "state_after", "zones": []},
    )
    response = {
        "request_signature": "req_random",
        "selected_candidate_ids": ["coin:heads"],
    }
    event = ReplayEventV03a(
        step=0,
        request_signature="req_random",
        action=Action(
            kind=ActionKind.SELECT_OPTION,
            player=0,
            selections=(Selection(candidate_id="coin:heads"),),
            request_signature="req_random",
        ),
        core_input_ref=stable_digest(response, prefix="input_"),
        core_response=response,
        core_output=output,
        state_hash_before="state_before",
        state_hash_after="state_after",
    )
    replay = ReplayHistoryV03a(
        initial_snapshot={"state_hash": "state_before"},
        version_metadata={},
        events=(event,),
        initial_core_output=build_scripted_output_trace(
            state_hash="state_before",
            request_signature="req_random",
        ),
    ).to_dict()

    assert_complete_io_trace(replay)
    assert replay["random_events"][0]["after_response_step"] == 0
    assert replay["random_events"][0]["outcome"]["results"] == [1]

    replay["random_events"][0]["after_response_step"] = 1
    with pytest.raises(ReplayFormatError, match="ordered index"):
        assert_complete_io_trace(replay)
