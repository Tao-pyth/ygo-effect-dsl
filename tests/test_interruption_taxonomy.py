from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ygo_effect_dsl.engine.bridge import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
)
from ygo_effect_dsl.engine.interruption import (
    INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION,
    InterruptionValidationPolicy,
    classify_interruption_candidates,
)


SOURCE_CARD_CODE = 97268402


def _activation_request(
    *,
    location: int = 0x02,
    phase: str = "main1",
    extra: dict[str, object] | None = None,
) -> DecisionRequest:
    return DecisionRequest(
        request_id="request:chain",
        request_type="select_chain",
        player=1,
        candidates=(
            Candidate(
                candidate_id="chain:veiler",
                kind="effect",
                card_ref={
                    "controller": 1,
                    "location": location,
                    "public_card_id": SOURCE_CARD_CODE,
                    "sequence": 0,
                },
            ),
            Candidate(candidate_id="control:pass", kind="pass"),
        ),
        constraints=DecisionConstraints(),
        context=DecisionContext(phase=phase, extra=extra or {}),
    )


def _response_request(
    *,
    role: str,
    minimum: int = 1,
    maximum: int = 1,
) -> dict[str, object]:
    request_type = "select_option" if role == "option" else "select_card"
    return {
        "request_id": f"request:{role}",
        "request_type": request_type,
        "player": 1,
        "candidates": [
            {
                "candidate_id": f"{role}:0",
                "kind": "option" if role == "option" else "card",
                "card_ref": None,
                "effect_ref": None,
                "payload": {},
            },
            {
                "candidate_id": f"{role}:1",
                "kind": "option" if role == "option" else "card",
                "card_ref": None,
                "effect_ref": None,
                "payload": {},
            },
        ],
        "constraints": {
            "min_selections": minimum,
            "max_selections": maximum,
            "ordered": False,
            "allow_duplicates": False,
            "required": True,
        },
        "context": {
            "phase": "main1",
            "extra": {
                "interruption_role": role,
                "interruption_source": {
                    "card_code": SOURCE_CARD_CODE,
                    "zone": "field",
                },
            },
        },
    }


def test_typed_activation_classifies_only_matching_core_candidate() -> None:
    outcome = classify_interruption_candidates(
        _activation_request(extra={"interruption_target": "targetless"}),
        source_card_code=SOURCE_CARD_CODE,
    )

    assert outcome.supported is True
    assert outcome.status == "supported"
    assert len(outcome.candidates) == 1
    support = outcome.candidates[0]
    assert support.candidate_id == "chain:veiler"
    assert support.source_zone == "hand"
    assert support.activation is True
    assert support.cost is False
    assert support.target == "targetless"
    assert support.option is False
    assert support.validation_categories == ("standard",)
    assert outcome.to_dict()["schema_version"] == (
        INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION
    )


def test_activation_source_player_and_zone_must_match_core_candidate() -> None:
    wrong_player = classify_interruption_candidates(
        _activation_request(),
        source_card_code=SOURCE_CARD_CODE,
        source_player=0,
        source_zone="hand",
    )
    wrong_zone = classify_interruption_candidates(
        _activation_request(),
        source_card_code=SOURCE_CARD_CODE,
        source_player=1,
        source_zone="field",
    )

    assert wrong_player.status == "path_failure"
    assert wrong_zone.status == "path_failure"


@pytest.mark.parametrize(
    ("role", "maximum", "expected"),
    [
        ("cost", 1, {"cost": True, "target": "not_applicable"}),
        ("target", 1, {"cost": False, "target": "single"}),
        ("target", 2, {"cost": False, "target": "multi"}),
        ("option", 1, {"cost": False, "target": "not_applicable"}),
    ],
)
def test_mapping_response_roles_require_explicit_source_binding(
    role: str, maximum: int, expected: dict[str, object]
) -> None:
    outcome = classify_interruption_candidates(
        _response_request(role=role, maximum=maximum),
        source_card_code=SOURCE_CARD_CODE,
    )

    assert outcome.status == "supported"
    assert {candidate.candidate_id for candidate in outcome.candidates} == {
        f"{role}:0",
        f"{role}:1",
    }
    support = outcome.candidates[0]
    assert support.source_zone == "field"
    assert support.cost is expected["cost"]
    assert support.target == expected["target"]
    assert support.option is (role == "option")


def test_candidate_disappearance_is_a_path_failure() -> None:
    outcome = classify_interruption_candidates(
        _activation_request(),
        source_card_code=SOURCE_CARD_CODE,
        expected_candidate_ids=("chain:missing",),
    )

    assert outcome.status == "path_failure"
    assert outcome.supported is False
    assert outcome.diagnostics[0].code == "candidate_disappeared"
    assert outcome.diagnostics[0].candidate_ids == ("chain:missing",)


def test_unknown_and_ambiguous_candidate_shapes_fail_configuration() -> None:
    unknown = _activation_request().to_dict()
    unknown["candidates"][0]["card_ref"] = None
    unknown_outcome = classify_interruption_candidates(
        unknown, source_card_code=SOURCE_CARD_CODE
    )
    assert unknown_outcome.status == "configuration_failure"
    assert unknown_outcome.diagnostics[0].code == "unknown_candidate_shape"

    ambiguous = _activation_request().to_dict()
    ambiguous["candidates"][0]["card_ref"]["code"] = SOURCE_CARD_CODE + 1
    ambiguous_outcome = classify_interruption_candidates(
        ambiguous, source_card_code=SOURCE_CARD_CODE
    )
    assert ambiguous_outcome.status == "configuration_failure"
    assert ambiguous_outcome.diagnostics[0].code == "ambiguous_candidate_source"


@pytest.mark.parametrize(
    ("decision_request", "category"),
    [
        (_activation_request(phase="damage_step"), "damage_step"),
        (
            _activation_request(extra={"simultaneous_trigger": True}),
            "simultaneous_trigger",
        ),
        (_activation_request(extra={"mandatory_trigger": True}), "mandatory_trigger"),
        (_activation_request(extra={"segoc": True}), "segoc"),
    ],
)
def test_unverified_timing_categories_fail_close(
    decision_request: DecisionRequest, category: str
) -> None:
    rejected = classify_interruption_candidates(
        decision_request, source_card_code=SOURCE_CARD_CODE
    )
    assert rejected.status == "unsupported_category"
    assert rejected.diagnostics[0].code == "unverified_fixture_category"

    policy = InterruptionValidationPolicy().register_verified(category)
    accepted = classify_interruption_candidates(
        decision_request,
        source_card_code=SOURCE_CARD_CODE,
        policy=policy,
    )
    assert accepted.status == "supported"
    assert category in accepted.candidates[0].validation_categories


def test_taxonomy_dataclasses_and_policy_are_immutable() -> None:
    base = InterruptionValidationPolicy()
    extended = base.register_verified("damage_step")

    assert base.verified_fixture_categories == frozenset({"standard"})
    assert extended.verified_fixture_categories == frozenset(
        {"standard", "damage_step"}
    )
    assert extended.to_dict()["fail_close_categories"] == [
        "damage_step",
        "mandatory_trigger",
        "segoc",
        "simultaneous_trigger",
    ]
    with pytest.raises(FrozenInstanceError):
        extended.schema_version = "changed"  # type: ignore[misc]


def test_simultaneous_trigger_marker_must_be_boolean() -> None:
    outcome = classify_interruption_candidates(
        _activation_request(extra={"simultaneous_trigger": "yes"}),
        source_card_code=SOURCE_CARD_CODE,
    )

    assert outcome.status == "configuration_failure"
    assert outcome.diagnostics[0].code == "unknown_validation_category"
    assert outcome.diagnostics[0].path.endswith(".simultaneous_trigger")


def test_cost_target_role_is_never_inferred_from_select_card() -> None:
    request = _response_request(role="cost")
    request["context"]["extra"].pop("interruption_role")

    outcome = classify_interruption_candidates(
        request, source_card_code=SOURCE_CARD_CODE
    )

    assert outcome.status == "configuration_failure"
    assert outcome.diagnostics[0].code == "unknown_candidate_shape"
