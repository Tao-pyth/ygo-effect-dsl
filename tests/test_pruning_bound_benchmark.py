from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.search import (
    LEGACY_PRUNING_BOUND_METHOD,
    PRUNING_BOUND_METHOD,
)
from ygo_effect_dsl.spikes.pruning_bound_benchmark import (
    RANGE_ONLY_METHOD,
    run_pruning_bound_benchmark,
)


def test_correlated_benchmark_rejects_raw_iid_counting() -> None:
    report = run_pruning_bound_benchmark(
        trials=500,
        repo_root=Path(__file__).resolve().parents[1],
    )
    scenario = next(
        item
        for item in report["scenarios"]
        if item["scenario_id"] == "correlated_10x100"
    )

    assert report["benchmark_id"].startswith("prunebench_")
    assert report["decision"]["default_method"] == PRUNING_BOUND_METHOD
    assert scenario["raw_score_count"] == 1000
    assert scenario["known_effective_sample_size"] == 10
    assert scenario["false_prune_results"][LEGACY_PRUNING_BOUND_METHOD][
        "rate"
    ] > report["confidence_delta"]
    assert scenario["false_prune_results"][PRUNING_BOUND_METHOD]["count"] == 0
    assert scenario["false_prune_results"][RANGE_ONLY_METHOD]["count"] == 0


def test_current_real_route_inventory_is_not_misrepresented_as_search_samples() -> None:
    report = run_pruning_bound_benchmark(
        trials=10,
        repo_root=Path(__file__).resolve().parents[1],
    )
    inventory = report["real_trace_inventory"]

    assert inventory["statistically_usable"] is False
    assert inventory["independent_unit_count"] is None
    assert len(inventory["records"]) == 4
    assert report["limitations"]["production_default_calibration"] == (
        "not_supported_by_current_corpus"
    )
    assert report["limitations"]["required_follow_up"]["issue"] == 110


def test_checked_benchmark_evidence_has_a_valid_content_id() -> None:
    evidence_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "search"
        / "evidence"
        / "pruning_bound_benchmark.json"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    benchmark_id = evidence.pop("benchmark_id")

    assert benchmark_id == stable_digest(evidence, prefix="prunebench_")
    assert evidence["trials"] == 5_000
