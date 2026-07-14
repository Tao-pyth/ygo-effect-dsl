from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


STATE_ID_SCHEMA_VERSION = "ygo-state-id-v1"


class InformationMode(str, Enum):
    COMPLETE_INFORMATION = "complete_information"
    PLAYER_VIEW = "player_view"
    SAMPLED_PRIVATE_STATE = "sampled_private_state"


class StateIdentityCompleteness(str, Enum):
    EXACT = "exact"
    QUERY_API_PROJECTION = "query_api_projection"


@dataclass(frozen=True)
class CanonicalState:
    public_state: Mapping[str, Any]
    private_state: Mapping[str, Any]
    constraints: Mapping[str, Any]
    history: Mapping[str, Any]
    pending_request: Mapping[str, Any] | None
    engine_state: Mapping[str, Any]
    information_mode: InformationMode
    completeness: StateIdentityCompleteness
    viewer: int | None = None
    sampling_reference: Mapping[str, Any] | None = None
    missing_fields: tuple[str, ...] = ()
    schema_version: str = STATE_ID_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.information_mode, InformationMode):
            object.__setattr__(
                self, "information_mode", InformationMode(self.information_mode)
            )
        if not isinstance(self.completeness, StateIdentityCompleteness):
            object.__setattr__(
                self,
                "completeness",
                StateIdentityCompleteness(self.completeness),
            )
        if self.schema_version != STATE_ID_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported State ID schema version {self.schema_version!r}"
            )
        mappings = {
            "public_state": self.public_state,
            "private_state": self.private_state,
            "constraints": self.constraints,
            "history": self.history,
            "engine_state": self.engine_state,
        }
        for name, value in mappings.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"{name} must be a mapping")
        if self.pending_request is not None and not isinstance(
            self.pending_request, Mapping
        ):
            raise ValueError("pending_request must be a mapping or None")
        if self.sampling_reference is not None and not isinstance(
            self.sampling_reference, Mapping
        ):
            raise ValueError("sampling_reference must be a mapping or None")
        if self.information_mode == InformationMode.PLAYER_VIEW:
            if self.viewer not in (0, 1):
                raise ValueError("player_view requires viewer 0 or 1")
        elif self.viewer is not None:
            raise ValueError("viewer is only valid for player_view")
        if (
            self.information_mode == InformationMode.SAMPLED_PRIVATE_STATE
            and self.sampling_reference is None
        ):
            raise ValueError("sampled_private_state requires sampling_reference")
        if self.completeness == StateIdentityCompleteness.EXACT and self.missing_fields:
            raise ValueError("exact State identity cannot declare missing_fields")
        normalized_missing = tuple(sorted(set(self.missing_fields)))
        if normalized_missing != self.missing_fields:
            object.__setattr__(self, "missing_fields", normalized_missing)

    def to_identity_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "completeness": self.completeness.value,
                "constraints": self.constraints,
                "engine_state": self.engine_state,
                "history": self.history,
                "information_mode": self.information_mode.value,
                "missing_fields": list(self.missing_fields),
                "pending_request": self.pending_request,
                "private_state": self.private_state,
                "public_state": self.public_state,
                "sampling_reference": self.sampling_reference,
                "schema_version": self.schema_version,
                "viewer": self.viewer,
            }
        )

    @property
    def state_id(self) -> str:
        return stable_digest(self.to_identity_dict(), prefix="state_")

    def to_dict(self) -> dict[str, Any]:
        return {**self.to_identity_dict(), "state_id": self.state_id}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CanonicalState":
        required = {
            "completeness",
            "constraints",
            "engine_state",
            "history",
            "information_mode",
            "missing_fields",
            "pending_request",
            "private_state",
            "public_state",
            "sampling_reference",
            "schema_version",
            "viewer",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValueError(f"State identity is missing fields: {missing}")
        raw_missing = data["missing_fields"]
        if not isinstance(raw_missing, list) or not all(
            isinstance(item, str) and item for item in raw_missing
        ):
            raise ValueError("missing_fields must be a list of non-empty strings")
        state = cls(
            public_state=data["public_state"],
            private_state=data["private_state"],
            constraints=data["constraints"],
            history=data["history"],
            pending_request=data["pending_request"],
            engine_state=data["engine_state"],
            information_mode=InformationMode(str(data["information_mode"])),
            completeness=StateIdentityCompleteness(str(data["completeness"])),
            viewer=data["viewer"],
            sampling_reference=data["sampling_reference"],
            missing_fields=tuple(raw_missing),
            schema_version=str(data["schema_version"]),
        )
        supplied_id = data.get("state_id")
        if supplied_id is not None and supplied_id != state.state_id:
            raise ValueError("state_id does not match canonical State identity")
        return state
