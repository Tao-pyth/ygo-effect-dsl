"""Replay baseline for deterministic action history storage."""

from ygo_effect_dsl.engine.replay.errors import (
    ReplayEnvironmentMismatchError,
    ReplayFormatError,
    ReplayManifestIncompleteError,
    ReplaySignatureMismatchError,
)
from ygo_effect_dsl.engine.replay.manifest import (
    REPLAY_MANIFEST_SCHEMA_VERSION,
    ReplayManifestDifference,
    ReplayManifestV03a,
    assert_manifest_matches,
    first_manifest_difference,
)
from ygo_effect_dsl.engine.replay.io_trace import (
    assert_complete_io_trace,
    build_scripted_output_trace,
)
from ygo_effect_dsl.engine.replay.models import ActionRecord, ReplayHistory
from ygo_effect_dsl.engine.replay.serializer import dumps_replay, load_replay, loads_replay, save_replay
from ygo_effect_dsl.engine.replay.v03a import (
    ACTION_OCCURRENCE_SCHEMA_VERSION,
    ReplayEventV03a,
    ReplayHistoryV03a,
    build_action_occurrence_id,
)
from ygo_effect_dsl.engine.replay.verifier import (
    RequestDifference,
    assert_replay_request_signatures,
    first_canonical_difference,
    first_request_difference,
    request_signature_identity,
)

__all__ = [
    "ActionRecord",
    "ACTION_OCCURRENCE_SCHEMA_VERSION",
    "ReplayFormatError",
    "ReplayEnvironmentMismatchError",
    "ReplayHistory",
    "ReplayEventV03a",
    "ReplayHistoryV03a",
    "ReplayManifestDifference",
    "ReplayManifestIncompleteError",
    "ReplayManifestV03a",
    "REPLAY_MANIFEST_SCHEMA_VERSION",
    "ReplaySignatureMismatchError",
    "RequestDifference",
    "assert_replay_request_signatures",
    "assert_manifest_matches",
    "assert_complete_io_trace",
    "build_action_occurrence_id",
    "build_scripted_output_trace",
    "dumps_replay",
    "first_canonical_difference",
    "first_manifest_difference",
    "first_request_difference",
    "load_replay",
    "loads_replay",
    "request_signature_identity",
    "save_replay",
]
