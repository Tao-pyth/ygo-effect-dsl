from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from hashlib import sha256
import struct
from typing import Any, Callable, Mapping, Sequence

from ygo_effect_dsl.engine.action.models import Action, Selection
from ygo_effect_dsl.engine.bridge.decision import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
    DecisionResponse,
    validate_decision_response,
)
from ygo_effect_dsl.engine.bridge.errors import (
    InvalidBridgeMessageError,
    InvalidBridgeResponseError,
    UnsupportedBridgeMessageError,
)
from ygo_effect_dsl.engine.bridge.ocgcore.errors import OcgcoreVersionMismatchError
from ygo_effect_dsl.engine.bridge.ocgcore.types import (
    API_VERSION,
    MAX_RESPONSE_BYTES,
    CoreLog,
)
from ygo_effect_dsl.engine.canonical import canonical_json


PROTOCOL_VERSION = "ocgcore-api-11.0"
RESPONSE_CODEC_VERSION = "ocgcore-api-11.0-response-v1"
MAX_MESSAGE_BYTES = 1024 * 1024
_FRAME_LENGTH = struct.Struct("<I")
_INT32 = struct.Struct("<i")
_CARD_RESPONSE_HEADER = struct.Struct("<iI")


class MessageType(IntEnum):
    SELECT_BATTLE_COMMAND = 10
    SELECT_IDLE_COMMAND = 11
    SELECT_EFFECT_YES_NO = 12
    SELECT_YES_NO = 13
    SELECT_OPTION = 14
    SELECT_CARD = 15
    SELECT_CHAIN = 16
    SELECT_PLACE = 18
    SELECT_POSITION = 19
    SELECT_TRIBUTE = 20
    SORT_CHAIN = 21
    SELECT_COUNTER = 22
    SELECT_SUM = 23
    SELECT_DISABLED_FIELD = 24
    SORT_CARD = 25
    SELECT_UNSELECT_CARD = 26
    ROCK_PAPER_SCISSORS = 132
    ANNOUNCE_RACE = 140
    ANNOUNCE_ATTRIBUTE = 141
    ANNOUNCE_CARD = 142
    ANNOUNCE_NUMBER = 143


SELECTION_MESSAGE_TYPES = frozenset(int(message_type) for message_type in MessageType)


@dataclass(frozen=True)
class MessageFrame:
    message_type: int
    payload: bytes


@dataclass(frozen=True)
class DecodedMessageBatch:
    frames: tuple[MessageFrame, ...]
    request: DecisionRequest | None
    logs: tuple[CoreLog, ...] = ()


@dataclass(frozen=True)
class EncodedResponse:
    request_type: str
    request_signature: str
    selected_candidate_ids: tuple[str, ...]
    data: bytes
    codec_version: str = RESPONSE_CODEC_VERSION

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "codec_version": self.codec_version,
            "request_signature": self.request_signature,
            "request_type": self.request_type,
            "response_hex": self.data.hex(),
            "response_length": len(self.data),
            "response_sha256": sha256(self.data).hexdigest(),
            "selected_candidate_ids": list(self.selected_candidate_ids),
        }


class _Reader:
    def __init__(self, payload: bytes, message_name: str) -> None:
        self.payload = payload
        self.message_name = message_name
        self.offset = 0

    def _read(self, format_: str, label: str) -> int:
        size = struct.calcsize(format_)
        end = self.offset + size
        if end > len(self.payload):
            raise InvalidBridgeMessageError(
                f"{self.message_name}.{label} is truncated at byte {self.offset}"
            )
        value = struct.unpack_from(format_, self.payload, self.offset)[0]
        self.offset = end
        return int(value)

    def u8(self, label: str) -> int:
        return self._read("<B", label)

    def u16(self, label: str) -> int:
        return self._read("<H", label)

    def u32(self, label: str) -> int:
        return self._read("<I", label)

    def u64(self, label: str) -> int:
        return self._read("<Q", label)

    def finish(self) -> None:
        if self.offset != len(self.payload):
            raise InvalidBridgeMessageError(
                f"{self.message_name} has {len(self.payload) - self.offset} trailing byte(s)"
            )


def split_message_stream(data: bytes) -> tuple[MessageFrame, ...]:
    if len(data) > MAX_MESSAGE_BYTES:
        raise InvalidBridgeMessageError(
            f"ocgcore message stream exceeds {MAX_MESSAGE_BYTES} bytes"
        )
    frames: list[MessageFrame] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < _FRAME_LENGTH.size:
            raise InvalidBridgeMessageError("ocgcore message frame length is truncated")
        length = _FRAME_LENGTH.unpack_from(data, offset)[0]
        offset += _FRAME_LENGTH.size
        if length < 1:
            raise InvalidBridgeMessageError("ocgcore message frame must include a message type")
        if length > MAX_MESSAGE_BYTES:
            raise InvalidBridgeMessageError(
                f"ocgcore message frame exceeds {MAX_MESSAGE_BYTES} bytes"
            )
        end = offset + length
        if end > len(data):
            raise InvalidBridgeMessageError(
                f"ocgcore message frame declares {length} bytes but only {len(data) - offset} remain"
            )
        message = bytes(data[offset:end])
        frames.append(MessageFrame(message_type=message[0], payload=message[1:]))
        offset = end
    return tuple(frames)


def _read_player(reader: _Reader) -> int:
    player = reader.u8("player")
    if player not in (0, 1):
        raise InvalidBridgeMessageError(f"{reader.message_name}.player must be 0 or 1")
    return player


class OcgcoreMessageDecoder:
    """Decode API 11.0 selection messages into pointer-free DecisionRequests."""

    def __init__(self, api_version: tuple[int, int] = API_VERSION) -> None:
        if api_version != API_VERSION:
            raise OcgcoreVersionMismatchError(
                f"decoder supports ocgcore API {API_VERSION[0]}.{API_VERSION[1]}, "
                f"got {api_version[0]}.{api_version[1]}"
            )
        self.api_version = api_version
        self._registry: dict[
            int, Callable[[MessageFrame, str, DecisionContext], DecisionRequest]
        ] = {
            MessageType.SELECT_BATTLE_COMMAND: self._decode_battle_command,
            MessageType.SELECT_IDLE_COMMAND: self._decode_idle_command,
            MessageType.SELECT_EFFECT_YES_NO: self._decode_effect_yes_no,
            MessageType.SELECT_YES_NO: self._decode_yes_no,
            MessageType.SELECT_OPTION: self._decode_option,
            MessageType.SELECT_CARD: self._decode_card,
            MessageType.SELECT_CHAIN: self._decode_chain,
            MessageType.SELECT_PLACE: self._decode_place,
            MessageType.SELECT_POSITION: self._decode_position,
            MessageType.SELECT_TRIBUTE: self._decode_tribute,
            MessageType.SORT_CHAIN: self._decode_sort,
            MessageType.SELECT_COUNTER: self._decode_counter,
            MessageType.SELECT_SUM: self._decode_sum,
            MessageType.SELECT_DISABLED_FIELD: self._decode_place,
            MessageType.SORT_CARD: self._decode_sort,
            MessageType.SELECT_UNSELECT_CARD: self._decode_unselect_card,
            MessageType.ROCK_PAPER_SCISSORS: self._decode_rock_paper_scissors,
            MessageType.ANNOUNCE_RACE: self._decode_announce_mask,
            MessageType.ANNOUNCE_ATTRIBUTE: self._decode_announce_mask,
            MessageType.ANNOUNCE_CARD: self._decode_announce_card,
            MessageType.ANNOUNCE_NUMBER: self._decode_announce_number,
        }

    @property
    def supported_message_types(self) -> tuple[int, ...]:
        return tuple(sorted(int(key) for key in self._registry))

    def decode_batch(
        self,
        data: bytes,
        *,
        request_id: str,
        context: DecisionContext | None = None,
        logs: Sequence[CoreLog] = (),
    ) -> DecodedMessageBatch:
        frames = split_message_stream(data)
        base_context = context or DecisionContext()
        request: DecisionRequest | None = None
        for frame in frames:
            if frame.message_type == 162:
                raise UnsupportedBridgeMessageError(
                    "MSG_RELOAD_FIELD invalidates persistent card-instance authority"
                )
            decoder = self._registry.get(frame.message_type)
            if decoder is None:
                if frame.message_type in SELECTION_MESSAGE_TYPES:
                    raise UnsupportedBridgeMessageError(
                        f"ocgcore selection message {frame.message_type} is not registered "
                        f"for {PROTOCOL_VERSION}"
                    )
                continue
            if request is not None:
                raise InvalidBridgeMessageError(
                    "one process batch must not contain multiple selection requests"
                )
            request = decoder(frame, request_id, base_context)
        return DecodedMessageBatch(
            frames=frames,
            request=request,
            logs=tuple(logs),
        )

    @staticmethod
    def _request_context(
        base: DecisionContext,
        message_type: MessageType,
        player: int,
        extra: Mapping[str, Any],
    ) -> DecisionContext:
        version_metadata = dict(base.version_metadata)
        version_metadata["ocgcore_api"] = f"{API_VERSION[0]}.{API_VERSION[1]}"
        version_metadata["ocgcore_protocol"] = PROTOCOL_VERSION
        merged_extra = dict(base.extra)
        merged_extra.update(
            {
                "message_type": int(message_type),
                "message_name": message_type.name.lower(),
                **extra,
            }
        )
        return DecisionContext(
            phase=base.phase,
            chain=base.chain,
            turn_player=base.turn_player,
            priority_player=player,
            visible_board=dict(base.visible_board),
            request_source="ocgcore",
            version_metadata=version_metadata,
            extra=merged_extra,
        )

    def _decode_battle_command(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_battle_command")
        player = _read_player(reader)
        candidates: list[Candidate] = []
        activate_count = reader.u32("activate_count")
        for index in range(activate_count):
            code = reader.u32(f"activate[{index}].code")
            controller = reader.u8(f"activate[{index}].controller")
            location = reader.u8(f"activate[{index}].location")
            sequence = reader.u32(f"activate[{index}].sequence")
            description = reader.u64(f"activate[{index}].description")
            client_mode = reader.u8(f"activate[{index}].client_mode")
            candidates.append(
                Candidate(
                    candidate_id=f"activate:{index}",
                    kind="effect",
                    label=str(description),
                    card_ref={
                        "controller": controller,
                        "location": location,
                        "public_card_id": code,
                        "sequence": sequence,
                    },
                    effect_ref={
                        "client_mode": client_mode,
                        "description": description,
                    },
                    payload={
                        "action_kind": "ACTIVATE_EFFECT",
                        "response_codec": "int32",
                        "response_value": index << 16,
                    },
                )
            )
        attack_count = reader.u32("attack_count")
        for index in range(attack_count):
            code = reader.u32(f"attack[{index}].code")
            controller = reader.u8(f"attack[{index}].controller")
            location = reader.u8(f"attack[{index}].location")
            sequence = reader.u8(f"attack[{index}].sequence")
            direct_attackable = reader.u8(f"attack[{index}].direct_attackable")
            if direct_attackable not in (0, 1):
                raise InvalidBridgeMessageError(
                    "select_battle_command.direct_attackable must be 0 or 1"
                )
            candidates.append(
                Candidate(
                    candidate_id=f"attack:{index}",
                    kind="attack",
                    label=str(code),
                    card_ref={
                        "controller": controller,
                        "location": location,
                        "public_card_id": code,
                        "sequence": sequence,
                    },
                    payload={
                        "action_kind": "ATTACK",
                        "direct_attackable": bool(direct_attackable),
                        "response_codec": "int32",
                        "response_value": (index << 16) | 1,
                    },
                )
            )
        to_main_phase_2 = reader.u8("to_main_phase_2")
        to_end_phase = reader.u8("to_end_phase")
        reader.finish()
        if to_main_phase_2 not in (0, 1) or to_end_phase not in (0, 1):
            raise InvalidBridgeMessageError(
                "select_battle_command phase flags must be 0 or 1"
            )
        if to_main_phase_2:
            candidates.append(
                Candidate(
                    candidate_id="control:enter_main_phase_2",
                    kind="phase",
                    label="Enter main phase 2",
                    payload={
                        "action_kind": "ENTER_MAIN_PHASE_2",
                        "response_codec": "int32",
                        "response_value": 2,
                    },
                )
            )
        if to_end_phase:
            candidates.append(
                Candidate(
                    candidate_id="control:end_turn",
                    kind="end_turn",
                    label="End turn",
                    payload={
                        "action_kind": "END_TURN",
                        "response_codec": "int32",
                        "response_value": 3,
                    },
                )
            )
        if not candidates:
            raise InvalidBridgeMessageError(
                "select_battle_command must expose at least one core-derived action"
            )
        return DecisionRequest(
            request_id=request_id,
            request_type="select_battle_command",
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(),
            context=self._request_context(
                base,
                MessageType.SELECT_BATTLE_COMMAND,
                player,
                {
                    "to_end_phase": bool(to_end_phase),
                    "to_main_phase_2": bool(to_main_phase_2),
                },
            ),
        )

    def _decode_effect_yes_no(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_effect_yes_no")
        player = _read_player(reader)
        code = reader.u32("code")
        controller = reader.u8("controller")
        location = reader.u8("location")
        sequence = reader.u32("sequence")
        position = reader.u32("position")
        description = reader.u64("description")
        reader.finish()
        card_ref = {
            "controller": controller,
            "location": location,
            "position": position,
            "public_card_id": code,
            "sequence": sequence,
        }
        candidates = (
            Candidate(
                candidate_id="choice:0",
                kind="decline",
                label="No",
                card_ref=card_ref,
                effect_ref={"description": description},
                payload={
                    "action_kind": "DECLINE",
                    "response_codec": "int32",
                    "response_value": 0,
                },
            ),
            Candidate(
                candidate_id="choice:1",
                kind="effect",
                label="Yes",
                card_ref=card_ref,
                effect_ref={"description": description},
                payload={
                    "action_kind": "ACTIVATE_EFFECT",
                    "response_codec": "int32",
                    "response_value": 1,
                },
            ),
        )
        return DecisionRequest(
            request_id=request_id,
            request_type="select_effect_yes_no",
            player=player,
            candidates=candidates,
            constraints=DecisionConstraints(),
            context=self._request_context(
                base,
                MessageType.SELECT_EFFECT_YES_NO,
                player,
                {"description": description},
            ),
        )

    def _decode_sort(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        message_type = MessageType(frame.message_type)
        request_type = (
            "sort_chain" if message_type == MessageType.SORT_CHAIN else "sort_card"
        )
        reader = _Reader(frame.payload, request_type)
        player = _read_player(reader)
        count = reader.u32("count")
        if count == 0 or count > 0xFF:
            raise InvalidBridgeMessageError(
                f"{request_type}.count must be between 1 and 255"
            )
        candidates: list[Candidate] = []
        for index in range(count):
            code = reader.u32(f"cards[{index}].code")
            controller = reader.u8(f"cards[{index}].controller")
            location = reader.u32(f"cards[{index}].location")
            sequence = reader.u32(f"cards[{index}].sequence")
            candidates.append(
                Candidate(
                    candidate_id=f"card:{index}",
                    kind="card",
                    label=str(code),
                    card_ref={
                        "controller": controller,
                        "location": location,
                        "public_card_id": code,
                        "sequence": sequence,
                    },
                    payload={
                        "action_kind": "ORDER_CARDS",
                        "response_codec": "sort_order",
                        "response_index": index,
                    },
                )
            )
        reader.finish()
        candidates.append(
            Candidate(
                candidate_id="control:keep_order",
                kind="finish",
                label="Keep current order",
                payload={
                    "action_kind": "FINISH_SELECTION",
                    "response_codec": "sort_order",
                    "response_index": -1,
                },
            )
        )
        return DecisionRequest(
            request_id=request_id,
            request_type=request_type,
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(
                min_selections=1,
                max_selections=count,
                ordered=False,
            ),
            context=self._request_context(base, message_type, player, {"count": count}),
        )

    def _decode_rock_paper_scissors(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "rock_paper_scissors")
        player = _read_player(reader)
        reader.finish()
        candidates = tuple(
            Candidate(
                candidate_id=f"hand:{value}",
                kind="hand_sign",
                label=label,
                payload={
                    "action_kind": "ROCK_PAPER_SCISSORS",
                    "response_codec": "int32",
                    "response_value": value,
                },
            )
            for value, label in ((1, "Rock"), (2, "Paper"), (3, "Scissors"))
        )
        return DecisionRequest(
            request_id=request_id,
            request_type="rock_paper_scissors",
            player=player,
            candidates=candidates,
            constraints=DecisionConstraints(),
            context=self._request_context(
                base, MessageType.ROCK_PAPER_SCISSORS, player, {}
            ),
        )

    def _decode_announce_mask(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        message_type = MessageType(frame.message_type)
        is_race = message_type == MessageType.ANNOUNCE_RACE
        request_type = "announce_race" if is_race else "announce_attribute"
        reader = _Reader(frame.payload, request_type)
        player = _read_player(reader)
        count = reader.u8("count")
        available = reader.u64("available") if is_race else reader.u32("available")
        reader.finish()
        if count == 0 or available.bit_count() < count:
            raise InvalidBridgeMessageError(
                f"{request_type} requires enough available bits for count"
            )
        action_kind = "ANNOUNCE_RACE" if is_race else "ANNOUNCE_ATTRIBUTE"
        candidates = tuple(
            Candidate(
                candidate_id=f"bit:{bit}",
                kind="race" if is_race else "attribute",
                label=str(bit),
                payload={
                    "action_kind": action_kind,
                    "response_bit": 1 << bit,
                    "response_codec": "bit_mask",
                },
            )
            for bit in range(64 if is_race else 32)
            if available & (1 << bit)
        )
        return DecisionRequest(
            request_id=request_id,
            request_type=request_type,
            player=player,
            candidates=candidates,
            constraints=DecisionConstraints(
                min_selections=count,
                max_selections=count,
            ),
            context=self._request_context(
                base,
                message_type,
                player,
                {
                    "available_mask": available,
                    "count": count,
                    "response_width": 64 if is_race else 32,
                },
            ),
        )

    def _decode_announce_card(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "announce_card")
        player = _read_player(reader)
        count = reader.u8("opcode_count")
        opcodes = [reader.u64(f"opcodes[{index}]") for index in range(count)]
        reader.finish()
        return DecisionRequest(
            request_id=request_id,
            request_type="announce_card",
            player=player,
            candidates=(
                Candidate(
                    candidate_id="input:card_code",
                    kind="card_code",
                    label="Card code",
                    payload={
                        "action_kind": "ANNOUNCE_CARD",
                        "response_codec": "selection_int32",
                    },
                ),
            ),
            constraints=DecisionConstraints(),
            context=self._request_context(
                base, MessageType.ANNOUNCE_CARD, player, {"opcodes": opcodes}
            ),
        )

    def _decode_announce_number(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "announce_number")
        player = _read_player(reader)
        count = reader.u8("count")
        if count == 0:
            raise InvalidBridgeMessageError("announce_number.count must be positive")
        candidates = tuple(
            Candidate(
                candidate_id=f"number:{index}",
                kind="number",
                label=str(number),
                payload={
                    "action_kind": "ANNOUNCE_NUMBER",
                    "announced_number": number,
                    "response_codec": "int32",
                    "response_value": index,
                },
            )
            for index in range(count)
            for number in [reader.u64(f"numbers[{index}]")]
        )
        reader.finish()
        return DecisionRequest(
            request_id=request_id,
            request_type="announce_number",
            player=player,
            candidates=candidates,
            constraints=DecisionConstraints(),
            context=self._request_context(
                base, MessageType.ANNOUNCE_NUMBER, player, {}
            ),
        )

    def _decode_yes_no(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_yes_no")
        player = _read_player(reader)
        description = reader.u64("description")
        reader.finish()
        candidates = (
            Candidate(
                candidate_id="choice:0",
                kind="option",
                label="No",
                payload={
                    "response_codec": "int32",
                    "response_value": 0,
                },
            ),
            Candidate(
                candidate_id="choice:1",
                kind="option",
                label="Yes",
                payload={
                    "response_codec": "int32",
                    "response_value": 1,
                },
            ),
        )
        return DecisionRequest(
            request_id=request_id,
            request_type="select_yes_no",
            player=player,
            candidates=candidates,
            constraints=DecisionConstraints(),
            context=self._request_context(
                base, MessageType.SELECT_YES_NO, player, {"description": description}
            ),
        )

    @staticmethod
    def _idle_card_candidate(
        reader: _Reader,
        *,
        group: str,
        index: int,
        command_type: int,
        action_kind: str,
        compact_sequence: bool = False,
    ) -> Candidate:
        code = reader.u32(f"{group}[{index}].code")
        controller = reader.u8(f"{group}[{index}].controller")
        location = reader.u8(f"{group}[{index}].location")
        sequence = (
            reader.u8(f"{group}[{index}].sequence")
            if compact_sequence
            else reader.u32(f"{group}[{index}].sequence")
        )
        return Candidate(
            candidate_id=f"{group}:{index}",
            kind="card",
            label=str(code),
            card_ref={
                "controller": controller,
                "location": location,
                "public_card_id": code,
                "sequence": sequence,
            },
            payload={
                "action_kind": action_kind,
                "response_codec": "int32",
                "response_value": (index << 16) | command_type,
            },
        )

    def _decode_idle_command(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_idle_command")
        player = _read_player(reader)
        candidates: list[Candidate] = []
        groups = (
            ("normal_summon", 0, "NORMAL_SUMMON", False),
            ("special_summon", 1, "SPECIAL_SUMMON", False),
            ("change_position", 2, "CHANGE_POSITION", True),
            ("set_monster", 3, "SET_MONSTER", False),
            ("set_spell_trap", 4, "SET_SPELL_TRAP", False),
        )
        for group, command_type, action_kind, compact_sequence in groups:
            count = reader.u32(f"{group}_count")
            for index in range(count):
                candidates.append(
                    self._idle_card_candidate(
                        reader,
                        group=group,
                        index=index,
                        command_type=command_type,
                        action_kind=action_kind,
                        compact_sequence=compact_sequence,
                    )
                )

        activate_count = reader.u32("activate_count")
        for index in range(activate_count):
            code = reader.u32(f"activate[{index}].code")
            controller = reader.u8(f"activate[{index}].controller")
            location = reader.u8(f"activate[{index}].location")
            sequence = reader.u32(f"activate[{index}].sequence")
            description = reader.u64(f"activate[{index}].description")
            client_mode = reader.u8(f"activate[{index}].client_mode")
            candidates.append(
                Candidate(
                    candidate_id=f"activate:{index}",
                    kind="effect",
                    label=str(description),
                    card_ref={
                        "controller": controller,
                        "location": location,
                        "public_card_id": code,
                        "sequence": sequence,
                    },
                    effect_ref={
                        "client_mode": client_mode,
                        "description": description,
                    },
                    payload={
                        "action_kind": "ACTIVATE_EFFECT",
                        "response_codec": "int32",
                        "response_value": (index << 16) | 5,
                    },
                )
            )

        to_battle_phase = reader.u8("to_battle_phase")
        to_end_phase = reader.u8("to_end_phase")
        can_shuffle = reader.u8("can_shuffle")
        for label, value in (
            ("to_battle_phase", to_battle_phase),
            ("to_end_phase", to_end_phase),
            ("can_shuffle", can_shuffle),
        ):
            if value not in (0, 1):
                raise InvalidBridgeMessageError(
                    f"select_idle_command.{label} must be 0 or 1"
                )
        if to_battle_phase:
            candidates.append(
                Candidate(
                    candidate_id="control:enter_battle_phase",
                    kind="phase",
                    label="Enter battle phase",
                    payload={
                        "action_kind": "ENTER_BATTLE_PHASE",
                        "response_codec": "int32",
                        "response_value": 6,
                    },
                )
            )
        if to_end_phase:
            candidates.append(
                Candidate(
                    candidate_id="control:end_turn",
                    kind="end_turn",
                    label="End turn",
                    payload={
                        "action_kind": "END_TURN",
                        "response_codec": "int32",
                        "response_value": 7,
                    },
                )
            )
        if can_shuffle:
            candidates.append(
                Candidate(
                    candidate_id="control:shuffle_hand",
                    kind="command",
                    label="Shuffle hand",
                    payload={
                        "action_kind": "SHUFFLE_HAND",
                        "response_codec": "int32",
                        "response_value": 8,
                    },
                )
            )
        reader.finish()
        if not candidates:
            raise InvalidBridgeMessageError(
                "select_idle_command must expose at least one core-derived action"
            )
        return DecisionRequest(
            request_id=request_id,
            request_type="select_idle_command",
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(),
            context=self._request_context(
                base,
                MessageType.SELECT_IDLE_COMMAND,
                player,
                {
                    "can_shuffle": bool(can_shuffle),
                    "to_battle_phase": bool(to_battle_phase),
                    "to_end_phase": bool(to_end_phase),
                },
            ),
        )

    def _decode_option(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_option")
        player = _read_player(reader)
        count = reader.u8("count")
        if count == 0:
            raise InvalidBridgeMessageError("select_option.count must be positive")
        candidates = tuple(
            Candidate(
                candidate_id=f"option:{index}",
                kind="option",
                label=str(description),
                payload={
                    "option_description": description,
                    "response_codec": "int32",
                    "response_value": index,
                },
            )
            for index in range(count)
            for description in [reader.u64(f"options[{index}]")]
        )
        reader.finish()
        return DecisionRequest(
            request_id=request_id,
            request_type="select_option",
            player=player,
            candidates=candidates,
            constraints=DecisionConstraints(),
            context=self._request_context(base, MessageType.SELECT_OPTION, player, {}),
        )

    def _decode_card(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_card")
        player = _read_player(reader)
        raw_cancelable = reader.u8("cancelable")
        if raw_cancelable not in (0, 1):
            raise InvalidBridgeMessageError("select_card.cancelable must be 0 or 1")
        cancelable = bool(raw_cancelable)
        core_min = reader.u32("min")
        core_max = reader.u32("max")
        count = reader.u32("count")
        if count == 0 or core_min > core_max or core_max > count:
            raise InvalidBridgeMessageError(
                "select_card requires 0 <= min <= max <= candidate count and a non-empty list"
            )
        candidates: list[Candidate] = []
        for index in range(count):
            code = reader.u32(f"cards[{index}].code")
            controller = reader.u8(f"cards[{index}].controller")
            location = reader.u8(f"cards[{index}].location")
            sequence = reader.u32(f"cards[{index}].sequence")
            position = reader.u32(f"cards[{index}].position")
            candidates.append(
                Candidate(
                    candidate_id=f"card:{index}",
                    kind="card",
                    label=str(code),
                    card_ref={
                        "controller": controller,
                        "location": location,
                        "position": position,
                        "public_card_id": code,
                        "sequence": sequence,
                    },
                    payload={
                        "response_codec": "card_indices",
                        "response_index": index,
                    },
                )
            )
        reader.finish()
        return DecisionRequest(
            request_id=request_id,
            request_type="select_card",
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(
                min_selections=0 if cancelable else core_min,
                max_selections=core_max,
                ordered=False,
                allow_duplicates=False,
                required=not cancelable and core_min > 0,
            ),
            context=self._request_context(
                base,
                MessageType.SELECT_CARD,
                player,
                {"cancelable": cancelable, "core_max": core_max, "core_min": core_min},
            ),
        )

    def _decode_tribute(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_tribute")
        player = _read_player(reader)
        raw_cancelable = reader.u8("cancelable")
        if raw_cancelable not in (0, 1):
            raise InvalidBridgeMessageError("select_tribute.cancelable must be 0 or 1")
        cancelable = bool(raw_cancelable)
        core_min = reader.u32("min")
        core_max = reader.u32("max")
        count = reader.u32("count")
        if count == 0 or core_min > core_max:
            raise InvalidBridgeMessageError(
                "select_tribute requires a non-empty list and min <= max"
            )
        candidates: list[Candidate] = []
        for index in range(count):
            code = reader.u32(f"cards[{index}].code")
            controller = reader.u8(f"cards[{index}].controller")
            location = reader.u8(f"cards[{index}].location")
            sequence = reader.u32(f"cards[{index}].sequence")
            release_value = reader.u8(f"cards[{index}].release_value")
            if release_value == 0:
                raise InvalidBridgeMessageError(
                    "select_tribute.release_value must be positive"
                )
            candidates.append(
                Candidate(
                    candidate_id=f"card:{index}",
                    kind="card",
                    label=str(code),
                    card_ref={
                        "controller": controller,
                        "location": location,
                        "public_card_id": code,
                        "sequence": sequence,
                    },
                    payload={
                        "action_kind": "SELECT_TRIBUTE",
                        "release_value": release_value,
                        "response_codec": "card_indices",
                        "response_index": index,
                    },
                )
            )
        reader.finish()
        return DecisionRequest(
            request_id=request_id,
            request_type="select_tribute",
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(
                min_selections=0 if cancelable else 1,
                max_selections=min(count, core_max),
                required=not cancelable,
            ),
            context=self._request_context(
                base,
                MessageType.SELECT_TRIBUTE,
                player,
                {"cancelable": cancelable, "core_max": core_max, "core_min": core_min},
            ),
        )

    def _decode_counter(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_counter")
        player = _read_player(reader)
        counter_type = reader.u16("counter_type")
        required_count = reader.u16("required_count")
        count = reader.u32("count")
        if required_count == 0 or count == 0:
            raise InvalidBridgeMessageError(
                "select_counter requires counters and at least one card"
            )
        candidates: list[Candidate] = []
        available_total = 0
        for index in range(count):
            code = reader.u32(f"cards[{index}].code")
            controller = reader.u8(f"cards[{index}].controller")
            location = reader.u8(f"cards[{index}].location")
            sequence = reader.u8(f"cards[{index}].sequence")
            available = reader.u16(f"cards[{index}].available")
            if available == 0:
                raise InvalidBridgeMessageError(
                    "select_counter candidate availability must be positive"
                )
            available_total += available
            candidates.append(
                Candidate(
                    candidate_id=f"card:{index}",
                    kind="card_counter",
                    label=str(code),
                    card_ref={
                        "controller": controller,
                        "location": location,
                        "public_card_id": code,
                        "sequence": sequence,
                    },
                    payload={
                        "action_kind": "DISTRIBUTE_COUNTERS",
                        "available_count": available,
                        "response_codec": "counter_vector",
                        "response_index": index,
                    },
                )
            )
        reader.finish()
        if available_total < required_count:
            raise InvalidBridgeMessageError(
                "select_counter exposes fewer counters than required"
            )
        return DecisionRequest(
            request_id=request_id,
            request_type="select_counter",
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(
                min_selections=1,
                max_selections=min(count, required_count),
            ),
            context=self._request_context(
                base,
                MessageType.SELECT_COUNTER,
                player,
                {"counter_type": counter_type, "required_count": required_count},
            ),
        )

    @staticmethod
    def _read_sum_card(reader: _Reader, group: str, index: int) -> dict[str, Any]:
        code = reader.u32(f"{group}[{index}].code")
        controller = reader.u8(f"{group}[{index}].controller")
        location = reader.u8(f"{group}[{index}].location")
        sequence = reader.u32(f"{group}[{index}].sequence")
        position = reader.u32(f"{group}[{index}].position")
        sum_param = reader.u32(f"{group}[{index}].sum_param")
        return {
            "card_ref": {
                "controller": controller,
                "location": location,
                "position": position,
                "public_card_id": code,
                "sequence": sequence,
            },
            "code": code,
            "sum_param": sum_param,
        }

    def _decode_sum(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_sum")
        player = _read_player(reader)
        mode = reader.u8("mode")
        if mode not in (0, 1):
            raise InvalidBridgeMessageError("select_sum.mode must be 0 or 1")
        target = reader.u32("target")
        core_min = reader.u32("min")
        core_max = reader.u32("max")
        must_count = reader.u32("must_count")
        must_cards = [
            self._read_sum_card(reader, "must_cards", index)
            for index in range(must_count)
        ]
        count = reader.u32("count")
        if count == 0:
            raise InvalidBridgeMessageError("select_sum requires selectable cards")
        if mode == 0 and (core_min > core_max or core_max > count):
            raise InvalidBridgeMessageError(
                "select_sum exact mode requires min <= max <= candidate count"
            )
        candidates: list[Candidate] = []
        for index in range(count):
            card = self._read_sum_card(reader, "cards", index)
            candidates.append(
                Candidate(
                    candidate_id=f"card:{index}",
                    kind="card_sum",
                    label=str(card["code"]),
                    card_ref=card["card_ref"],
                    payload={
                        "action_kind": "SELECT_SUM",
                        "response_codec": "card_indices",
                        "response_index": index,
                        "sum_param": card["sum_param"],
                    },
                )
            )
        reader.finish()
        return DecisionRequest(
            request_id=request_id,
            request_type="select_sum",
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(
                min_selections=core_min if mode == 0 else 0,
                max_selections=core_max if mode == 0 else count,
                required=mode == 0 and core_min > 0,
            ),
            context=self._request_context(
                base,
                MessageType.SELECT_SUM,
                player,
                {
                    "core_max": core_max,
                    "core_min": core_min,
                    "mode": mode,
                    "must_sum_params": [card["sum_param"] for card in must_cards],
                    "target": target,
                },
            ),
        )

    def _decode_unselect_card(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_unselect_card")
        player = _read_player(reader)
        raw_finishable = reader.u8("finishable")
        raw_cancelable = reader.u8("cancelable")
        if raw_finishable not in (0, 1) or raw_cancelable not in (0, 1):
            raise InvalidBridgeMessageError(
                "select_unselect_card finishable/cancelable must be 0 or 1"
            )
        finishable = bool(raw_finishable)
        cancelable = bool(raw_cancelable)
        core_min = reader.u32("min")
        core_max = reader.u32("max")
        candidates: list[Candidate] = []
        response_index = 0
        for group, selected in (("select", False), ("unselect", True)):
            count = reader.u32(f"{group}_count")
            for index in range(count):
                code = reader.u32(f"{group}[{index}].code")
                controller = reader.u8(f"{group}[{index}].controller")
                location = reader.u8(f"{group}[{index}].location")
                sequence = reader.u32(f"{group}[{index}].sequence")
                position = reader.u32(f"{group}[{index}].position")
                candidates.append(
                    Candidate(
                        candidate_id=f"{group}:{index}",
                        kind="selected_card" if selected else "card",
                        label=str(code),
                        card_ref={
                            "controller": controller,
                            "location": location,
                            "position": position,
                            "public_card_id": code,
                            "sequence": sequence,
                        },
                        payload={
                            "action_kind": "SELECT_CARD",
                            "response_codec": "unselect_action",
                            "response_index": response_index,
                        },
                    )
                )
                response_index += 1
        reader.finish()
        if finishable or cancelable:
            candidates.append(
                Candidate(
                    candidate_id="control:finish",
                    kind="finish",
                    label="Finish",
                    payload={
                        "action_kind": "FINISH_SELECTION",
                        "response_codec": "unselect_action",
                        "response_index": -1,
                    },
                )
            )
        if not candidates:
            raise InvalidBridgeMessageError(
                "select_unselect_card must expose a card or finish control"
            )
        return DecisionRequest(
            request_id=request_id,
            request_type="select_unselect_card",
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(),
            context=self._request_context(
                base,
                MessageType.SELECT_UNSELECT_CARD,
                player,
                {
                    "cancelable": cancelable,
                    "core_max": core_max,
                    "core_min": core_min,
                    "finishable": finishable,
                },
            ),
        )

    def _decode_position(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_position")
        player = _read_player(reader)
        code = reader.u32("code")
        positions = reader.u8("positions")
        reader.finish()
        allowed = positions & 0x0F
        if allowed == 0 or positions != allowed:
            raise InvalidBridgeMessageError("select_position.positions has no supported bit")
        names = {1: "face-up attack", 2: "face-down attack", 4: "face-up defense", 8: "face-down defense"}
        candidates = tuple(
            Candidate(
                candidate_id=f"position:{position}",
                kind="position",
                label=names[position],
                payload={
                    "response_codec": "int32",
                    "response_value": position,
                },
            )
            for position in (1, 2, 4, 8)
            if allowed & position
        )
        return DecisionRequest(
            request_id=request_id,
            request_type="select_position",
            player=player,
            candidates=candidates,
            constraints=DecisionConstraints(),
            context=self._request_context(
                base,
                MessageType.SELECT_POSITION,
                player,
                {"card_code": code, "position_mask": allowed},
            ),
        )

    def _decode_place(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        message_type = MessageType(frame.message_type)
        request_type = (
            "select_disabled_field"
            if message_type == MessageType.SELECT_DISABLED_FIELD
            else "select_place"
        )
        reader = _Reader(frame.payload, request_type)
        player = _read_player(reader)
        count = reader.u8("count")
        unavailable = reader.u32("unavailable_mask")
        reader.finish()
        if count == 0:
            raise InvalidBridgeMessageError("select_place.count must be positive")
        candidates: list[Candidate] = []
        for opponent, bit_shift in ((False, 0), (True, 16)):
            controller = 1 - player if opponent else player
            for location, location_shift, zone_count in ((0x04, 0, 7), (0x08, 8, 8)):
                for sequence in range(zone_count):
                    bit = 1 << (bit_shift + location_shift + sequence)
                    if unavailable & bit:
                        continue
                    candidates.append(
                        Candidate(
                            candidate_id=f"zone:{controller}:{location}:{sequence}",
                            kind="zone",
                            label=f"{controller}:{location}:{sequence}",
                            payload={
                                "action_kind": "SELECT_ZONE",
                                "response_codec": "place_triplets",
                                "response_controller": controller,
                                "response_location": location,
                                "response_sequence": sequence,
                            },
                        )
                    )
        if len(candidates) < count:
            raise InvalidBridgeMessageError(
                "select_place exposes fewer zones than its required count"
            )
        return DecisionRequest(
            request_id=request_id,
            request_type=request_type,
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(
                min_selections=count,
                max_selections=count,
                ordered=False,
                allow_duplicates=False,
                required=True,
            ),
            context=self._request_context(
                base,
                message_type,
                player,
                {"count": count, "unavailable_mask": unavailable},
            ),
        )

    def _decode_chain(
        self, frame: MessageFrame, request_id: str, base: DecisionContext
    ) -> DecisionRequest:
        reader = _Reader(frame.payload, "select_chain")
        player = _read_player(reader)
        special_count = reader.u8("special_count")
        raw_forced = reader.u8("forced")
        if raw_forced not in (0, 1):
            raise InvalidBridgeMessageError("select_chain.forced must be 0 or 1")
        forced = bool(raw_forced)
        hint_timing_player = reader.u32("hint_timing_player")
        hint_timing_opponent = reader.u32("hint_timing_opponent")
        count = reader.u32("count")
        candidates: list[Candidate] = []
        for index in range(count):
            code = reader.u32(f"chains[{index}].code")
            controller = reader.u8(f"chains[{index}].controller")
            location = reader.u8(f"chains[{index}].location")
            sequence = reader.u32(f"chains[{index}].sequence")
            position = reader.u32(f"chains[{index}].position")
            description = reader.u64(f"chains[{index}].description")
            client_mode = reader.u8(f"chains[{index}].client_mode")
            candidates.append(
                Candidate(
                    candidate_id=f"chain:{index}",
                    kind="effect",
                    label=str(description),
                    card_ref={
                        "controller": controller,
                        "location": location,
                        "position": position,
                        "public_card_id": code,
                        "sequence": sequence,
                    },
                    effect_ref={
                        "client_mode": client_mode,
                        "description": description,
                    },
                    payload={
                        "action_kind": "ACTIVATE_EFFECT",
                        "response_codec": "int32",
                        "response_value": index,
                    },
                )
            )
        if not forced:
            candidates.append(
                Candidate(
                    candidate_id="control:pass",
                    kind="pass",
                    label="Pass",
                    payload={
                        "action_kind": "PASS",
                        "response_codec": "int32",
                        "response_value": -1,
                    },
                )
            )
        reader.finish()
        if not candidates:
            raise InvalidBridgeMessageError(
                "forced select_chain must expose at least one effect candidate"
            )
        return DecisionRequest(
            request_id=request_id,
            request_type="select_chain",
            player=player,
            candidates=tuple(candidates),
            constraints=DecisionConstraints(),
            context=self._request_context(
                base,
                MessageType.SELECT_CHAIN,
                player,
                {
                    "forced": forced,
                    "hint_timing_opponent": hint_timing_opponent,
                    "hint_timing_player": hint_timing_player,
                    "special_count": special_count,
                },
            ),
        )


class ActionResponseEncoder:
    """Encode a validated Action using only owned Candidate primitive payloads."""

    def __init__(self, api_version: tuple[int, int] = API_VERSION) -> None:
        if api_version != API_VERSION:
            raise OcgcoreVersionMismatchError(
                f"encoder supports ocgcore API {API_VERSION[0]}.{API_VERSION[1]}, "
                f"got {api_version[0]}.{api_version[1]}"
            )
        self.api_version = api_version
        self._registry: dict[
            str,
            Callable[
                [DecisionRequest, tuple[Candidate, ...], tuple[Selection, ...]], bytes
            ],
        ] = {
            "select_battle_command": self._encode_int32,
            "select_idle_command": self._encode_int32,
            "select_effect_yes_no": self._encode_int32,
            "select_yes_no": self._encode_int32,
            "select_option": self._encode_int32,
            "select_card": self._encode_card_indices,
            "select_chain": self._encode_int32,
            "select_place": self._encode_place,
            "select_disabled_field": self._encode_place,
            "select_position": self._encode_int32,
            "select_tribute": self._encode_tribute_indices,
            "select_counter": self._encode_counter_vector,
            "select_sum": self._encode_sum_indices,
            "select_unselect_card": self._encode_unselect_action,
            "sort_chain": self._encode_sort_order,
            "sort_card": self._encode_sort_order,
            "rock_paper_scissors": self._encode_int32,
            "announce_race": self._encode_bit_mask,
            "announce_attribute": self._encode_bit_mask,
            "announce_card": self._encode_selection_int32,
            "announce_number": self._encode_int32,
        }

    @property
    def supported_request_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._registry))

    def encode(self, request: DecisionRequest, action: Action) -> EncodedResponse:
        try:
            return self._encode(request, action)
        except InvalidBridgeResponseError as exc:
            if exc.context:
                raise
            try:
                request_diagnostic = request.to_dict()
            except (TypeError, ValueError):
                request_diagnostic = {
                    "request_id": request.request_id,
                    "request_type": request.request_type,
                    "serialization_error": "request identity contains non-primitive data",
                }
            raise InvalidBridgeResponseError(
                str(exc),
                context={
                    "request": request_diagnostic,
                    "response": action.to_dict(),
                },
            ) from exc

    def _encode(self, request: DecisionRequest, action: Action) -> EncodedResponse:
        self._validate_request_identity(request)
        if action.player != request.player:
            raise InvalidBridgeResponseError("action.player does not match request.player")
        response = DecisionResponse(
            request_id=request.request_id,
            request_signature=action.request_signature,
            selected_candidate_ids=tuple(
                selection.candidate_id for selection in action.selections
            ),
        )
        validate_decision_response(request, response)
        codec = self._registry.get(request.request_type)
        if codec is None:
            raise UnsupportedBridgeMessageError(
                f"no response codec for request_type {request.request_type!r} in "
                f"{RESPONSE_CODEC_VERSION}"
            )
        candidate_by_id = {candidate.candidate_id: candidate for candidate in request.candidates}
        selected = tuple(
            candidate_by_id[selection.candidate_id] for selection in action.selections
        )
        self._validate_owned_payloads(selected)
        declared_action_kinds = {
            candidate.payload["action_kind"]
            for candidate in selected
            if "action_kind" in candidate.payload
        }
        if declared_action_kinds and declared_action_kinds != {action.kind.value}:
            raise InvalidBridgeResponseError(
                "action.kind does not match the selected candidate action_kind"
            )
        if request.constraints.ordered:
            orders = tuple(selection.order for selection in action.selections)
            if (
                any(not isinstance(order, int) or isinstance(order, bool) for order in orders)
                or sorted(orders) != list(range(len(orders)))
            ):
                raise InvalidBridgeResponseError(
                    "ordered response requires each order exactly once from zero"
                )
        data = codec(request, selected, action.selections)
        if not data:
            raise InvalidBridgeResponseError("response codec produced an empty buffer")
        if len(data) > MAX_RESPONSE_BYTES:
            raise InvalidBridgeResponseError(
                f"response buffer exceeds {MAX_RESPONSE_BYTES} bytes"
            )
        selected_ids = tuple(candidate.candidate_id for candidate in selected)
        return EncodedResponse(
            request_type=request.request_type,
            request_signature=request.request_signature,
            selected_candidate_ids=selected_ids,
            data=data,
        )

    def verify_trace(
        self,
        request: DecisionRequest,
        action: Action,
        trace: Mapping[str, Any],
    ) -> EncodedResponse:
        encoded = self.encode(request, action)
        expected = encoded.to_trace_dict()
        for key in (
            "codec_version",
            "request_signature",
            "request_type",
            "response_hex",
            "response_length",
            "response_sha256",
            "selected_candidate_ids",
        ):
            if trace.get(key) != expected[key]:
                raise InvalidBridgeResponseError(f"response trace mismatch for {key}")
        return encoded

    @staticmethod
    def _validate_request_identity(request: DecisionRequest) -> None:
        try:
            canonical_json(request.to_signature_dict())
        except (TypeError, ValueError) as exc:
            raise InvalidBridgeResponseError(
                "DecisionRequest identity contains non-primitive data"
            ) from exc

    @staticmethod
    def _validate_owned_payloads(candidates: tuple[Candidate, ...]) -> None:
        for candidate in candidates:
            try:
                canonical_json(candidate.payload)
            except (TypeError, ValueError) as exc:
                raise InvalidBridgeResponseError(
                    f"candidate {candidate.candidate_id!r} payload is not owned primitive data"
                ) from exc

    @staticmethod
    def _encode_int32(
        _request: DecisionRequest,
        selected: tuple[Candidate, ...],
        _selections: tuple[Selection, ...],
    ) -> bytes:
        if len(selected) != 1:
            raise InvalidBridgeResponseError("int32 response requires exactly one candidate")
        payload = selected[0].payload
        if payload.get("response_codec") != "int32":
            raise InvalidBridgeResponseError("candidate does not use the int32 response codec")
        value = payload.get("response_value")
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not -(1 << 31) <= value < (1 << 31)
        ):
            raise InvalidBridgeResponseError("candidate response_value must fit int32")
        return _INT32.pack(value)

    @staticmethod
    def _encode_card_indices(
        request: DecisionRequest,
        selected: tuple[Candidate, ...],
        _selections: tuple[Selection, ...],
    ) -> bytes:
        extra = request.context.extra
        cancelable = extra.get("cancelable") is True
        core_min = extra.get("core_min")
        core_max = extra.get("core_max")
        if not isinstance(core_min, int) or not isinstance(core_max, int):
            raise InvalidBridgeResponseError("select_card is missing native min/max metadata")
        if not selected:
            if not cancelable:
                raise InvalidBridgeResponseError("select_card is not cancelable")
            return _INT32.pack(-1)
        if not core_min <= len(selected) <= core_max:
            raise InvalidBridgeResponseError(
                "selected card count violates the native min/max constraint"
            )
        return ActionResponseEncoder._encode_card_index_payload(selected)

    @staticmethod
    def _encode_card_index_payload(selected: tuple[Candidate, ...]) -> bytes:
        indices: list[int] = []
        for candidate in selected:
            payload = candidate.payload
            if payload.get("response_codec") != "card_indices":
                raise InvalidBridgeResponseError(
                    "candidate does not use the card_indices response codec"
                )
            index = payload.get("response_index")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or index < 0
                or index > 0xFFFFFFFF
            ):
                raise InvalidBridgeResponseError("candidate response_index must fit uint32")
            indices.append(index)
        if not indices:
            return _CARD_RESPONSE_HEADER.pack(2, 0)
        if len(indices) != len(set(indices)):
            raise InvalidBridgeResponseError("selected candidates contain duplicate core indices")
        indices.sort()
        if indices[-1] <= 0xFF and len(indices) <= 0xFFFFFFFF:
            return _CARD_RESPONSE_HEADER.pack(2, len(indices)) + bytes(indices)
        if indices[-1] <= 0xFFFF:
            return _CARD_RESPONSE_HEADER.pack(1, len(indices)) + struct.pack(
                f"<{len(indices)}H", *indices
            )
        return _CARD_RESPONSE_HEADER.pack(0, len(indices)) + struct.pack(
            f"<{len(indices)}I", *indices
        )

    @staticmethod
    def _encode_tribute_indices(
        request: DecisionRequest,
        selected: tuple[Candidate, ...],
        _selections: tuple[Selection, ...],
    ) -> bytes:
        extra = request.context.extra
        cancelable = extra.get("cancelable") is True
        core_min = extra.get("core_min")
        core_max = extra.get("core_max")
        if not isinstance(core_min, int) or not isinstance(core_max, int):
            raise InvalidBridgeResponseError(
                "select_tribute is missing native min/max metadata"
            )
        if not selected:
            if not cancelable:
                raise InvalidBridgeResponseError("select_tribute is not cancelable")
            return _INT32.pack(-1)
        if len(selected) > core_max:
            raise InvalidBridgeResponseError(
                "selected tribute count exceeds the native maximum"
            )
        total = 0
        for candidate in selected:
            value = candidate.payload.get("release_value")
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise InvalidBridgeResponseError(
                    "tribute candidate release_value must be a positive integer"
                )
            total += value
        if total < core_min:
            raise InvalidBridgeResponseError(
                "selected tribute value is below the native minimum"
            )
        return ActionResponseEncoder._encode_card_index_payload(selected)

    @staticmethod
    def _encode_counter_vector(
        request: DecisionRequest,
        selected: tuple[Candidate, ...],
        selections: tuple[Selection, ...],
    ) -> bytes:
        required_count = request.context.extra.get("required_count")
        if not isinstance(required_count, int) or required_count <= 0:
            raise InvalidBridgeResponseError(
                "select_counter is missing required_count metadata"
            )
        selected_values: dict[str, int] = {}
        for candidate, selection in zip(selected, selections, strict=True):
            value = selection.value
            available = candidate.payload.get("available_count")
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value <= 0
                or not isinstance(available, int)
                or value > available
            ):
                raise InvalidBridgeResponseError(
                    "counter allocation must be a positive integer within availability"
                )
            selected_values[candidate.candidate_id] = value
        if sum(selected_values.values()) != required_count:
            raise InvalidBridgeResponseError(
                "counter allocation total does not match required_count"
            )
        values: list[int] = []
        for candidate in request.candidates:
            value = selected_values.get(candidate.candidate_id, 0)
            if value > 0x7FFF:
                raise InvalidBridgeResponseError(
                    "counter allocation must fit positive int16"
                )
            values.append(value)
        return struct.pack(f"<{len(values)}h", *values)

    @staticmethod
    def _sum_options(sum_param: int) -> tuple[int, ...]:
        first = sum_param & 0xFFFF
        second = sum_param >> 16
        return (first,) if second == 0 or second == first else (first, second)

    @classmethod
    def _encode_sum_indices(
        cls,
        request: DecisionRequest,
        selected: tuple[Candidate, ...],
        _selections: tuple[Selection, ...],
    ) -> bytes:
        extra = request.context.extra
        mode = extra.get("mode")
        target = extra.get("target")
        must_params = extra.get("must_sum_params")
        if (
            mode not in (0, 1)
            or not isinstance(target, int)
            or not isinstance(must_params, list)
            or any(not isinstance(value, int) for value in must_params)
        ):
            raise InvalidBridgeResponseError("select_sum metadata is invalid")
        selected_params: list[int] = []
        for candidate in selected:
            value = candidate.payload.get("sum_param")
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidBridgeResponseError(
                    "sum candidate sum_param must be an integer"
                )
            selected_params.append(value)
        all_params = [*must_params, *selected_params]
        if not all_params:
            raise InvalidBridgeResponseError("select_sum response selects no values")
        if mode == 0:
            reachable = {0}
            for value in all_params:
                reachable = {
                    subtotal + option
                    for subtotal in reachable
                    for option in cls._sum_options(value)
                }
            if target not in reachable:
                raise InvalidBridgeResponseError(
                    "selected sum cards cannot produce the required exact value"
                )
        else:
            minimums = [min(cls._sum_options(value)) for value in all_params]
            maximum = sum(max(cls._sum_options(value)) for value in all_params)
            if maximum < target or sum(minimums) - min(minimums) >= target:
                raise InvalidBridgeResponseError(
                    "selected sum cards do not form a minimal threshold set"
                )
        return cls._encode_card_index_payload(selected)

    @staticmethod
    def _encode_unselect_action(
        _request: DecisionRequest,
        selected: tuple[Candidate, ...],
        _selections: tuple[Selection, ...],
    ) -> bytes:
        if len(selected) != 1:
            raise InvalidBridgeResponseError(
                "select_unselect_card requires exactly one action"
            )
        candidate = selected[0]
        if candidate.payload.get("response_codec") != "unselect_action":
            raise InvalidBridgeResponseError(
                "candidate does not use the unselect_action response codec"
            )
        index = candidate.payload.get("response_index")
        if index == -1:
            return _INT32.pack(-1)
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise InvalidBridgeResponseError(
                "unselect response_index must be non-negative or -1"
            )
        return struct.pack("<ii", 1, index)

    @staticmethod
    def _encode_sort_order(
        request: DecisionRequest,
        selected: tuple[Candidate, ...],
        selections: tuple[Selection, ...],
    ) -> bytes:
        if len(selected) == 1 and selected[0].payload.get("response_index") == -1:
            return b"\xff"
        card_candidates = tuple(
            candidate
            for candidate in request.candidates
            if candidate.payload.get("response_index") != -1
        )
        if len(selected) != len(card_candidates):
            raise InvalidBridgeResponseError(
                "sort response must order every card or keep the current order"
            )
        orders = {
            candidate.candidate_id: selection.order
            for candidate, selection in zip(selected, selections, strict=True)
        }
        values: list[int] = []
        for candidate in card_candidates:
            order = orders.get(candidate.candidate_id)
            if not isinstance(order, int) or isinstance(order, bool):
                raise InvalidBridgeResponseError(
                    "sort response is missing a candidate order"
                )
            values.append(order)
        if sorted(values) != list(range(len(card_candidates))):
            raise InvalidBridgeResponseError(
                "sort response requires each order exactly once from zero"
            )
        return bytes(values)

    @staticmethod
    def _encode_bit_mask(
        request: DecisionRequest,
        selected: tuple[Candidate, ...],
        _selections: tuple[Selection, ...],
    ) -> bytes:
        mask = 0
        for candidate in selected:
            bit = candidate.payload.get("response_bit")
            if not isinstance(bit, int) or isinstance(bit, bool) or bit <= 0:
                raise InvalidBridgeResponseError(
                    "mask candidate response_bit must be a positive integer"
                )
            mask |= bit
        width = request.context.extra.get("response_width")
        if width == 64:
            return struct.pack("<Q", mask)
        if width == 32 and mask <= 0xFFFFFFFF:
            return struct.pack("<I", mask)
        raise InvalidBridgeResponseError("mask response width or value is invalid")

    @staticmethod
    def _encode_selection_int32(
        _request: DecisionRequest,
        selected: tuple[Candidate, ...],
        selections: tuple[Selection, ...],
    ) -> bytes:
        if len(selected) != 1 or len(selections) != 1:
            raise InvalidBridgeResponseError(
                "selection_int32 response requires exactly one selection"
            )
        if selected[0].payload.get("response_codec") != "selection_int32":
            raise InvalidBridgeResponseError(
                "candidate does not use the selection_int32 response codec"
            )
        value = selections[0].value
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not -(1 << 31) <= value < (1 << 31)
        ):
            raise InvalidBridgeResponseError(
                "selection value must fit int32"
            )
        return _INT32.pack(value)

    @staticmethod
    def _encode_place(
        _request: DecisionRequest,
        selected: tuple[Candidate, ...],
        _selections: tuple[Selection, ...],
    ) -> bytes:
        triplets: list[tuple[int, int, int]] = []
        for candidate in selected:
            payload = candidate.payload
            if payload.get("response_codec") != "place_triplets":
                raise InvalidBridgeResponseError(
                    "candidate does not use the place_triplets response codec"
                )
            values = tuple(
                payload.get(field)
                for field in (
                    "response_controller",
                    "response_location",
                    "response_sequence",
                )
            )
            if any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 0 <= value <= 0xFF
                for value in values
            ):
                raise InvalidBridgeResponseError(
                    "place response controller/location/sequence must fit uint8"
                )
            triplets.append((int(values[0]), int(values[1]), int(values[2])))
        triplets.sort()
        if len(triplets) != len(set(triplets)):
            raise InvalidBridgeResponseError("place response contains duplicate zones")
        return b"".join(bytes(values) for values in triplets)
