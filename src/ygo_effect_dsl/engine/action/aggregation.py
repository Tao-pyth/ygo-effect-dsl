from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
import struct
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


ACTION_AGGREGATION_SCHEMA_VERSION = "2"
OCGCORE_ACTION_AGGREGATION_EVIDENCE_SCHEMA_VERSION = (
    "ocgcore-action-aggregation-evidence-v2"
)
OCGCORE_ACTION_AGGREGATION_METHOD = "ocgcore-lifecycle-v2"
OCGCORE_ACTION_AGGREGATION_SUPPORTED_APIS = ("11.0",)

_MSG_HINT = 2
_MSG_MOVE = 50
_MSG_CHAINING = 70
_MSG_CHAINED = 71
_MSG_CHAIN_SOLVING = 72
_MSG_CHAIN_SOLVED = 73
_MSG_CHAIN_END = 74
_MSG_CHAIN_NEGATED = 75
_MSG_CHAIN_DISABLED = 76
_HINT_SELECTMSG = 3
_HINTMSG_TARGET = 551
_REASON_COST = 0x80
_MOVE_PAYLOAD = struct.Struct("<IBBIIBBIII")
_CHAIN_MESSAGE_NAMES = {
    _MSG_HINT: "MSG_HINT",
    _MSG_MOVE: "MSG_MOVE",
    _MSG_CHAINING: "MSG_CHAINING",
    _MSG_CHAINED: "MSG_CHAINED",
    _MSG_CHAIN_SOLVING: "MSG_CHAIN_SOLVING",
    _MSG_CHAIN_SOLVED: "MSG_CHAIN_SOLVED",
    _MSG_CHAIN_END: "MSG_CHAIN_END",
    _MSG_CHAIN_NEGATED: "MSG_CHAIN_NEGATED",
    _MSG_CHAIN_DISABLED: "MSG_CHAIN_DISABLED",
}
_API_11_PAYLOAD_SIZES = {
    _MSG_HINT: 10,
    _MSG_MOVE: _MOVE_PAYLOAD.size,
    _MSG_CHAINING: 32,
    _MSG_CHAINED: 1,
    _MSG_CHAIN_SOLVING: 1,
    _MSG_CHAIN_SOLVED: 1,
    _MSG_CHAIN_END: 0,
    _MSG_CHAIN_NEGATED: 1,
    _MSG_CHAIN_DISABLED: 1,
}


def action_aggregation_compatibility_report() -> dict[str, Any]:
    return to_canonical_data(
        {
            "apis": {
                "11.0": {
                    "fixture_status": {
                        "activation_setup": "real_core",
                        "cancel": "raw_replay_contract_core_unreachable",
                        "chain_disabled": "real_core",
                        "chain_negated": "real_core",
                        "multi_chain": "real_core",
                        "multi_selection": "real_core",
                        "resolution_selection": "real_core",
                        "target_loss_fizzle": "real_core",
                    },
                    "payload_sizes": {
                        _CHAIN_MESSAGE_NAMES.get(message_type, str(message_type)): size
                        for message_type, size in _API_11_PAYLOAD_SIZES.items()
                    },
                    "status": "supported",
                }
            },
            "evidence_schema_version": (
                OCGCORE_ACTION_AGGREGATION_EVIDENCE_SCHEMA_VERSION
            ),
            "fail_close": {
                "malformed_known_frame": True,
                "unknown_api_version": True,
                "unfinished_activation_group": True,
                "unfinished_resolution_group": True,
            },
            "method": OCGCORE_ACTION_AGGREGATION_METHOD,
            "limitations": {
                "activation_cancel": {
                    "audit_date": "2026-07-14",
                    "audit_evidence_id": (
                        "rollbackaudit_"
                        "2476441a3c8ed5acb8c7107acf7a2e39"
                        "61f1be81bc9ad01a9cb634db44131c98"
                    ),
                    "audit_evidence_path": (
                        "docs/ocgcore/evidence/activation_rollback_audit.json"
                    ),
                    "follow_up_issue": 117,
                    "latest_upstream_release": "v11.0",
                    "native_cancel_response_hex": "ffffffff",
                    "next_review_trigger": "upstream_tag_or_api_change",
                    "observed_followup": "MSG_CHAINED",
                    "reason": "cost_and_target_return_values_do_not_abort_add_chain",
                    "status": "unreachable_in_ocgcore_api_11_0",
                    "tracking_issue": 115,
                    "upstream_head": (
                        "0764db0c75b3d1d574880d365aa3695ab1f13b43"
                    ),
                    "upstream_head_api": "11.0",
                    "upstream_head_runtime_tested": False,
                    "upstream_source_flow_matches_v11_0": True,
                }
            },
            "schema_version": "ocgcore-action-aggregation-compatibility-v2",
        }
    )


class ActionRole(str, Enum):
    PRIMARY = "primary"
    COST = "cost"
    TARGET = "target"
    OPTION = "option"
    SELECTION = "selection"
    RESOLUTION = "resolution"
    CONTROL = "control"


class ActionDiffTag(str, Enum):
    EQUAL = "equal"
    REPLACE = "replace"
    INSERT = "insert"
    DELETE = "delete"


@dataclass(frozen=True)
class ActionAggregationHint:
    step: int
    group_key: str
    role: ActionRole

    def __post_init__(self) -> None:
        if not isinstance(self.step, int) or isinstance(self.step, bool) or self.step < 0:
            raise ValueError("step must be a non-negative integer")
        if not isinstance(self.group_key, str) or not self.group_key:
            raise ValueError("group_key must be a non-empty string")
        if not isinstance(self.role, ActionRole):
            object.__setattr__(self, "role", ActionRole(self.role))


@dataclass(frozen=True)
class DisplaySelection:
    candidate_id: str
    label: str
    kind: str
    order: int | None = None
    value: Any = None
    card_ref: Mapping[str, Any] | None = None
    effect_ref: Mapping[str, Any] | None = None

    def to_identity_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "candidate_id": self.candidate_id,
                "card_ref": self.card_ref,
                "effect_ref": self.effect_ref,
                "kind": self.kind,
                "order": self.order,
                "value": self.value,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {**self.to_identity_dict(), "label": self.label}


@dataclass(frozen=True)
class AtomicActionPresentation:
    step: int
    action_id: str
    action_occurrence_id: str
    action_kind: str
    request_type: str
    role: ActionRole
    selections: tuple[DisplaySelection, ...]

    def to_comparison_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_kind": self.action_kind,
            "request_type": self.request_type,
            "role": self.role.value,
            "selections": [selection.to_identity_dict() for selection in self.selections],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_kind": self.action_kind,
            "action_occurrence_id": self.action_occurrence_id,
            "request_type": self.request_type,
            "role": self.role.value,
            "selections": [selection.to_dict() for selection in self.selections],
            "step": self.step,
        }


@dataclass(frozen=True)
class CompositeActionPresentation:
    parts: tuple[AtomicActionPresentation, ...]

    @property
    def composite_id(self) -> str:
        return stable_digest(
            {
                "action_occurrence_ids": [part.action_occurrence_id for part in self.parts],
                "schema_version": ACTION_AGGREGATION_SCHEMA_VERSION,
            },
            prefix="cmpact_",
        )

    @property
    def comparison_key(self) -> str:
        return stable_digest(
            {
                "parts": [part.to_comparison_dict() for part in self.parts],
                "schema_version": ACTION_AGGREGATION_SCHEMA_VERSION,
            },
            prefix="cmpkey_",
        )

    @property
    def primary_kind(self) -> str:
        primary = next(
            (part for part in self.parts if part.role == ActionRole.PRIMARY),
            self.parts[0],
        )
        return primary.action_kind

    def selections_for(self, role: ActionRole) -> tuple[DisplaySelection, ...]:
        return tuple(
            selection
            for part in self.parts
            if part.role == role
            for selection in part.selections
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_ids": [part.action_id for part in self.parts],
            "action_occurrence_ids": [part.action_occurrence_id for part in self.parts],
            "atomic_steps": [part.step for part in self.parts],
            "comparison_key": self.comparison_key,
            "composite_id": self.composite_id,
            "costs": [item.to_dict() for item in self.selections_for(ActionRole.COST)],
            "options": [item.to_dict() for item in self.selections_for(ActionRole.OPTION)],
            "parts": [part.to_dict() for part in self.parts],
            "primary_kind": self.primary_kind,
            "selections": [
                item.to_dict() for item in self.selections_for(ActionRole.SELECTION)
            ],
            "targets": [item.to_dict() for item in self.selections_for(ActionRole.TARGET)],
        }


@dataclass(frozen=True)
class ActionAggregationLink:
    step: int
    action_occurrence_id: str
    composite_id: str
    part_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_occurrence_id": self.action_occurrence_id,
            "composite_id": self.composite_id,
            "part_index": self.part_index,
            "step": self.step,
        }


@dataclass(frozen=True)
class ActionAggregation:
    groups: tuple[CompositeActionPresentation, ...]
    links: tuple[ActionAggregationLink, ...]
    schema_version: str = ACTION_AGGREGATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": [group.to_dict() for group in self.groups],
            "links": [link.to_dict() for link in self.links],
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ActionDiffOperation:
    tag: ActionDiffTag
    before_start: int
    before_end: int
    after_start: int
    after_end: int
    before_composite_ids: tuple[str, ...]
    after_composite_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "after": {
                "composite_ids": list(self.after_composite_ids),
                "end": self.after_end,
                "start": self.after_start,
            },
            "before": {
                "composite_ids": list(self.before_composite_ids),
                "end": self.before_end,
                "start": self.before_start,
            },
            "tag": self.tag.value,
        }


_PRIMARY_ACTION_KINDS = frozenset(
    {
        "ACTIVATE_EFFECT",
        "ATTACK",
        "CHANGE_POSITION",
        "NORMAL_SUMMON",
        "SET_MONSTER",
        "SET_SPELL_TRAP",
        "SPECIAL_SUMMON",
    }
)
_CONTROL_ACTION_KINDS = frozenset(
    {
        "DECLINE",
        "END_TURN",
        "ENTER_BATTLE_PHASE",
        "ENTER_MAIN_PHASE_2",
        "PASS",
        "STOP_LINE",
    }
)
_OPTION_REQUEST_TYPES = frozenset(
    {
        "announce_attribute",
        "announce_card",
        "announce_number",
        "announce_race",
        "rock_paper_scissors",
        "select_effect_yes_no",
        "select_option",
        "select_yes_no",
    }
)


def _default_role(action_kind: str, request_type: str) -> ActionRole:
    if action_kind in _PRIMARY_ACTION_KINDS:
        return ActionRole.PRIMARY
    if action_kind in _CONTROL_ACTION_KINDS:
        return ActionRole.CONTROL
    if request_type in _OPTION_REQUEST_TYPES:
        return ActionRole.OPTION
    return ActionRole.SELECTION


def _required_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _required_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _event_part(
    raw_event: Mapping[str, Any],
    index: int,
    role: ActionRole,
) -> AtomicActionPresentation:
    step = raw_event.get("step")
    if step != index:
        raise ValueError(f"events[{index}].step must be {index}")
    action = _required_mapping(raw_event.get("action"), f"events[{index}].action")
    request = _required_mapping(raw_event.get("request", {}), f"events[{index}].request")
    action_id = _required_string(action.get("action_id"), f"events[{index}].action.action_id")
    occurrence_id = raw_event.get("action_occurrence_id")
    if not isinstance(occurrence_id, str) or not occurrence_id:
        occurrence_id = stable_digest(
            {
                "action_id": action_id,
                "state_hash_before": raw_event.get("state_hash_before"),
                "step": step,
            },
            prefix="aocc_legacy_",
        )
    candidates: dict[str, Mapping[str, Any]] = {}
    raw_candidates = request.get("candidates", [])
    if isinstance(raw_candidates, list):
        for raw_candidate in raw_candidates:
            if isinstance(raw_candidate, Mapping) and isinstance(
                raw_candidate.get("candidate_id"), str
            ):
                candidates[str(raw_candidate["candidate_id"])] = raw_candidate
    selections: list[DisplaySelection] = []
    raw_selections = action.get("selections", [])
    if not isinstance(raw_selections, list):
        raise ValueError(f"events[{index}].action.selections must be a list")
    for selection_index, raw_selection in enumerate(raw_selections):
        selection = _required_mapping(
            raw_selection,
            f"events[{index}].action.selections[{selection_index}]",
        )
        candidate_id = _required_string(
            selection.get("candidate_id"),
            f"events[{index}].action.selections[{selection_index}].candidate_id",
        )
        candidate = candidates.get(candidate_id, {})
        selections.append(
            DisplaySelection(
                candidate_id=candidate_id,
                label=str(candidate.get("label", "")),
                kind=str(candidate.get("kind", "")),
                order=selection.get("order"),
                value=selection.get("value"),
                card_ref=candidate.get("card_ref") or selection.get("card_ref"),
                effect_ref=candidate.get("effect_ref") or selection.get("effect_ref"),
            )
        )
    return AtomicActionPresentation(
        step=step,
        action_id=action_id,
        action_occurrence_id=occurrence_id,
        action_kind=_required_string(action.get("kind"), f"events[{index}].action.kind"),
        request_type=str(request.get("request_type", "")),
        role=role,
        selections=tuple(selections),
    )


def aggregate_replay_events(
    events: Sequence[Mapping[str, Any]],
    *,
    hints: Sequence[ActionAggregationHint] = (),
) -> ActionAggregation:
    hint_by_step: dict[int, ActionAggregationHint] = {}
    for hint in hints:
        if hint.step in hint_by_step:
            raise ValueError(f"duplicate aggregation hint for step {hint.step}")
        hint_by_step[hint.step] = hint
    unknown_steps = sorted(set(hint_by_step) - set(range(len(events))))
    if unknown_steps:
        raise ValueError(f"aggregation hints reference unknown steps: {unknown_steps}")

    grouped_parts: list[list[AtomicActionPresentation]] = []
    active_key: str | None = None
    seen_explicit_keys: set[str] = set()
    for index, raw_event in enumerate(events):
        event = _required_mapping(raw_event, f"events[{index}]")
        action = _required_mapping(event.get("action"), f"events[{index}].action")
        request = _required_mapping(event.get("request", {}), f"events[{index}].request")
        hint = hint_by_step.get(index)
        role = hint.role if hint is not None else _default_role(
            str(action.get("kind", "")), str(request.get("request_type", ""))
        )
        group_key = hint.group_key if hint is not None else f"event:{index}"
        if group_key != active_key:
            if hint is not None and group_key in seen_explicit_keys:
                raise ValueError(
                    f"aggregation group {group_key!r} must reference a contiguous event span"
                )
            grouped_parts.append([])
            active_key = group_key
            if hint is not None:
                seen_explicit_keys.add(group_key)
        grouped_parts[-1].append(_event_part(event, index, role))

    groups = tuple(CompositeActionPresentation(tuple(parts)) for parts in grouped_parts)
    links = tuple(
        ActionAggregationLink(
            step=part.step,
            action_occurrence_id=part.action_occurrence_id,
            composite_id=group.composite_id,
            part_index=part_index,
        )
        for group in groups
        for part_index, part in enumerate(group.parts)
    )
    return ActionAggregation(groups=groups, links=links)


def _trace_frames(value: Any, path: str) -> list[Mapping[str, Any]]:
    trace = _required_mapping(value, path)
    frames = trace.get("frames")
    if not isinstance(frames, list):
        raise ValueError(f"{path}.frames must be a list")
    return [
        _required_mapping(frame, f"{path}.frames[{index}]")
        for index, frame in enumerate(frames)
    ]


def _frame_payload(frame: Mapping[str, Any], path: str) -> bytes:
    payload_hex = frame.get("payload_hex")
    if not isinstance(payload_hex, str):
        raise ValueError(f"{path}.payload_hex must be a string")
    try:
        return bytes.fromhex(payload_hex)
    except ValueError as exc:
        raise ValueError(f"{path}.payload_hex must be hexadecimal") from exc


def _assert_supported_ocgcore_layout(
    replay: Mapping[str, Any],
    frame_batches: Sequence[tuple[str, Sequence[Mapping[str, Any]]]],
) -> None:
    version_metadata = replay.get("version_metadata")
    if isinstance(version_metadata, Mapping):
        api_version = version_metadata.get("ocgcore_api")
        if api_version not in OCGCORE_ACTION_AGGREGATION_SUPPORTED_APIS:
            raise ValueError(
                "action aggregation does not support ocgcore_api "
                f"{api_version!r}; supported versions are "
                f"{list(OCGCORE_ACTION_AGGREGATION_SUPPORTED_APIS)}"
            )
    for batch_path, frames in frame_batches:
        for index, frame in enumerate(frames):
            message_type = frame.get("message_type")
            expected_size = _API_11_PAYLOAD_SIZES.get(message_type)
            if expected_size is None:
                continue
            payload = _frame_payload(frame, f"{batch_path}[{index}]")
            if len(payload) != expected_size:
                message_name = _CHAIN_MESSAGE_NAMES.get(
                    message_type, f"message {message_type}"
                )
                raise ValueError(
                    f"{batch_path}[{index}] {message_name} payload must be "
                    f"{expected_size} bytes for ocgcore API 11.0"
                )


def _last_open_resolution_frame(
    frames: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    solving_frame: Mapping[str, Any] | None = None
    for frame in frames:
        message_type = frame.get("message_type")
        if message_type == _MSG_CHAIN_SOLVING:
            solving_frame = frame
        elif message_type in {_MSG_CHAIN_SOLVED, _MSG_CHAIN_END}:
            solving_frame = None
    return solving_frame


def _last_resolution_terminal_frame(
    frames: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    return next(
        (
            frame
            for frame in reversed(frames)
            if frame.get("message_type") in {_MSG_CHAIN_SOLVED, _MSG_CHAIN_END}
        ),
        None,
    )


def _is_cancelled_selection(
    action: Mapping[str, Any], request: Mapping[str, Any]
) -> bool:
    if action.get("kind") != "DECLINE":
        return False
    context = request.get("context")
    if not isinstance(context, Mapping):
        return False
    extra = context.get("extra")
    return isinstance(extra, Mapping) and extra.get("cancelable") is True


def _chain_lifecycle_evidence(
    frame_batches: Sequence[tuple[str, Sequence[Mapping[str, Any]]]],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for batch_path, frames in frame_batches:
        for index, frame in enumerate(frames):
            message_type = frame.get("message_type")
            message_name = _CHAIN_MESSAGE_NAMES.get(message_type)
            if message_name is None or message_type in {_MSG_HINT, _MSG_MOVE}:
                continue
            evidence.append(
                {
                    "batch_path": batch_path,
                    "frame_index": frame.get("frame_index", index),
                    "message_name": message_name,
                    "message_type": message_type,
                    "payload_hex": frame.get("payload_hex"),
                }
            )
    return evidence


def _selection_hint_evidence(
    frames: Sequence[Mapping[str, Any]],
    *,
    player: int,
    path: str,
) -> dict[str, Any] | None:
    evidence = None
    for index, frame in enumerate(frames):
        if frame.get("message_type") != _MSG_HINT:
            continue
        payload = _frame_payload(frame, f"{path}[{index}]")
        if len(payload) != 10:
            continue
        hint_type, hint_player, description = struct.unpack("<BBQ", payload)
        if hint_type == _HINT_SELECTMSG and hint_player == player:
            evidence = {
                "description": description,
                "frame_index": frame.get("frame_index", index),
                "hint_type": hint_type,
                "message_type": _MSG_HINT,
                "player": hint_player,
            }
    return evidence


def _selected_card_refs(event: Mapping[str, Any], path: str) -> list[Mapping[str, Any]]:
    request = _required_mapping(event.get("request"), f"{path}.request")
    action = _required_mapping(event.get("action"), f"{path}.action")
    raw_candidates = request.get("candidates")
    raw_selections = action.get("selections")
    if not isinstance(raw_candidates, list) or not isinstance(raw_selections, list):
        return []
    candidates = {
        candidate.get("candidate_id"): candidate
        for candidate in raw_candidates
        if isinstance(candidate, Mapping)
        and isinstance(candidate.get("candidate_id"), str)
    }
    selected_refs: list[Mapping[str, Any]] = []
    for selection in raw_selections:
        if not isinstance(selection, Mapping):
            continue
        candidate = candidates.get(selection.get("candidate_id"))
        if not isinstance(candidate, Mapping):
            continue
        card_ref = candidate.get("card_ref")
        if isinstance(card_ref, Mapping):
            selected_refs.append(card_ref)
    return selected_refs


def _cost_move_evidence(
    event: Mapping[str, Any],
    frames: Sequence[Mapping[str, Any]],
    *,
    path: str,
) -> dict[str, Any] | None:
    selected_refs = _selected_card_refs(event, path)
    if not selected_refs:
        return None
    for index, frame in enumerate(frames):
        if frame.get("message_type") != _MSG_MOVE:
            continue
        payload = _frame_payload(frame, f"{path}.core_output.frames[{index}]")
        if len(payload) != _MOVE_PAYLOAD.size:
            continue
        (
            code,
            previous_controller,
            previous_location,
            previous_sequence,
            previous_position,
            current_controller,
            current_location,
            current_sequence,
            current_position,
            reason,
        ) = _MOVE_PAYLOAD.unpack(payload)
        if not reason & _REASON_COST:
            continue
        matching_ref = next(
            (
                card_ref
                for card_ref in selected_refs
                if card_ref.get("public_card_id") == code
                and card_ref.get("controller") == previous_controller
                and card_ref.get("location") == previous_location
                and card_ref.get("sequence") == previous_sequence
            ),
            None,
        )
        if matching_ref is None:
            continue
        return {
            "card": {
                "code": code,
                "previous": {
                    "controller": previous_controller,
                    "location": previous_location,
                    "position": previous_position,
                    "sequence": previous_sequence,
                },
                "current": {
                    "controller": current_controller,
                    "location": current_location,
                    "position": current_position,
                    "sequence": current_sequence,
                },
            },
            "frame_index": frame.get("frame_index", index),
            "message_type": _MSG_MOVE,
            "reason": reason,
            "reason_mask": _REASON_COST,
        }
    return None


def derive_ocgcore_action_aggregation(
    replay: Mapping[str, Any],
) -> tuple[ActionAggregation, dict[str, Any]]:
    if not isinstance(replay, Mapping):
        raise ValueError("replay must be a mapping")
    events = replay.get("events")
    if not isinstance(events, list):
        raise ValueError("replay.events must be a list")
    initial_frames = _trace_frames(
        replay.get("initial_core_output"), "replay.initial_core_output"
    )
    event_frames = [
        _trace_frames(
            _required_mapping(event, f"replay.events[{index}]").get("core_output"),
            f"replay.events[{index}].core_output",
        )
        for index, event in enumerate(events)
    ]
    frame_batches = [
        ("replay.initial_core_output.frames", initial_frames),
        *[
            (f"replay.events[{index}].core_output.frames", frames)
            for index, frames in enumerate(event_frames)
        ],
    ]
    _assert_supported_ocgcore_layout(replay, frame_batches)
    hints: list[ActionAggregationHint] = []
    role_evidence: list[dict[str, Any]] = []
    group_boundaries: list[dict[str, Any]] = []
    fallback_steps: list[int] = []
    active_group_key: str | None = None
    active_group_kind: str | None = None
    active_group_start: int | None = None

    for index, raw_event in enumerate(events):
        event = _required_mapping(raw_event, f"replay.events[{index}]")
        if event.get("step") != index:
            raise ValueError(f"replay.events[{index}].step must be {index}")
        action = _required_mapping(
            event.get("action"), f"replay.events[{index}].action"
        )
        request = _required_mapping(
            event.get("request"), f"replay.events[{index}].request"
        )
        request_frames = (
            initial_frames
            if index == 0
            else event_frames[index - 1]
        )
        response_frames = event_frames[index]
        action_kind = str(action.get("kind", ""))
        request_type = str(request.get("request_type", ""))
        evidence: dict[str, Any] | None = None
        cancelled_selection = False

        if active_group_key is None:
            solving_frame = _last_open_resolution_frame(request_frames)
            if solving_frame is not None:
                active_group_key = (
                    f"ocgcore-resolution:{index}:"
                    f"{solving_frame.get('frame_index', 0)}"
                )
                active_group_kind = "resolution"
                active_group_start = index

        if action_kind == "ACTIVATE_EFFECT":
            if active_group_key is not None:
                raise ValueError(
                    "ACTIVATE_EFFECT cannot start inside an unfinished "
                    f"{active_group_kind} group"
                )
            occurrence_id = _required_string(
                event.get("action_occurrence_id"),
                f"replay.events[{index}].action_occurrence_id",
            )
            active_group_key = f"ocgcore-activation:{occurrence_id}"
            active_group_kind = "activation_setup"
            active_group_start = index
            role = ActionRole.PRIMARY
            evidence = {
                "basis": "action_kind",
                "value": "ACTIVATE_EFFECT",
            }
        elif active_group_kind == "activation_setup":
            cancelled_selection = _is_cancelled_selection(action, request)
            cost_evidence = _cost_move_evidence(
                event,
                response_frames,
                path=f"replay.events[{index}]",
            )
            selection_hint = _selection_hint_evidence(
                request_frames,
                player=int(request.get("player", -1)),
                path=(
                    "replay.initial_core_output.frames"
                    if index == 0
                    else f"replay.events[{index - 1}].core_output.frames"
                ),
            )
            if cancelled_selection:
                role = ActionRole.CONTROL
                evidence = {
                    "basis": "cancelable_selection_declined",
                    "request_type": request_type,
                }
            elif cost_evidence is not None:
                role = ActionRole.COST
                evidence = {"basis": "selected_card_reason_cost_move", **cost_evidence}
            elif (
                selection_hint is not None
                and selection_hint["description"] == _HINTMSG_TARGET
            ):
                role = ActionRole.TARGET
                evidence = {"basis": "select_hint_target", **selection_hint}
            elif request_type in _OPTION_REQUEST_TYPES:
                role = ActionRole.OPTION
                evidence = {
                    "basis": "selection_message_type",
                    "request_type": request_type,
                }
            else:
                role = ActionRole.SELECTION
                evidence = {
                    "basis": "conservative_fallback",
                    "request_type": request_type,
                }
                fallback_steps.append(index)
        elif active_group_kind == "resolution":
            role = ActionRole.RESOLUTION
            solving_frame = _last_open_resolution_frame(request_frames)
            evidence = {
                "basis": (
                    "msg_chain_solving"
                    if index == active_group_start
                    else "active_resolution_group"
                ),
                "request_type": request_type,
            }
            if solving_frame is not None:
                evidence.update(
                    {
                        "frame_index": solving_frame.get("frame_index"),
                        "message_type": _MSG_CHAIN_SOLVING,
                        "payload_hex": solving_frame.get("payload_hex"),
                    }
                )
        else:
            role = _default_role(action_kind, request_type)
            if role == ActionRole.SELECTION:
                fallback_steps.append(index)

        if active_group_key is not None:
            hints.append(ActionAggregationHint(index, active_group_key, role))
            role_evidence.append(
                {
                    "evidence": evidence,
                    "group_key": active_group_key,
                    "group_kind": active_group_kind,
                    "role": role.value,
                    "step": index,
                }
            )
            chained_frame = next(
                (
                    frame
                    for frame in response_frames
                    if frame.get("message_type") == _MSG_CHAINED
                ),
                None,
            )
            if (
                active_group_kind == "activation_setup"
                and cancelled_selection
                and chained_frame is not None
            ):
                raise ValueError(
                    "cancelled activation response cannot also contain MSG_CHAINED"
                )
            if active_group_kind == "activation_setup" and (
                chained_frame is not None or cancelled_selection
            ):
                group_boundaries.append(
                    {
                        "boundary_kind": (
                            "msg_chained"
                            if chained_frame is not None
                            else "cancelled_selection"
                        ),
                        "end_after_response_step": index,
                        "end_frame_index": (
                            chained_frame.get("frame_index")
                            if chained_frame is not None
                            else None
                        ),
                        "end_message_type": (
                            _MSG_CHAINED if chained_frame is not None else None
                        ),
                        "group_key": active_group_key,
                        "group_kind": active_group_kind,
                        "start_step": active_group_start,
                    }
                )
                active_group_key = None
                active_group_kind = None
                active_group_start = None
            elif active_group_kind == "resolution":
                terminal_frame = _last_resolution_terminal_frame(response_frames)
                if terminal_frame is not None:
                    terminal_type = int(terminal_frame["message_type"])
                    group_boundaries.append(
                        {
                            "boundary_kind": _CHAIN_MESSAGE_NAMES[
                                terminal_type
                            ].lower(),
                            "end_after_response_step": index,
                            "end_frame_index": terminal_frame.get("frame_index"),
                            "end_message_type": terminal_type,
                            "group_key": active_group_key,
                            "group_kind": active_group_kind,
                            "start_step": active_group_start,
                        }
                    )
                    active_group_key = None
                    active_group_kind = None
                    active_group_start = None

    if active_group_key is not None:
        raise ValueError(
            f"{active_group_kind} group {active_group_key!r} did not reach a "
            "validated lifecycle boundary"
        )
    aggregation = aggregate_replay_events(events, hints=tuple(hints))
    identity = to_canonical_data(
        {
            "chain_lifecycle": _chain_lifecycle_evidence(frame_batches),
            "fallback_steps": sorted(set(fallback_steps)),
            "group_boundaries": group_boundaries,
            "method": OCGCORE_ACTION_AGGREGATION_METHOD,
            "role_evidence": role_evidence,
            "schema_version": OCGCORE_ACTION_AGGREGATION_EVIDENCE_SCHEMA_VERSION,
        }
    )
    return aggregation, {
        **identity,
        "evidence_id": stable_digest(identity, prefix="actaggev_"),
    }


def diff_action_aggregations(
    before: ActionAggregation,
    after: ActionAggregation,
) -> tuple[ActionDiffOperation, ...]:
    matcher = SequenceMatcher(
        a=[group.comparison_key for group in before.groups],
        b=[group.comparison_key for group in after.groups],
        autojunk=False,
    )
    return tuple(
        ActionDiffOperation(
            tag=ActionDiffTag(tag),
            before_start=before_start,
            before_end=before_end,
            after_start=after_start,
            after_end=after_end,
            before_composite_ids=tuple(
                group.composite_id for group in before.groups[before_start:before_end]
            ),
            after_composite_ids=tuple(
                group.composite_id for group in after.groups[after_start:after_end]
            ),
        )
        for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes()
    )
