from __future__ import annotations

from pathlib import Path

from ygo_effect_dsl.engine.search import PrefixCachePolicy
from ygo_effect_dsl.spikes import prefix_cache_benchmark


def test_recommended_prefix_cache_policy_is_the_versioned_default() -> None:
    recommended = prefix_cache_benchmark.recommended_prefix_cache_policy()

    assert recommended == PrefixCachePolicy()
    assert recommended.to_dict() == {
        "flush_every_mutations": 1000,
        "max_bytes": 16 * 1024 * 1024,
        "max_entries": 4096,
        "max_entry_bytes": 64 * 1024,
        "persistence_mode": "index_only",
        "policy_id": recommended.to_dict()["policy_id"],
        "schema_version": "prefix-cache-policy-v1",
    }


def test_benchmark_records_fresh_replay_and_private_data_boundary(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(
        prefix_cache_benchmark,
        "_real_core_worker_peak_rss",
        lambda: 10 * 1024 * 1024,
    )

    report = prefix_cache_benchmark.run_prefix_cache_benchmark(
        entry_count=64,
        access_count=256,
        worker_rss_runs=1,
        repo_root=repo_root,
    )

    assert report["benchmark_id"].startswith("prefixbench_")
    assert report["content_audit"]["passed"] is True
    assert report["route_prefix_count"] == 23
    assert report["capacity_results"][0]["fresh_replay_count"] == 256
    assert report["capacity_results"][0]["verified_hint_hits"] > 0
    assert report["worker_memory"]["per_worker_budget_bytes"] == 13 * 1024 * 1024
    assert report["recommended_policy"] == PrefixCachePolicy().to_dict()
