from __future__ import annotations

import importlib.resources
import json


def test_bundled_interruption_taxonomy_fails_closed_for_unverified_categories() -> None:
    resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
        "interruption-support-taxonomy-v1.json"
    )
    document = json.loads(resource.read_text(encoding="utf-8"))

    assert document["schema_version"] == "interruption-support-taxonomy-v1"
    assert document["rules"]["candidate_authority"] == "ocgcore_decision_request_only"
    assert document["rules"]["effect_inference"] is False
    for category in ("damage_step", "mandatory_trigger", "segoc"):
        assert document["validation_categories"][category] == {
            "status": "fail_close_pending_fixture",
            "default": False,
        }
