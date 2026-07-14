from __future__ import annotations

import json
from pathlib import Path

import pytest

from ygo_effect_dsl.external.licensing import (
    DistributionPolicyError,
    assert_release_bundle_allowed,
    load_distribution_policy,
)
from ygo_effect_dsl.external.ocgcore import load_ocgcore_asset_lock, load_ocgcore_lock


def test_distribution_policy_matches_pinned_dependency_licenses() -> None:
    policy = load_distribution_policy()
    core_lock = load_ocgcore_lock()
    asset_lock = load_ocgcore_asset_lock()

    assert policy.policy_id == "prototype-local-only-v1"
    assert policy.artifacts["ocgcore"]["license"] == core_lock.source["license"]
    assert policy.artifacts["card_scripts"]["license"] == (
        asset_lock.repositories["card_scripts"]["license"]
    )
    assert policy.artifacts["card_database"]["license"] == (
        asset_lock.repositories["card_database"]["license"]
    )


def test_distribution_policy_keeps_all_third_party_payloads_out_of_releases() -> None:
    policy = load_distribution_policy()

    assert policy.data["project"] == {
        "license": "NOASSERTION",
        "release_status": "blocked",
        "reason": (
            "The repository has no root LICENSE file. Publishing source does not "
            "establish an express reuse grant."
        ),
    }
    assert all(
        artifact["include_in_release"] is False
        for artifact in policy.artifacts.values()
    )
    assert policy.artifacts["card_database"]["commercial_bundle_status"] == "blocked"
    assert policy.data["controls"]["external_files_location"] == "user_cache_only"


def test_release_gate_fails_closed_even_for_an_empty_bundle() -> None:
    with pytest.raises(DistributionPolicyError, match="project has no approved"):
        assert_release_bundle_allowed([])


def test_policy_rejects_accidental_release_enablement(tmp_path: Path) -> None:
    policy = load_distribution_policy()
    changed = json.loads(json.dumps(policy.data))
    changed["artifacts"]["ocgcore"]["include_in_release"] = True
    path = tmp_path / "distribution-policy.json"
    path.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(DistributionPolicyError, match="cannot be release-enabled"):
        load_distribution_policy(path)
