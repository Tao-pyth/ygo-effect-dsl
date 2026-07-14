from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.replay import build_action_occurrence_id


INTERRUPTION_TARGET_SCHEMA_VERSION = "interruption-target-v1"
INTERRUPTION_TARGET_RESOLUTION_SCHEMA_VERSION = "interruption-target-resolution-v1"


class InterruptionTargetResolutionError(ValueError):
    pass


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _coordinate(value: Any, path: str, *, minimum: int = 0) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{path} must be an integer >= {minimum} or None")
    return value


def _card_identity(value: Any, path: str) -> dict[str, Any] | None:
    if value is None:
        return None
    card = _mapping(value, path)
    controller = _coordinate(card.get("controller"), f"{path}.controller")
    owner = _coordinate(card.get("owner"), f"{path}.owner")
    sequence = _coordinate(card.get("sequence"), f"{path}.sequence")
    if controller is None or owner is None or sequence is None:
        raise ValueError(f"{path} controller, owner, and sequence are required")
    public_card_id = card.get("public_card_id")
    if public_card_id is not None and (
        not isinstance(public_card_id, int)
        or isinstance(public_card_id, bool)
        or public_card_id < 1
    ):
        raise ValueError(f"{path}.public_card_id must be an integer >= 1 or None")
    instance_id = card.get("instance_id")
    if instance_id is not None and (not isinstance(instance_id, str) or not instance_id):
        raise ValueError(f"{path}.instance_id must be a non-empty string or None")
    if public_card_id is None and instance_id is None:
        raise ValueError(f"{path} requires public_card_id or instance_id")
    return to_canonical_data(
        {
            "controller": controller,
            "instance_id": instance_id,
            "location": _string(card.get("location"), f"{path}.location"),
            "owner": owner,
            "public_card_id": public_card_id,
            "sequence": sequence,
        }
    )


def _effect_identity(value: Any, path: str) -> dict[str, Any] | None:
    if value is None:
        return None
    effect = _mapping(value, path)
    effect_index = _coordinate(effect.get("effect_index"), f"{path}.effect_index")
    if effect_index is None:
        raise ValueError(f"{path}.effect_index is required")
    card_ref = _card_identity(effect.get("card_ref"), f"{path}.card_ref")
    if card_ref is None:
        raise ValueError(f"{path}.card_ref is required")
    once_per_turn_key = effect.get("once_per_turn_key")
    if once_per_turn_key is not None and (
        not isinstance(once_per_turn_key, str) or not once_per_turn_key
    ):
        raise ValueError(f"{path}.once_per_turn_key must be a non-empty string or None")
    return to_canonical_data(
        {
            "card_ref": card_ref,
            "effect_index": effect_index,
            "once_per_turn_key": once_per_turn_key,
        }
    )


@dataclass(frozen=True)
class InterruptionTarget:
    action_occurrence_id: str
    action_id: str
    request_signature: str
    state_hash_before: str
    step: int
    turn: int | None
    turn_action_index: int | None
    chain_index: int | None
    player: int
    source: Mapping[str, Any] | None
    effect_ref: Mapping[str, Any] | None
    schema_version: str = INTERRUPTION_TARGET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "action_occurrence_id",
            "action_id",
            "request_signature",
            "state_hash_before",
        ):
            _string(getattr(self, name), name)
        step = _coordinate(self.step, "step")
        if step is None:
            raise ValueError("step is required")
        _coordinate(self.turn, "turn", minimum=1)
        _coordinate(self.turn_action_index, "turn_action_index")
        _coordinate(self.chain_index, "chain_index")
        player = _coordinate(self.player, "player")
        if player is None:
            raise ValueError("player is required")
        object.__setattr__(self, "source", _card_identity(self.source, "source"))
        object.__setattr__(
            self, "effect_ref", _effect_identity(self.effect_ref, "effect_ref")
        )
        if self.schema_version != INTERRUPTION_TARGET_SCHEMA_VERSION:
            raise ValueError("unsupported interruption target schema")
        expected_occurrence_id = build_action_occurrence_id(
            action_id=self.action_id,
            step=self.step,
            state_hash_before=self.state_hash_before,
            turn=self.turn,
            turn_action_index=self.turn_action_index,
            chain_index=self.chain_index,
        )
        if self.action_occurrence_id != expected_occurrence_id:
            raise ValueError("action_occurrence_id does not match target coordinates")

    @classmethod
    def from_replay_event(cls, event: Mapping[str, Any]) -> "InterruptionTarget":
        event = _mapping(event, "event")
        action = _mapping(event.get("action"), "event.action")
        step = _coordinate(event.get("step"), "event.step")
        if step is None:
            raise ValueError("event.step is required")
        action_id = _string(action.get("action_id"), "event.action.action_id")
        request_signature = _string(
            event.get("request_signature"), "event.request_signature"
        )
        if action.get("request_signature") != request_signature:
            raise ValueError("event action request_signature does not match event")
        state_hash_before = _string(
            event.get("state_hash_before"), "event.state_hash_before"
        )
        turn = _coordinate(event.get("turn"), "event.turn", minimum=1)
        turn_action_index = _coordinate(
            event.get("turn_action_index"), "event.turn_action_index"
        )
        chain_index = _coordinate(event.get("chain_index"), "event.chain_index")
        occurrence_id = build_action_occurrence_id(
            action_id=action_id,
            step=step,
            state_hash_before=state_hash_before,
            turn=turn,
            turn_action_index=turn_action_index,
            chain_index=chain_index,
        )
        recorded_occurrence_id = event.get("action_occurrence_id")
        if recorded_occurrence_id is not None and recorded_occurrence_id != occurrence_id:
            raise ValueError("event action_occurrence_id does not match event coordinates")
        return cls(
            action_occurrence_id=occurrence_id,
            action_id=action_id,
            request_signature=request_signature,
            state_hash_before=state_hash_before,
            step=step,
            turn=turn,
            turn_action_index=turn_action_index,
            chain_index=chain_index,
            player=action.get("player"),
            source=action.get("source"),
            effect_ref=action.get("effect_ref"),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InterruptionTarget":
        value = _mapping(value, "target")
        target = cls(
            action_occurrence_id=value.get("action_occurrence_id"),
            action_id=value.get("action_id"),
            request_signature=value.get("request_signature"),
            state_hash_before=value.get("state_hash_before"),
            step=value.get("step"),
            turn=value.get("turn"),
            turn_action_index=value.get("turn_action_index"),
            chain_index=value.get("chain_index"),
            player=value.get("player"),
            source=value.get("source"),
            effect_ref=value.get("effect_ref"),
            schema_version=value.get("schema_version"),
        )
        if target.to_dict() != to_canonical_data(value):
            raise ValueError("interruption target does not match target_id or fields")
        return target

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "action_id": self.action_id,
                "action_occurrence_id": self.action_occurrence_id,
                "chain_index": self.chain_index,
                "effect_ref": self.effect_ref,
                "player": self.player,
                "request_signature": self.request_signature,
                "schema_version": self.schema_version,
                "source": self.source,
                "state_hash_before": self.state_hash_before,
                "step": self.step,
                "turn": self.turn,
                "turn_action_index": self.turn_action_index,
            }
        )
        return {**identity, "target_id": stable_digest(identity, prefix="inttarget_")}

    @property
    def target_id(self) -> str:
        return str(self.to_dict()["target_id"])


@dataclass(frozen=True)
class InterruptionTargetResolution:
    target: InterruptionTarget
    replay_step: int
    schema_version: str = INTERRUPTION_TARGET_RESOLUTION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "action_occurrence_id": self.target.action_occurrence_id,
                "replay_step": self.replay_step,
                "schema_version": self.schema_version,
                "target_id": self.target.target_id,
            }
        )
        return {
            **identity,
            "resolution_id": stable_digest(identity, prefix="intresolve_"),
        }


def resolve_interruption_target(
    replay_or_events: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    target: InterruptionTarget | Mapping[str, Any],
) -> InterruptionTargetResolution:
    if not isinstance(target, InterruptionTarget):
        target = InterruptionTarget.from_dict(target)
    if isinstance(replay_or_events, Mapping):
        events = replay_or_events.get("events")
    else:
        events = replay_or_events
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        raise ValueError("replay events must be a sequence")
    matches: list[InterruptionTarget] = []
    invalid_events: list[int] = []
    for index, raw_event in enumerate(events):
        try:
            candidate = InterruptionTarget.from_replay_event(raw_event)
        except (TypeError, ValueError):
            invalid_events.append(index)
            continue
        if candidate.target_id == target.target_id:
            matches.append(candidate)
    if invalid_events:
        raise InterruptionTargetResolutionError(
            f"cannot resolve against invalid Replay events: {invalid_events}"
        )
    if not matches:
        raise InterruptionTargetResolutionError(
            f"interruption target {target.target_id} was not found in Replay"
        )
    if len(matches) > 1:
        raise InterruptionTargetResolutionError(
            f"interruption target {target.target_id} is ambiguous in Replay"
        )
    match = matches[0]
    return InterruptionTargetResolution(target=match, replay_step=match.step)
