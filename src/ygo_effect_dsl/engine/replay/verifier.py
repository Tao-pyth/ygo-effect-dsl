from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ygo_effect_dsl.engine.bridge.decision import REQUEST_SCHEMA_VERSION
from ygo_effect_dsl.engine.replay.errors import ReplaySignatureMismatchError


@dataclass(frozen=True)
class RequestDifference:
    path: str
    recorded: Any
    current: Any


def first_canonical_difference(
    recorded: Any, current: Any, path: str = ""
) -> RequestDifference | None:
    if isinstance(recorded, Mapping) and isinstance(current, Mapping):
        for key in sorted(set(recorded) | set(current)):
            next_path = f"{path}.{key}" if path else str(key)
            if key not in recorded:
                return RequestDifference(next_path, "<missing>", current[key])
            if key not in current:
                return RequestDifference(next_path, recorded[key], "<missing>")
            difference = first_canonical_difference(
                recorded[key], current[key], next_path
            )
            if difference is not None:
                return difference
        return None
    if isinstance(recorded, (list, tuple)) and isinstance(current, (list, tuple)):
        if len(recorded) != len(current):
            return RequestDifference(f"{path}.length", len(recorded), len(current))
        for index, (recorded_item, current_item) in enumerate(
            zip(recorded, current, strict=True)
        ):
            difference = first_canonical_difference(
                recorded_item, current_item, f"{path}[{index}]"
            )
            if difference is not None:
                return difference
        return None
    if recorded != current:
        return RequestDifference(path, recorded, current)
    return None


def request_signature_identity(request: Mapping[str, Any]) -> dict[str, Any]:
    raw_candidates = request.get("candidates", [])
    candidates = []
    if isinstance(raw_candidates, list):
        for candidate in raw_candidates:
            if not isinstance(candidate, Mapping):
                candidates.append(candidate)
                continue
            candidates.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "card_ref": candidate.get("card_ref"),
                    "effect_ref": candidate.get("effect_ref"),
                    "kind": candidate.get("kind"),
                    "payload": candidate.get("payload", {}),
                }
            )
    return {
        "candidates": candidates,
        "constraints": request.get("constraints"),
        "context": request.get("context"),
        "player": request.get("player"),
        "request_schema_version": request.get(
            "request_schema_version", REQUEST_SCHEMA_VERSION
        ),
        "request_type": request.get("request_type"),
    }


def first_request_difference(
    recorded: Mapping[str, Any], current: Mapping[str, Any]
) -> RequestDifference | None:
    return first_canonical_difference(
        request_signature_identity(recorded),
        request_signature_identity(current),
    )


def _raise_request_mismatch(
    *,
    step: int,
    recorded_signature: Any,
    current_signature: Any,
    recorded_request: Mapping[str, Any] | None,
    current_request: Mapping[str, Any] | None,
) -> None:
    difference = None
    if recorded_request is not None and current_request is not None:
        difference = first_request_difference(recorded_request, current_request)
    path = difference.path if difference is not None else "request_signature"
    recorded = difference.recorded if difference is not None else recorded_signature
    current = difference.current if difference is not None else current_signature
    raise ReplaySignatureMismatchError(
        f"replay request_signature mismatch at step {step}; "
        f"first difference at {path}: recorded={recorded!r}, current={current!r}",
        step=step,
        path=path,
        recorded=recorded,
        current=current,
    )


def assert_replay_request_signatures(
    recorded_replay: Mapping[str, Any], current_replay: Mapping[str, Any]
) -> None:
    recorded_events = recorded_replay.get("events")
    current_events = current_replay.get("events")
    if not isinstance(recorded_events, list) or not isinstance(current_events, list):
        raise ReplaySignatureMismatchError(
            "replay events must be lists before request verification",
            path="events",
            recorded=type(recorded_events).__name__,
            current=type(current_events).__name__,
        )
    if len(recorded_events) != len(current_events):
        raise ReplaySignatureMismatchError(
            "replay request count mismatch: "
            f"recorded={len(recorded_events)}, current={len(current_events)}",
            path="events.length",
            recorded=len(recorded_events),
            current=len(current_events),
        )
    for step, (recorded_event, current_event) in enumerate(
        zip(recorded_events, current_events, strict=True)
    ):
        recorded_signature = recorded_event.get("request_signature")
        current_signature = current_event.get("request_signature")
        if recorded_signature == current_signature:
            continue
        recorded_request = recorded_event.get("request")
        current_request = current_event.get("request")
        _raise_request_mismatch(
            step=step,
            recorded_signature=recorded_signature,
            current_signature=current_signature,
            recorded_request=(
                recorded_request if isinstance(recorded_request, Mapping) else None
            ),
            current_request=(
                current_request if isinstance(current_request, Mapping) else None
            ),
        )
