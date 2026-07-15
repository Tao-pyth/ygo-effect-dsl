from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.bridge.ocgcore import (
    CARD_SCRIPTS_PROFILE_OFFICIAL,
    CardScriptsProvider,
)
from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.experiment import (
    assert_experiment_matches_route,
    load_experiment_document,
)
from ygo_effect_dsl.external.ocgcore import resolve_ocgcore_assets
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.route_dsl import (
    assert_valid_route_document,
    load_route_document,
)
from ygo_effect_dsl.runtime_imports import current_checkout_environment
from ygo_effect_dsl.spikes.general_search_benchmark import (
    CACHE_WORKER_POLICY_SCHEMA_VERSION,
    GENERAL_SEARCH_BENCHMARK_SCHEMA_VERSION,
    MEMORY_PREFLIGHT_SCHEMA_VERSION,
    PROFILES,
    REAL_CORE_BASE_EVIDENCE_SCHEMA_VERSION,
)


REAL_CORE_REPLAY_BENCHMARK_SCHEMA_VERSION = "real-core-replay-benchmark-v1"
REAL_CORE_WORKER_POLICY_SCHEMA_VERSION = "real-core-worker-policy-v1"
REAL_CORE_MEMORY_PREFLIGHT_SCHEMA_VERSION = "real-core-memory-preflight-v1"
DEFAULT_POOLS = (1, 2, 4, 8, 16)
DEFAULT_PERSISTENCE_MODES = ("disabled", "index_only")


@dataclass(frozen=True)
class ReplayBenchmarkProfile:
    profile_id: str
    workload_kind: str
    experiment_path: Path
    route_path: Path
    experiment_sha256: str
    route_sha256: str
    route_document_digest: str
    route_id: str
    terminal_state_hash: str
    event_count: int
    environment_identity: Mapping[str, Any]
    script_names: tuple[str, ...] = ()

    def public_identity(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "environment": self.environment_identity,
                "event_count": self.event_count,
                "experiment_sha256": self.experiment_sha256,
                "profile_id": self.profile_id,
                "route_document_digest": self.route_document_digest,
                "route_id": self.route_id,
                "route_sha256": self.route_sha256,
                "script_load_count": len(self.script_names),
                "terminal_state_hash": self.terminal_state_hash,
                "workload_kind": self.workload_kind,
            }
        )


@dataclass(frozen=True)
class ReplayTaskMeasurement:
    task_index: int
    route_id: str
    terminal_state_hash: str
    elapsed_seconds: float
    replay_coordinator_peak_rss_bytes: int
    worker_peak_rss_bytes: int
    process_tree_peak_rss_bytes: int
    process_output_bytes: int
    artifact_bytes: int
    artifact_count: int


class PoolRssTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: dict[int, tuple[int, int]] = {}
        self._peak_coordinator = 0
        self._peak_worker = 0
        self._peak_tree = 0
        self._peak_main = 0

    def update(self, task_index: int, coordinator: int, worker: int) -> None:
        with self._lock:
            self._current[task_index] = (coordinator, worker)
            self._peak_coordinator = max(
                self._peak_coordinator,
                sum(value[0] for value in self._current.values()),
            )
            self._peak_worker = max(
                self._peak_worker,
                sum(value[1] for value in self._current.values()),
            )
            self._peak_tree = max(
                self._peak_tree,
                sum(sum(value) for value in self._current.values()),
            )
            self._peak_main = max(self._peak_main, _current_rss_bytes())

    def finish(self, task_index: int) -> None:
        with self._lock:
            self._current.pop(task_index, None)
            self._peak_main = max(self._peak_main, _current_rss_bytes())

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "main_peak_rss_bytes": self._peak_main,
                "pool_coordinator_peak_rss_bytes": self._peak_coordinator,
                "pool_process_tree_peak_rss_bytes": self._peak_tree,
                "pool_worker_peak_rss_bytes": self._peak_worker,
            }


TaskRunner = Callable[
    [ReplayBenchmarkProfile, int, str, Path, float, PoolRssTracker],
    ReplayTaskMeasurement,
]


def _require_psutil() -> Any:
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError(
            "real-core Replay benchmark requires psutil for process-tree RSS"
        ) from exc
    return psutil


def _current_rss_bytes() -> int:
    try:
        psutil = _require_psutil()
        return int(psutil.Process().memory_info().rss)
    except (RuntimeError, OSError):
        return 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_environment_identity(route: Mapping[str, Any]) -> dict[str, Any]:
    manifest = route.get("replay", {}).get("manifest", {})
    environment = manifest.get("environment", {})
    core = environment.get("core", {})
    assets = environment.get("assets", {})
    return to_canonical_data(
        {
            "assets": {
                key: assets.get(key)
                for key in (
                    "card_database_commit",
                    "card_scripts_commit",
                    "database_sha256",
                    "lock_id",
                )
            },
            "core": {
                key: core.get(key)
                for key in (
                    "api",
                    "binary_sha256",
                    "lock_id",
                    "source_commit",
                )
            },
        }
    )


def _script_names(route: Mapping[str, Any]) -> tuple[str, ...]:
    resolution = route.get("result", {}).get("lua_script_resolution", {})
    loads = resolution.get("loads", []) if isinstance(resolution, Mapping) else []
    names = {
        str(item["requested_name"])
        for item in loads
        if isinstance(item, Mapping)
        and isinstance(item.get("requested_name"), str)
        and item.get("source_kind") == "filesystem"
    }
    names.update(("constant.lua", "utility.lua"))
    return tuple(sorted(names))


def load_benchmark_profiles(
    *,
    experiments: Mapping[str, str | Path],
    routes: Mapping[str, str | Path],
    base_evidence_path: str | Path,
) -> tuple[ReplayBenchmarkProfile, ...]:
    expected = {profile.profile_id for profile in PROFILES}
    if set(experiments) != expected or set(routes) != expected:
        raise ValueError(
            f"experiments and routes must contain exactly {sorted(expected)}"
        )
    base = json.loads(Path(base_evidence_path).read_text(encoding="utf-8"))
    if base.get("schema_version") != REAL_CORE_BASE_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported real-core base evidence schema")
    base_records = {
        str(record["profile_id"]): record for record in base.get("records", [])
    }
    if set(base_records) != expected:
        raise ValueError("real-core base evidence profile set is incomplete")

    result = []
    for definition in PROFILES:
        experiment_path = Path(experiments[definition.profile_id]).resolve()
        route_path = Path(routes[definition.profile_id]).resolve()
        experiment = load_experiment_document(experiment_path)
        route = load_route_document(route_path)
        assert_valid_route_document(route)
        assert_experiment_matches_route(experiment, route)
        terminal_state_hash = str(
            route["result"]["terminal_board"]["state_hash"]
        )
        route_digest = stable_digest(route, prefix="basedoc_")
        expected_record = base_records[definition.profile_id]
        checks = {
            "route_document_digest": route_digest,
            "route_id": str(route["route_id"]),
            "terminal_state_hash": terminal_state_hash,
        }
        for key, value in checks.items():
            if value != expected_record.get(key):
                raise ValueError(
                    f"{definition.profile_id} {key} does not match base evidence"
                )
        result.append(
            ReplayBenchmarkProfile(
                profile_id=definition.profile_id,
                workload_kind=definition.workload_kind,
                experiment_path=experiment_path,
                route_path=route_path,
                experiment_sha256=_sha256_file(experiment_path),
                route_sha256=_sha256_file(route_path),
                route_document_digest=route_digest,
                route_id=str(route["route_id"]),
                terminal_state_hash=terminal_state_hash,
                event_count=len(route["replay"]["events"]),
                environment_identity=_safe_environment_identity(route),
                script_names=_script_names(route),
            )
        )
    return tuple(result)


def _sample_process_tree(process_id: int) -> tuple[int, int]:
    psutil = _require_psutil()
    try:
        root = psutil.Process(process_id)
        coordinator = int(root.memory_info().rss)
        worker = sum(
            int(child.memory_info().rss)
            for child in root.children(recursive=True)
        )
        return coordinator, worker
    except (psutil.Error, OSError):
        return 0, 0


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    psutil = _require_psutil()
    try:
        root = psutil.Process(process.pid)
        children = root.children(recursive=True)
        for child in children:
            child.kill()
        psutil.wait_procs(children, timeout=5)
    except (psutil.Error, OSError):
        pass
    if process.poll() is None:
        process.kill()


def _parse_replay_stdout(stdout: str) -> tuple[str, str]:
    fields = {}
    for token in stdout.strip().split():
        key, separator, value = token.partition("=")
        if separator:
            fields[key] = value
    route_id = fields.get("route_id")
    state_hash = fields.get("final_state_hash")
    if not route_id or not state_hash:
        raise RuntimeError("experiment-replay output is missing semantic identifiers")
    return route_id, state_hash


def run_cli_replay_task(
    profile: ReplayBenchmarkProfile,
    task_index: int,
    persistence_mode: str,
    artifact_root: Path,
    timeout_seconds: float,
    tracker: PoolRssTracker,
) -> ReplayTaskMeasurement:
    _require_psutil()
    if persistence_mode not in DEFAULT_PERSISTENCE_MODES:
        raise ValueError(f"unsupported persistence mode {persistence_mode!r}")
    artifact_path = artifact_root / f"task-{task_index:04d}.json"
    command = [
        sys.executable,
        "-m",
        "ygo_effect_dsl",
        "experiment-replay",
        str(profile.experiment_path),
        str(profile.route_path),
        "--run-id",
        f"run_benchmark_{profile.profile_id}_{persistence_mode}_{task_index}",
        "--worker-timeout",
        str(max(30.0, timeout_seconds * 0.75)),
    ]
    if persistence_mode == "index_only":
        command.extend(["--verification-report", str(artifact_path)])
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[3],
        env=current_checkout_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    coordinator_peak = 0
    worker_peak = 0
    tree_peak = 0
    stdout = ""
    stderr = ""
    try:
        while True:
            coordinator, worker = _sample_process_tree(process.pid)
            coordinator_peak = max(coordinator_peak, coordinator)
            worker_peak = max(worker_peak, worker)
            tree_peak = max(tree_peak, coordinator + worker)
            tracker.update(task_index, coordinator, worker)
            remaining = timeout_seconds - (time.perf_counter() - started)
            if remaining <= 0:
                _terminate_process_tree(process)
                stdout, stderr = process.communicate()
                raise TimeoutError(
                    f"Replay task {profile.profile_id}/{task_index} timed out"
                )
            try:
                stdout, stderr = process.communicate(timeout=min(0.02, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        tracker.finish(task_index)
    elapsed = time.perf_counter() - started
    if process.returncode != 0:
        diagnostic = stderr.strip().splitlines()[-1:] or stdout.strip().splitlines()[-1:]
        raise RuntimeError(
            f"Replay task {profile.profile_id}/{task_index} failed: "
            f"{diagnostic[0] if diagnostic else process.returncode}"
        )
    route_id, state_hash = _parse_replay_stdout(stdout)
    if route_id != profile.route_id or state_hash != profile.terminal_state_hash:
        raise RuntimeError(
            f"Replay task {profile.profile_id}/{task_index} changed semantics"
        )
    artifact_bytes = artifact_path.stat().st_size if artifact_path.is_file() else 0
    artifact_count = 1 if artifact_path.is_file() else 0
    return ReplayTaskMeasurement(
        task_index=task_index,
        route_id=route_id,
        terminal_state_hash=state_hash,
        elapsed_seconds=elapsed,
        replay_coordinator_peak_rss_bytes=coordinator_peak,
        worker_peak_rss_bytes=worker_peak,
        process_tree_peak_rss_bytes=tree_peak,
        process_output_bytes=len(stdout.encode("utf-8")) + len(stderr.encode("utf-8")),
        artifact_bytes=artifact_bytes,
        artifact_count=artifact_count,
    )


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)
    return ordered[max(0, index)]


def _run_profile_pool(
    profile: ReplayBenchmarkProfile,
    *,
    pool_size: int,
    persistence_mode: str,
    task_count: int,
    work_root: Path,
    timeout_seconds: float,
    task_runner: TaskRunner,
) -> dict[str, Any]:
    tracker = PoolRssTracker()
    artifact_root = work_root / profile.profile_id / persistence_mode / f"pool-{pool_size}"
    artifact_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    measurements: list[ReplayTaskMeasurement] = []
    with ThreadPoolExecutor(max_workers=pool_size) as executor:
        futures = [
            executor.submit(
                task_runner,
                profile,
                task_index,
                persistence_mode,
                artifact_root,
                timeout_seconds,
                tracker,
            )
            for task_index in range(task_count)
        ]
        for future in as_completed(futures):
            measurements.append(future.result())
    elapsed = time.perf_counter() - started
    measurements.sort(key=lambda item: item.task_index)
    semantics = {
        (item.route_id, item.terminal_state_hash) for item in measurements
    }
    if semantics != {(profile.route_id, profile.terminal_state_hash)}:
        raise AssertionError(f"semantic Replay divergence for {profile.profile_id}")
    durations = [item.elapsed_seconds for item in measurements]
    semantic_payload_bytes = len(
        canonical_json(
            [
                {
                    "route_id": item.route_id,
                    "terminal_state_hash": item.terminal_state_hash,
                }
                for item in measurements
            ]
        ).encode("utf-8")
    )
    artifact_bytes = sum(item.artifact_bytes for item in measurements)
    return to_canonical_data(
        {
            "artifact_bytes": artifact_bytes,
            "artifact_count": sum(item.artifact_count for item in measurements),
            "elapsed_seconds": elapsed,
            "persistence_mode": persistence_mode,
            "pool_size": pool_size,
            "process_output_bytes": sum(
                item.process_output_bytes for item in measurements
            ),
            "profile_id": profile.profile_id,
            "replay_coordinator_peak_rss_bytes": max(
                item.replay_coordinator_peak_rss_bytes for item in measurements
            ),
            "replay_seconds": {
                "max": max(durations),
                "mean": statistics.fmean(durations),
                "p50": _percentile(durations, 0.50),
                "p95": _percentile(durations, 0.95),
            },
            "semantic_digest": stable_digest(
                {
                    "route_id": profile.route_id,
                    "terminal_state_hash": profile.terminal_state_hash,
                },
                prefix="replaybenchsem_",
            ),
            "semantic_payload_bytes": semantic_payload_bytes,
            "successful_replays": len(measurements),
            "task_count": task_count,
            "throughput_replays_per_second": task_count / elapsed,
            **tracker.snapshot(),
            "worker_peak_rss_bytes": max(
                item.worker_peak_rss_bytes for item in measurements
            ),
            "worker_process_observations": sum(
                item.worker_peak_rss_bytes > 0 for item in measurements
            ),
            "workload_kind": profile.workload_kind,
            "write_amplification": (
                artifact_bytes / semantic_payload_bytes
                if semantic_payload_bytes
                else 0.0
            ),
        }
    )


def probe_resolver_index(
    profiles: Sequence[ReplayBenchmarkProfile],
    *,
    external_root: str | Path | None = None,
) -> dict[str, Any]:
    assets = resolve_ocgcore_assets(external_root=external_root)
    names = sorted({name for profile in profiles for name in profile.script_names})
    provider = CardScriptsProvider(
        assets.scripts_root,
        profile_id=CARD_SCRIPTS_PROFILE_OFFICIAL,
        card_directories=("official",),
    )
    rss_before = _current_rss_bytes()
    cold_started = time.perf_counter()
    for name in names:
        provider.resolve_script(name)
    cold_seconds = time.perf_counter() - cold_started
    rss_after_cold = _current_rss_bytes()
    warm_started = time.perf_counter()
    for name in names:
        provider.resolve_script(name)
    warm_seconds = time.perf_counter() - warm_started
    telemetry = provider.directory_index_telemetry()
    return to_canonical_data(
        {
            "cold_resolution_seconds": cold_seconds,
            "fresh_process_amplification": (
                cold_seconds / warm_seconds if warm_seconds > 0 else None
            ),
            "index": telemetry,
            "persistent_index_adopted": False,
            "persistent_index_decision": (
                "retain checked process-local directory identity validation; "
                "persistent reuse requires a separate mutation and trust-boundary review"
            ),
            "resolved_script_count": len(names),
            "rss_delta_bytes": max(0, rss_after_cold - rss_before),
            "warm_resolution_seconds": warm_seconds,
        }
    )


def _policy(
    records: Sequence[Mapping[str, Any]],
    *,
    pool_sizes: Sequence[int],
    total_memory_bytes: int,
    logical_evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    logical_limit = int(
        logical_evidence["memory_preflight"][
            "recommended_process_memory_limit_bytes"
        ]
    )
    measured_by_pool = {
        pool: max(
            int(record["main_peak_rss_bytes"])
            + int(record["pool_process_tree_peak_rss_bytes"])
            for record in records
            if record["pool_size"] == pool
        )
        for pool in pool_sizes
    }
    memory_ceiling = min(logical_limit, total_memory_bytes // 2)
    eligible = [
        pool for pool in pool_sizes if measured_by_pool[pool] <= memory_ceiling
    ]
    max_pool = max(eligible) if eligible else min(pool_sizes)
    default_pool = min(4, max_pool)
    policy_identity = {
        "default_pool_size": default_pool,
        "logical_cache_policy_id": logical_evidence["cache_worker_policy"][
            "policy_id"
        ],
        "max_pool_size": max_pool,
        "native_state_reuse": False,
        "prefix_reuse_mode": "verified_replay_hint",
        "resolver_index_mode": "checked_process_local",
        "schema_version": REAL_CORE_WORKER_POLICY_SCHEMA_VERSION,
    }
    observed_at_max = measured_by_pool[max_pool]
    increment = 256 * 1024 * 1024
    recommended_limit = math.ceil(observed_at_max * 1.25 / increment) * increment
    memory_identity = {
        "calibrated_pool_sizes": list(pool_sizes),
        "host_total_memory_bytes": total_memory_bytes,
        "logical_memory_schema_version": MEMORY_PREFLIGHT_SCHEMA_VERSION,
        "logical_process_limit_bytes": logical_limit,
        "measured_process_tree_bytes_by_pool": measured_by_pool,
        "recommended_process_memory_limit_bytes": recommended_limit,
        "safety_factor": 1.25,
        "schema_version": REAL_CORE_MEMORY_PREFLIGHT_SCHEMA_VERSION,
    }
    return (
        {
            **policy_identity,
            "policy_id": stable_digest(policy_identity, prefix="realworkerpol_"),
        },
        {
            **memory_identity,
            "policy_id": stable_digest(memory_identity, prefix="realmemorypol_"),
        },
    )


def run_replay_benchmark(
    profiles: Sequence[ReplayBenchmarkProfile],
    *,
    pool_sizes: Sequence[int] = DEFAULT_POOLS,
    persistence_modes: Sequence[str] = DEFAULT_PERSISTENCE_MODES,
    task_count: int = 16,
    work_root: str | Path,
    logical_evidence: Mapping[str, Any],
    failure_evidence: Mapping[str, Any],
    resolver_evidence: Mapping[str, Any],
    timeout_seconds: float = 120.0,
    task_runner: TaskRunner = run_cli_replay_task,
    total_memory_bytes: int | None = None,
) -> dict[str, Any]:
    expected_profiles = {profile.profile_id for profile in PROFILES}
    if {profile.profile_id for profile in profiles} != expected_profiles:
        raise ValueError("profiles must contain the three pinned benchmark profiles")
    if not pool_sizes or any(pool < 1 for pool in pool_sizes):
        raise ValueError("pool_sizes must contain positive integers")
    if task_count < max(pool_sizes):
        raise ValueError("task_count must be >= the largest pool size")
    if set(persistence_modes) != set(DEFAULT_PERSISTENCE_MODES):
        raise ValueError("persistence modes must be disabled and index_only")
    if logical_evidence.get("schema_version") != GENERAL_SEARCH_BENCHMARK_SCHEMA_VERSION:
        raise ValueError("unsupported logical benchmark evidence")
    if logical_evidence.get("cache_worker_policy", {}).get("schema_version") != (
        CACHE_WORKER_POLICY_SCHEMA_VERSION
    ):
        raise ValueError("unsupported cache worker policy evidence")
    if not all(failure_evidence.get("verification", {}).values()):
        raise ValueError("failure recovery evidence is incomplete")
    memory_total = total_memory_bytes
    if memory_total is None:
        memory_total = int(_require_psutil().virtual_memory().total)

    root = Path(work_root)
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for profile in profiles:
        for persistence_mode in persistence_modes:
            for pool_size in pool_sizes:
                records.append(
                    _run_profile_pool(
                        profile,
                        pool_size=pool_size,
                        persistence_mode=persistence_mode,
                        task_count=task_count,
                        work_root=root,
                        timeout_seconds=timeout_seconds,
                        task_runner=task_runner,
                    )
                )
    invariants = []
    for profile in profiles:
        selected = [
            record for record in records if record["profile_id"] == profile.profile_id
        ]
        invariant = {
            "best_route_pool_independent": all(
                record["semantic_digest"] == selected[0]["semantic_digest"]
                for record in selected
            ),
            "persistence_mode_semantic_independent": len(
                {record["semantic_digest"] for record in selected}
            )
            == 1,
            "profile_id": profile.profile_id,
            "semantic_result_pool_independent": len(
                {record["semantic_digest"] for record in selected}
            )
            == 1,
        }
        if not all(value for key, value in invariant.items() if key != "profile_id"):
            raise AssertionError(f"Replay benchmark invariant failed: {invariant}")
        invariants.append(invariant)
    worker_policy, memory_preflight = _policy(
        records,
        pool_sizes=pool_sizes,
        total_memory_bytes=memory_total,
        logical_evidence=logical_evidence,
    )
    telemetry_complete = all(
        record["worker_process_observations"] == task_count for record in records
    )
    if task_runner is run_cli_replay_task and not telemetry_complete:
        raise AssertionError("active worker RSS was not observed for every Replay")
    document = to_canonical_data(
        {
            "calibration_kind": "fresh-real-core-replay-pool-workload",
            "failure_recovery": {
                "evidence_schema_version": failure_evidence.get("schema_version"),
                "semantic_report_id": failure_evidence.get("semantic_report_id"),
                "verification": failure_evidence.get("verification"),
            },
            "host": {
                "cpu_count": os.cpu_count(),
                "package_version": __version__,
                "platform": platform.platform(),
                "python": platform.python_version(),
                "total_memory_bytes": memory_total,
            },
            "invariants": invariants,
            "logical_policy_reference": {
                "cache_policy_id": logical_evidence["cache_worker_policy"][
                    "policy_id"
                ],
                "memory_schema_version": logical_evidence["memory_preflight"][
                    "schema_version"
                ],
                "schema_version": logical_evidence["schema_version"],
            },
            "memory_preflight": memory_preflight,
            "persistence_modes": list(persistence_modes),
            "pool_sizes": list(pool_sizes),
            "profile_sources": [profile.public_identity() for profile in profiles],
            "records": records,
            "resolver_index": resolver_evidence,
            "schema_version": REAL_CORE_REPLAY_BENCHMARK_SCHEMA_VERSION,
            "task_count_per_profile_pool_mode": task_count,
            "telemetry_complete": telemetry_complete,
            "worker_policy": worker_policy,
        }
    )
    return {
        **document,
        "benchmark_id": stable_digest(document, prefix="realreplaybench_"),
    }


def write_evidence(
    evidence: Mapping[str, Any],
    *,
    json_path: str | Path,
    parquet_path: str | Path | None = None,
) -> dict[str, Any]:
    destination = Path(json_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, canonical_json(evidence) + "\n")
    status: dict[str, Any] = {"path": None, "written": False}
    if parquet_path is not None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            status["diagnostic"] = (
                "pyarrow is not installed; canonical JSON is authoritative"
            )
        else:
            target = Path(parquet_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.Table.from_pylist(evidence["records"]), target)
            status = {"path": str(target), "written": True}
    return status


def _parse_mapping(values: Sequence[str], option: str) -> dict[str, str]:
    result = {}
    for raw in values:
        profile_id, separator, path = raw.partition("=")
        if not separator or not profile_id or not path:
            raise ValueError(f"{option} must use PROFILE=PATH")
        if profile_id in result:
            raise ValueError(f"{option} repeats profile {profile_id!r}")
        result[profile_id] = path
    return result


def main() -> int:
    parser = argparse.ArgumentParser(prog="real-core-replay-benchmark")
    parser.add_argument("--experiment", action="append", default=[])
    parser.add_argument("--route", action="append", default=[])
    parser.add_argument("--base-evidence", required=True)
    parser.add_argument("--logical-evidence", required=True)
    parser.add_argument("--failure-evidence", required=True)
    parser.add_argument("--pool-sizes", default="1,2,4,8,16")
    parser.add_argument("--task-count", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--external-root")
    parser.add_argument("--work-root")
    parser.add_argument("--out", required=True)
    parser.add_argument("--parquet-out")
    args = parser.parse_args()
    experiments = _parse_mapping(args.experiment, "--experiment")
    routes = _parse_mapping(args.route, "--route")
    profiles = load_benchmark_profiles(
        experiments=experiments,
        routes=routes,
        base_evidence_path=args.base_evidence,
    )
    logical = json.loads(Path(args.logical_evidence).read_text(encoding="utf-8"))
    failure = json.loads(Path(args.failure_evidence).read_text(encoding="utf-8"))
    resolver = probe_resolver_index(profiles, external_root=args.external_root)
    pools = tuple(int(value) for value in args.pool_sizes.split(",") if value)

    if args.work_root:
        work_root = Path(args.work_root)
        evidence = run_replay_benchmark(
            profiles,
            pool_sizes=pools,
            task_count=args.task_count,
            work_root=work_root,
            logical_evidence=logical,
            failure_evidence=failure,
            resolver_evidence=resolver,
            timeout_seconds=args.timeout,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="real-core-replay-benchmark-") as temp:
            evidence = run_replay_benchmark(
                profiles,
                pool_sizes=pools,
                task_count=args.task_count,
                work_root=temp,
                logical_evidence=logical,
                failure_evidence=failure,
                resolver_evidence=resolver,
                timeout_seconds=args.timeout,
            )
    parquet = write_evidence(
        evidence,
        json_path=args.out,
        parquet_path=args.parquet_out,
    )
    print(
        "real-core-replay-benchmark: ok "
        f"benchmark_id={evidence['benchmark_id']} "
        f"records={len(evidence['records'])} "
        f"policy_id={evidence['worker_policy']['policy_id']} "
        f"parquet={str(parquet['written']).lower()} out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
