from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.search import (
    CachePersistenceMode,
    CacheVerificationStatus,
    PrefixCachePolicy,
    ReplayPrefixCache,
    ReplayPrefixCacheEntry,
    ReplayPrefixCacheKey,
    build_prefix_cache_run_metadata,
    read_prefix_cache_index,
    write_prefix_cache_index,
)
from ygo_effect_dsl.route_dsl import load_route_document


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTE = load_route_document(
    REPO_ROOT
    / "examples"
    / "prototype"
    / "real_core_effect_veiler.route.yaml"
)
REPLAY = ROUTE["replay"]


def _entry(prefix_length: int, *, artifact_ref: str | None = None) -> ReplayPrefixCacheEntry:
    next_signature = (
        REPLAY["events"][prefix_length]["request_signature"]
        if prefix_length < len(REPLAY["events"])
        else ROUTE["result"]["final_request_signature"]
    )
    return ReplayPrefixCacheEntry.from_replay(
        REPLAY,
        prefix_length,
        artifact_ref=artifact_ref or f"route:{ROUTE['route_id']}#prefix={prefix_length}",
        state_completeness="query_api_projection",
        next_request_signature=next_signature,
    )


def test_policy_resolves_from_existing_experiment_extension_point() -> None:
    experiment = deepcopy(ROUTE["experiment"])
    experiment["search"].setdefault("parameters", {})["performance"] = {
        "prefix_cache": {
            "max_entries": 20,
            "max_bytes": 4096,
            "max_entry_bytes": 2048,
            "persistence_mode": "disabled",
            "flush_every_mutations": 5,
        }
    }

    policy = PrefixCachePolicy.from_experiment(experiment)

    assert policy.max_entries == 20
    assert policy.persistence_mode == CachePersistenceMode.DISABLED
    assert policy.to_dict()["policy_id"].startswith("prefixpol_")


def test_prefix_key_changes_with_manifest_or_actions_but_not_timestamp() -> None:
    baseline = ReplayPrefixCacheKey.from_replay(REPLAY, 2)
    timestamp_only = deepcopy(REPLAY)
    timestamp_only["events"][0]["timestamp"] = "2099-01-01T00:00:00Z"
    changed_action = deepcopy(REPLAY)
    changed_action["events"][1]["action"]["action_id"] = "act_changed"
    changed_manifest = deepcopy(REPLAY)
    changed_manifest["manifest"].pop("manifest_hash", None)
    changed_manifest["manifest"]["environment"]["core"]["lock_id"] = "core-other"

    assert ReplayPrefixCacheKey.from_replay(timestamp_only, 2).key_id == baseline.key_id
    assert ReplayPrefixCacheKey.from_replay(changed_action, 2).key_id != baseline.key_id
    assert ReplayPrefixCacheKey.from_replay(changed_manifest, 2).key_id != baseline.key_id


def test_cache_uses_deterministic_lru_and_entry_limit() -> None:
    cache = ReplayPrefixCache(
        PrefixCachePolicy(
            max_entries=2,
            max_bytes=100_000,
            max_entry_bytes=10_000,
            flush_every_mutations=100,
        )
    )
    first = _entry(0)
    second = _entry(1)
    third = _entry(2)

    cache.put(first)
    cache.put(second)
    assert cache.get(first.key) is first
    evicted = cache.put(third)

    assert evicted == (second.key.key_id,)
    assert cache.get(second.key) is None
    assert cache.get(first.key) is first
    assert cache.stats()["evictions"] == 1


def test_replayed_prefix_mismatch_invalidates_cache_entry() -> None:
    cache = ReplayPrefixCache(PrefixCachePolicy())
    entry = _entry(3)
    cache.put(entry)

    verification = cache.verify_replayed_prefix(
        entry.key,
        terminal_state_id="state_unexpected",
        next_request_signature=entry.next_request_signature,
        core_trace_digest=entry.core_trace_digest,
    )

    assert verification.status == CacheVerificationStatus.INVALIDATED
    assert verification.to_dict()["verification_id"].startswith("prefixverify_")
    assert cache.get(entry.key) is None
    assert cache.stats()["invalidations"] == 1


def test_manifest_change_can_eagerly_invalidate_stale_entries() -> None:
    cache = ReplayPrefixCache(PrefixCachePolicy())
    entry = _entry(2)
    cache.put(entry)

    invalidated = cache.retain_manifest("manifest_new_environment")

    assert invalidated == (entry.key.key_id,)
    assert cache.stats()["entries"] == 0


def test_index_persistence_contains_only_refs_and_round_trips(tmp_path: Path) -> None:
    cache = ReplayPrefixCache(
        PrefixCachePolicy(flush_every_mutations=1)
    )
    entry = _entry(2, artifact_ref="raw-log:run-1#sequence=2")
    cache.put(entry)
    assert cache.should_flush is True
    path = tmp_path / "prefix-cache.json"

    write_prefix_cache_index(path, cache)
    loaded = read_prefix_cache_index(path)
    text = path.read_text(encoding="utf-8")

    assert cache.should_flush is False
    assert cache.stats()["flushes"] == 1
    assert loaded.get(entry.key).to_dict() == entry.to_dict()
    assert '"initial_snapshot":' not in text
    assert '"events"' not in text
    assert "raw-log:run-1#sequence=2" in text


def test_entry_byte_limit_and_disabled_persistence_fail_closed(tmp_path: Path) -> None:
    entry = _entry(1)
    cache = ReplayPrefixCache(
        PrefixCachePolicy(
            max_entries=10,
            max_bytes=entry.estimated_bytes,
            max_entry_bytes=entry.estimated_bytes - 1,
            persistence_mode=CachePersistenceMode.DISABLED,
        )
    )

    with pytest.raises(ValueError, match="max_entry_bytes"):
        cache.put(entry)
    with pytest.raises(ValueError, match="persistence is disabled"):
        write_prefix_cache_index(tmp_path / "disabled.json", cache)


def test_run_metadata_persists_policy_and_pool_memory_budget() -> None:
    policy = PrefixCachePolicy()

    metadata = build_prefix_cache_run_metadata(
        policy,
        pool_size=8,
        per_worker_budget_bytes=49 * 1024 * 1024,
        main_process_budget_bytes=128 * 1024 * 1024,
    )

    assert metadata["metadata_id"].startswith("prefixrun_")
    assert metadata["policy"] == policy.to_dict()
    assert metadata["memory_budget"]["worker_pool_bytes"] == 392 * 1024 * 1024
    assert metadata["memory_budget"]["total_bytes"] == 536 * 1024 * 1024
