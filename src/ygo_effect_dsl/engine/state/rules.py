from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ygo_effect_dsl.engine.canonical import to_canonical_data
from ygo_effect_dsl.engine.state.identity import InformationMode


RULE_STATE_SCHEMA_VERSION = "ygo-rule-state-v1"
VISIBILITY_STATE_SCHEMA_VERSION = "ygo-visibility-state-v1"


class ExpirationBoundary(str, Enum):
    END_OF_CHAIN = "end_of_chain"
    END_OF_PHASE = "end_of_phase"
    END_OF_TURN = "end_of_turn"
    START_OF_TURN = "start_of_turn"
    DUEL_END = "duel_end"
    ABSOLUTE_COORDINATE = "absolute_coordinate"


@dataclass(frozen=True)
class StateCoordinate:
    turn: int
    phase: str
    chain_index: int = 0
    turn_action_index: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.turn, int) or isinstance(self.turn, bool) or self.turn < 1:
            raise ValueError("turn must be an integer >= 1")
        if not isinstance(self.phase, str) or not self.phase:
            raise ValueError("phase must be a non-empty string")
        for name in ("chain_index", "turn_action_index"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_index": self.chain_index,
            "phase": self.phase,
            "turn": self.turn,
            "turn_action_index": self.turn_action_index,
        }


@dataclass(frozen=True)
class ConstraintExpiration:
    boundary: ExpirationBoundary
    turn: int | None = None
    phase: str | None = None
    chain_index: int | None = None
    turn_action_index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.boundary, ExpirationBoundary):
            object.__setattr__(self, "boundary", ExpirationBoundary(self.boundary))
        if self.turn is not None and (
            not isinstance(self.turn, int)
            or isinstance(self.turn, bool)
            or self.turn < 1
        ):
            raise ValueError("expiration turn must be an integer >= 1 or None")
        for name in ("chain_index", "turn_action_index"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"expiration {name} must be non-negative or None")
        if self.phase is not None and (not isinstance(self.phase, str) or not self.phase):
            raise ValueError("expiration phase must be non-empty or None")
        if self.boundary == ExpirationBoundary.ABSOLUTE_COORDINATE and (
            self.turn is None or self.phase is None
        ):
            raise ValueError("absolute expiration requires turn and phase")
        if self.boundary == ExpirationBoundary.END_OF_PHASE and self.phase is None:
            raise ValueError("end_of_phase expiration requires phase")
        if self.boundary in {
            ExpirationBoundary.END_OF_TURN,
            ExpirationBoundary.START_OF_TURN,
        } and self.turn is None:
            raise ValueError(f"{self.boundary.value} expiration requires turn")

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary": self.boundary.value,
            "chain_index": self.chain_index,
            "phase": self.phase,
            "turn": self.turn,
            "turn_action_index": self.turn_action_index,
        }


@dataclass(frozen=True)
class TimedConstraint:
    constraint_id: str
    kind: str
    player: int
    payload: Mapping[str, Any]
    starts_at: StateCoordinate
    expires_at: ConstraintExpiration
    source_ref: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.constraint_id, str) or not self.constraint_id:
            raise ValueError("constraint_id must be a non-empty string")
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("constraint kind must be a non-empty string")
        if self.player not in (0, 1):
            raise ValueError("constraint player must be 0 or 1")
        if not isinstance(self.payload, Mapping):
            raise ValueError("constraint payload must be a mapping")
        if self.source_ref is not None and not isinstance(self.source_ref, Mapping):
            raise ValueError("constraint source_ref must be a mapping or None")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "constraint_id": self.constraint_id,
                "expires_at": self.expires_at.to_dict(),
                "kind": self.kind,
                "payload": self.payload,
                "player": self.player,
                "source_ref": self.source_ref,
                "starts_at": self.starts_at.to_dict(),
            }
        )


@dataclass(frozen=True)
class EffectUsage:
    usage_key: str
    player: int
    uses: int
    limit: int
    reset_at: ConstraintExpiration
    source_ref: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.usage_key, str) or not self.usage_key:
            raise ValueError("usage_key must be a non-empty string")
        if self.player not in (0, 1):
            raise ValueError("effect usage player must be 0 or 1")
        for name in ("uses", "limit"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.limit < 1 or self.uses > self.limit:
            raise ValueError("effect usage requires 0 <= uses <= limit and limit >= 1")
        if self.source_ref is not None and not isinstance(self.source_ref, Mapping):
            raise ValueError("effect usage source_ref must be a mapping or None")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "limit": self.limit,
                "player": self.player,
                "reset_at": self.reset_at.to_dict(),
                "source_ref": self.source_ref,
                "usage_key": self.usage_key,
                "uses": self.uses,
            }
        )


@dataclass(frozen=True)
class PlayerSummonState:
    player: int
    normal_summons_remaining: int
    special_summon_allowed: bool
    extra_normal_summons: int = 0

    def __post_init__(self) -> None:
        if self.player not in (0, 1):
            raise ValueError("summon state player must be 0 or 1")
        for name in ("normal_summons_remaining", "extra_normal_summons"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.special_summon_allowed, bool):
            raise ValueError("special_summon_allowed must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "extra_normal_summons": self.extra_normal_summons,
            "normal_summons_remaining": self.normal_summons_remaining,
            "player": self.player,
            "special_summon_allowed": self.special_summon_allowed,
        }


@dataclass(frozen=True)
class RuleState:
    summon_states: tuple[PlayerSummonState, ...]
    effect_usages: tuple[EffectUsage, ...] = ()
    constraints: tuple[TimedConstraint, ...] = ()
    schema_version: str = RULE_STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RULE_STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported rule state schema {self.schema_version!r}")
        summon_states = tuple(sorted(self.summon_states, key=lambda item: item.player))
        if len({item.player for item in summon_states}) != len(summon_states):
            raise ValueError("summon state player must be unique")
        effect_usages = tuple(
            sorted(self.effect_usages, key=lambda item: (item.player, item.usage_key))
        )
        if len({(item.player, item.usage_key) for item in effect_usages}) != len(
            effect_usages
        ):
            raise ValueError("effect usage key must be unique per player")
        constraints = tuple(sorted(self.constraints, key=lambda item: item.constraint_id))
        if len({item.constraint_id for item in constraints}) != len(constraints):
            raise ValueError("constraint_id must be unique")
        object.__setattr__(self, "summon_states", summon_states)
        object.__setattr__(self, "effect_usages", effect_usages)
        object.__setattr__(self, "constraints", constraints)

    def to_constraints_dict(self) -> dict[str, Any]:
        return {
            "active_constraints": [item.to_dict() for item in self.constraints],
            "schema_version": self.schema_version,
            "summon_states": [item.to_dict() for item in self.summon_states],
        }

    def to_history_dict(self) -> dict[str, Any]:
        return {
            "effect_usages": [item.to_dict() for item in self.effect_usages],
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class VisibilityState:
    information_mode: InformationMode
    known_private_by_player: Mapping[str, Mapping[str, Any]]
    unknown_private_by_player: Mapping[str, Mapping[str, Any]]
    viewer: int | None = None
    sampling_reference: Mapping[str, Any] | None = None
    schema_version: str = VISIBILITY_STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.information_mode, InformationMode):
            object.__setattr__(
                self, "information_mode", InformationMode(self.information_mode)
            )
        if self.schema_version != VISIBILITY_STATE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported visibility state schema {self.schema_version!r}"
            )
        for name in ("known_private_by_player", "unknown_private_by_player"):
            value = getattr(self, name)
            if not isinstance(value, Mapping) or any(
                player not in {"0", "1"} or not isinstance(data, Mapping)
                for player, data in value.items()
            ):
                raise ValueError(f"{name} must map player keys '0'/'1' to mappings")
        known_players = set(self.known_private_by_player)
        if self.information_mode == InformationMode.COMPLETE_INFORMATION:
            if self.viewer is not None or self.sampling_reference is not None:
                raise ValueError("complete_information has no viewer or sample")
            if self.unknown_private_by_player:
                raise ValueError("complete_information cannot contain unknown private state")
        elif self.information_mode == InformationMode.PLAYER_VIEW:
            if self.viewer not in (0, 1):
                raise ValueError("player_view requires viewer 0 or 1")
            if known_players - {str(self.viewer)}:
                raise ValueError("player_view cannot expose another player's private state")
            if self.sampling_reference is not None:
                raise ValueError("player_view cannot contain a sampling_reference")
        elif self.information_mode == InformationMode.SAMPLED_PRIVATE_STATE:
            if self.viewer is not None:
                raise ValueError("sampled_private_state has no viewer")
            if self.sampling_reference is None:
                raise ValueError("sampled_private_state requires sampling_reference")

    def to_private_state_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "known_private_by_player": self.known_private_by_player,
                "schema_version": self.schema_version,
                "unknown_private_by_player": self.unknown_private_by_player,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_private_state_dict(),
            "information_mode": self.information_mode.value,
            "sampling_reference": to_canonical_data(self.sampling_reference),
            "viewer": self.viewer,
        }
