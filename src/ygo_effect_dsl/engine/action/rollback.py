from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
ACTIVATION_ROLLBACK_PROBE_SCHEMA_VERSION = (
    "ocgcore-activation-rollback-probe-v1"
)
ACTIVATION_ROLLBACK_UNREACHABLE = "raw_replay_contract_core_unreachable"
ACTIVATION_ROLLBACK_SUPPORT_CANDIDATE = "requires_versioned_route_validation"


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def build_activation_rollback_probe(
    *,
    activation_event: Mapping[str, Any],
    cancellation_action: Mapping[str, Any],
    cancellation_request: Mapping[str, Any],
    cancellation_response: Mapping[str, Any],
    followup_core_output: Mapping[str, Any],
    manifest: Mapping[str, Any],
    next_request: Mapping[str, Any],
    state_after: Mapping[str, Any],
    state_before: Mapping[str, Any],
) -> dict[str, Any]:
    activation_event = _mapping(activation_event, "activation_event")
    activation_action = _mapping(
        activation_event.get("action"), "activation_event.action"
    )
    cancellation_action = _mapping(cancellation_action, "cancellation_action")
    cancellation_request = _mapping(
        cancellation_request, "cancellation_request"
    )
    cancellation_response = _mapping(
        cancellation_response, "cancellation_response"
    )
    followup_core_output = _mapping(
        followup_core_output, "followup_core_output"
    )
    next_request = _mapping(next_request, "next_request")
    raw_frames = followup_core_output.get("frames")
    if not isinstance(raw_frames, list):
        raise ValueError("followup_core_output.frames must be a list")
    frames = []
    for index, raw_frame in enumerate(raw_frames):
        frame = _mapping(raw_frame, f"followup_core_output.frames[{index}]")
        frames.append(
            {
                "frame_index": frame.get("frame_index"),
                "message_type": frame.get("message_type"),
                "payload_hex": frame.get("payload_hex"),
            }
        )
    message_types = [frame["message_type"] for frame in frames]
    raw_candidates = next_request.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("next_request.candidates must be a list")
    next_candidates = []
    for index, raw_candidate in enumerate(raw_candidates):
        candidate = _mapping(
            raw_candidate, f"next_request.candidates[{index}]"
        )
        next_candidates.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "kind": candidate.get("kind"),
            }
        )
    known_unreachable = (
        message_types == [71, 16]
        and frames[0]["payload_hex"] == "01"
        and next_request.get("request_type") == "select_chain"
    )
    rollback_signal_observed = 71 not in message_types
    if not known_unreachable and not rollback_signal_observed:
        raise ValueError("activation rollback probe emitted an unknown follow-up")
    identity = to_canonical_data(
        {
            "activation": {
                "action_id": activation_action.get("action_id"),
                "action_occurrence_id": activation_event.get(
                    "action_occurrence_id"
                ),
                "kind": activation_action.get("kind"),
                "request_signature": activation_event.get(
                    "request_signature"
                ),
                "source": activation_action.get("source"),
                "state_hash_after": activation_event.get("state_hash_after"),
                "state_hash_before": activation_event.get(
                    "state_hash_before"
                ),
                "step": activation_event.get("step"),
            },
            "cancellation": {
                "action": cancellation_action,
                "request": cancellation_request,
                "response": cancellation_response,
                "state_after": state_after,
                "state_before": state_before,
            },
            "classification": (
                ACTIVATION_ROLLBACK_SUPPORT_CANDIDATE
                if rollback_signal_observed
                else ACTIVATION_ROLLBACK_UNREACHABLE
            ),
            "followup": {
                "frames": frames,
                "message_types": message_types,
                "next_request": {
                    "candidates": next_candidates,
                    "player": next_request.get("player"),
                    "request_signature": next_request.get("request_signature"),
                    "request_type": next_request.get("request_type"),
                },
            },
            "manifest": manifest,
            "rollback_supported": rollback_signal_observed,
            "schema_version": ACTIVATION_ROLLBACK_PROBE_SCHEMA_VERSION,
            "status": (
                "support_candidate"
                if rollback_signal_observed
                else "unsupported"
            ),
        }
    )
    document = {
        **identity,
        "evidence_id": stable_digest(identity, prefix="rollbackprobe_"),
    }
    assert_valid_activation_rollback_probe(document)
    return document


def assert_valid_activation_rollback_probe(
    document: Mapping[str, Any],
) -> None:
    from ygo_effect_dsl.engine.replay.manifest import ReplayManifestV03a

    document = _mapping(document, "probe")
    if document.get("schema_version") != ACTIVATION_ROLLBACK_PROBE_SCHEMA_VERSION:
        raise ValueError("unsupported activation rollback probe schema")
    identity = {
        key: value for key, value in document.items() if key != "evidence_id"
    }
    expected_id = stable_digest(identity, prefix="rollbackprobe_")
    if document.get("evidence_id") != expected_id:
        raise ValueError("activation rollback probe evidence_id mismatch")

    manifest = _mapping(document.get("manifest"), "probe.manifest")
    parsed_manifest = ReplayManifestV03a.from_dict(manifest)
    parsed_manifest.assert_reproducible()
    environment = _mapping(
        manifest.get("environment"), "probe.manifest.environment"
    )
    core = _mapping(environment.get("core"), "probe.manifest.environment.core")
    if core.get("api") != "11.0":
        raise ValueError("activation rollback probe requires ocgcore API 11.0")
    if core.get("custom_patches") != []:
        raise ValueError("activation rollback probe must use an unmodified core")
    _non_empty_string(core.get("binary_sha256"), "core.binary_sha256")
    fixture = _mapping(
        environment.get("fixture_script"),
        "probe.manifest.environment.fixture_script",
    )
    _non_empty_string(fixture.get("sha256"), "fixture_script.sha256")
    assets = _mapping(
        environment.get("assets"), "probe.manifest.environment.assets"
    )
    _non_empty_string(
        assets.get("card_database_commit"), "assets.card_database_commit"
    )
    _non_empty_string(assets.get("database_sha256"), "assets.database_sha256")
    randomness = _mapping(manifest.get("randomness"), "probe.manifest.randomness")
    if randomness.get("core_seed") != [1, 2, 3, 4]:
        raise ValueError("activation rollback probe seed mismatch")

    activation = _mapping(document.get("activation"), "probe.activation")
    if activation.get("kind") != "ACTIVATE_EFFECT":
        raise ValueError("probe activation must be ACTIVATE_EFFECT")
    _non_empty_string(
        activation.get("action_occurrence_id"),
        "probe.activation.action_occurrence_id",
    )
    cancellation = _mapping(
        document.get("cancellation"), "probe.cancellation"
    )
    action = _mapping(cancellation.get("action"), "probe.cancellation.action")
    if action.get("kind") != "DECLINE" or action.get("selections") != []:
        raise ValueError("probe cancellation must be an empty DECLINE action")
    request = _mapping(
        cancellation.get("request"), "probe.cancellation.request"
    )
    if request.get("request_type") != "select_card":
        raise ValueError("probe cancellation request must be select_card")
    context = _mapping(request.get("context"), "probe.cancellation.request.context")
    extra = _mapping(context.get("extra"), "probe.cancellation.request.context.extra")
    if extra.get("cancelable") is not True:
        raise ValueError("probe select_card request must be cancelable")
    response = _mapping(
        cancellation.get("response"), "probe.cancellation.response"
    )
    if response.get("response_hex") != "ffffffff":
        raise ValueError("probe cancellation response must be ffffffff")
    for name in ("state_before", "state_after"):
        state = _mapping(cancellation.get(name), f"probe.cancellation.{name}")
        _non_empty_string(state.get("state_hash"), f"{name}.state_hash")

    followup = _mapping(document.get("followup"), "probe.followup")
    message_types = followup.get("message_types")
    if not isinstance(message_types, list):
        raise ValueError("probe.followup.message_types must be a list")
    frames = followup.get("frames")
    if not isinstance(frames, list):
        raise ValueError("probe.followup.frames must be a list")
    next_request = _mapping(
        followup.get("next_request"), "probe.followup.next_request"
    )
    known_unreachable = (
        message_types == [71, 16]
        and len(frames) == 2
        and isinstance(frames[0], Mapping)
        and frames[0].get("payload_hex") == "01"
        and next_request.get("request_type") == "select_chain"
    )
    rollback_signal_observed = 71 not in message_types
    if not known_unreachable and not rollback_signal_observed:
        raise ValueError("probe follow-up is neither known-unreachable nor a candidate")
    if document.get("rollback_supported") is not rollback_signal_observed:
        raise ValueError("probe rollback_supported does not match raw frames")
    expected_status = (
        "support_candidate" if rollback_signal_observed else "unsupported"
    )
    expected_classification = (
        ACTIVATION_ROLLBACK_SUPPORT_CANDIDATE
        if rollback_signal_observed
        else ACTIVATION_ROLLBACK_UNREACHABLE
    )
    if document.get("status") != expected_status:
        raise ValueError("probe status does not match raw frames")
    if document.get("classification") != expected_classification:
        raise ValueError("probe classification does not match raw frames")
    _non_empty_string(
        next_request.get("request_type"),
        "probe.followup.next_request.request_type",
    )
