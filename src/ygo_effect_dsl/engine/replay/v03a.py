from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ygo_effect_dsl.engine.action import Action
from ygo_effect_dsl.engine.bridge import DecisionRequest
from ygo_effect_dsl.engine.replay.errors import ReplaySignatureMismatchError


REPLAY_V03A_SCHEMA_VERSION = "0.3a"


@dataclass(frozen=True)
class ReplayEventV03a:
    step: int
    request_signature: str
    action: Action
    node_id: str = ""
    request: dict[str, Any] = field(default_factory=dict)
    core_input_ref: str = ""
    state_hash_before: str = ""
    state_hash_after: str = ""
    timestamp: str | None = None
    failure: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "action_id": self.action.action_id,
            "core_input_ref": self.core_input_ref,
            "failure": self.failure,
            "node_id": self.node_id,
            "request": self.request,
            "request_signature": self.request_signature,
            "state_hash_after": self.state_hash_after,
            "state_hash_before": self.state_hash_before,
            "step": self.step,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class ReplayHistoryV03a:
    initial_snapshot: dict[str, Any]
    version_metadata: dict[str, Any]
    events: tuple[ReplayEventV03a, ...]
    seeds: dict[str, int | None] = field(default_factory=dict)
    schema_version: str = REPLAY_V03A_SCHEMA_VERSION
    strict_versions: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [event.to_dict() for event in self.events],
            "initial_snapshot": self.initial_snapshot,
            "schema_version": self.schema_version,
            "seeds": self.seeds,
            "strict_versions": self.strict_versions,
            "version_metadata": self.version_metadata,
        }

    def assert_request_matches(self, step: int, request: DecisionRequest) -> None:
        event = self.events[step]
        actual_signature = request.request_signature
        if event.request_signature != actual_signature:
            raise ReplaySignatureMismatchError(
                f"replay event request_signature mismatch at step {step}"
            )
        if event.action.request_signature != actual_signature:
            raise ReplaySignatureMismatchError(
                f"replay action request_signature mismatch at step {step}"
            )

    def assert_all_requests_match(self, requests: tuple[DecisionRequest, ...]) -> None:
        if len(requests) != len(self.events):
            raise ReplaySignatureMismatchError("replay request count does not match event count")
        for step, request in enumerate(requests):
            self.assert_request_matches(step, request)
