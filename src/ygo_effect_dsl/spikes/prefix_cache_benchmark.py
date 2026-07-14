from __future__ import annotations

import argparse
import gc
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from typing import Any, Mapping, Sequence

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.search import (
    CachePersistenceMode,
    PrefixCachePolicy,
    ReplayPrefixCache,
    ReplayPrefixCacheEntry,
    ReplayPrefixCacheKey,
    build_prefix_cache_run_metadata,
    read_prefix_cache_index,
    write_prefix_cache_index,
)
from ygo_effect_dsl.route_dsl import load_route_document
from ygo_effect_dsl.spikes.ocgcore_isolation import _process_rss_bytes


PREFIX_CACHE_BENCHMARK_SCHEMA_VERSION = "prefix-cache-benchmark-v1"
RECOMMENDED_MAX_ENTRIES = 4096
RECOMMENDED_MAX_BYTES = 16 * 1024 * 1024
RECOMMENDED_MAX_ENTRY_BYTES = 64 * 1024
RECOMMENDED_FLUSH_EVERY_MUTATIONS = 1000
_FORBIDDEN_INDEX_KEYS = {
    "card_data",
    "core_response",
    "deck_order",
    "events",
    "hand",
    "native_handle",
    "response_buffer",
}


def recommended_prefix_cache_policy() -> PrefixCachePolicy:
    return PrefixCachePolicy(
        max_entries=RECOMMENDED_MAX_ENTRIES,
        max_bytes=RECOMMENDED_MAX_BYTES,
        max_entry_bytes=RECOMMENDED_MAX_ENTRY_BYTES,
        persistence_mode=CachePersistenceMode.INDEX_ONLY,
        flush_every_mutations=RECOMMENDED_FLUSH_EVERY_MUTATIONS,
    )


def _percentile(values: Sequence[int], fraction: float) -> int:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def _entry_size_summary(entries: Sequence[ReplayPrefixCacheEntry]) -> dict[str, Any]:
    sizes = [entry.estimated_bytes for entry in entries]
    return {
        "count": len(sizes),
        "max": max(sizes),
        "mean": round(statistics.fmean(sizes), 3),
        "median": round(statistics.median(sizes), 3),
        "min": min(sizes),
        "p95": _percentile(sizes, 0.95),
    }


def _route_prefix_entries(route_path: Path) -> list[ReplayPrefixCacheEntry]:
    route = load_route_document(route_path)
    replay = route["replay"]
    events = replay["events"]
    entries: list[ReplayPrefixCacheEntry] = []
    for prefix_length in range(len(events) + 1):
        next_signature = (
            events[prefix_length]["request_signature"]
            if prefix_length < len(events)
            else route["result"]["final_request_signature"]
        )
        entries.append(
            ReplayPrefixCacheEntry.from_replay(
                replay,
                prefix_length,
                artifact_ref=f"route:{route['route_id']}#prefix={prefix_length}",
                state_completeness="query_api_projection",
                next_request_signature=next_signature,
            )
        )
    return entries


def _synthetic_entries(
    template: ReplayPrefixCacheEntry, count: int
) -> list[ReplayPrefixCacheEntry]:
    entries: list[ReplayPrefixCacheEntry] = []
    for index in range(count):
        key = ReplayPrefixCacheKey(
            manifest_hash=template.key.manifest_hash,
            initial_snapshot_hash=template.key.initial_snapshot_hash,
            replay_schema_version=template.key.replay_schema_version,
            prefix_length=template.key.prefix_length,
            prefix_digest=stable_digest(
                {"index": index, "template": template.key.prefix_digest},
                prefix="prefix_",
            ),
        )
        entries.append(
            ReplayPrefixCacheEntry(
                key=key,
                terminal_state_id=template.terminal_state_id,
                next_request_signature=template.next_request_signature,
                core_trace_digest=template.core_trace_digest,
                artifact_ref=f"route:benchmark#branch={index}",
                state_completeness=template.state_completeness,
            )
        )
    return entries


def _access_trace(entry_count: int, access_count: int) -> list[int]:
    hot_count = max(1, entry_count // 5)
    state = 0x20260713
    trace: list[int] = []
    for index in range(access_count):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        population = hot_count if index % 5 else entry_count
        trace.append(state % population)
    return trace


def _capacity_benchmark(
    entries: Sequence[ReplayPrefixCacheEntry],
    trace: Sequence[int],
    capacity: int,
) -> dict[str, Any]:
    max_entry = max(entry.estimated_bytes for entry in entries)
    policy = PrefixCachePolicy(
        max_entries=capacity,
        max_bytes=max_entry * capacity,
        max_entry_bytes=max_entry,
        persistence_mode=CachePersistenceMode.DISABLED,
        flush_every_mutations=max(1, capacity),
    )
    rss_before = _process_rss_bytes(os.getpid())
    tracemalloc.start()
    cache = ReplayPrefixCache(policy)
    started = time.perf_counter_ns()
    for entry_index in trace:
        entry = entries[entry_index]
        if cache.get(entry.key) is None:
            cache.put(entry)
    elapsed_ns = time.perf_counter_ns() - started
    _, heap_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_after = _process_rss_bytes(os.getpid())
    stats = cache.stats()
    lookups = stats["hits"] + stats["misses"]
    result = {
        "capacity": capacity,
        "elapsed_ms": round(elapsed_ns / 1_000_000, 3),
        "eviction_rate": round(stats["evictions"] / max(1, stats["misses"]), 6),
        "fresh_replay_count": lookups,
        "hit_rate": round(stats["hits"] / max(1, lookups), 6),
        "lookups_per_second": round(lookups / max(1, elapsed_ns) * 1_000_000_000, 3),
        "python_heap_peak_bytes": heap_peak,
        "rss_after_bytes": rss_after,
        "rss_before_bytes": rss_before,
        "rss_delta_bytes": (
            rss_after - rss_before
            if rss_after is not None and rss_before is not None
            else None
        ),
        "stats": stats,
        "verified_hint_hits": stats["hits"],
    }
    del cache
    gc.collect()
    return result


def _collect_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return {str(key) for key in value} | {
            child
            for item in value.values()
            for child in _collect_keys(item)
        }
    if isinstance(value, list):
        return {child for item in value for child in _collect_keys(item)}
    return set()


def _persistence_benchmark(
    entries: Sequence[ReplayPrefixCacheEntry],
    *,
    flush_interval: int,
    directory: Path,
) -> dict[str, Any]:
    max_entry = max(entry.estimated_bytes for entry in entries)
    policy = PrefixCachePolicy(
        max_entries=len(entries),
        max_bytes=max_entry * len(entries),
        max_entry_bytes=max_entry,
        persistence_mode=CachePersistenceMode.INDEX_ONLY,
        flush_every_mutations=flush_interval,
    )
    cache = ReplayPrefixCache(policy)
    path = directory / f"prefix-cache-{flush_interval}.json"
    cumulative_bytes = 0
    write_ns = 0
    for entry in entries:
        cache.put(entry)
        if cache.should_flush:
            started = time.perf_counter_ns()
            write_prefix_cache_index(path, cache)
            write_ns += time.perf_counter_ns() - started
            cumulative_bytes += path.stat().st_size
    if cache.stats()["mutations_since_flush"]:
        started = time.perf_counter_ns()
        write_prefix_cache_index(path, cache)
        write_ns += time.perf_counter_ns() - started
        cumulative_bytes += path.stat().st_size
    final_bytes = path.stat().st_size
    started = time.perf_counter_ns()
    recovered = read_prefix_cache_index(path)
    startup_ns = time.perf_counter_ns() - started
    index_value = json.loads(path.read_text(encoding="utf-8"))
    forbidden = sorted(_collect_keys(index_value) & _FORBIDDEN_INDEX_KEYS)
    return {
        "cumulative_write_bytes": cumulative_bytes,
        "final_index_bytes": final_bytes,
        "flush_count": cache.stats()["flushes"],
        "flush_interval": flush_interval,
        "forbidden_index_keys": forbidden,
        "recovered_entries": recovered.stats()["entries"],
        "startup_ms": round(startup_ns / 1_000_000, 3),
        "write_amplification": round(cumulative_bytes / max(1, final_bytes), 6),
        "write_ms": round(write_ns / 1_000_000, 3),
    }


def _worker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    src_root = str(Path(__file__).resolve().parents[2])
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        os.pathsep.join((src_root, existing)) if existing else src_root
    )
    return environment


def _real_core_worker_peak_rss() -> int | None:
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            [sys.executable, "-m", "ygo_effect_dsl.prototype._real_core_worker"],
            stdout=stdout,
            stderr=stderr,
            env=_worker_environment(),
        )
        peak: int | None = None
        deadline = time.monotonic() + 30
        while process.poll() is None:
            rss = _process_rss_bytes(process.pid)
            if rss is not None:
                peak = max(peak or 0, rss)
            if time.monotonic() >= deadline:
                process.kill()
                process.wait(timeout=5)
                raise TimeoutError("real-core worker RSS probe exceeded 30 seconds")
            time.sleep(0.01)
        if process.returncode != 0:
            stderr.seek(0)
            raise RuntimeError(
                "real-core worker RSS probe failed: "
                + stderr.read().decode("utf-8", errors="replace")
            )
        return peak


def run_prefix_cache_benchmark(
    *,
    entry_count: int = 4096,
    access_count: int = 20_000,
    worker_rss_runs: int = 3,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    if entry_count < 64:
        raise ValueError("entry_count must be >= 64")
    if access_count < entry_count:
        raise ValueError("access_count must be >= entry_count")
    if worker_rss_runs < 1:
        raise ValueError("worker_rss_runs must be >= 1")
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    route_paths = (
        root / "examples" / "prototype" / "real_core_effect_veiler.route.yaml",
        root
        / "examples"
        / "prototype"
        / "real_core_effect_veiler_interrupted.route.yaml",
    )
    route_entries = [
        entry for route_path in route_paths for entry in _route_prefix_entries(route_path)
    ]
    synthetic_entries = _synthetic_entries(route_entries[-1], entry_count)
    trace = _access_trace(entry_count, access_count)
    capacities = tuple(
        sorted(
            {
                min(entry_count, capacity)
                for capacity in (64, 256, 1024, RECOMMENDED_MAX_ENTRIES)
            }
        )
    )
    capacity_results = [
        _capacity_benchmark(synthetic_entries, trace, capacity)
        for capacity in capacities
    ]
    persistence_entries = synthetic_entries[:2048]
    with tempfile.TemporaryDirectory(prefix="prefix-cache-benchmark-") as temp:
        persistence = [
            _persistence_benchmark(
                persistence_entries,
                flush_interval=interval,
                directory=Path(temp),
            )
            for interval in (100, RECOMMENDED_FLUSH_EVERY_MUTATIONS)
        ]
    worker_samples = [_real_core_worker_peak_rss() for _ in range(worker_rss_runs)]
    observed_worker_peak = max(
        (sample for sample in worker_samples if sample is not None),
        default=None,
    )
    worker_budget = (
        math.ceil(observed_worker_peak * 1.25 / (1024 * 1024)) * 1024 * 1024
        if observed_worker_peak is not None
        else None
    )
    policy = recommended_prefix_cache_policy()
    run_metadata = {
        str(pool_size): (
            build_prefix_cache_run_metadata(
                policy,
                pool_size=pool_size,
                per_worker_budget_bytes=worker_budget,
            )
            if worker_budget is not None
            else None
        )
        for pool_size in (1, 2, 4, 8)
    }
    additional_budget = {
        pool_size: (
            metadata["memory_budget"]["total_bytes"]
            if metadata is not None
            else None
        )
        for pool_size, metadata in run_metadata.items()
    }
    content_audit_ok = all(
        not item["forbidden_index_keys"] for item in persistence
    )
    semantic_identity = to_canonical_data(
        {
            "access_count": access_count,
            "content_audit_ok": content_audit_ok,
            "entry_count": entry_count,
            "policy": policy.to_dict(),
            "route_entry_sizes": _entry_size_summary(route_entries),
            "route_ids": [load_route_document(path)["route_id"] for path in route_paths],
            "schema_version": PREFIX_CACHE_BENCHMARK_SCHEMA_VERSION,
            "workload": "deterministic_80_percent_hotset_v1",
        }
    )
    return {
        "benchmark_id": stable_digest(semantic_identity, prefix="prefixbench_"),
        "capacity_results": capacity_results,
        "content_audit": {
            "forbidden_keys": sorted(_FORBIDDEN_INDEX_KEYS),
            "passed": content_audit_ok,
        },
        "entry_count": entry_count,
        "persistence": {
            "disabled": {
                "recovery": "empty_cache_rebuild",
                "startup_ms": 0,
                "write_amplification": 0,
            },
            "index_only": persistence,
        },
        "recommended_policy": policy.to_dict(),
        "run_metadata_by_pool_size": run_metadata,
        "route_entry_sizes": _entry_size_summary(route_entries),
        "route_prefix_count": len(route_entries),
        "schema_version": PREFIX_CACHE_BENCHMARK_SCHEMA_VERSION,
        "worker_memory": {
            "additional_budget_bytes_by_pool_size": additional_budget,
            "formula": "cache.max_bytes + pool_size * ceil_1MiB(worker_peak_rss * 1.25)",
            "observed_peak_rss_bytes": observed_worker_peak,
            "per_worker_budget_bytes": worker_budget,
            "samples": worker_samples,
        },
        "workload": {
            "access_count": access_count,
            "distribution": "80% hot 20% of entries; 20% full population",
            "fresh_replay_semantics": (
                "verified_replay_hint requires fresh Replay on both hit and miss"
            ),
            "route_ids": semantic_identity["route_ids"],
            "synthetic_branch_count": entry_count,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="calibrate Replay prefix cache budgets")
    parser.add_argument("--entries", type=int, default=4096)
    parser.add_argument("--accesses", type=int, default=20_000)
    parser.add_argument("--worker-rss-runs", type=int, default=3)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_prefix_cache_benchmark(
        entry_count=args.entries,
        access_count=args.accesses,
        worker_rss_runs=args.worker_rss_runs,
        repo_root=args.repo_root,
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"prefix-cache-benchmark: wrote {args.out} "
            f"benchmark_id={report['benchmark_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
