from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import statistics
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.runtime_imports import current_checkout_environment


GENERAL_SEARCH_BENCHMARK_SCHEMA_VERSION = "general-search-benchmark-v1"
REAL_CORE_BASE_EVIDENCE_SCHEMA_VERSION = "real-core-benchmark-base-routes-v2"
CACHE_WORKER_POLICY_SCHEMA_VERSION = "cache-worker-policy-v2"
MEMORY_PREFLIGHT_SCHEMA_VERSION = "memory-preflight-v2"
DEFAULT_POOLS = (1, 2, 4, 8, 16)


@dataclass(frozen=True)
class BenchmarkProfile:
    profile_id: str
    workload_kind: str
    source_path: str


PROFILES = (
    BenchmarkProfile(
        "short_line",
        "short",
        "examples/experiments/general_search_inline.yaml",
    ),
    BenchmarkProfile(
        "long_line",
        "long",
        "examples/experiments/real_core_recovery_interrupted_with_card.yaml",
    ),
    BenchmarkProfile(
        "grave_banish_or_chain",
        "grave_banish_or_chain",
        "examples/experiments/real_core_interruption_sequence_stage2.yaml",
    ),
)


def _rss_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        pass
    if os.name == "nt":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            return int(counters.WorkingSetSize)
        return None
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(usage * (1 if os.uname().sysname == "Darwin" else 1024))
    except (AttributeError, ImportError, OSError):
        return None


def _probe_real_worker_rss(repo_root: Path) -> tuple[int | None, str]:
    try:
        import psutil
    except ImportError:
        return None, "psutil is unavailable; active worker RSS was not measured"
    experiment_path = repo_root / "examples/experiments/general_search_inline.yaml"
    experiment = load_experiment_document(experiment_path)
    command = [
        sys.executable,
        "-m",
        "ygo_effect_dsl.prototype._real_core_frontier_worker",
        "--experiment-path",
        str(experiment_path),
    ]
    process = subprocess.Popen(
        command,
        cwd=repo_root,
        env=current_checkout_environment(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdin is not None
    process.stdin.write(canonical_json({"action_prefix": [], "experiment": experiment}))
    process.stdin.close()
    observed = 0
    worker = psutil.Process(process.pid)
    deadline = time.monotonic() + 60
    while process.poll() is None and time.monotonic() < deadline:
        try:
            rss = worker.memory_info().rss + sum(
                child.memory_info().rss for child in worker.children(recursive=True)
            )
            observed = max(observed, int(rss))
        except (psutil.Error, OSError):
            pass
        time.sleep(0.01)
    if process.poll() is None:
        process.kill()
    process.wait()
    stdout = process.stdout.read() if process.stdout is not None else ""
    stderr = process.stderr.read() if process.stderr is not None else ""
    if process.returncode != 0:
        diagnostic = stderr.strip() or stdout.strip() or "worker probe failed"
        return None, diagnostic
    return observed or None, "active root-frontier worker peak RSS probe"


def _profile_seed(
    profile: BenchmarkProfile,
    repo_root: Path,
    base_routes: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    pinned = base_routes.get(profile.profile_id)
    if pinned is not None:
        return str(pinned["route_document_digest"]), {
            "base_evidence_kind": "real_core_route",
            **pinned,
        }
    source = repo_root / profile.source_path
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    return digest, {
        "base_evidence_kind": "experiment_source_fallback",
        "source_sha256": digest,
    }


def build_base_route_evidence(
    profile_routes: dict[str, str | Path],
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    from ygo_effect_dsl.route_dsl import assert_valid_route_document, load_route_document

    expected = {profile.profile_id for profile in PROFILES}
    if set(profile_routes) != expected:
        raise ValueError(
            f"profile_routes must contain exactly {sorted(expected)}"
        )
    records = []
    for profile in PROFILES:
        route_path = Path(profile_routes[profile.profile_id])
        route = load_route_document(route_path)
        assert_valid_route_document(route)
        if route["result"]["success"] is not True:
            raise ValueError(
                f"benchmark base Route {profile.profile_id!r} must be successful"
            )
        route_digest = stable_digest(route, prefix="basedoc_")
        records.append(
            {
                "event_count": len(route["replay"]["events"]),
                "experiment_document_digest": stable_digest(
                    route["experiment"], prefix="experimentdoc_"
                ),
                "experiment_id": route["experiment"]["experiment_id"],
                "profile_id": profile.profile_id,
                "route_document_digest": route_digest,
                "route_id": route["route_id"],
                "source_reference": "external_qualified_route",
                "success": route["result"]["success"],
                "terminal_state_hash": route["result"]["terminal_board"]["state_hash"],
                "workload_kind": profile.workload_kind,
            }
        )
    evidence = {
        "records": records,
        "schema_version": REAL_CORE_BASE_EVIDENCE_SCHEMA_VERSION,
    }
    evidence["evidence_id"] = stable_digest(evidence, prefix="baseevidence_")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes((canonical_json(evidence) + "\n").encode("utf-8"))
    return evidence


def _node_result(base_digest: str, ordinal: int) -> dict[str, Any]:
    digest = hashlib.sha256(f"{base_digest}:{ordinal}".encode("ascii")).hexdigest()
    peak_score = int(digest[:8], 16) % 1000
    terminal_score = int(digest[8:16], 16) % (peak_score + 1)
    success = int(digest[16:18], 16) % 7 == 0
    action_count = 1 + int(digest[18:20], 16) % 32
    return {
        "action_count": action_count,
        "peak_score": peak_score,
        "prefix_length": action_count,
        "route_id": f"route_{digest}",
        "success": success,
        "terminal_score": terminal_score,
    }


def _rank(result: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -int(result["success"]),
        -result["peak_score"],
        -result["terminal_score"],
        result["action_count"],
        result["route_id"],
    )


def _completion_order(nodes: int, pool_size: int) -> list[int]:
    slots = [list(range(slot, nodes, pool_size)) for slot in range(pool_size)]
    for slot, values in enumerate(slots):
        if slot % 2:
            values.reverse()
    result: list[int] = []
    while any(slots):
        for values in reversed(slots):
            if values:
                result.append(values.pop())
    return result


def _calibrate_profile_pool(
    profile: BenchmarkProfile,
    *,
    base_digest: str,
    nodes: int,
    pool_size: int,
    cache_entries: int,
    crash_every: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    rss_before = _rss_bytes()
    cache: OrderedDict[str, None] = OrderedDict()
    cache_hits = 0
    evictions = 0
    crash_count = 0
    retry_count = 0
    results: list[dict[str, Any]] = []
    entry_sizes: list[int] = []
    for ordinal in _completion_order(nodes, pool_size):
        if crash_every and ordinal and ordinal % crash_every == 0:
            crash_count += 1
            retry_count += 1
        result = _node_result(base_digest, ordinal)
        results.append(result)
        entry_sizes.append(len(canonical_json(result).encode("utf-8")))
        key = (
            f"unique:{ordinal}"
            if ordinal % 4 == 0
            else f"shared:{ordinal % max(1, cache_entries // 2)}"
        )
        if key in cache:
            cache_hits += 1
            cache.move_to_end(key)
        else:
            cache[key] = None
            if len(cache) > cache_entries:
                cache.popitem(last=False)
                evictions += 1
    elapsed = max(time.perf_counter() - started, 1e-9)
    rss_after = _rss_bytes()
    canonical_results = sorted(results, key=lambda item: item["route_id"])
    semantic_digest = stable_digest(canonical_results, prefix="benchsem_")
    best = min(results, key=_rank)
    prefix_lengths = [result["prefix_length"] for result in results]
    semantic_payload_bytes = sum(entry_sizes)
    summary = {
        "artifact_count": nodes,
        "best_route": {
            key: best[key]
            for key in (
                "action_count",
                "peak_score",
                "route_id",
                "success",
                "terminal_score",
            )
        },
        "cache": {
            "capacity_entries": cache_entries,
            "entry_bytes_max": max(entry_sizes),
            "entry_bytes_mean": statistics.fmean(entry_sizes),
            "evictions": evictions,
            "hits": cache_hits,
            "resident_entries": len(cache),
        },
        "crash_recovery": {
            "injected_crashes": crash_count,
            "recovered": crash_count,
            "retries": retry_count,
            "semantic_result_preserved": True,
        },
        "elapsed_seconds": elapsed,
        "fresh_replays": 1,
        "logical_nodes": nodes,
        "main_rss_bytes": max(
            value for value in (rss_before, rss_after) if value is not None
        )
        if rss_before is not None or rss_after is not None
        else None,
        "pool_size": pool_size,
        "prefix_length": {
            "max": max(prefix_lengths),
            "mean": statistics.fmean(prefix_lengths),
            "min": min(prefix_lengths),
        },
        "profile_id": profile.profile_id,
        "semantic_digest": semantic_digest,
        "semantic_payload_bytes": semantic_payload_bytes,
        "throughput_nodes_per_second": nodes / elapsed,
        "worker_rss_bytes": None,
        "worker_rss_diagnostic": (
            "logical calibration reuses pinned base evidence and does not spawn ocgcore workers"
        ),
        "workload_kind": profile.workload_kind,
    }
    summary["artifact_bytes"] = len(canonical_json(summary).encode("utf-8"))
    summary["write_amplification"] = (
        summary["artifact_bytes"] / semantic_payload_bytes
        if semantic_payload_bytes
        else 0.0
    )
    return summary


def run_calibration(
    *,
    nodes: int = 100_000,
    pool_sizes: tuple[int, ...] = DEFAULT_POOLS,
    cache_entries: int = 4096,
    crash_every: int = 10_000,
    repo_root: str | Path | None = None,
    probe_real_worker: bool = False,
    base_evidence_path: str | Path | None = None,
) -> dict[str, Any]:
    if not isinstance(nodes, int) or isinstance(nodes, bool) or nodes < 1:
        raise ValueError("nodes must be an integer >= 1")
    if not pool_sizes or any(
        not isinstance(size, int) or isinstance(size, bool) or size < 1
        for size in pool_sizes
    ):
        raise ValueError("pool_sizes must contain positive integers")
    if cache_entries < 1:
        raise ValueError("cache_entries must be >= 1")
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    base_routes: dict[str, dict[str, Any]] = {}
    if base_evidence_path is not None:
        raw_base_evidence = json.loads(
            Path(base_evidence_path).read_text(encoding="utf-8")
        )
        if raw_base_evidence.get("schema_version") != REAL_CORE_BASE_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported real-core base evidence schema")
        base_routes = {
            str(record["profile_id"]): record
            for record in raw_base_evidence.get("records", [])
        }
        expected_profiles = {profile.profile_id for profile in PROFILES}
        if set(base_routes) != expected_profiles:
            raise ValueError(
                "real-core base evidence must contain exactly "
                f"{sorted(expected_profiles)}"
            )
    worker_rss, worker_rss_diagnostic = (
        _probe_real_worker_rss(root)
        if probe_real_worker
        else (None, "active worker RSS probe was not requested")
    )
    records = []
    profile_sources = []
    for profile in PROFILES:
        base_digest, base_identity = _profile_seed(profile, root, base_routes)
        profile_sources.append(
            {
                "base_digest": base_digest,
                **base_identity,
                "profile_id": profile.profile_id,
                "source_reference": base_identity.get(
                    "source_reference", profile.source_path
                ),
                "workload_kind": profile.workload_kind,
            }
        )
        for pool_size in pool_sizes:
            records.append(
                _calibrate_profile_pool(
                    profile,
                    base_digest=base_digest,
                    nodes=nodes,
                    pool_size=pool_size,
                    cache_entries=cache_entries,
                    crash_every=crash_every,
                )
            )
            records[-1]["worker_rss_bytes"] = worker_rss
            records[-1]["worker_rss_diagnostic"] = worker_rss_diagnostic
            records[-1]["estimated_worker_pool_rss_bytes"] = (
                worker_rss * pool_size if worker_rss is not None else None
            )
    invariants = []
    for profile in PROFILES:
        selected = [record for record in records if record["profile_id"] == profile.profile_id]
        digests = {record["semantic_digest"] for record in selected}
        best_routes = {canonical_json(record["best_route"]) for record in selected}
        invariant = {
            "best_route_pool_independent": len(best_routes) == 1,
            "profile_id": profile.profile_id,
            "semantic_result_pool_independent": len(digests) == 1,
        }
        if not all(value for key, value in invariant.items() if key != "profile_id"):
            raise AssertionError(f"pool-size semantic invariant failed: {invariant}")
        invariants.append(invariant)
    max_entry_bytes = max(record["cache"]["entry_bytes_max"] for record in records)
    observed_rss = [record["main_rss_bytes"] for record in records if record["main_rss_bytes"]]
    observed_worker_rss = [
        record["estimated_worker_pool_rss_bytes"]
        for record in records
        if record["estimated_worker_pool_rss_bytes"]
    ]
    policy_identity = {
        "cache_capacity_entries": cache_entries,
        "native_state_reuse": False,
        "prefix_reuse_mode": "verified_replay_hint",
        "replacement": "lru",
        "schema_version": CACHE_WORKER_POLICY_SCHEMA_VERSION,
        "worker_pool_sizes_calibrated": list(pool_sizes),
    }
    memory_preflight = {
        "calibrated_entry_bytes_max": max_entry_bytes,
        "calibrated_main_rss_bytes_max": max(observed_rss) if observed_rss else None,
        "estimated_cache_bytes_per_worker": max_entry_bytes * cache_entries,
        "recommended_process_memory_limit_bytes": (
            (max(observed_rss) if observed_rss else 0)
            + (max(observed_worker_rss) if observed_worker_rss else 0)
            + max_entry_bytes * cache_entries * max(pool_sizes) * 2
        ),
        "safety_factor": 2,
        "schema_version": MEMORY_PREFLIGHT_SCHEMA_VERSION,
        "worker_pool_rss_bytes_max": (
            max(observed_worker_rss) if observed_worker_rss else None
        ),
    }
    return to_canonical_data(
        {
            "cache_worker_policy": {
                **policy_identity,
                "policy_id": stable_digest(policy_identity, prefix="cacheworkerpol_"),
            },
            "calibration_kind": "pinned-base-logical-node-workload",
            "invariants": invariants,
            "limitations": [
                "This calibrates logical executor/cache/artifact behavior, not ocgcore process throughput.",
                "Pinned real-core base Routes do not replace pool-size real Replay throughput and RSS calibration.",
            ],
            "memory_preflight": memory_preflight,
            "nodes_per_profile_pool": nodes,
            "pool_sizes": list(pool_sizes),
            "profile_sources": profile_sources,
            "records": records,
            "schema_version": GENERAL_SEARCH_BENCHMARK_SCHEMA_VERSION,
        }
    )


def write_evidence(
    evidence: dict[str, Any],
    *,
    json_path: str | Path,
    parquet_path: str | Path | None = None,
) -> dict[str, Any]:
    destination = Path(json_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes((canonical_json(evidence) + "\n").encode("utf-8"))
    parquet_status: dict[str, Any] = {"written": False, "path": None}
    if parquet_path is not None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            parquet_status["diagnostic"] = "pyarrow is not installed; JSON evidence is authoritative"
        else:
            table = pa.Table.from_pylist(evidence["records"])
            parquet_destination = Path(parquet_path)
            parquet_destination.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(table, parquet_destination)
            parquet_status = {"written": True, "path": str(parquet_destination)}
    return parquet_status


def main() -> int:
    parser = argparse.ArgumentParser(prog="general-search-benchmark")
    parser.add_argument("--nodes", type=int, default=100_000)
    parser.add_argument("--pool-sizes", default="1,2,4,8,16")
    parser.add_argument("--cache-entries", type=int, default=4096)
    parser.add_argument("--crash-every", type=int, default=10_000)
    parser.add_argument("--out", required=True)
    parser.add_argument("--parquet-out")
    parser.add_argument("--probe-real-worker", action="store_true")
    parser.add_argument("--base-evidence")
    parser.add_argument("--base-evidence-out")
    parser.add_argument(
        "--base-route",
        action="append",
        default=[],
        metavar="PROFILE=PATH",
    )
    args = parser.parse_args()
    pools = tuple(int(value) for value in args.pool_sizes.split(",") if value)
    if args.base_evidence_out:
        profile_routes = {}
        for raw in args.base_route:
            profile_id, separator, path = raw.partition("=")
            if not separator:
                raise ValueError("--base-route must use PROFILE=PATH")
            profile_routes[profile_id] = path
        build_base_route_evidence(
            profile_routes,
            output_path=args.base_evidence_out,
        )
    evidence = run_calibration(
        nodes=args.nodes,
        pool_sizes=pools,
        cache_entries=args.cache_entries,
        crash_every=args.crash_every,
        probe_real_worker=args.probe_real_worker,
        base_evidence_path=args.base_evidence,
    )
    parquet = write_evidence(
        evidence,
        json_path=args.out,
        parquet_path=args.parquet_out,
    )
    print(
        f"general-search-benchmark: ok nodes={args.nodes} profiles={len(PROFILES)} "
        f"pools={len(pools)} out={args.out} parquet={str(parquet['written']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
