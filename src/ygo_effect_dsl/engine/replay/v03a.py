from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ygo_effect_dsl.engine.action import Action
from ygo_effect_dsl.engine.bridge import DecisionRequest
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.replay.errors import ReplaySignatureMismatchError
from ygo_effect_dsl.engine.replay.errors import ReplayFormatError
from ygo_effect_dsl.engine.replay.manifest import ReplayManifestV03a
from ygo_effect_dsl.engine.replay.verifier import (
    first_canonical_difference,
    first_request_difference,
)


REPLAY_V03A_SCHEMA_VERSION = "0.3a"
ACTION_OCCURRENCE_SCHEMA_VERSION = "1"


def build_action_occurrence_id(
    *,
    action_id: str,
    step: int,
    state_hash_before: str,
    turn: int | None = None,
    turn_action_index: int | None = None,
    chain_index: int | None = None,
) -> str:
    """Identify one execution of a semantic Action within a replay."""
    if not isinstance(action_id, str) or not action_id:
        raise ValueError("action_id must be a non-empty string")
    if not isinstance(state_hash_before, str) or not state_hash_before:
        raise ValueError("state_hash_before must be a non-empty string")
    coordinates = {
        "step": step,
        "turn": turn,
        "turn_action_index": turn_action_index,
        "chain_index": chain_index,
    }
    for name, value in coordinates.items():
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer or None")
    if turn == 0:
        raise ValueError("turn must be at least 1 when present")
    return stable_digest(
        {
            "action_id": action_id,
            "chain_index": chain_index,
            "schema_version": ACTION_OCCURRENCE_SCHEMA_VERSION,
            "state_hash_before": state_hash_before,
            "step": step,
            "turn": turn,
            "turn_action_index": turn_action_index,
        },
        prefix="aocc_",
    )


@dataclass(frozen=True)
class ReplayEventV03a:
    step: int
    request_signature: str
    action: Action
    node_id: str = ""
    request: dict[str, Any] = field(default_factory=dict)
    core_input_ref: str = ""
    core_response: dict[str, Any] = field(default_factory=dict)
    core_output: dict[str, Any] = field(default_factory=dict)
    state_hash_before: str = ""
    state_hash_after: str = ""
    turn: int | None = None
    turn_action_index: int | None = None
    chain_index: int | None = None
    timestamp: str | None = None
    failure: dict[str, Any] | None = None

    @property
    def action_occurrence_id(self) -> str:
        return build_action_occurrence_id(
            action_id=self.action.action_id,
            step=self.step,
            state_hash_before=self.state_hash_before,
            turn=self.turn,
            turn_action_index=self.turn_action_index,
            chain_index=self.chain_index,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "action_id": self.action.action_id,
            "action_occurrence_id": self.action_occurrence_id,
            "chain_index": self.chain_index,
            "core_input_ref": self.core_input_ref,
            "core_output": self.core_output,
            "core_response": self.core_response,
            "failure": self.failure,
            "node_id": self.node_id,
            "request": self.request,
            "request_signature": self.request_signature,
            "state_hash_after": self.state_hash_after,
            "state_hash_before": self.state_hash_before,
            "step": self.step,
            "timestamp": self.timestamp,
            "turn": self.turn,
            "turn_action_index": self.turn_action_index,
        }


@dataclass(frozen=True)
class ReplayHistoryV03a:
    initial_snapshot: dict[str, Any]
    version_metadata: dict[str, Any]
    events: tuple[ReplayEventV03a, ...]
    seeds: dict[str, int | None] = field(default_factory=dict)
    schema_version: str = REPLAY_V03A_SCHEMA_VERSION
    strict_versions: bool = True
    manifest: ReplayManifestV03a | None = None
    initial_core_output: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.manifest is None:
            return
        if self.strict_versions:
            self.manifest.assert_reproducible()
        expected_hash = self.manifest.initial_conditions.get("snapshot_hash")
        actual_hash = self.initial_snapshot.get("state_hash")
        if expected_hash != actual_hash:
            raise ReplayFormatError(
                "replay manifest initial snapshot hash does not match initial_snapshot"
            )

    def to_dict(self) -> dict[str, Any]:
        event_payloads = [event.to_dict() for event in self.events]
        random_events = [
            {"after_response_step": None, **event}
            for event in self.initial_core_output.get("random_events", [])
        ]
        for event in event_payloads:
            random_events.extend(
                {"after_response_step": event["step"], **random_event}
                for random_event in event.get("core_output", {}).get(
                    "random_events", []
                )
            )
        payload = {
            "events": event_payloads,
            "initial_snapshot": self.initial_snapshot,
            "initial_core_output": self.initial_core_output,
            "random_events": random_events,
            "schema_version": self.schema_version,
            "seeds": self.seeds,
            "strict_versions": self.strict_versions,
            "version_metadata": self.version_metadata,
        }
        if self.manifest is not None:
            payload["manifest"] = self.manifest.to_dict()
        return payload

    def assert_request_matches(self, step: int, request: DecisionRequest) -> None:
        event = self.events[step]
        actual_signature = request.request_signature
        if event.request_signature != actual_signature:
            difference = (
                first_request_difference(event.request, request.to_dict())
                if event.request
                else None
            )
            path = difference.path if difference is not None else "request_signature"
            recorded = (
                difference.recorded if difference is not None else event.request_signature
            )
            current = difference.current if difference is not None else actual_signature
            raise ReplaySignatureMismatchError(
                f"replay event request_signature mismatch at step {step}; "
                f"first difference at {path}: "
                f"recorded={recorded!r}, current={current!r}",
                step=step,
                path=path,
                recorded=recorded,
                current=current,
            )
        if event.action.request_signature != actual_signature:
            raise ReplaySignatureMismatchError(
                f"replay action request_signature mismatch at step {step}",
                step=step,
                path="action.request_signature",
                recorded=event.action.request_signature,
                current=actual_signature,
            )

    def assert_all_requests_match(self, requests: tuple[DecisionRequest, ...]) -> None:
        if len(requests) != len(self.events):
            raise ReplaySignatureMismatchError(
                "replay request count does not match event count",
                path="events.length",
                recorded=len(self.events),
                current=len(requests),
            )
        for step, request in enumerate(requests):
            self.assert_request_matches(step, request)

    def assert_failure_matches(
        self, step: int, failure: dict[str, Any] | None
    ) -> None:
        recorded = to_canonical_data(self.events[step].failure)
        current = to_canonical_data(failure)
        difference = first_canonical_difference(recorded, current)
        if difference is None:
            return
        path = f"failure.{difference.path}" if difference.path else "failure"
        raise ReplaySignatureMismatchError(
            f"replay failure mismatch at step {step}; first difference at {path}: "
            f"recorded={difference.recorded!r}, current={difference.current!r}",
            step=step,
            path=path,
            recorded=difference.recorded,
            current=difference.current,
        )
