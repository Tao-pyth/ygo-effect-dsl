from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ygo_effect_dsl.engine.replay.errors import ReplayFormatError


SCHEMA_VERSION = "0.2"


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayFormatError(f"{path} must be object")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise ReplayFormatError(f"{path} must be string")
    return value


@dataclass(frozen=True)
class ActionRecord:
    """A single replay step. It does not interpret game rules."""

    step: int
    action_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "synthetic"
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "created_at": self.created_at,
            "payload": self.payload,
            "source": self.source,
            "step": self.step,
        }

    @classmethod
    def from_dict(cls, data: Any, path: str = "actions[*]") -> "ActionRecord":
        record = _require_mapping(data, path)
        missing = {"step", "action_type", "payload", "source"} - set(record)
        if missing:
            raise ReplayFormatError(f"{path} missing required fields: {sorted(missing)}")
        step = record["step"]
        if not isinstance(step, int) or isinstance(step, bool):
            raise ReplayFormatError(f"{path}.step must be integer")
        payload = _require_mapping(record["payload"], f"{path}.payload")
        created_at = record.get("created_at")
        if created_at is not None and not isinstance(created_at, str):
            raise ReplayFormatError(f"{path}.created_at must be string or null")
        return cls(
            step=step,
            action_type=_require_string(record["action_type"], f"{path}.action_type"),
            payload=payload,
            source=_require_string(record["source"], f"{path}.source"),
            created_at=created_at,
        )


@dataclass(frozen=True)
class ReplayHistory:
    """Replay history container for V0.2 deterministic JSON round-trips."""

    seed: int | None
    deck_identifier: str
    actions: list[ActionRecord] = field(default_factory=list)
    version_metadata: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [action.to_dict() for action in self.actions],
            "deck_identifier": self.deck_identifier,
            "notes": self.notes,
            "schema_version": self.schema_version,
            "seed": self.seed,
            "version_metadata": self.version_metadata,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ReplayHistory":
        root = _require_mapping(data, "replay")
        required = {"schema_version", "seed", "deck_identifier", "actions", "version_metadata", "notes"}
        missing = required - set(root)
        if missing:
            raise ReplayFormatError(f"replay missing required fields: {sorted(missing)}")
        seed = root["seed"]
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            raise ReplayFormatError("replay.seed must be integer or null")
        actions_data = root["actions"]
        if not isinstance(actions_data, list):
            raise ReplayFormatError("replay.actions must be array")
        actions = [ActionRecord.from_dict(action, f"actions[{idx}]") for idx, action in enumerate(actions_data)]
        version_metadata = _require_mapping(root["version_metadata"], "replay.version_metadata")
        return cls(
            schema_version=_require_string(root["schema_version"], "replay.schema_version"),
            seed=seed,
            deck_identifier=_require_string(root["deck_identifier"], "replay.deck_identifier"),
            actions=actions,
            version_metadata=version_metadata,
            notes=_require_string(root["notes"], "replay.notes"),
        )
