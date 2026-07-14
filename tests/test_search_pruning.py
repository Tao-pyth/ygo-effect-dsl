from __future__ import annotations

from copy import deepcopy

import pytest

from ygo_effect_dsl.engine.search import (
    ActionEvidence,
    ExplorationReason,
    LEGACY_PRUNING_BOUND_METHOD,
    PRUNING_BOUND_METHOD,
    PruningDataIdentity,
    PruningDisposition,
    PruningGuardrailPolicy,
    PruningReason,
    SearchPruningGuardrails,
)
from ygo_effect_dsl.experiment import load_experiment_document


def _policy(**overrides: object) -> PruningGuardrailPolicy:
    values = {
        "minimum_action_visits": 3,
        "unexplored_action_probability": 0.2,
        "confidence_delta": 0.05,
        "score_lower_bound": 0,
        "score_upper_bound": 100,
        "prune_margin": 0,
    }
    values.update(overrides)
    return PruningGuardrailPolicy(**values)


def _identity(**overrides: str) -> PruningDataIdentity:
    values = {
        "evaluator_id": "board",
        "evaluator_version": "1",
        "evaluator_config_hash": "evalcfg_a",
        "information_mode": "complete_information",
        "evaluate_at": "turn_1_end",
        "environment_hash": "searchenv_a",
    }
    values.update(overrides)
    return PruningDataIdentity(**values)


def _evidence(
    identity: PruningDataIdentity,
    action_id: str,
    scores: tuple[int | float, ...],
    *,
    state_id: str = "state_exact_a",
    sampling_unit_ids: tuple[str, ...] | None = None,
) -> ActionEvidence:
    if sampling_unit_ids is None:
        sampling_unit_ids = tuple(f"root_seed_{index}" for index in range(len(scores)))
    return ActionEvidence(
        state_id,
        action_id,
        identity.dataset_id,
        scores,
        sampling_unit_ids,
        "distinct deterministic root seeds",
    )


def test_policy_resolves_from_existing_experiment_parameters() -> None:
    experiment = load_experiment_document(
        "examples/experiments/real_core_effect_veiler.yaml"
    )
    experiment = deepcopy(experiment)
    experiment["search"]["parameters"]["pruning"] = {
        "minimum_action_visits": 5,
        "unexplored_action_probability": 0.15,
        "confidence_delta": 0.01,
        "score_lower_bound": -10,
        "score_upper_bound": 200,
    }

    policy = PruningGuardrailPolicy.from_experiment(experiment)
    identity = PruningDataIdentity.from_experiment(experiment)

    assert policy.minimum_action_visits == 5
    assert policy.bound_method == PRUNING_BOUND_METHOD
    assert policy.to_dict()["policy_id"].startswith("prunepol_")
    assert identity.evaluator_id == experiment["evaluator"]["id"]
    assert identity.to_dict()["dataset_id"].startswith("prunedata_")


def test_minimum_visits_protect_candidate_from_pruning() -> None:
    identity = _identity()
    guardrails = SearchPruningGuardrails(_policy(), identity)

    decision = guardrails.assess(
        _evidence(identity, "weak_candidate", (0, 0)),
        _evidence(identity, "strong_incumbent", (100,) * 100),
    )

    assert decision.disposition == PruningDisposition.KEEP
    assert decision.reason == PruningReason.MANDATORY_MINIMUM_VISITS
    assert decision.detail["remaining_visits"] == 1


def test_unexplored_selection_probability_uses_replayable_draw_and_is_logged() -> None:
    guardrails = SearchPruningGuardrails(_policy(), _identity())

    selected = guardrails.choose_unexplored(has_unexplored_actions=True, draw=0.19)
    skipped = guardrails.choose_unexplored(has_unexplored_actions=True, draw=0.2)
    unavailable = guardrails.choose_unexplored(
        has_unexplored_actions=False, draw=0.01
    )

    assert selected.select_unexplored is True
    assert selected.reason == ExplorationReason.PROBABILITY_SELECTED_UNEXPLORED
    assert skipped.select_unexplored is False
    assert unavailable.reason == ExplorationReason.NO_UNEXPLORED_ACTIONS
    assert len(guardrails.export_audit_log()["records"]) == 3


def test_only_dominated_optimistic_bound_is_pruned() -> None:
    identity = _identity()
    guardrails = SearchPruningGuardrails(_policy(), identity)

    decision = guardrails.assess(
        _evidence(identity, "candidate", (0,) * 100),
        _evidence(identity, "incumbent", (100,) * 100),
    )

    assert decision.disposition == PruningDisposition.PRUNE
    assert decision.reason == PruningReason.OPTIMISTIC_BOUND_DOMINATED
    assert decision.candidate_interval.upper < decision.incumbent_interval.lower
    assert decision.candidate_interval.sample_count == 100
    assert decision.candidate_interval.raw_sample_count == 100
    assert decision.to_dict()["decision_id"].startswith("prune_")


def test_unidentified_independence_keeps_candidate_after_raw_minimum() -> None:
    identity = _identity()
    guardrails = SearchPruningGuardrails(_policy(), identity)
    candidate = ActionEvidence(
        "state_exact_a", "candidate", identity.dataset_id, (0,) * 100
    )
    incumbent = ActionEvidence(
        "state_exact_a", "incumbent", identity.dataset_id, (100,) * 100
    )

    decision = guardrails.assess(candidate, incumbent)

    assert decision.disposition == PruningDisposition.KEEP
    assert decision.reason == PruningReason.INDEPENDENCE_UNVERIFIED
    assert decision.candidate_interval is None
    assert decision.detail["required_action"] == (
        "identify_independently_seeded_sampling_units_or_keep"
    )


def test_correlated_scores_are_collapsed_by_independent_sampling_unit() -> None:
    identity = _identity()
    guardrails = SearchPruningGuardrails(_policy(minimum_action_visits=3), identity)
    unit_ids = ("seed_a",) * 50 + ("seed_b",) * 50

    decision = guardrails.assess(
        _evidence(
            identity,
            "candidate",
            (0,) * 100,
            sampling_unit_ids=unit_ids,
        ),
        _evidence(
            identity,
            "incumbent",
            (100,) * 100,
            sampling_unit_ids=unit_ids,
        ),
    )

    assert decision.disposition == PruningDisposition.KEEP
    assert decision.reason == PruningReason.MANDATORY_MINIMUM_VISITS
    assert decision.detail["sample_count_kind"] == "independent_unit_count"
    assert decision.detail["remaining_visits"] == 1


def test_legacy_iid_bound_requires_explicit_method_and_is_marked_deprecated() -> None:
    identity = _identity()
    guardrails = SearchPruningGuardrails(
        _policy(bound_method=LEGACY_PRUNING_BOUND_METHOD), identity
    )
    candidate = ActionEvidence(
        "state_exact_a", "candidate", identity.dataset_id, (0,) * 100
    )
    incumbent = ActionEvidence(
        "state_exact_a", "incumbent", identity.dataset_id, (100,) * 100
    )

    decision = guardrails.assess(candidate, incumbent)

    assert decision.disposition == PruningDisposition.PRUNE
    assert decision.candidate_interval.method == LEGACY_PRUNING_BOUND_METHOD
    assert decision.detail["bound_method_status"] == "deprecated_iid_compatibility"


def test_confidence_overlap_preserves_low_frequency_outlier_candidate() -> None:
    identity = _identity()
    guardrails = SearchPruningGuardrails(_policy(), identity)

    decision = guardrails.assess(
        _evidence(identity, "rare_route", (0,) * 99 + (100,)),
        _evidence(identity, "stable_route", (20,) * 100),
    )

    assert decision.disposition == PruningDisposition.KEEP
    assert decision.reason == PruningReason.CONFIDENCE_OVERLAP


def test_evaluator_or_environment_change_invalidates_old_search_data() -> None:
    old_identity = _identity()
    current_identity = _identity(evaluator_version="2")
    guardrails = SearchPruningGuardrails(_policy(), current_identity)

    decision = guardrails.assess(
        _evidence(old_identity, "candidate", (0,) * 100),
        _evidence(old_identity, "incumbent", (100,) * 100),
    )

    assert decision.disposition == PruningDisposition.INVALIDATE
    assert decision.reason == PruningReason.DATA_IDENTITY_MISMATCH
    assert decision.detail["required_action"] == "discard_and_resample"


def test_pruning_comparison_requires_same_exact_parent_state() -> None:
    identity = _identity()
    guardrails = SearchPruningGuardrails(_policy(), identity)

    with pytest.raises(ValueError, match="same exact parent_state_id"):
        guardrails.assess(
            _evidence(identity, "candidate", (0,) * 10, state_id="state_a"),
            _evidence(identity, "incumbent", (100,) * 10, state_id="state_b"),
        )


def test_policy_rejects_invalid_probability_bounds_and_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unexplored_action_probability"):
        _policy(unexplored_action_probability=0)
    with pytest.raises(ValueError, match="score_lower_bound"):
        _policy(score_lower_bound=100)
    with pytest.raises(ValueError, match="unknown search pruning"):
        PruningGuardrailPolicy.from_mapping(
            {
                "minimum_action_visits": 3,
                "unexplored_action_probability": 0.2,
                "confidence_delta": 0.05,
                "score_lower_bound": 0,
                "score_upper_bound": 100,
                "unsafe_fast_prune": True,
            }
        )
    with pytest.raises(ValueError, match="bound_method must be one of"):
        _policy(bound_method="bootstrap_v0")


def test_action_evidence_requires_auditable_sampling_unit_metadata() -> None:
    identity = _identity()
    with pytest.raises(ValueError, match="one ID for each score"):
        ActionEvidence(
            "state_a",
            "action_a",
            identity.dataset_id,
            (1, 2),
            ("seed_a",),
            "distinct seeds",
        )
    with pytest.raises(ValueError, match="independence_basis"):
        ActionEvidence(
            "state_a",
            "action_a",
            identity.dataset_id,
            (1,),
            ("seed_a",),
        )
