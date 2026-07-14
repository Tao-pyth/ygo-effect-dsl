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
    pending = {
        "damage_step": (1, 207),
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
    assert set(runtime_policy["fail_close_categories"]) == set(pending)
    assert runtime_policy["verified_fixture_categories"] == ["standard"]
