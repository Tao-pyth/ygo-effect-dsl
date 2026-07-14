from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.information import (
    AccessDecision,
    DeckOrderKnowledge,
    InformationAccessAudit,
    InformationAccessPolicy,
    InformationField,
    InformationLeakError,
    OpeningHandPolicy,
    build_opening_hand_sampling_reference,
)
from ygo_effect_dsl.engine.state import InformationMode
from ygo_effect_dsl.experiment import load_experiment_document


def test_complete_information_with_known_order_allows_private_access() -> None:
    policy = InformationAccessPolicy(
        information_mode=InformationMode.COMPLETE_INFORMATION,
        deck_order=DeckOrderKnowledge.KNOWN,
        opening_hand=OpeningHandPolicy.FIXED,
    )
    audit = InformationAccessAudit(policy)

    audit.require(
        InformationField.HAND_IDENTITY,
        owner=1,
        purpose="complete-information evaluator",
    )
    audit.require(
        InformationField.DECK_ORDER,
        owner=1,
        purpose="deterministic replay",
    )

    assert audit.to_dict()["leak_count"] == 0


def test_player_view_unknown_order_detects_private_information_leaks() -> None:
    policy = InformationAccessPolicy(
        information_mode=InformationMode.PLAYER_VIEW,
        viewer=0,
        deck_order=DeckOrderKnowledge.UNKNOWN,
        opening_hand=OpeningHandPolicy.NATURAL,
    )
    audit = InformationAccessAudit(policy)

    assert audit.record(
        InformationField.HAND_IDENTITY,
        owner=0,
        purpose="own hand evaluation",
    ) == AccessDecision.ALLOWED
    assert audit.record(
        InformationField.HAND_IDENTITY,
        owner=1,
        purpose="deck performance evaluator",
    ) == AccessDecision.DENIED_PRIVATE_OWNER
    assert audit.record(
        InformationField.DECK_ORDER,
        owner=0,
        purpose="future draw evaluator",
    ) == AccessDecision.DENIED_UNKNOWN_DECK_ORDER

    report = audit.to_dict()
    assert report["schema_version"] == "information-audit-v1"
    assert report["leak_count"] == 2
    assert report["policy"]["schema_version"] == "information-policy-v1"
    assert report["policy"]["policy_id"].startswith("infopol_")
    assert {leak["decision"] for leak in report["leaks"]} == {
        "denied_private_owner",
        "denied_unknown_deck_order",
    }
    with pytest.raises(InformationLeakError, match="forbidden access"):
        audit.assert_no_leaks()


def test_sampled_distribution_requires_and_records_sampling_reference() -> None:
    sampling_reference = build_opening_hand_sampling_reference(
        seed=7,
        candidates=[
            {
                "hands_by_player": {"1": [14558127]},
                "weight": 1,
            }
        ],
    )
    policy = InformationAccessPolicy(
        information_mode=InformationMode.SAMPLED_PRIVATE_STATE,
        deck_order=DeckOrderKnowledge.UNKNOWN,
        opening_hand=OpeningHandPolicy.PROBABILITY_DISTRIBUTION,
        sampling_reference=sampling_reference,
    )
    audit = InformationAccessAudit(policy)

    audit.require(
        InformationField.HAND_IDENTITY,
        owner=1,
        purpose="sampled opponent hand",
    )
    audit.require(
        InformationField.PROBABILITY_DISTRIBUTION,
        owner=None,
        purpose="opening hand probability",
    )

    assert audit.to_dict()["policy"]["sampling_reference"]["seed"] == 7
    assert policy.decide(InformationField.DECK_ORDER, 0) == (
        AccessDecision.DENIED_UNKNOWN_DECK_ORDER
    )


@pytest.mark.parametrize(
    "sampling_reference",
    [
        {},
        {
            "schema_version": "opening-hand-sampling-v1",
            "sampler_id": "stable-digest-mod-v1",
            "seed": 7,
            "sampled_owners": [1],
            "candidates": [
                {"hands_by_player": {"1": [14558127]}, "weight": 1}
            ],
            "sampling_policy_id": "handsampol_tampered",
        },
    ],
)
def test_sampled_policy_rejects_invalid_sampling_reference(
    sampling_reference: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="sampling_reference"):
        InformationAccessPolicy(
            information_mode=InformationMode.SAMPLED_PRIVATE_STATE,
            deck_order=DeckOrderKnowledge.UNKNOWN,
            opening_hand=OpeningHandPolicy.PROBABILITY_DISTRIBUTION,
            sampling_reference=sampling_reference,
        )


def test_information_policy_is_constructed_from_experiment() -> None:
    experiment = load_experiment_document(
        "examples/experiments/real_core_effect_veiler.yaml"
    )
    policy = InformationAccessPolicy.from_experiment(experiment)

    assert policy.information_mode == InformationMode.COMPLETE_INFORMATION
    assert policy.deck_order == DeckOrderKnowledge.KNOWN
    assert policy.opening_hand == OpeningHandPolicy.FIXED
    assert experiment["information_policy"] == policy.to_experiment_dict()


def test_distribution_policy_without_sampling_reference_is_invalid() -> None:
    with pytest.raises(ValueError, match="sampling_reference"):
        InformationAccessPolicy(
            information_mode=InformationMode.COMPLETE_INFORMATION,
            deck_order=DeckOrderKnowledge.UNKNOWN,
            opening_hand=OpeningHandPolicy.PROBABILITY_DISTRIBUTION,
        )
