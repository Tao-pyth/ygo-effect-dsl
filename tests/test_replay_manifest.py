from __future__ import annotations

from copy import deepcopy

import pytest

from ygo_effect_dsl.engine.replay import (
    ReplayEnvironmentMismatchError,
    ReplayFormatError,
    ReplayHistoryV03a,
    ReplayManifestIncompleteError,
    ReplayManifestV03a,
    assert_manifest_matches,
    first_manifest_difference,
)
from ygo_effect_dsl.engine.replay.manifest import RANDOM_TRACE_POLICY


def _manifest(*, binary_sha256: str = "a" * 64) -> ReplayManifestV03a:
    return ReplayManifestV03a(
        environment={
            "project": {
                "replay_schema": "0.3a",
                "bridge_protocol": "ocgcore-api-11.0",
                "snapshot_schema": "ocgcore-query-v1",
            },
            "core": {
                "api": "11.0",
                "lock_id": "core-lock",
                "source_commit": "core-commit",
                "binary_sha256": binary_sha256,
                "custom_patches": [],
            },
            "assets": {
                "lock_id": "asset-lock",
                "card_scripts_commit": "scripts-commit",
                "card_database_commit": "database-commit",
                "constant_sha256": "b" * 64,
                "utility_sha256": "c" * 64,
                "database_sha256": "d" * 64,
            },
            "instrumentation": {
                "direct_random_trace": {
                    "enabled": True,
                    "schema_version": "ocgcore-direct-random-trace-v1",
                    "script_sha256": "e" * 64,
                }
            },
        },
        randomness={
            "core_seed": [1, 2, 3, 4],
            "python_random_used": False,
            "python_seed": None,
            "trace_policy": RANDOM_TRACE_POLICY,
        },
        rules={
            "duel_flags": 0,
            "master_rule": "flags:0",
            "forbidden_limited_list": "none",
            "unsafe_lua_libraries": False,
        },
        initial_conditions={
            "snapshot_hash": "state_initial",
            "snapshot_kind": "complete_information",
            "starting_player": 0,
            "deck_order_in_snapshot": True,
        },
    )


def _sampled_private_state_manifest() -> ReplayManifestV03a:
    complete = _manifest()
    return ReplayManifestV03a(
        environment=complete.environment,
        randomness={
            **complete.randomness,
            "opening_hand_sampling": {
                "schema_version": "opening-hand-sampling-v1",
                "sampler_id": "stable-digest-mod-v1",
                "seed": 0,
                "sampling_policy_id": "handsampol_fixture",
                "information_policy_id": "infopol_fixture",
                "selected_index": 0,
                "result": {"hands_by_player": {"0": [100], "1": [200]}},
                "sample_id": "handsample_fixture",
            },
        },
        rules=complete.rules,
        initial_conditions={
            **complete.initial_conditions,
            "snapshot_kind": "sampled_private_state",
            "opening_hand_kind": "probability_distribution",
        },
    )


def test_complete_manifest_is_versioned_hashed_and_reproducible() -> None:
    manifest = _manifest()
    manifest.assert_reproducible()
    payload = manifest.to_dict()

    assert payload["reproducible"] is True
    assert payload["missing_requirements"] == []
    assert payload["manifest_hash"].startswith("manifest_")
    assert ReplayManifestV03a.from_dict(payload).to_dict() == payload


def test_sampled_private_state_manifest_with_sampling_evidence_is_reproducible() -> None:
    manifest = _sampled_private_state_manifest()

    manifest.assert_reproducible()

    assert manifest.reproducible is True
    assert manifest.missing_requirements == ()


@pytest.mark.parametrize(
    "missing_path",
    (
        "randomness.opening_hand_sampling.schema_version",
        "randomness.opening_hand_sampling.sampler_id",
        "randomness.opening_hand_sampling.seed",
        "randomness.opening_hand_sampling.sampling_policy_id",
        "randomness.opening_hand_sampling.information_policy_id",
        "randomness.opening_hand_sampling.selected_index",
        "randomness.opening_hand_sampling.result.hands_by_player",
        "randomness.opening_hand_sampling.sample_id",
        "initial_conditions.opening_hand_kind",
    ),
)
def test_sampled_private_state_manifest_missing_sampling_evidence_fails_closed(
    missing_path: str,
) -> None:
    payload = _sampled_private_state_manifest().to_identity_dict()
    current = payload
    for part in missing_path.split(".")[:-1]:
        current = current[part]
    del current[missing_path.rsplit(".", maxsplit=1)[-1]]

    manifest = ReplayManifestV03a.from_dict(payload)

    assert manifest.reproducible is False
    assert missing_path in manifest.missing_requirements


def test_missing_required_version_or_used_python_seed_fails_closed() -> None:
    payload = _manifest().to_dict()
    del payload["environment"]["assets"]["card_database_commit"]
    payload.pop("manifest_hash")
    incomplete = ReplayManifestV03a.from_dict(payload)

    with pytest.raises(
        ReplayManifestIncompleteError, match="card_database_commit"
    ):
        incomplete.assert_reproducible()

    random_payload = _manifest().to_dict()
    random_payload["randomness"]["python_random_used"] = True
    random_payload.pop("manifest_hash")
    with pytest.raises(ReplayManifestIncompleteError, match="python_seed"):
        ReplayManifestV03a.from_dict(random_payload).assert_reproducible()

    trace_payload = _manifest().to_dict()
    del trace_payload["randomness"]["trace_policy"]
    trace_payload.pop("manifest_hash")
    with pytest.raises(ReplayManifestIncompleteError, match="trace_policy"):
        ReplayManifestV03a.from_dict(trace_payload).assert_reproducible()


def test_manifest_comparison_reports_first_environment_difference() -> None:
    recorded = _manifest(binary_sha256="a" * 64)
    current = _manifest(binary_sha256="f" * 64)

    difference = first_manifest_difference(recorded, current)
    assert difference is not None
    assert difference.path == "environment.core.binary_sha256"
    with pytest.raises(
        ReplayEnvironmentMismatchError,
        match="environment.core.binary_sha256",
    ):
        assert_manifest_matches(recorded, current)


def test_manifest_identity_reports_direct_random_instrumentation_difference() -> None:
    recorded_payload = _manifest().to_dict()
    current_payload = deepcopy(recorded_payload)
    current_payload.pop("manifest_hash")
    current_payload["environment"]["instrumentation"]["direct_random_trace"][
        "enabled"
    ] = False
    recorded = ReplayManifestV03a.from_dict(recorded_payload)
    current = ReplayManifestV03a.from_dict(current_payload)

    difference = first_manifest_difference(recorded, current)

    assert difference is not None
    assert difference.path == (
        "environment.instrumentation.direct_random_trace.enabled"
    )


def test_manifest_hash_and_initial_snapshot_tampering_are_rejected() -> None:
    payload = deepcopy(_manifest().to_dict())
    payload["rules"]["duel_flags"] = 1
    with pytest.raises(ReplayFormatError, match="manifest hash"):
        ReplayManifestV03a.from_dict(payload)

    with pytest.raises(ReplayFormatError, match="initial snapshot hash"):
        ReplayHistoryV03a(
            initial_snapshot={"state_hash": "state_other"},
            version_metadata={},
            events=(),
            manifest=_manifest(),
        )
