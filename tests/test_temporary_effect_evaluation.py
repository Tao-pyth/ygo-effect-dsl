from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.evaluation import (
    BoundaryEvidence,
    EvaluationValueComponent,
    ValuePermanence,
    assert_valid_temporary_modifier_observation,
    assert_valid_temporary_effect_report,
    build_temporary_modifier_observation,
    build_temporary_effect_report,
)
from ygo_effect_dsl.engine.state import (
    ConstraintExpiration,
    ExpirationBoundary,
    StateCoordinate,
)


def _expiration() -> ConstraintExpiration:
    return ConstraintExpiration(
        ExpirationBoundary.END_OF_TURN,
        turn=1,
    )


def test_expired_and_unverified_temporary_values_are_excluded() -> None:
    components = (
        EvaluationValueComponent(
            component_id="field:persistent",
            metric="field_value",
            value=2,
            permanence=ValuePermanence.PERSISTENT,
            source_ref={"state_hash": "state_after"},
        ),
        EvaluationValueComponent(
            component_id="atk:active",
            metric="field_value",
            value=100,
            permanence=ValuePermanence.TEMPORARY,
            expires_at=ConstraintExpiration(
                ExpirationBoundary.END_OF_TURN,
                turn=2,
            ),
            boundary_evidence=BoundaryEvidence.OBSERVED_ACTIVE,
        ),
        EvaluationValueComponent(
            component_id="atk:expired",
            metric="field_value",
            value=1000,
            permanence=ValuePermanence.TEMPORARY,
            expires_at=_expiration(),
            boundary_evidence=BoundaryEvidence.OBSERVED_EXPIRED,
        ),
        EvaluationValueComponent(
            component_id="protection:unknown",
            metric="protection",
            value=1,
            permanence=ValuePermanence.TEMPORARY,
            expires_at=_expiration(),
            boundary_evidence=BoundaryEvidence.UNVERIFIED,
        ),
    )

    report = build_temporary_effect_report(
        components,
        evaluation_boundary=StateCoordinate(turn=2, phase="main1"),
    )

    assert report["values"]["field_value"] == {
        "durable": 102,
        "excluded_temporary": 1000,
        "raw": 1102,
    }
    assert report["values"]["protection"] == {
        "durable": 0,
        "excluded_temporary": 1,
        "raw": 1,
    }
    prevention = report["overvaluation_prevention"]
    assert prevention["applied"] is True
    assert prevention["excluded_component_ids"] == [
        "atk:expired",
        "protection:unknown",
    ]
    assert prevention["unverified_component_ids"] == ["protection:unknown"]
    assert {item["code"] for item in report["explanations"]} == {
        "expired_before_evaluation_boundary",
        "unverified_at_evaluation_boundary",
    }
    assert_valid_temporary_effect_report(report)


def test_temporary_report_rejects_tampered_durable_value() -> None:
    report = build_temporary_effect_report(
        (
            EvaluationValueComponent(
                component_id="atk:expired",
                metric="attack",
                value=500,
                permanence=ValuePermanence.TEMPORARY,
                expires_at=_expiration(),
                boundary_evidence=BoundaryEvidence.OBSERVED_EXPIRED,
            ),
        ),
        evaluation_boundary=StateCoordinate(turn=2, phase="main1"),
    )
    report["values"]["attack"]["durable"] = 500

    with pytest.raises(ValueError, match="does not match"):
        assert_valid_temporary_effect_report(report)


def test_temporary_value_requires_expiration() -> None:
    with pytest.raises(ValueError, match="requires expires_at"):
        EvaluationValueComponent(
            component_id="atk:temporary",
            metric="attack",
            value=500,
            permanence=ValuePermanence.TEMPORARY,
        )


def test_query_transition_and_reset_source_prove_expiration() -> None:
    observation = build_temporary_modifier_observation(
        component_id="attack:fixture",
        modifier_kind="attack_delta",
        metric="attack",
        baseline={"state_hash": "state_before", "value": 0},
        active={"state_hash": "state_active", "value": 500},
        expired={"state_hash": "state_after", "value": 0},
        expiration=_expiration(),
        source_ref={
            "reset_expression": "RESET_PHASE+PHASE_END",
            "script_sha256": "sha256_fixture",
        },
    )

    assert observation["boundary_evidence"] == "observed_expired"
    assert observation["transition"] == {
        "activated": True,
        "active_delta": 500,
        "expired_delta": 0,
        "returned_to_baseline": True,
    }
    assert_valid_temporary_modifier_observation(observation)


def test_query_transition_without_return_to_baseline_is_unverified() -> None:
    observation = build_temporary_modifier_observation(
        component_id="attack:fixture",
        modifier_kind="attack_delta",
        metric="attack",
        baseline={"state_hash": "state_before", "value": 0},
        active={"state_hash": "state_active", "value": 500},
        expired={"state_hash": "state_after", "value": 500},
        expiration=_expiration(),
        source_ref={"reset_expression": "unavailable"},
    )

    assert observation["boundary_evidence"] == "unverified"
    component = EvaluationValueComponent(
        component_id="attack:fixture",
        metric="attack",
        value=500,
        permanence=ValuePermanence.TEMPORARY,
        expires_at=_expiration(),
        boundary_evidence=BoundaryEvidence.UNVERIFIED,
    )
    report = build_temporary_effect_report(
        (component,), evaluation_boundary=StateCoordinate(turn=2, phase="main1")
    )
    assert report["values"]["attack"]["durable"] == 0
