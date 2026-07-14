from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest


ACTION_SCHEMA_VERSION = "0.3a"


class ActionKind(str, Enum):
    ACTIVATE_EFFECT = "ACTIVATE_EFFECT"
    ATTACK = "ATTACK"
    SELECT_CARD = "SELECT_CARD"
    SELECT_OPTION = "SELECT_OPTION"
    NORMAL_SUMMON = "NORMAL_SUMMON"
    SPECIAL_SUMMON = "SPECIAL_SUMMON"
    PASS = "PASS"
    DECLINE = "DECLINE"
    STOP_LINE = "STOP_LINE"
    END_TURN = "END_TURN"
    CHANGE_POSITION = "CHANGE_POSITION"
    SET_MONSTER = "SET_MONSTER"
    SET_SPELL_TRAP = "SET_SPELL_TRAP"
    ENTER_BATTLE_PHASE = "ENTER_BATTLE_PHASE"
    ENTER_MAIN_PHASE_2 = "ENTER_MAIN_PHASE_2"
    SHUFFLE_HAND = "SHUFFLE_HAND"
    SELECT_ZONE = "SELECT_ZONE"
    SELECT_POSITION = "SELECT_POSITION"
    SELECT_TRIBUTE = "SELECT_TRIBUTE"
    DISTRIBUTE_COUNTERS = "DISTRIBUTE_COUNTERS"
    SELECT_SUM = "SELECT_SUM"
    FINISH_SELECTION = "FINISH_SELECTION"
    ORDER_CARDS = "ORDER_CARDS"
    ANNOUNCE_RACE = "ANNOUNCE_RACE"
    ANNOUNCE_ATTRIBUTE = "ANNOUNCE_ATTRIBUTE"
    ANNOUNCE_CARD = "ANNOUNCE_CARD"
    ANNOUNCE_NUMBER = "ANNOUNCE_NUMBER"
    ROCK_PAPER_SCISSORS = "ROCK_PAPER_SCISSORS"


@dataclass(frozen=True)
class CardRef:
    controller: int
    owner: int
    location: str
    sequence: int
    public_card_id: int | None = None
    instance_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "controller": self.controller,
            "instance_id": self.instance_id,
            "location": self.location,
            "owner": self.owner,
            "public_card_id": self.public_card_id,
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class EffectRef:
    card_ref: CardRef
    effect_index: int
    effect_label: str = ""
    once_per_turn_key: str | None = None

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "card_ref": self.card_ref.to_dict(),
            "effect_index": self.effect_index,
            "once_per_turn_key": self.once_per_turn_key,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.to_identity_dict())
        payload["effect_label"] = self.effect_label
        return payload


@dataclass(frozen=True)
class Selection:
    candidate_id: str
    order: int | None = None
    card_ref: CardRef | None = None
    effect_ref: EffectRef | None = None
    value: Any = None
    payload_ref: str | None = None

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "card_ref": self.card_ref.to_dict() if self.card_ref else None,
            "effect_ref": self.effect_ref.to_identity_dict() if self.effect_ref else None,
            "order": self.order,
            "payload_ref": self.payload_ref,
            "value": self.value,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.to_identity_dict())
        payload["effect_ref"] = self.effect_ref.to_dict() if self.effect_ref else None
        return payload


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    player: int
    selections: tuple[Selection, ...]
    request_signature: str
    source: CardRef | None = None
    effect_ref: EffectRef | None = None
    action_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ActionKind):
            object.__setattr__(self, "kind", ActionKind(self.kind))
        if not isinstance(self.selections, tuple):
            object.__setattr__(self, "selections", tuple(self.selections))
        if not self.action_id:
            object.__setattr__(self, "action_id", build_action_id(self))

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "effect_ref": self.effect_ref.to_identity_dict() if self.effect_ref else None,
            "kind": self.kind.value,
            "player": self.player,
            "request_signature": self.request_signature,
            "schema_version": ACTION_SCHEMA_VERSION,
            "selections": [selection.to_identity_dict() for selection in self.selections],
            "source": self.source.to_dict() if self.source else None,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.to_identity_dict())
        payload["effect_ref"] = self.effect_ref.to_dict() if self.effect_ref else None
        payload["selections"] = [selection.to_dict() for selection in self.selections]
        payload["action_id"] = self.action_id
        return payload


def build_action_id(action: Action) -> str:
    return stable_digest(action.to_identity_dict(), prefix="act_")
