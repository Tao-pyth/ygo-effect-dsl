from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ygo_effect_dsl.route_dsl import load_route_document
from ygo_effect_dsl.spikes.temporary_modifier_evidence import (
    build_temporary_modifier_evidence,
    run_checked_temporary_modifier_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ATTACK_ROUTE = (
    REPO_ROOT / "examples" / "prototype" / "real_core_temporary_atk.route.yaml"
)
NEGATE_ROUTE = (
    REPO_ROOT
    / "examples"
    / "prototype"
    / "real_core_effect_veiler_interrupted.route.yaml"
)


def test_checked_routes_prove_temporary_modifiers_expire() -> None:
    evidence = run_checked_temporary_modifier_evidence(repo_root=REPO_ROOT)

    assert evidence["evidence_id"].startswith("tempevidence_")
    assert evidence["proofs"]["temporary_attack"]["transition"] == {
        "activated": True,
        "active_delta": 500,
        "expired_delta": 0,
        "returned_to_baseline": True,
    }
    assert evidence["proofs"]["effect_negate"]["durable_evaluation"] == {
        "durable": 0,
        "excluded_temporary": 1,
        "raw": 1,
    }


def test_evidence_rejects_modifier_that_does_not_return_to_baseline() -> None:
    attack_route = load_route_document(ATTACK_ROUTE)
    negate_route = load_route_document(NEGATE_ROUTE)
    tampered = deepcopy(attack_route)
    observation = tampered["result"]["temporary_modifier_observation"]
    observation["points"]["expired"]["value"] = 500

    with pytest.raises(ValueError, match="does not match its points"):
        build_temporary_modifier_evidence(
            attack_route=tampered,
            effect_negate_route=negate_route,
        )
