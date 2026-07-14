from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ygo_effect_dsl.engine.bridge.errors import InvalidBridgeResponseError
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


REQUEST_SCHEMA_VERSION = "0.3a"


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    kind: str
    label: str = ""
    card_ref: dict[str, Any] | None = None
    effect_ref: dict[str, Any] | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "card_ref": self.card_ref,
            "effect_ref": self.effect_ref,
            "kind": self.kind,
            "payload": self.payload,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.to_identity_dict())
        payload["label"] = self.label
        return payload


@dataclass(frozen=True)
class DecisionConstraints:
    min_selections: int = 1
    max_selections: int = 1
    ordered: bool = False
    allow_duplicates: bool = False
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_duplicates": self.allow_duplicates,
            "max_selections": self.max_selections,
            "min_selections": self.min_selections,
            "ordered": self.ordered,
            "required": self.required,
        }


@dataclass(frozen=True)
class DecisionContext:
    phase: str = ""
    chain: tuple[dict[str, Any], ...] = ()
    turn_player: int | None = None
    priority_player: int | None = None
    visible_board: dict[str, Any] = field(default_factory=dict)
    request_source: str = ""
    version_metadata: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": list(self.chain),
            "extra": self.extra,
            "phase": self.phase,
            "priority_player": self.priority_player,
            "request_source": self.request_source,
            "turn_player": self.turn_player,
            "version_metadata": self.version_metadata,
            "visible_board": self.visible_board,
        }


@dataclass(frozen=True)
class DecisionRequest:
    request_id: str
    request_type: str
    player: int
    candidates: tuple[Candidate, ...]
    constraints: DecisionConstraints
    context: DecisionContext

    def to_signature_dict(self) -> dict[str, Any]:
        return {
            "candidates": [candidate.to_identity_dict() for candidate in self.candidates],
            "constraints": self.constraints.to_dict(),
            "context": self.context.to_dict(),
            "player": self.player,
            "request_schema_version": REQUEST_SCHEMA_VERSION,
            "request_type": self.request_type,
        }

    @property
    def request_signature(self) -> str:
        return stable_digest(self.to_signature_dict(), prefix="req_")

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.to_signature_dict())
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        payload["request_id"] = self.request_id
        payload["request_signature"] = self.request_signature
        return payload


@dataclass(frozen=True)
class DecisionResponse:
    request_id: str
    request_signature: str
    selected_candidate_ids: tuple[str, ...]
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload": self.payload,
            "request_id": self.request_id,
            "request_signature": self.request_signature,
            "selected_candidate_ids": list(self.selected_candidate_ids),
        }


def validate_decision_response(request: DecisionRequest, response: DecisionResponse) -> None:
    context = {"request": request.to_dict(), "response": response.to_dict()}

    def invalid(message: str) -> InvalidBridgeResponseError:
        return InvalidBridgeResponseError(message, context=context)

    if response.request_id != request.request_id:
        raise invalid("response.request_id does not match request.request_id")
    if response.request_signature != request.request_signature:
        raise invalid(
            "response.request_signature does not match request.request_signature"
        )

    candidate_ids = {candidate.candidate_id for candidate in request.candidates}
    selected = list(response.selected_candidate_ids)
    unknown = sorted(candidate_id for candidate_id in selected if candidate_id not in candidate_ids)
    if unknown:
        raise invalid(f"response selected unknown candidates: {unknown}")

    constraints = request.constraints
    if len(selected) < constraints.min_selections:
        raise invalid(
            "response selected fewer candidates than constraints.min_selections"
        )
    if len(selected) > constraints.max_selections:
        raise invalid(
            "response selected more candidates than constraints.max_selections"
        )
    if not constraints.allow_duplicates and len(selected) != len(set(selected)):
        raise invalid("response selected duplicate candidates")

    # Keep payload opaque, but force it through canonical conversion so invalid
    # non-JSON-like values fail close to the bridge boundary.
    try:
        to_canonical_data(response.payload)
    except (TypeError, ValueError) as exc:
        raise invalid(str(exc)) from exc
