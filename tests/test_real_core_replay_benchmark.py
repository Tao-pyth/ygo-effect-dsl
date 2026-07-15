from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.bridge.ocgcore import FilesystemScriptProvider
from ygo_effect_dsl.spikes.general_search_benchmark import (
    CACHE_WORKER_POLICY_SCHEMA_VERSION,
    GENERAL_SEARCH_BENCHMARK_SCHEMA_VERSION,
    MEMORY_PREFLIGHT_SCHEMA_VERSION,
)
from ygo_effect_dsl.spikes.real_core_replay_benchmark import (
    REAL_CORE_MEMORY_PREFLIGHT_SCHEMA_VERSION,
    REAL_CORE_REPLAY_BENCHMARK_SCHEMA_VERSION,
    REAL_CORE_WORKER_POLICY_SCHEMA_VERSION,
    PoolRssTracker,
    ReplayBenchmarkProfile,
    ReplayTaskMeasurement,
    run_replay_benchmark,
    write_evidence,
)


def _profiles(tmp_path: Path) -> tuple[ReplayBenchmarkProfile, ...]:
    return tuple(
        ReplayBenchmarkProfile(
            profile_id=profile_id,
            workload_kind=workload_kind,
            experiment_path=tmp_path / f"{profile_id}.yaml",
            route_path=tmp_path / f"{profile_id}.route.yaml",
            experiment_sha256="a" * 64,
            route_sha256="b" * 64,
            route_document_digest=f"basedoc_{profile_id}",
            route_id=f"route_{profile_id}",
            terminal_state_hash=f"state_{profile_id}",
            event_count=5,
            environment_identity={"core": {"api": "11.0"}},
        )
        for profile_id, workload_kind in (
            ("short_line", "short"),
            ("long_line", "long"),
            ("grave_banish_or_chain", "grave_banish_or_chain"),
        )
    )


def _logical_evidence() -> dict[str, object]:
    return {
        "schema_version": GENERAL_SEARCH_BENCHMARK_SCHEMA_VERSION,
        "cache_worker_policy": {
            "schema_version": CACHE_WORKER_POLICY_SCHEMA_VERSION,
            "policy_id": "cacheworkerpol_test",
        },
        "memory_preflight": {
            "schema_version": MEMORY_PREFLIGHT_SCHEMA_VERSION,
            "recommended_process_memory_limit_bytes": 2 * 1024**3,
        },
    }


def _fake_task(
    profile: ReplayBenchmarkProfile,
    task_index: int,
    persistence_mode: str,
    _artifact_root: Path,
    _timeout_seconds: float,
    tracker: PoolRssTracker,
) -> ReplayTaskMeasurement:
    tracker.update(task_index, 10_000_000, 20_000_000)
    tracker.finish(task_index)
    return ReplayTaskMeasurement(
        task_index=task_index,
        route_id=profile.route_id,
        terminal_state_hash=profile.terminal_state_hash,
        elapsed_seconds=0.01 + task_index / 1000,
        replay_coordinator_peak_rss_bytes=10_000_000,
        worker_peak_rss_bytes=20_000_000,
        process_tree_peak_rss_bytes=30_000_000,
        process_output_bytes=128,
        artifact_bytes=256 if persistence_mode == "index_only" else 0,
        artifact_count=1 if persistence_mode == "index_only" else 0,
    )


def test_real_replay_calibration_is_pool_and_persistence_independent(
    tmp_path: Path,
) -> None:
    evidence = run_replay_benchmark(
        _profiles(tmp_path),
        pool_sizes=(1, 2),
        task_count=2,
        work_root=tmp_path / "work",
        logical_evidence=_logical_evidence(),
        failure_evidence={
            "schema_version": "real-core-parallel-stress-v2",
            "semantic_report_id": "realcorestress_test",
            "verification": {"process_cleanup_observed": True},
        },
        resolver_evidence={
            "persistent_index_adopted": False,
            "index": {"persistence": "process_local_only"},
        },
        task_runner=_fake_task,
        total_memory_bytes=8 * 1024**3,
    )

    assert evidence["schema_version"] == REAL_CORE_REPLAY_BENCHMARK_SCHEMA_VERSION
    assert len(evidence["records"]) == 12
    assert all(item["semantic_result_pool_independent"] for item in evidence["invariants"])
    assert all(
        item["persistence_mode_semantic_independent"]
        for item in evidence["invariants"]
    )
    assert evidence["worker_policy"]["schema_version"] == (
        REAL_CORE_WORKER_POLICY_SCHEMA_VERSION
    )
    assert evidence["memory_preflight"]["schema_version"] == (
        REAL_CORE_MEMORY_PREFLIGHT_SCHEMA_VERSION
    )
    assert evidence["telemetry_complete"] is True

    destination = tmp_path / "evidence.json"
    status = write_evidence(evidence, json_path=destination)
    assert status == {"path": None, "written": False}
    assert json.loads(destination.read_text(encoding="utf-8"))["benchmark_id"] == (
        evidence["benchmark_id"]
    )


def test_filesystem_script_provider_reports_process_local_index_telemetry(
    tmp_path: Path,
) -> None:
    (tmp_path / "constant.lua").write_text("return 1\n", encoding="utf-8")
    provider = FilesystemScriptProvider(tmp_path)

    provider.resolve_script("constant.lua")
    provider.resolve_script("constant.lua")
    telemetry = provider.directory_index_telemetry()

    assert telemetry["persistence"] == "process_local_only"
    assert telemetry["builds"] == 1
    assert telemetry["hits"] >= 1
    assert telemetry["directories"] == 1
    assert telemetry["entries"] == 1
    assert telemetry["estimated_name_bytes"] > 0


def test_checked_real_replay_evidence_is_sanitized_and_content_addressed() -> None:
    path = Path(__file__).parents[1] / (
        "docs/adr/evidence/0128_real_core_replay_pool.json"
    )
    raw = path.read_text(encoding="utf-8")
    evidence = json.loads(raw)
    benchmark_id = evidence.pop("benchmark_id")

    assert benchmark_id == stable_digest(evidence, prefix="realreplaybench_")
    assert evidence["schema_version"] == REAL_CORE_REPLAY_BENCHMARK_SCHEMA_VERSION
    assert evidence["task_count_per_profile_pool_mode"] == 16
    assert len(evidence["records"]) == 30
    assert evidence["telemetry_complete"] is True
    assert evidence["worker_policy"]["default_pool_size"] == 4
    assert evidence["worker_policy"]["max_pool_size"] == 8
    assert all(item["semantic_result_pool_independent"] for item in evidence["invariants"])
    assert all(
        item["persistence_mode_semantic_independent"]
        for item in evidence["invariants"]
    )
    for forbidden in (
        "D:\\\\",
        "D:/",
        "card_code",
        "opening_hand",
        "source_path",
        "route_path",
        "experiment_path",
    ):
        assert forbidden not in raw
