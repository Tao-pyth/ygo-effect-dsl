from __future__ import annotations

from copy import deepcopy
import importlib.resources
import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.experiment.cross_validation import (
    STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION,
)
from ygo_effect_dsl.storage.comparison import (
    ANALYTICS_COMPARISON_CONTRACT_VERSION,
    ANALYTICS_COMPARISON_RESPONSE_SCHEMA_VERSION,
    AnalyticsComparisonRequest,
    BudgetEvidenceStatus,
    ComparisonArm,
    ComparisonBudget,
    ComparisonCompatibilityEvidence,
    ComparisonCompletion,
    ComparisonContext,
    ComparisonLineageKey,
    ComparisonObservation,
    ConfidenceMethod,
    ValidatedComparisonLineage,
    analytics_comparison_contract_document,
    build_analytics_comparison_report,
    comparison_observation_from_query_row,
)
from ygo_effect_dsl.storage.query import (
    AnalyticsQueryRow,
    AnalyticsValue,
)


SNAPSHOT_ID = "analyticssnapshot_comparison_fixture"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _lineage_document() -> dict[str, object]:
    divergence = {
        "baseline_action": {"kind": "PASS"},
        "fork_request": {"request_signature": "request_fixture"},
        "fork_step": 0,
        "interrupted_action": {"kind": "ACTIVATE_EFFECT"},
        "schema_version": "strategy-first-divergence-v1",
        "state_hash_before": "state_before",
    }
    recovery_ids = (
        stable_digest({"step": 1}, prefix="strategyrecoveryevent_"),
        stable_digest({"step": 2}, prefix="strategyrecoveryevent_"),
    )
    identity = {
        "baseline_semantic_id": stable_digest(
            {"arm": "baseline"}, prefix="strategyroute_"
        ),
        "divergence": divergence,
        "interrupted_semantic_id": stable_digest(
            {"arm": "interrupted"}, prefix="strategyroute_"
        ),
        "recovery_event_semantic_ids": list(recovery_ids),
        "schema_version": STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION,
        "trace_id": "interruptiontrace_fixture",
    }
    return {
        **identity,
        "divergence_id": stable_digest(
            divergence, prefix="strategydivergence_"
        ),
        "lineage_id": stable_digest(identity, prefix="strategylineage_"),
        "recovery_action_count": len(recovery_ids),
        "status": "validated",
    }


def _key(*, trial_id: str = "trial_0") -> ComparisonLineageKey:
    return ComparisonLineageKey(
        lineage=ValidatedComparisonLineage(_lineage_document()),
        deck_id="deck_fixture",
        scenario_id="scenario_fixture",
        opening_hand_id="opening_fixture",
        trial_id=trial_id,
        interruption_id="ash_blossom_fixture",
    )


def _context(
    *, evaluator_version: str = "1", search_version: str = "1"
) -> ComparisonContext:
    return ComparisonContext(
        evaluator_id="board-score",
        evaluator_version=evaluator_version,
        evaluator_config_hash=f"evaluator_config_{evaluator_version}",
        search_strategy_id="random-search",
        search_strategy_version=search_version,
        search_config_hash=f"search_config_{search_version}",
        observation_schema_version="analytics-query-row-v1",
        search_schema_version="search-run-result-v5",
    )


def _observation(
    arm: ComparisonArm,
    score: float,
    *,
    key: ComparisonLineageKey | None = None,
    context: ComparisonContext | None = None,
    completion: ComparisonCompletion = ComparisonCompletion.COMPLETE,
    budget: ComparisonBudget | None = None,
    success: AnalyticsValue | bool = True,
    pruning_policy_version: str | None = None,
) -> ComparisonObservation:
    lineage_key = key or _key()
    success_value = (
        success
        if isinstance(success, AnalyticsValue)
        else AnalyticsValue.present(success)
    )
    return ComparisonObservation(
        query_snapshot_id=SNAPSHOT_ID,
        lineage_key=lineage_key,
        arm=arm,
        semantic_id=lineage_key.lineage.semantic_id_for(arm),
        run_id=f"run_{lineage_key.trial_id}_{arm.value}",
        route_id=f"route_{lineage_key.trial_id}_{arm.value}",
        context=context or _context(),
        completion=completion,
        budget=budget or ComparisonBudget("logical_nodes", 100, 100),
        success=success_value,
        metrics={"score": AnalyticsValue.present(score)},
        pruning_policy_version=pruning_policy_version,
    )


def _request(
    *,
    method: ConfidenceMethod = ConfidenceMethod.NORMAL_MEAN_V1,
) -> AnalyticsComparisonRequest:
    return AnalyticsComparisonRequest(
        query_snapshot_id=SNAPSHOT_ID,
        metrics=("score", "success"),
        confidence_method=method,
    )


def _complete_pair(
    *, key: ComparisonLineageKey | None = None
) -> tuple[ComparisonObservation, ...]:
    pair_key = key or _key()
    return (
        _observation(ComparisonArm.BASELINE, 10, key=pair_key),
        _observation(ComparisonArm.INTERRUPTED, 6, key=pair_key, success=False),
        _observation(ComparisonArm.RECOVERY, 9, key=pair_key),
    )


def test_validated_lineage_checks_source_content_ids() -> None:
    parsed = ValidatedComparisonLineage(_lineage_document())

    assert parsed.lineage_id.startswith("strategylineage_")
    assert parsed.recovery_semantic_id.startswith("strategyrecovery_")

    tampered = deepcopy(_lineage_document())
    tampered["divergence"]["fork_step"] = 1
    with pytest.raises(ValueError, match="divergence_id"):
        ValidatedComparisonLineage(tampered)

    unvalidated = deepcopy(_lineage_document())
    unvalidated["status"] = "unverified"
    with pytest.raises(ValueError, match="must be validated"):
        ValidatedComparisonLineage(unvalidated)


def test_pinned_real_core_cross_validation_lineage_is_accepted() -> None:
    evidence = json.loads(
        (
            REPO_ROOT
            / "docs/ocgcore/evidence/strategy_interruption_cross_validation.json"
        ).read_text(encoding="utf-8")
    )
    lineage = evidence["profiles"][0]["strategy_runs"][0]["lineage"]

    parsed = ValidatedComparisonLineage(lineage)

    assert parsed.lineage_id == lineage["lineage_id"]
    assert parsed.recovery_semantic_id.startswith("strategyrecovery_")


def test_complete_pair_emits_absolute_relative_and_recovery_deltas() -> None:
    report = build_analytics_comparison_report(_complete_pair(), _request())
    pair = report["pairs"][0]

    assert report["schema_version"] == ANALYTICS_COMPARISON_RESPONSE_SCHEMA_VERSION
    assert pair["status"] == "complete"
    interrupted = pair["transitions"]["baseline_to_interrupted"]["metrics"]
    recovery = pair["transitions"]["baseline_to_recovery"]["metrics"]
    assert interrupted["score"]["absolute_delta"]["value"] == -4.0
    assert interrupted["score"]["relative_delta"]["value"] == -0.4
    assert interrupted["success"]["absolute_delta"]["value"] == -1.0
    assert recovery["score"]["absolute_delta"]["value"] == -1.0
    assert report["sample"]["pair_status_counts"]["complete"] == 1
    assert report["comparison_report_id"].startswith("comparisonreport_")


def test_missing_recovery_is_incomplete_and_never_zero_delta() -> None:
    observations = _complete_pair()[:2]

    report = build_analytics_comparison_report(observations, _request())
    pair = report["pairs"][0]
    metric = pair["transitions"]["baseline_to_recovery"]["metrics"]["score"]

    assert pair["status"] == "incomplete"
    assert pair["missing_arms"] == ["recovery"]
    assert metric["status"] == "unavailable_missing_arm"
    assert metric["absolute_delta"] == {
        "schema_version": "analytics-query-value-v1",
        "state": "missing",
    }
    assert report["sample"]["pair_status_counts"]["incomplete"] == 1


@pytest.mark.parametrize(
    "completion",
    (
        ComparisonCompletion.EARLY_STOP,
        ComparisonCompletion.TIMEOUT,
        ComparisonCompletion.PARTIAL_BUDGET,
        ComparisonCompletion.FAILED,
        ComparisonCompletion.QUARANTINED,
    ),
)
def test_censored_arm_is_visible_but_excluded_from_deltas(
    completion: ComparisonCompletion,
) -> None:
    key = _key()
    observations = (
        _observation(ComparisonArm.BASELINE, 10, key=key),
        _observation(
            ComparisonArm.INTERRUPTED,
            6,
            key=key,
            completion=completion,
        ),
        _observation(ComparisonArm.RECOVERY, 9, key=key),
    )

    report = build_analytics_comparison_report(observations, _request())
    pair = report["pairs"][0]
    metric = pair["transitions"]["baseline_to_interrupted"]["metrics"]["score"]

    assert pair["status"] == "censored"
    assert completion.value in pair["censor_reasons"]
    assert metric["status"] == "unavailable_censored"
    assert metric["absolute_delta"]["state"] == "unknown"
    assert report["metric_summaries"]["baseline_to_interrupted"]["score"][
        "available_pair_count"
    ] == 0


def test_pruning_bias_and_partial_budget_are_reported_separately() -> None:
    key = _key()
    partial = ComparisonBudget("logical_nodes", 100, 50)
    observations = tuple(
        _observation(
            arm,
            score,
            key=key,
            budget=partial,
            pruning_policy_version=(
                "statistical-pruning-v1"
                if arm == ComparisonArm.INTERRUPTED
                else None
            ),
        )
        for arm, score in (
            (ComparisonArm.BASELINE, 10),
            (ComparisonArm.INTERRUPTED, 6),
            (ComparisonArm.RECOVERY, 9),
        )
    )

    report = build_analytics_comparison_report(observations, _request())

    assert report["pairs"][0]["status"] == "complete"
    assert report["sample"]["partial_budget_pair_count"] == 1
    assert report["sample"]["pruning_affected_pair_count"] == 1
    assert report["uncertainty"]["statistical_pruning_bias"] == "present"


def test_unrecorded_or_different_budget_is_incomparable() -> None:
    key = _key()
    for interrupted_budget, expected in (
        (ComparisonBudget.not_recorded(), "unavailable_unrecorded_budget"),
        (
            ComparisonBudget("logical_nodes", 200, 200),
            "unavailable_incomparable_budget",
        ),
    ):
        observations = (
            _observation(ComparisonArm.BASELINE, 10, key=key),
            _observation(
                ComparisonArm.INTERRUPTED,
                6,
                key=key,
                budget=interrupted_budget,
            ),
            _observation(ComparisonArm.RECOVERY, 9, key=key),
        )

        report = build_analytics_comparison_report(observations, _request())
        metric = report["pairs"][0]["transitions"][
            "baseline_to_interrupted"
        ]["metrics"]["score"]

        assert report["pairs"][0]["status"] == "incomparable"
        assert metric["status"] == expected
        assert metric["absolute_delta"]["state"] == "not_applicable"


def test_context_version_mismatch_requires_explicit_validated_evidence() -> None:
    key = _key()
    baseline_context = _context()
    changed_context = _context(evaluator_version="2", search_version="2")
    observations = (
        _observation(
            ComparisonArm.BASELINE, 10, key=key, context=baseline_context
        ),
        _observation(
            ComparisonArm.INTERRUPTED, 6, key=key, context=changed_context
        ),
        _observation(
            ComparisonArm.RECOVERY, 9, key=key, context=changed_context
        ),
    )

    rejected = build_analytics_comparison_report(observations, _request())
    metric = rejected["pairs"][0]["transitions"][
        "baseline_to_interrupted"
    ]["metrics"]["score"]
    assert rejected["pairs"][0]["status"] == "incomparable"
    assert metric["status"] == "unavailable_incomparable_context"

    evidence = ComparisonCompatibilityEvidence(
        left_context_id=baseline_context.context_id,
        right_context_id=changed_context.context_id,
        evidence_id="compatibility_evidence_fixture",
        method="fresh_replay_semantic_equivalence_v1",
    )
    accepted = build_analytics_comparison_report(
        observations,
        _request(),
        compatibility_evidence=(evidence,),
    )
    accepted_metric = accepted["pairs"][0]["transitions"][
        "baseline_to_interrupted"
    ]["metrics"]["score"]
    assert accepted["pairs"][0]["status"] == "complete"
    assert accepted_metric["status"] == "available"
    assert accepted_metric["compatibility_evidence_id"] == (
        "compatibility_evidence_fixture"
    )


@pytest.mark.parametrize(
    ("value", "state"),
    (
        (AnalyticsValue.missing(), "missing"),
        (AnalyticsValue.unknown(), "unknown"),
        (AnalyticsValue.redacted(), "redacted"),
        (AnalyticsValue.quarantined(), "quarantined"),
        (AnalyticsValue.not_applicable(), "not_applicable"),
    ),
)
def test_metric_value_state_propagates_without_becoming_zero(
    value: AnalyticsValue, state: str
) -> None:
    key = _key()
    interrupted = _observation(ComparisonArm.INTERRUPTED, 6, key=key)
    interrupted = ComparisonObservation(
        **{
            **{
                name: getattr(interrupted, name)
                for name in (
                    "query_snapshot_id",
                    "lineage_key",
                    "arm",
                    "semantic_id",
                    "run_id",
                    "route_id",
                    "context",
                    "completion",
                    "budget",
                    "success",
                    "pruning_policy_version",
                )
            },
            "metrics": {"score": value},
        }
    )
    report = build_analytics_comparison_report(
        (
            _observation(ComparisonArm.BASELINE, 10, key=key),
            interrupted,
            _observation(ComparisonArm.RECOVERY, 9, key=key),
        ),
        _request(),
    )
    metric = report["pairs"][0]["transitions"][
        "baseline_to_interrupted"
    ]["metrics"]["score"]

    assert metric["status"] == "unavailable_value_state"
    assert metric["absolute_delta"]["state"] == state
    assert "value" not in metric["absolute_delta"]


def test_zero_baseline_has_absolute_but_not_relative_delta() -> None:
    key = _key()
    observations = (
        _observation(ComparisonArm.BASELINE, 0, key=key),
        _observation(ComparisonArm.INTERRUPTED, 2, key=key),
        _observation(ComparisonArm.RECOVERY, 1, key=key),
    )

    report = build_analytics_comparison_report(observations, _request())
    metric = report["pairs"][0]["transitions"][
        "baseline_to_interrupted"
    ]["metrics"]["score"]

    assert metric["absolute_delta"]["value"] == 2.0
    assert metric["relative_delta"]["state"] == "not_applicable"


def test_confidence_records_method_assumptions_and_sample_count() -> None:
    observations = (
        *_complete_pair(key=_key(trial_id="trial_0")),
        *_complete_pair(key=_key(trial_id="trial_1")),
    )

    report = build_analytics_comparison_report(observations, _request())
    confidence = report["metric_summaries"]["baseline_to_interrupted"][
        "score"
    ]["absolute_delta_confidence"]

    assert confidence["status"] == "available_provisional"
    assert confidence["method"] == "normal_mean_v1"
    assert confidence["sample_count"] == 2
    assert "normal_approximation_of_paired_mean" in confidence["assumptions"]

    disabled = build_analytics_comparison_report(
        observations, _request(method=ConfidenceMethod.NONE)
    )
    assert disabled["metric_summaries"]["baseline_to_interrupted"]["score"][
        "absolute_delta_confidence"
    ]["status"] == "disabled"


def test_single_pair_confidence_is_explicitly_unavailable() -> None:
    report = build_analytics_comparison_report(_complete_pair(), _request())
    confidence = report["metric_summaries"]["baseline_to_interrupted"][
        "score"
    ]["absolute_delta_confidence"]

    assert confidence["status"] == "unavailable_insufficient_sample"
    assert confidence["sample_count"] == 1
    assert confidence["lower"] is None


def test_comparison_request_mapping_round_trip_is_strict() -> None:
    request = _request()

    assert AnalyticsComparisonRequest.from_mapping(request.to_dict()) == request

    unexpected = {**request.to_dict(), "unversioned_option": True}
    with pytest.raises(ValueError, match="fields must be exactly"):
        AnalyticsComparisonRequest.from_mapping(unexpected)


def test_duplicate_arm_and_snapshot_mismatch_fail_close() -> None:
    baseline = _complete_pair()[0]
    with pytest.raises(ValueError, match="duplicate baseline"):
        build_analytics_comparison_report((baseline, baseline), _request())

    wrong_snapshot = ComparisonObservation(
        **{
            **{
                name: getattr(baseline, name)
                for name in (
                    "lineage_key",
                    "arm",
                    "semantic_id",
                    "run_id",
                    "route_id",
                    "context",
                    "completion",
                    "budget",
                    "success",
                    "metrics",
                    "pruning_policy_version",
                )
            },
            "query_snapshot_id": "analyticssnapshot_other",
        }
    )
    with pytest.raises(ValueError, match="request snapshot"):
        build_analytics_comparison_report((wrong_snapshot,), _request())


def test_observation_rejects_semantic_id_outside_validated_lineage() -> None:
    key = _key()

    with pytest.raises(ValueError, match="does not match validated lineage"):
        ComparisonObservation(
            query_snapshot_id=SNAPSHOT_ID,
            lineage_key=key,
            arm=ComparisonArm.BASELINE,
            semantic_id=key.lineage.interrupted_semantic_id,
            run_id="run_invalid",
            route_id="route_invalid",
            context=_context(),
            completion=ComparisonCompletion.COMPLETE,
            budget=ComparisonBudget("logical_nodes", 100, 100),
            success=AnalyticsValue.present(True),
            metrics={"score": AnalyticsValue.present(1)},
        )


def test_query_row_adapter_preserves_explicit_value_states() -> None:
    key = _key()
    row = AnalyticsQueryRow.build(
        {
            "run": "run_query_adapter",
            "route": "route_query_adapter",
            "success": AnalyticsValue.unknown(),
            "score": 4.0,
            "resource_consumption": AnalyticsValue.redacted(),
        },
        row_id="analyticsrow_comparison_adapter",
    )

    observation = comparison_observation_from_query_row(
        row,
        query_snapshot_id=SNAPSHOT_ID,
        lineage_key=key,
        arm=ComparisonArm.BASELINE,
        semantic_id=key.lineage.baseline_semantic_id,
        context=_context(),
        completion=ComparisonCompletion.FRONTIER_EXHAUSTED,
        budget=ComparisonBudget("logical_nodes", 100, 80),
    )

    assert observation.run_id == "run_query_adapter"
    assert observation.success.state.value == "unknown"
    assert observation.metrics["resource_consumption"].state.value == "redacted"
    assert observation.budget.fraction == 0.8


def test_budget_and_pruning_contracts_fail_close() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        ComparisonBudget("logical_nodes", 10, 11)
    with pytest.raises(ValueError, match="must not contain values"):
        ComparisonBudget(
            "nodes", 10, 0, status=BudgetEvidenceStatus.NOT_RECORDED
        )

    key = _key()
    with pytest.raises(ValueError, match="pruning_policy_version"):
        _observation(
            ComparisonArm.BASELINE,
            1,
            key=key,
            completion=ComparisonCompletion.PRUNED,
        )


def test_machine_readable_comparison_contract_matches_runtime() -> None:
    resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
        "analytics-comparison-contract-v1.json"
    )
    stored = json.loads(resource.read_text(encoding="utf-8"))
    runtime = analytics_comparison_contract_document()

    assert stored == runtime
    assert runtime["version"] == ANALYTICS_COMPARISON_CONTRACT_VERSION
    assert runtime["metrics"]["missing_or_incomparable"] == (
        "never coerced to zero or failure"
    )
    assert runtime["lineage"]["requires_status"] == "validated"
