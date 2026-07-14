from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
import struct
from typing import Any

from ygo_effect_dsl.engine.action.models import action_from_dict
from ygo_effect_dsl.engine.bridge.decision import DecisionContext
from ygo_effect_dsl.engine.bridge.ocgcore.protocol import (
    MESSAGE_REGISTRY_VERSION,
    PROTOCOL_VERSION,
    ActionResponseEncoder,
    OcgcoreMessageDecoder,
)
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data
from ygo_effect_dsl.engine.replay.verifier import request_signature_identity
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.route_dsl import assert_valid_route_document


DECISION_SHAPE_CORPUS_SCHEMA_VERSION = "ocgcore-decision-shape-corpus-v1"
REQUIRED_SHAPE_CATEGORIES = frozenset(
    {
        "cost",
        "field_source",
        "hand_source",
        "multi_target",
        "option",
        "single_target",
        "targetless",
    }
)
_FORBIDDEN_RAW_FIELDS = frozenset({"payload_hex", "response_hex"})

_NEGATIVE_CASES = (
    {
        "case_id": "unknown_message_id",
        "classification": "path_failure",
        "diagnostic_code": "unsupported_message",
        "evidence": ["tests/test_ocgcore_protocol.py"],
        "required_context": [
            "decision_context",
            "message_registry_version",
            "message_type",
            "payload_length",
            "payload_sha256",
            "protocol_version",
        ],
    },
    {
        "case_id": "unknown_candidate_shape",
        "classification": "configuration_failure",
        "diagnostic_code": "unknown_candidate_shape",
        "evidence": ["tests/test_interruption_taxonomy.py"],
        "required_context": ["request_id", "request_type"],
    },
    {
        "case_id": "candidate_disappeared",
        "classification": "path_failure",
        "diagnostic_code": "candidate_disappeared",
        "evidence": ["tests/test_interruption_taxonomy.py"],
        "required_context": ["candidate_ids", "request_id"],
    },
    {
        "case_id": "ambiguous_candidate_identity",
        "classification": "configuration_failure",
        "diagnostic_code": "ambiguous_candidate_identity",
        "evidence": ["tests/test_interruption_taxonomy.py"],
        "required_context": ["candidate_ids", "request_id"],
    },
    {
        "case_id": "ambiguous_response_mapping",
        "classification": "path_failure",
        "diagnostic_code": "invalid_response",
        "evidence": ["tests/test_ocgcore_protocol.py"],
        "required_context": ["duplicate_candidate_ids", "request_id", "request_type"],
    },
    {
        "case_id": "unverified_interruption_category",
        "classification": "unsupported_category",
        "diagnostic_code": "unverified_fixture_category",
        "evidence": ["tests/test_interruption_taxonomy.py"],
        "required_context": ["request_id", "validation_categories"],
    },
)


class DecisionShapeCorpusError(ValueError):
    """A Route cannot prove the recorded Decision shape by binary round-trip."""


def negative_decision_shape_registry() -> tuple[dict[str, Any], ...]:
    return tuple(to_canonical_data(case) for case in _NEGATIVE_CASES)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DecisionShapeCorpusError(f"{path} must be a mapping")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise DecisionShapeCorpusError(f"{path} must be a list")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise DecisionShapeCorpusError(f"{path} must be a non-empty string")
    return value


def _integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DecisionShapeCorpusError(f"{path} must be an integer")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise DecisionShapeCorpusError(f"{path} must be a string")
    return value


def _reject_raw_binary_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            field = str(key)
            if field in _FORBIDDEN_RAW_FIELDS:
                raise DecisionShapeCorpusError(
                    f"{path}.{field} is forbidden in a sanitized Decision corpus"
                )
            _reject_raw_binary_fields(item, f"{path}.{field}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_raw_binary_fields(item, f"{path}[{index}]")


def _decision_context(value: Any, path: str) -> DecisionContext:
    raw = _mapping(value, path)
    chain = tuple(
        dict(_mapping(item, f"{path}.chain[{index}]"))
        for index, item in enumerate(_list(raw.get("chain"), f"{path}.chain"))
    )
    return DecisionContext(
        phase=_text(raw.get("phase"), f"{path}.phase"),
        chain=chain,
        turn_player=raw.get("turn_player"),
        priority_player=raw.get("priority_player"),
        visible_board=dict(
            _mapping(raw.get("visible_board"), f"{path}.visible_board")
        ),
        request_source=_text(
            raw.get("request_source"), f"{path}.request_source"
        ),
        version_metadata=dict(
            _mapping(raw.get("version_metadata"), f"{path}.version_metadata")
        ),
        extra=dict(_mapping(raw.get("extra"), f"{path}.extra")),
    )


def _trace_stream(
    trace: Mapping[str, Any], path: str
) -> tuple[bytes, tuple[dict[str, Any], ...]]:
    stream = bytearray()
    summaries: list[dict[str, Any]] = []
    for index, raw_frame in enumerate(_list(trace.get("frames"), f"{path}.frames")):
        frame_path = f"{path}.frames[{index}]"
        frame = _mapping(raw_frame, frame_path)
        message_type = _integer(frame.get("message_type"), f"{frame_path}.message_type")
        if not 0 <= message_type <= 255:
            raise DecisionShapeCorpusError(
                f"{frame_path}.message_type must fit one byte"
            )
        payload_hex = frame.get("payload_hex")
        if not isinstance(payload_hex, str):
            raise DecisionShapeCorpusError(f"{frame_path}.payload_hex must be a string")
        try:
            payload = bytes.fromhex(payload_hex)
        except ValueError as exc:
            raise DecisionShapeCorpusError(
                f"{frame_path}.payload_hex is not valid hexadecimal"
            ) from exc
        payload_hash = sha256(payload).hexdigest()
        if frame.get("payload_sha256") != payload_hash:
            raise DecisionShapeCorpusError(
                f"{frame_path}.payload_sha256 does not match payload_hex"
            )
        body = bytes((message_type,)) + payload
        stream.extend(struct.pack("<I", len(body)))
        stream.extend(body)
        summaries.append(
            {
                "frame_index": _integer(
                    frame.get("frame_index"), f"{frame_path}.frame_index"
                ),
                "message_type": message_type,
                "payload_length": len(payload),
                "payload_sha256": payload_hash,
            }
        )
    return bytes(stream), tuple(summaries)


def _roles_by_step(route: Mapping[str, Any]) -> dict[int, str]:
    presentation = route.get("presentation")
    if not isinstance(presentation, Mapping):
        return {}
    aggregation = presentation.get("action_aggregation")
    if not isinstance(aggregation, Mapping):
        return {}
    roles: dict[int, str] = {}
    for raw_group in aggregation.get("groups", []):
        if not isinstance(raw_group, Mapping):
            continue
        for raw_part in raw_group.get("parts", []):
            if not isinstance(raw_part, Mapping):
                continue
            step = raw_part.get("step")
            role = raw_part.get("role")
            if (
                not isinstance(step, int)
                or isinstance(step, bool)
                or not isinstance(role, str)
            ):
                continue
            previous = roles.get(step)
            if previous not in {None, role}:
                raise DecisionShapeCorpusError(
                    f"presentation assigns conflicting roles to replay step {step}"
                )
            roles[step] = role
    return roles


def _candidate_shapes(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for index, raw_candidate in enumerate(
        _list(request.get("candidates"), "request.candidates")
    ):
        candidate = _mapping(raw_candidate, f"request.candidates[{index}]")
        card_ref = candidate.get("card_ref")
        effect_ref = candidate.get("effect_ref")
        payload = _mapping(
            candidate.get("payload"), f"request.candidates[{index}].payload"
        )
        shape = {
            "card_ref_fields": (
                sorted(str(key) for key in card_ref)
                if isinstance(card_ref, Mapping)
                else []
            ),
            "effect_ref_fields": (
                sorted(str(key) for key in effect_ref)
                if isinstance(effect_ref, Mapping)
                else []
            ),
            "kind": candidate.get("kind"),
            "payload_fields": sorted(str(key) for key in payload),
            "response_codec": payload.get("response_codec"),
        }
        unique[canonical_json(shape)] = shape
    return [unique[key] for key in sorted(unique)]


def _source_category(location: Any) -> str | None:
    if location in {2, "hand"}:
        return "hand_source"
    if location in {
        4,
        8,
        "field",
        "monster_zone",
        "spell_trap_zone",
        "core_location_4",
        "core_location_8",
    }:
        return "field_source"
    return None


def _event_categories(
    event: Mapping[str, Any], role: str | None
) -> set[str]:
    categories: set[str] = set()
    action = _mapping(event.get("action"), "event.action")
    selections = _list(action.get("selections"), "event.action.selections")
    if role == "cost":
        categories.add("cost")
    elif role == "option":
        categories.add("option")
    elif role == "target":
        categories.add("single_target" if len(selections) == 1 else "multi_target")
    if action.get("kind") == "ACTIVATE_EFFECT":
        refs = [action.get("source")]
        refs.extend(
            selection.get("card_ref")
            for selection in selections
            if isinstance(selection, Mapping)
        )
        for ref in refs:
            if isinstance(ref, Mapping):
                category = _source_category(ref.get("location"))
                if category is not None:
                    categories.add(category)
    return categories


def _interruption_categories(route: Mapping[str, Any]) -> set[str]:
    categories: set[str] = set()
    raw_interruptions = route.get("interruptions", [])
    if not isinstance(raw_interruptions, list):
        return categories
    for raw_interruption in raw_interruptions:
        if not isinstance(raw_interruption, Mapping):
            continue
        source = _source_category(raw_interruption.get("source_zone"))
        if source is not None:
            categories.add(source)
        response_steps = raw_interruption.get("response_steps")
        if response_steps == []:
            categories.add("targetless")
        if not isinstance(response_steps, list):
            continue
        for response in response_steps:
            if not isinstance(response, Mapping):
                continue
            role = response.get("role")
            candidate_ids = response.get("candidate_ids")
            count = len(candidate_ids) if isinstance(candidate_ids, list) else 0
            if role == "cost":
                categories.add("cost")
            elif role == "option":
                categories.add("option")
            elif role == "target":
                categories.add("single_target" if count == 1 else "multi_target")
    return categories


def _build_case(
    *,
    route_id: str,
    step: int,
    event: Mapping[str, Any],
    source_trace: Mapping[str, Any],
    role: str | None,
) -> tuple[dict[str, Any], set[str]]:
    event_path = f"route[{route_id}].replay.events[{step}]"
    request = _mapping(event.get("request"), f"{event_path}.request")
    request_id = _string(request.get("request_id"), f"{event_path}.request.request_id")
    request_signature = _string(
        event.get("request_signature"), f"{event_path}.request_signature"
    )
    if request.get("request_signature") != request_signature:
        raise DecisionShapeCorpusError(
            f"{event_path}.request signature does not match its event"
        )
    if source_trace.get("request_signature") != request_signature:
        raise DecisionShapeCorpusError(
            f"{event_path} is not linked to the preceding core output"
        )

    stream, frame_summaries = _trace_stream(
        source_trace, f"{event_path}.source_core_output"
    )
    context = _decision_context(
        request.get("context"), f"{event_path}.request.context"
    )
    decoded = OcgcoreMessageDecoder().decode_batch(
        stream,
        request_id=request_id,
        context=context,
    ).request
    if decoded is None:
        raise DecisionShapeCorpusError(f"{event_path} source has no Decision message")
    recorded_identity = request_signature_identity(request)
    if decoded.to_signature_dict() != recorded_identity:
        raise DecisionShapeCorpusError(
            f"{event_path}.request does not match binary decoder output"
        )
    if decoded.request_signature != request_signature:
        raise DecisionShapeCorpusError(
            f"{event_path}.request_signature is not canonical"
        )

    action = action_from_dict(_mapping(event.get("action"), f"{event_path}.action"))
    encoded = ActionResponseEncoder().encode(decoded, action)
    expected_response = encoded.to_trace_dict()
    recorded_response = _mapping(
        event.get("core_response"), f"{event_path}.core_response"
    )
    for key, expected in expected_response.items():
        if recorded_response.get(key) != expected:
            raise DecisionShapeCorpusError(
                f"{event_path}.core_response.{key} does not match response encoder"
            )

    message_type = _integer(
        _mapping(request.get("context"), f"{event_path}.request.context")
        .get("extra", {})
        .get("message_type"),
        f"{event_path}.request.context.extra.message_type",
    )
    decision_frames = [
        frame for frame in frame_summaries if frame["message_type"] == message_type
    ]
    if len(decision_frames) != 1:
        raise DecisionShapeCorpusError(
            f"{event_path} must have exactly one source frame for message {message_type}"
        )
    raw_context = _mapping(request.get("context"), f"{event_path}.request.context")
    extra = _mapping(raw_context.get("extra"), f"{event_path}.request.context.extra")
    case = {
        "candidate_shapes": _candidate_shapes(request),
        "case_id": "",
        "constraints": request.get("constraints"),
        "context": {
            "chain_length": len(_list(raw_context.get("chain"), "request.context.chain")),
            "message_name": extra.get("message_name"),
            "message_type": message_type,
            "phase": raw_context.get("phase"),
            "request_source": raw_context.get("request_source"),
            "version_metadata": raw_context.get("version_metadata"),
        },
        "request_signature": request_signature,
        "request_type": request.get("request_type"),
        "response": {
            "codec_version": expected_response["codec_version"],
            "response_length": expected_response["response_length"],
            "response_sha256": expected_response["response_sha256"],
            "selected_candidate_count": len(
                expected_response["selected_candidate_ids"]
            ),
        },
        "role": role,
        "route_id": route_id,
        "round_trip": "verified",
        "source_frame": {
            "batch_id": source_trace.get("batch_id"),
            **decision_frames[0],
        },
        "step": step,
    }
    case["case_id"] = stable_digest(
        {key: value for key, value in case.items() if key != "case_id"},
        prefix="decisionshape_",
    )
    return to_canonical_data(case), _event_categories(event, role)


def build_decision_shape_corpus(
    route_documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not route_documents:
        raise DecisionShapeCorpusError("at least one Route document is required")
    cases: dict[str, dict[str, Any]] = {}
    routes: list[dict[str, Any]] = []
    categories: set[str] = set()
    route_ids: set[str] = set()
    for route in sorted(
        route_documents,
        key=lambda document: str(document.get("route_id", "")),
    ):
        try:
            assert_valid_route_document(route)
        except ValueError as exc:
            raise DecisionShapeCorpusError(f"Route validation failed: {exc}") from exc
        route_id = _string(route.get("route_id"), "route.route_id")
        if route_id in route_ids:
            raise DecisionShapeCorpusError(
                f"duplicate Route ID in Decision corpus input: {route_id}"
            )
        route_ids.add(route_id)
        replay = _mapping(route.get("replay"), f"route[{route_id}].replay")
        events = _list(replay.get("events"), f"route[{route_id}].replay.events")
        roles = _roles_by_step(route)
        route_case_ids: list[str] = []
        for step, raw_event in enumerate(events):
            event = _mapping(raw_event, f"route[{route_id}].replay.events[{step}]")
            source_trace = _mapping(
                replay.get("initial_core_output")
                if step == 0
                else _mapping(
                    events[step - 1],
                    f"route[{route_id}].replay.events[{step - 1}]",
                ).get("core_output"),
                f"route[{route_id}].source_core_output[{step}]",
            )
            case, event_categories = _build_case(
                route_id=route_id,
                step=step,
                event=event,
                source_trace=source_trace,
                role=roles.get(step),
            )
            cases[case["case_id"]] = case
            route_case_ids.append(case["case_id"])
            categories.update(event_categories)
        categories.update(_interruption_categories(route))
        experiment = route.get("experiment")
        routes.append(
            {
                "case_ids": route_case_ids,
                "event_count": len(events),
                "experiment_id": (
                    experiment.get("experiment_id")
                    if isinstance(experiment, Mapping)
                    else None
                ),
                "route_id": route_id,
            }
        )

    ordered_cases = [cases[key] for key in sorted(cases)]
    missing = sorted(REQUIRED_SHAPE_CATEGORIES - categories)
    report: dict[str, Any] = {
        "corpus_id": "",
        "coverage": {
            "categories": sorted(categories),
            "message_types": sorted(
                {case["context"]["message_type"] for case in ordered_cases}
            ),
            "missing_required_categories": missing,
            "request_types": sorted(
                {str(case["request_type"]) for case in ordered_cases}
            ),
            "required_categories": sorted(REQUIRED_SHAPE_CATEGORIES),
            "shape_coverage_status": "complete" if not missing else "incomplete",
        },
        "message_registry_version": MESSAGE_REGISTRY_VERSION,
        "negative_cases": list(negative_decision_shape_registry()),
        "protocol_version": PROTOCOL_VERSION,
        "routes": routes,
        "schema_version": DECISION_SHAPE_CORPUS_SCHEMA_VERSION,
        "supported_cases": ordered_cases,
    }
    report["corpus_id"] = stable_digest(
        {key: value for key, value in report.items() if key != "corpus_id"},
        prefix="decisioncorpus_",
    )
    return to_canonical_data(report)


def write_decision_shape_corpus(
    path: str | Path,
    corpus: Mapping[str, Any],
) -> None:
    _reject_raw_binary_fields(corpus)
    if corpus.get("schema_version") != DECISION_SHAPE_CORPUS_SCHEMA_VERSION:
        raise DecisionShapeCorpusError("unsupported Decision shape corpus schema")
    expected = stable_digest(
        {key: value for key, value in corpus.items() if key != "corpus_id"},
        prefix="decisioncorpus_",
    )
    if corpus.get("corpus_id") != expected:
        raise DecisionShapeCorpusError("Decision shape corpus ID is not canonical")
    atomic_write_text(path, canonical_json(corpus) + "\n")


__all__ = [
    "DECISION_SHAPE_CORPUS_SCHEMA_VERSION",
    "REQUIRED_SHAPE_CATEGORIES",
    "DecisionShapeCorpusError",
    "build_decision_shape_corpus",
    "negative_decision_shape_registry",
    "write_decision_shape_corpus",
]
