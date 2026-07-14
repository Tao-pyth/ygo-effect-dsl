from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import build_real_core_route, verify_real_core_route
from ygo_effect_dsl.route_dsl import validate_route_document


EXPERIMENTS = Path(__file__).parents[1] / "examples" / "experiments"
SAMPLED_EXPERIMENTS = {
    name: EXPERIMENTS / f"real_core_interruption_matrix_sampled_{name}.yaml"
    for name in ("control", "targetless")
}


@pytest.fixture(scope="module")
def sampled_routes() -> dict[str, dict[str, Any]]:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    return {
        name: build_real_core_route(experiment=load_experiment_document(path))
        for name, path in SAMPLED_EXPERIMENTS.items()
    }


def test_sampled_hidden_hand_is_reproducible_and_independent_from_interruption(
    sampled_routes: dict[str, dict[str, Any]],
) -> None:
    control = sampled_routes["control"]
    interrupted = sampled_routes["targetless"]

    assert control["route_id"] == (
        "route_da4cb53e6394eaf1889f69a3e9fc08e8e7c425586bf765ad9015b7ab6f91ab0f"
    )
    assert interrupted["route_id"] == (
        "route_bfeddc3740c6172b11ac16d24c1db27aa655998e31de8394733c4f1796813655"
    )
    assert interrupted["lineage"] == {
        "fork_step": 5,
        "parent_route_id": control["route_id"],
    }

    for route in (control, interrupted):
        manifest = route["replay"]["manifest"]
        opening_sample = manifest["randomness"]["opening_hand_sampling"]
        assert manifest["randomness"]["interruption_sampling"] is None
        assert opening_sample["seed"] == 20260714
        assert opening_sample["selected_index"] == 0
        assert opening_sample["result"]["hands_by_player"] == {
            "1": [14558127, 27204311, 73642296]
        }
        assert opening_sample["sampling_policy_id"] == (
            "handsampol_cd5607267725cd1baa1c2a4ae1c0c8eabdb837fea227b11d8c150dbc8d3248f4"
        )
        assert opening_sample["sample_id"] == (
            "handsample_620208ec16527e3c45f61c82a7cbc95c6b7d8027ba04ff67bdc2036b0cee8d6e"
        )


def test_sampled_policy_manifest_state_identity_and_audit_are_linked(
    sampled_routes: dict[str, dict[str, Any]],
) -> None:
    route = sampled_routes["targetless"]
    policy = route["information_audit"]["policy"]
    manifest = route["replay"]["manifest"]
    state_identity = route["replay"]["initial_snapshot"]["state_identity"]
    accesses = route["information_audit"]["accesses"]

    assert policy["information_mode"] == "sampled_private_state"
    assert manifest["initial_conditions"]["snapshot_kind"] == (
        "sampled_private_state"
    )
    assert manifest["initial_conditions"]["deck_order_in_snapshot"] is False
    assert state_identity["information_mode"] == "sampled_private_state"
    assert state_identity["sampling_reference"] == policy["sampling_reference"]
    assert accesses[0]["field"] == "probability_distribution"
    assert all(access["decision"] == "allowed" for access in accesses)
    assert route["information_audit"]["leak_count"] == 0


def test_validator_rejects_tampered_sampled_opening_hand_result(
    sampled_routes: dict[str, dict[str, Any]],
) -> None:
    tampered = deepcopy(sampled_routes["targetless"])
    tampered["replay"]["manifest"]["randomness"]["opening_hand_sampling"][
        "result"
    ]["hands_by_player"]["1"] = [14558127]

    assert "sampled_opening_hand_result_mismatch" in {
        issue.code for issue in validate_route_document(tampered)
    }


@pytest.mark.parametrize("field", ["selected_index", "sample_id"])
def test_validator_recomputes_opening_hand_sampling_evidence(
    sampled_routes: dict[str, dict[str, Any]],
    field: str,
) -> None:
    tampered = deepcopy(sampled_routes["targetless"])
    evidence = tampered["replay"]["manifest"]["randomness"][
        "opening_hand_sampling"
    ]
    evidence[field] = 1 if field == "selected_index" else "handsample_tampered"

    assert "opening_hand_sampling_evidence_mismatch" in {
        issue.code for issue in validate_route_document(tampered)
    }


def test_validator_rejects_state_mode_and_audit_decision_tampering(
    sampled_routes: dict[str, dict[str, Any]],
) -> None:
    state_tampered = deepcopy(sampled_routes["targetless"])
    state_tampered["replay"]["initial_snapshot"]["state_identity"][
        "information_mode"
    ] = "complete_information"
    assert "information_state_mode_mismatch" in {
        issue.code for issue in validate_route_document(state_tampered)
    }

    audit_tampered = deepcopy(sampled_routes["targetless"])
    audit = audit_tampered["information_audit"]
    audit["accesses"][0]["decision"] = "denied_distribution_not_configured"
    audit_identity = to_canonical_data(
        {
            key: audit[key]
            for key in ("accesses", "leak_count", "leaks", "policy", "schema_version")
        }
    )
    audit["audit_id"] = stable_digest(audit_identity, prefix="infoaudit_")
    assert "information_access_decision_mismatch" in {
        issue.code for issue in validate_route_document(audit_tampered)
    }


def test_sampled_route_matches_fresh_real_core_worker(
    sampled_routes: dict[str, dict[str, Any]],
) -> None:
    verification = verify_real_core_route(sampled_routes["targetless"])

    assert verification.route_id == sampled_routes["targetless"]["route_id"]
    assert verification.event_count == len(
        sampled_routes["targetless"]["replay"]["events"]
    )
