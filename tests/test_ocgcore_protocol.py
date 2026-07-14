from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import struct

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.engine.bridge import (
    Candidate,
    DecisionContext,
    DecisionRequest,
    InvalidBridgeMessageError,
    InvalidBridgeResponseError,
    UnsupportedBridgeMessageError,
)
from ygo_effect_dsl.engine.bridge.ocgcore import (
    KNOWN_MESSAGE_TYPES,
    MESSAGE_REGISTRY_VERSION,
    NON_DECISION_MESSAGE_TYPES,
    RESPONSE_CODEC_VERSION,
    SELECTION_MESSAGE_TYPES,
    UNSUPPORTED_MESSAGE_TYPES,
    ActionResponseEncoder,
    MessageType,
    OcgcoreMessageDecoder,
    OcgcoreVersionMismatchError,
    split_message_stream,
)
from ygo_effect_dsl.engine.failures import classify_failure


FIXTURE = Path(__file__).parent / "golden" / "ocgcore_v11" / "codec_cases.json"


def _cases() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _message(message_type: MessageType, payload: bytes) -> bytes:
    body = bytes((int(message_type),)) + payload
    return struct.pack("<I", len(body)) + body


def _raw_message(message_type: int, payload: bytes = b"") -> bytes:
    body = bytes((message_type,)) + payload
    return struct.pack("<I", len(body)) + body


def test_api_11_message_registry_is_exact_and_unknown_ids_fail_closed() -> None:
    expected_non_decision = {
        1, 2, 3, 4, 5, 6, 7, 8,
        30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42,
        50, 53, 54, 55, 56,
        60, 61, 62, 63, 64, 65,
        70, 71, 72, 73, 74, 75, 76,
        80, 81, 83,
        90, 91, 92, 93, 94, 95, 96, 97,
        100, 101, 102,
        110, 111, 112, 113, 114,
        120, 121, 122, 123,
        130, 131, 133,
        160, 161, 163, 164, 165, 170, 180, 190,
    }
    assert NON_DECISION_MESSAGE_TYPES == expected_non_decision
    assert UNSUPPORTED_MESSAGE_TYPES == {162}
    assert KNOWN_MESSAGE_TYPES == (
        expected_non_decision | SELECTION_MESSAGE_TYPES | {162}
    )

    batch = OcgcoreMessageDecoder().decode_batch(
        b"".join(_raw_message(message_type) for message_type in sorted(expected_non_decision)),
        request_id="known-non-decision",
    )
    assert batch.request is None
    assert len(batch.frames) == len(expected_non_decision)

    payload = b"future-decision-shape"
    context = DecisionContext(
        phase="main1",
        chain=({"link": 1},),
        request_source="worker",
        visible_board={"private": "must-not-leak"},
        extra={"scenario_id": "shape-probe"},
    )
    with pytest.raises(UnsupportedBridgeMessageError, match="unknown ocgcore message") as captured:
        OcgcoreMessageDecoder().decode_batch(
            _raw_message(17, payload),
            request_id="unknown-message",
            context=context,
        )
    error_context = captured.value.context
    assert error_context == {
        "decision_context": {
            "chain_length": 1,
            "extra": {"scenario_id": "shape-probe"},
            "phase": "main1",
            "priority_player": None,
            "request_source": "worker",
            "turn_player": None,
            "version_metadata": {},
        },
        "message_registry_version": MESSAGE_REGISTRY_VERSION,
        "message_type": 17,
        "payload_length": len(payload),
        "payload_sha256": sha256(payload).hexdigest(),
        "protocol_version": "ocgcore-api-11.0",
    }
    assert "payload_hex" not in error_context
    failure = classify_failure(captured.value)
    assert failure.disposition.value == "path_failure"
    assert failure.recovery.value == "stop_path"

    unsafe_context = DecisionContext(extra={"opaque": object()})
    with pytest.raises(UnsupportedBridgeMessageError) as unsafe:
        OcgcoreMessageDecoder().decode_batch(
            _raw_message(17),
            request_id="unsafe-context",
            context=unsafe_context,
        )
    assert unsafe.value.context["decision_context"]["extra"] == {
        "opaque": {"unsupported_type": "object"}
    }


def test_missing_decision_decoder_and_ambiguous_candidate_ids_fail_closed() -> None:
    decoder = OcgcoreMessageDecoder()
    decoder._registry.pop(MessageType.SELECT_YES_NO)
    with pytest.raises(UnsupportedBridgeMessageError, match="not registered") as captured:
        decoder.decode_batch(
            _message(MessageType.SELECT_YES_NO, struct.pack("<BQ", 0, 1)),
            request_id="registry-gap",
        )
    assert captured.value.context["message_type"] == int(MessageType.SELECT_YES_NO)
    assert len(captured.value.context["payload_sha256"]) == 64

    request = OcgcoreMessageDecoder().decode_batch(
        bytes.fromhex(str(_cases()[1]["message_hex"])),
        request_id="ambiguous-candidate",
    ).request
    assert request is not None
    duplicate = replace(
        request,
        candidates=(
            request.candidates[0],
            replace(
                request.candidates[1],
                candidate_id=request.candidates[0].candidate_id,
            ),
        ),
    )
    action = _action(
        duplicate,
        ActionKind.SELECT_OPTION,
        (Selection(duplicate.candidates[0].candidate_id),),
    )
    with pytest.raises(InvalidBridgeResponseError, match="ambiguous") as ambiguous:
        ActionResponseEncoder().encode(duplicate, action)
    assert ambiguous.value.context["duplicate_candidate_ids"] == [
        duplicate.candidates[0].candidate_id
    ]


def _action(
    request: DecisionRequest,
    kind: ActionKind,
    selections: tuple[Selection, ...],
) -> Action:
    return Action(
        kind=kind,
        player=request.player,
        selections=selections,
        request_signature=request.request_signature,
    )


def test_battle_effect_and_disabled_field_decisions_round_trip() -> None:
    decoder = OcgcoreMessageDecoder()
    encoder = ActionResponseEncoder()

    battle_payload = struct.pack("<BI", 0, 0)
    battle_payload += struct.pack("<IIBBBB", 1, 1001, 0, 0x04, 2, 1)
    battle_payload += bytes((1, 1))
    battle = decoder.decode_batch(
        _message(MessageType.SELECT_BATTLE_COMMAND, battle_payload),
        request_id="battle",
    ).request
    assert battle is not None
    assert [candidate.candidate_id for candidate in battle.candidates] == [
        "attack:0",
        "control:enter_main_phase_2",
        "control:end_turn",
    ]
    attack = _action(
        battle,
        ActionKind.ATTACK,
        (Selection(candidate_id="attack:0"),),
    )
    assert encoder.encode(battle, attack).data == struct.pack("<i", 1)

    effect_payload = struct.pack(
        "<BIBBIIQ", 0, 2001, 0, 0x04, 1, 1, 9001
    )
    effect = decoder.decode_batch(
        _message(MessageType.SELECT_EFFECT_YES_NO, effect_payload),
        request_id="effect-yes-no",
    ).request
    assert effect is not None
    assert effect.candidates[1].card_ref["public_card_id"] == 2001
    accept = _action(
        effect,
        ActionKind.ACTIVATE_EFFECT,
        (Selection(candidate_id="choice:1"),),
    )
    assert encoder.encode(effect, accept).data == struct.pack("<i", 1)

    disabled = decoder.decode_batch(
        _message(MessageType.SELECT_DISABLED_FIELD, struct.pack("<BBI", 0, 1, 0xFFFFFFFE)),
        request_id="disabled-field",
    ).request
    assert disabled is not None
    assert disabled.request_type == "select_disabled_field"
    zone = _action(
        disabled,
        ActionKind.SELECT_ZONE,
        (Selection(candidate_id=disabled.candidates[0].candidate_id),),
    )
    assert len(encoder.encode(disabled, zone).data) == 3


def test_weighted_card_decisions_round_trip() -> None:
    decoder = OcgcoreMessageDecoder()
    encoder = ActionResponseEncoder()

    tribute_payload = struct.pack("<BBIII", 0, 0, 2, 2, 2)
    tribute_payload += struct.pack("<IBBIB", 3001, 0, 0x04, 0, 1)
    tribute_payload += struct.pack("<IBBIB", 3002, 0, 0x04, 1, 1)
    tribute = decoder.decode_batch(
        _message(MessageType.SELECT_TRIBUTE, tribute_payload), request_id="tribute"
    ).request
    assert tribute is not None
    tribute_action = _action(
        tribute,
        ActionKind.SELECT_TRIBUTE,
        (Selection("card:0"), Selection("card:1")),
    )
    assert encoder.encode(tribute, tribute_action).data == struct.pack(
        "<iI2B", 2, 2, 0, 1
    )
    insufficient_tribute = _action(
        tribute,
        ActionKind.SELECT_TRIBUTE,
        (Selection("card:0"),),
    )
    with pytest.raises(InvalidBridgeResponseError, match="tribute value"):
        encoder.encode(tribute, insufficient_tribute)

    counter_payload = struct.pack("<BHHI", 0, 0x10, 3, 2)
    counter_payload += struct.pack("<IBBBH", 4001, 0, 0x04, 0, 2)
    counter_payload += struct.pack("<IBBBH", 4002, 0, 0x04, 1, 2)
    counter = decoder.decode_batch(
        _message(MessageType.SELECT_COUNTER, counter_payload), request_id="counter"
    ).request
    assert counter is not None
    counter_action = _action(
        counter,
        ActionKind.DISTRIBUTE_COUNTERS,
        (Selection("card:0", value=1), Selection("card:1", value=2)),
    )
    assert encoder.encode(counter, counter_action).data == struct.pack("<2h", 1, 2)
    bad_counter_total = _action(
        counter,
        ActionKind.DISTRIBUTE_COUNTERS,
        (Selection("card:0", value=1), Selection("card:1", value=1)),
    )
    with pytest.raises(InvalidBridgeResponseError, match="allocation total"):
        encoder.encode(counter, bad_counter_total)

    sum_payload = struct.pack("<BBIIII", 0, 0, 3, 2, 2, 0)
    sum_payload += struct.pack("<I", 2)
    sum_payload += struct.pack("<IBBIII", 5001, 0, 0x02, 0, 0, 1)
    sum_payload += struct.pack("<IBBIII", 5002, 0, 0x02, 1, 0, 2)
    sum_request = decoder.decode_batch(
        _message(MessageType.SELECT_SUM, sum_payload), request_id="sum"
    ).request
    assert sum_request is not None
    sum_action = _action(
        sum_request,
        ActionKind.SELECT_SUM,
        (Selection("card:0"), Selection("card:1")),
    )
    assert encoder.encode(sum_request, sum_action).data == struct.pack(
        "<iI2B", 2, 2, 0, 1
    )


def test_unselect_sort_announce_and_rps_decisions_round_trip() -> None:
    decoder = OcgcoreMessageDecoder()
    encoder = ActionResponseEncoder()

    unselect_payload = struct.pack("<BBBII", 0, 1, 0, 1, 2)
    unselect_payload += struct.pack("<I", 1)
    unselect_payload += struct.pack("<IBBII", 6001, 0, 0x02, 0, 0)
    unselect_payload += struct.pack("<I", 1)
    unselect_payload += struct.pack("<IBBII", 6002, 0, 0x02, 1, 0)
    unselect = decoder.decode_batch(
        _message(MessageType.SELECT_UNSELECT_CARD, unselect_payload),
        request_id="unselect",
    ).request
    assert unselect is not None
    toggle = _action(
        unselect,
        ActionKind.SELECT_CARD,
        (Selection("unselect:0"),),
    )
    assert encoder.encode(unselect, toggle).data == struct.pack("<ii", 1, 1)
    finish = _action(
        unselect,
        ActionKind.FINISH_SELECTION,
        (Selection("control:finish"),),
    )
    assert encoder.encode(unselect, finish).data == struct.pack("<i", -1)

    sort_payload = struct.pack("<BI", 0, 3)
    for index, code in enumerate((7001, 7002, 7003)):
        sort_payload += struct.pack("<IBII", code, 0, 0x01, index)
    sort_request = decoder.decode_batch(
        _message(MessageType.SORT_CARD, sort_payload), request_id="sort"
    ).request
    assert sort_request is not None
    sort_action = _action(
        sort_request,
        ActionKind.ORDER_CARDS,
        (
            Selection("card:0", order=2),
            Selection("card:1", order=0),
            Selection("card:2", order=1),
        ),
    )
    assert encoder.encode(sort_request, sort_action).data == bytes((2, 0, 1))
    duplicate_order = _action(
        sort_request,
        ActionKind.ORDER_CARDS,
        (
            Selection("card:0", order=0),
            Selection("card:1", order=0),
            Selection("card:2", order=1),
        ),
    )
    with pytest.raises(InvalidBridgeResponseError, match="each order"):
        encoder.encode(sort_request, duplicate_order)
    keep_order = _action(
        sort_request,
        ActionKind.FINISH_SELECTION,
        (Selection("control:keep_order"),),
    )
    assert encoder.encode(sort_request, keep_order).data == b"\xff"

    race = decoder.decode_batch(
        _message(MessageType.ANNOUNCE_RACE, struct.pack("<BBQ", 0, 2, 0b1101)),
        request_id="race",
    ).request
    assert race is not None
    race_action = _action(
        race,
        ActionKind.ANNOUNCE_RACE,
        (Selection("bit:0"), Selection("bit:3")),
    )
    assert encoder.encode(race, race_action).data == struct.pack("<Q", 9)

    attribute = decoder.decode_batch(
        _message(MessageType.ANNOUNCE_ATTRIBUTE, struct.pack("<BBI", 0, 1, 0b10)),
        request_id="attribute",
    ).request
    assert attribute is not None
    attribute_action = _action(
        attribute,
        ActionKind.ANNOUNCE_ATTRIBUTE,
        (Selection("bit:1"),),
    )
    assert encoder.encode(attribute, attribute_action).data == struct.pack("<I", 2)

    number = decoder.decode_batch(
        _message(MessageType.ANNOUNCE_NUMBER, struct.pack("<BBQQ", 0, 2, 3, 6)),
        request_id="number",
    ).request
    assert number is not None
    number_action = _action(
        number,
        ActionKind.ANNOUNCE_NUMBER,
        (Selection("number:1"),),
    )
    assert encoder.encode(number, number_action).data == struct.pack("<i", 1)

    card = decoder.decode_batch(
        _message(MessageType.ANNOUNCE_CARD, struct.pack("<BBQ", 0, 1, 123)),
        request_id="card-code",
    ).request
    assert card is not None
    card_action = _action(
        card,
        ActionKind.ANNOUNCE_CARD,
        (Selection("input:card_code", value=97268402),),
    )
    assert encoder.encode(card, card_action).data == struct.pack("<i", 97268402)

    rps = decoder.decode_batch(
        _message(MessageType.ROCK_PAPER_SCISSORS, bytes((0,))), request_id="rps"
    ).request
    assert rps is not None
    rps_action = _action(
        rps,
        ActionKind.ROCK_PAPER_SCISSORS,
        (Selection("hand:2"),),
    )
    assert encoder.encode(rps, rps_action).data == struct.pack("<i", 2)


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["name"]))
def test_v11_golden_message_and_response_codecs(case: dict[str, object]) -> None:
    decoder = OcgcoreMessageDecoder()
    batch = decoder.decode_batch(
        bytes.fromhex(str(case["message_hex"])),
        request_id=f"golden:{case['name']}",
    )
    request = batch.request
    assert request is not None
    assert request.request_type == case["request_type"]
    assert request.request_signature == case["request_signature"]
    assert [candidate.candidate_id for candidate in request.candidates] == case["candidate_ids"]

    action = Action(
        kind=ActionKind(str(case["action_kind"])),
        player=request.player,
        selections=tuple(
            Selection(candidate_id=str(candidate_id))
            for candidate_id in case["selected_candidate_ids"]
        ),
        request_signature=request.request_signature,
    )
    encoded = ActionResponseEncoder().encode(request, action)
    assert encoded.data.hex() == case["response_hex"]
    trace = encoded.to_trace_dict()
    assert trace["codec_version"] == RESPONSE_CODEC_VERSION
    assert trace["request_signature"] == request.request_signature
    assert trace["response_length"] == len(encoded.data)
    ActionResponseEncoder().verify_trace(request, action, trace)


def test_display_labels_do_not_change_signature_action_id_or_response() -> None:
    case = _cases()[1]
    request = OcgcoreMessageDecoder().decode_batch(
        bytes.fromhex(str(case["message_hex"])), request_id="label-test"
    ).request
    assert request is not None
    renamed = replace(
        request,
        candidates=tuple(
            replace(candidate, label=f"renamed-{index}")
            for index, candidate in enumerate(request.candidates)
        ),
    )
    first = Action(
        kind=ActionKind.SELECT_OPTION,
        player=request.player,
        selections=(Selection(candidate_id="option:1"),),
        request_signature=request.request_signature,
    )
    second = replace(first, request_signature=renamed.request_signature, action_id="")

    assert renamed.request_signature == request.request_signature
    assert first.action_id == second.action_id
    encoder = ActionResponseEncoder()
    assert encoder.encode(request, first).data == encoder.encode(renamed, second).data


def test_encoder_rejects_stale_unknown_constraint_and_nonprimitive_payloads() -> None:
    case = _cases()[3]
    request = OcgcoreMessageDecoder().decode_batch(
        bytes.fromhex(str(case["message_hex"])), request_id="invalid-response"
    ).request
    assert request is not None
    encoder = ActionResponseEncoder()

    stale = Action(
        kind=ActionKind.SELECT_CARD,
        player=request.player,
        selections=(Selection("card:0"), Selection("card:1")),
        request_signature="req_stale",
    )
    with pytest.raises(InvalidBridgeResponseError, match="request_signature") as captured:
        encoder.encode(request, stale)
    failure = classify_failure(captured.value)
    assert failure.context["request"] == request.to_dict()
    assert failure.context["response"]["selected_candidate_ids"] == [
        "card:0",
        "card:1",
    ]

    unknown = replace(stale, selections=(Selection("card:missing"),), request_signature=request.request_signature)
    with pytest.raises(InvalidBridgeResponseError, match="unknown"):
        encoder.encode(request, unknown)

    too_few = replace(stale, selections=(Selection("card:0"),), request_signature=request.request_signature)
    with pytest.raises(InvalidBridgeResponseError, match="fewer"):
        encoder.encode(request, too_few)

    bad_candidate = Candidate(
        candidate_id="option:bad",
        kind="option",
        payload={"response_codec": "int32", "response_value": object()},
    )
    bad_request = replace(request, candidates=(bad_candidate,))
    with pytest.raises(InvalidBridgeResponseError, match="non-primitive"):
        encoder.encode(bad_request, too_few)


def test_cancelable_card_request_encodes_explicit_cancel() -> None:
    body = struct.pack("<BBBIII", 15, 0, 1, 1, 1, 1)
    body += struct.pack("<IBBII", 1001, 0, 2, 0, 0)
    message = struct.pack("<I", len(body)) + body
    request = OcgcoreMessageDecoder().decode_batch(
        message, request_id="cancelable"
    ).request
    assert request is not None
    action = Action(
        kind=ActionKind.DECLINE,
        player=0,
        selections=(),
        request_signature=request.request_signature,
    )
    assert ActionResponseEncoder().encode(request, action).data == struct.pack("<i", -1)


def test_idle_command_and_place_are_separate_core_derived_decisions() -> None:
    idle = struct.pack("<BBI", 11, 0, 1)
    idle += struct.pack("<IBBI", 97268402, 0, 0x02, 0)
    idle += struct.pack("<I", 0)  # special summon
    idle += struct.pack("<I", 0)  # change position
    idle += struct.pack("<I", 0)  # set monster
    idle += struct.pack("<I", 0)  # set spell/trap
    idle += struct.pack("<I", 0)  # activate
    idle += bytes((0, 1, 0))
    idle_message = struct.pack("<I", len(idle)) + idle
    idle_request = OcgcoreMessageDecoder().decode_batch(
        idle_message, request_id="idle"
    ).request
    assert idle_request is not None
    assert [candidate.candidate_id for candidate in idle_request.candidates] == [
        "normal_summon:0",
        "control:end_turn",
    ]
    normal_summon = Action(
        kind=ActionKind.NORMAL_SUMMON,
        player=0,
        selections=(Selection("normal_summon:0"),),
        request_signature=idle_request.request_signature,
    )
    assert ActionResponseEncoder().encode(idle_request, normal_summon).data == b"\0\0\0\0"

    unavailable = 0xFFFFFFFF ^ (1 << 0) ^ (1 << 2)
    place = struct.pack("<BBBI", 18, 0, 1, unavailable)
    place_message = struct.pack("<I", len(place)) + place
    place_request = OcgcoreMessageDecoder().decode_batch(
        place_message, request_id="place"
    ).request
    assert place_request is not None
    assert [candidate.candidate_id for candidate in place_request.candidates] == [
        "zone:0:4:0",
        "zone:0:4:2",
    ]
    zone = Action(
        kind=ActionKind.SELECT_ZONE,
        player=0,
        selections=(Selection("zone:0:4:2"),),
        request_signature=place_request.request_signature,
    )
    assert ActionResponseEncoder().encode(place_request, zone).data == bytes((0, 4, 2))


def test_optional_empty_chain_request_requires_explicit_pass() -> None:
    chain = struct.pack("<BBBBIII", 16, 0, 0, 0, 0, 0, 0)
    message = struct.pack("<I", len(chain)) + chain
    request = OcgcoreMessageDecoder().decode_batch(
        message, request_id="empty-chain"
    ).request
    assert request is not None
    assert request.request_type == "select_chain"
    assert [candidate.candidate_id for candidate in request.candidates] == ["control:pass"]
    action = Action(
        kind=ActionKind.PASS,
        player=0,
        selections=(Selection("control:pass"),),
        request_signature=request.request_signature,
    )
    assert ActionResponseEncoder().encode(request, action).data == struct.pack("<i", -1)


def test_malformed_selection_frames_fail_explicitly() -> None:
    decoder = OcgcoreMessageDecoder()
    truncated_effect = struct.pack("<I", 1) + bytes([12])
    with pytest.raises(InvalidBridgeMessageError, match="truncated"):
        decoder.decode_batch(truncated_effect, request_id="truncated-effect")

    decoder._registry.pop(MessageType.SELECT_YES_NO)
    valid_yes_no = bytes.fromhex("0a0000000d000807060504030201")
    with pytest.raises(UnsupportedBridgeMessageError) as captured:
        decoder.decode_batch(valid_yes_no, request_id="registry-gap")
    assert captured.value.category == "unsupported_message"

    valid = bytes.fromhex("0a0000000d000807060504030201")
    for end in range(1, len(valid)):
        with pytest.raises(InvalidBridgeMessageError):
            decoder.decode_batch(valid[:end], request_id=f"truncated:{end}")
    with pytest.raises(InvalidBridgeMessageError, match="message type"):
        split_message_stream(struct.pack("<I", 0))
    with pytest.raises(InvalidBridgeMessageError, match="declares"):
        split_message_stream(struct.pack("<I", 100) + b"short")


def test_protocol_version_mismatch_is_rejected_before_decode_or_encode() -> None:
    with pytest.raises(OcgcoreVersionMismatchError, match="decoder supports"):
        OcgcoreMessageDecoder((12, 0))
    with pytest.raises(OcgcoreVersionMismatchError, match="encoder supports"):
        ActionResponseEncoder((12, 0))
