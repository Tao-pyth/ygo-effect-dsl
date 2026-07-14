from __future__ import annotations

from copy import deepcopy

import pytest

from ygo_effect_dsl.engine.bridge import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
)
from ygo_effect_dsl.engine.interruption import (
    CoreInterruptionCandidatePolicy,
    CoreInterruptionStep,
    InterruptionCandidatePolicyError,
)


def _request(
    request_type: str,
    candidates: tuple[Candidate, ...],
    *,
    player: int = 1,
    min_selections: int = 1,
    max_selections: int = 1,
) -> DecisionRequest:
    return DecisionRequest(
        request_id=f"request:{request_type}",
        request_type=request_type,
        player=player,
        candidates=candidates,
        constraints=DecisionConstraints(
            min_selections=min_selections,
            max_selections=max_selections,
        ),
        context=DecisionContext(),
    )


def _policy_document() -> dict[str, object]:
    return {
        "schema_version": "core-interruption-candidate-policy-v1",
        "activation": {
            "role": "activation",
            "request_type": "select_chain",
            "player": 1,
            "selection_count": 1,
            "selector": {
                "kind": "effect",
                "card_ref": {
                    "controller": 1,
                    "location": 2,
                    "public_card_id": 97268402,
                },
            },
        },
        "responses": [
            {
                "role": "target",
                "request_type": "select_card",
                "player": 1,
                "selection_count": 1,
                "selector": {
                    "card_ref": {
                        "controller": 0,
                        "location": 4,
                        "public_card_id": 14558127,
                    }
                },
            }
        ],
    }


def test_versioned_policy_selects_only_core_exposed_candidates() -> None:
    policy = CoreInterruptionCandidatePolicy.from_dict(_policy_document())
    activate = Candidate(
        candidate_id="effect:veiler",
        kind="effect",
        card_ref={
            "controller": 1,
            "location": 2,
            "public_card_id": 97268402,
            "sequence": 0,
        },
        effect_ref={"description": 123},
    )
    pass_candidate = Candidate(candidate_id="control:pass", kind="control")
    target = Candidate(
        candidate_id="card:primary",
        kind="card",
        card_ref={
            "controller": 0,
            "location": 4,
            "public_card_id": 14558127,
            "sequence": 0,
        },
    )

    assert policy.activation.select(
        _request("select_chain", (pass_candidate, activate)),
        path="$.definition.activation",
    ) == (activate,)
    assert policy.responses[0].select(
        _request("select_card", (target,)),
        path="$.definition.responses[0]",
    ) == (target,)
    assert policy.policy_id.startswith("intpolicy_")


def test_policy_supports_targetless_and_multi_target_core_requests() -> None:
    targetless_document = _policy_document()
    targetless_document["responses"] = []
    targetless = CoreInterruptionCandidatePolicy.from_dict(targetless_document)
    assert targetless.responses == ()

    multi_document = _policy_document()
    multi_document["responses"][0]["selection_count"] = 2
    multi_document["responses"][0]["selector"]["card_ref"].pop(
        "public_card_id"
    )
    multi = CoreInterruptionCandidatePolicy.from_dict(multi_document)
    first = Candidate(
        candidate_id="card:1",
        kind="card",
        card_ref={"controller": 0, "location": 4, "public_card_id": 1},
    )
    second = Candidate(
        candidate_id="card:2",
        kind="card",
        card_ref={"controller": 0, "location": 4, "public_card_id": 2},
    )

    selected = multi.responses[0].select(
        _request(
            "select_card",
            (second, first),
            min_selections=2,
            max_selections=2,
        ),
        path="$.definition.responses[0]",
    )
    assert [candidate.candidate_id for candidate in selected] == ["card:1", "card:2"]


@pytest.mark.parametrize("role", ["cost", "target", "option", "placement"])
def test_response_roles_are_data_not_card_specific_branches(role: str) -> None:
    document = _policy_document()
    document["responses"][0]["role"] = role

    policy = CoreInterruptionCandidatePolicy.from_dict(document)

    assert policy.responses[0].role == role


def test_candidate_ambiguity_and_request_mismatch_fail_with_definition_path() -> None:
    policy = CoreInterruptionCandidatePolicy.from_dict(_policy_document())
    matching = Candidate(
        candidate_id="effect:veiler:0",
        kind="effect",
        card_ref={"controller": 1, "location": 2, "public_card_id": 97268402},
    )
    duplicate = deepcopy(matching)
    object.__setattr__(duplicate, "candidate_id", "effect:veiler:1")

    with pytest.raises(
        InterruptionCandidatePolicyError,
        match=r"\$\.interruption\.definitions\[0\]\.candidate_policy\.activation",
    ) as captured:
        policy.activation.select(
            _request("select_chain", (matching, duplicate)),
            path="$.interruption.definitions[0].candidate_policy.activation",
        )
    assert captured.value.context["matching_candidate_ids"] == [
        "effect:veiler:0",
        "effect:veiler:1",
    ]

    with pytest.raises(InterruptionCandidatePolicyError, match="expected request_type"):
        policy.activation.select(
            _request("select_card", (matching,)),
            path="$.interruption.definitions[0].candidate_policy.activation",
        )


def test_policy_rejects_unknown_fields_and_unsupported_roles() -> None:
    unknown = _policy_document()
    unknown["activation"]["selector"]["python_rule"] = "guess-legality"
    with pytest.raises(InterruptionCandidatePolicyError, match="python_rule"):
        CoreInterruptionCandidatePolicy.from_dict(unknown)

    unsupported = _policy_document()
    unsupported["responses"][0]["role"] = "card_specific_resolution"
    with pytest.raises(InterruptionCandidatePolicyError, match="must be one of"):
        CoreInterruptionCandidatePolicy.from_dict(unsupported)


def test_legacy_effect_veiler_policy_is_a_generic_targeted_policy() -> None:
    policy = CoreInterruptionCandidatePolicy.targeted_hand_activation(
        source_player=1,
        source_card_code=97268402,
        target_player=0,
        target_card_code=14558127,
    )

    assert policy.activation.selector.card_ref == {
        "controller": 1,
        "location": 2,
        "public_card_id": 97268402,
    }
    assert policy.responses[0].role == "target"
    assert policy.responses[0].selector.card_ref["public_card_id"] == 14558127
