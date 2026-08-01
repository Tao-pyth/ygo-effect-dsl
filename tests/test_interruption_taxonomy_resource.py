from __future__ import annotations

import importlib.resources
import json

from ygo_effect_dsl.engine.interruption import InterruptionValidationPolicy


def test_bundled_interruption_taxonomy_fails_closed_for_unverified_categories() -> None:
    resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
        "interruption-support-taxonomy-v1.json"
    )
    document = json.loads(resource.read_text(encoding="utf-8"))

    assert document["schema_version"] == "interruption-support-taxonomy-v1"
    assert document["rules"]["candidate_authority"] == "ocgcore_decision_request_only"
    assert document["rules"]["effect_inference"] is False
    assert document["validation_categories"]["standard"]["production_claim"] == (
        "fixed_fixture_scope_only"
    )
    assert document["validation_categories"]["damage_step"] == {
        "status": "verified_fixture_category",
        "default": False,
        "production_claim": "pinned_fixture_scope_only",
        "priority": 1,
        "evidence": [
            "damagestepev_3158b0ba058fbd5763a95656db85f71f98e1fc28c395dfa180a3d58fa5d02a16"
        ],
        "follow_up_issue": 207,
    }
    pending = {
        "simultaneous_trigger": (2, 208),
        "mandatory_trigger": (3, 209),
        "segoc": (4, 210),
    }
    for category, (priority, issue_number) in pending.items():
        assert document["validation_categories"][category] == {
            "status": "fail_close_pending_fixture",
            "default": False,
            "production_claim": "prohibited",
            "priority": priority,
            "follow_up_issue": issue_number,
        }
    assert document["fixture_promotion_requirements"] == [
        "pinned_core_api_source_and_asset_hashes",
        "fresh_real_core_replay_two_repetitions",
        "route_and_state_lineage",
        "decision_candidate_and_action_response_evidence",
        "tamper_detecting_validator",
        "no_python_effect_legality_or_timing_inference",
    ]
    assert document["rules"]["unverified_fixture_category"] == (
        "unsupported_category"
    )
    runtime_policy = InterruptionValidationPolicy().to_dict()
    assert set(runtime_policy["fail_close_categories"]) == {
        "damage_step",
        *pending,
    }
    assert runtime_policy["verified_fixture_categories"] == ["standard"]
