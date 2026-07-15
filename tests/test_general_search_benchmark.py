from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.spikes.general_search_benchmark import (
    CACHE_WORKER_POLICY_SCHEMA_VERSION,
    GENERAL_SEARCH_BENCHMARK_SCHEMA_VERSION,
    MEMORY_PREFLIGHT_SCHEMA_VERSION,
    run_calibration,
    write_evidence,
)


ROOT = Path(__file__).parents[1]


def test_logical_calibration_is_pool_independent_and_measured(tmp_path: Path) -> None:
    evidence = run_calibration(
        nodes=128,
        pool_sizes=(1, 2, 4),
        cache_entries=16,
        crash_every=31,
        repo_root=ROOT,
    )

    assert evidence["schema_version"] == GENERAL_SEARCH_BENCHMARK_SCHEMA_VERSION
    assert len(evidence["records"]) == 9
    assert all(item["semantic_result_pool_independent"] for item in evidence["invariants"])
    assert all(item["best_route_pool_independent"] for item in evidence["invariants"])
    assert evidence["cache_worker_policy"]["schema_version"] == CACHE_WORKER_POLICY_SCHEMA_VERSION
    assert evidence["cache_worker_policy"]["native_state_reuse"] is False
    assert evidence["memory_preflight"]["schema_version"] == MEMORY_PREFLIGHT_SCHEMA_VERSION
    assert all(record["fresh_replays"] == 1 for record in evidence["records"])
    assert all(record["crash_recovery"]["semantic_result_preserved"] for record in evidence["records"])

    destination = tmp_path / "evidence.json"
    status = write_evidence(evidence, json_path=destination)
    assert status == {"written": False, "path": None}
    assert json.loads(destination.read_text(encoding="utf-8"))["records"] == evidence["records"]


def test_different_pool_completion_orders_have_identical_semantics() -> None:
    evidence = run_calibration(
        nodes=33,
        pool_sizes=(1, 16),
        cache_entries=8,
        crash_every=0,
        repo_root=ROOT,
    )
    for profile in {record["profile_id"] for record in evidence["records"]}:
        selected = [record for record in evidence["records"] if record["profile_id"] == profile]
        assert len({record["semantic_digest"] for record in selected}) == 1
        assert len({record["best_route"]["route_id"] for record in selected}) == 1


def test_checked_base_and_logical_evidence_use_successful_external_routes() -> None:
    base = json.loads(
        (ROOT / "docs/adr/evidence/0105_real_core_base_routes.json").read_text(
            encoding="utf-8"
        )
    )
    assert base["schema_version"] == "real-core-benchmark-base-routes-v2"
    assert all(record["success"] is True for record in base["records"])
    assert all(
        record["source_reference"] == "external_qualified_route"
        for record in base["records"]
    )
    assert all("source_path" not in record for record in base["records"])

    logical = json.loads(
        (ROOT / "docs/adr/evidence/0105_general_search_100k.json").read_text(
            encoding="utf-8"
        )
    )
    assert logical["nodes_per_profile_pool"] == 100_000
    assert all(
        source["source_reference"] == "external_qualified_route"
        for source in logical["profile_sources"]
    )
