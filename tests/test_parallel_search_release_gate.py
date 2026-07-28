from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from ygo_effect_dsl.cli.cmd_qualification import (
    cmd_parallel_search_collect,
    cmd_parallel_search_gate,
    cmd_parallel_search_records,
)
from ygo_effect_dsl.cli import cmd_qualification as qualification_module
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.io_atomic import sha256_file
from ygo_effect_dsl.spikes.parallel_search_release_gate import (
    PARALLEL_SEARCH_RECORD_INPUT_MANIFEST_SCHEMA_VERSION,
    PARALLEL_SEARCH_RELEASE_GATE_SCHEMA_VERSION,
    PARALLEL_SEARCH_RELEASE_RECORDS_PENDING_SCHEMA_VERSION,
    PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION,
    build_parallel_search_release_record,
    build_parallel_search_release_records,
    evaluate_parallel_search_release_gate,
    expand_parallel_search_release_record_inputs,
    _record_bundle_witness,
    read_parallel_search_release_gate,
    read_parallel_search_release_records,
    summarize_parallel_search_release_source,
    validate_parallel_search_release_gate,
    validate_parallel_search_release_records,
    write_parallel_search_release_gate,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO_ROOT / "docs" / "release" / "evidence" / "parallel_search_gate.json"
STRESS_EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "search" / "evidence" / "real_core_parallel_stress.json"
)
LOGICAL_100K_EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "adr" / "evidence" / "0105_general_search_100k.json"
)
REPLAY_BENCHMARK_EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "adr" / "evidence" / "0128_real_core_replay_pool.json"
)


def _record(
    profile: str,
    pool: int,
    repeat: int,
    wall: float,
    *,
    worker_kind: str = "real_core",
    semantic: str | None = None,
) -> dict[str, object]:
    semantic_digest = semantic or f"semantic_{profile}"
    return {
        "best_route_id": f"route_{profile}",
        "committed_nodes": 100_000,
        "lineage_digest": f"lineage_{profile}",
        "node_budget": 100_000,
        "pool_size": pool,
        "profile_id": profile,
        "repeat_index": repeat,
        "replay_budget": 100_000,
        "rss_peak_bytes": 256_000_000 + pool,
        "semantic_digest": semantic_digest,
        "timing_censored": False,
        "wall_seconds": wall,
        "worker_kind": worker_kind,
    }


def _passing_records() -> list[dict[str, object]]:
    profiles = {
        "grave_banish_or_chain": {1: 100.0, 2: 80.0, 4: 70.0},
        "long_line": {1: 120.0, 2: 95.0, 4: 89.0},
        "short_line": {1: 80.0, 2: 70.0, 4: 74.0},
    }
    records: list[dict[str, object]] = []
    for profile, by_pool in profiles.items():
        for pool, base_wall in by_pool.items():
            for repeat in range(5):
                records.append(_record(profile, pool, repeat, base_wall + repeat * 0.1))
    return records


def _source_summaries() -> list[dict[str, object]]:
    summaries = []
    for path in (
        STRESS_EVIDENCE_PATH,
        LOGICAL_100K_EVIDENCE_PATH,
        REPLAY_BENCHMARK_EVIDENCE_PATH,
    ):
        summary, _rejections = summarize_parallel_search_release_source(
            json.loads(path.read_text(encoding="utf-8")),
            source_path=path,
        )
        summaries.append(summary)
    return summaries


def _manifest_for_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    manifest = []
    for record in records:
        report_name = (
            f"{record['profile_id']}-{record['pool_size']}-"
            f"{record['repeat_index']}.json"
        )
        manifest.append(
            {
                "node_budget": record["node_budget"],
                "path_redacted": True,
                "pool_size": record["pool_size"],
                "profile_id": record["profile_id"],
                "repeat_index": record["repeat_index"],
                "replay_budget": record["replay_budget"],
                "report_path_name": report_name,
                "report_sha256": hashlib.sha256(report_name.encode("utf-8")).hexdigest(),
                "rss_peak_bytes": record["rss_peak_bytes"],
                "timing_censored": record["timing_censored"],
                "worker_kind": record["worker_kind"],
            }
        )
    return sorted(
        manifest,
        key=lambda entry: (
            entry["profile_id"],
            entry["pool_size"],
            entry["repeat_index"],
            entry["report_sha256"],
            entry.get("route_sha256") or "",
        ),
    )


def _records_document(records: list[dict[str, object]]) -> dict[str, object]:
    document = {
        "input_manifest": _manifest_for_records(records),
        "records": records,
        "schema_version": PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION,
    }
    document["evidence_id"] = stable_digest(document, prefix="parsearchrecords_")
    return document


def _search_report(*, pool_size: int = 1) -> dict[str, object]:
    strategy_parameters: dict[str, object] = {
        "parallel": {
            "pool_size": pool_size,
            "schema_version": "parallel-search-policy-v1",
        }
    }
    return {
        "artifact_commit": {
            "route_id": "route_fixture",
            "route_sha256": "a" * 64,
            "schema_version": "search-artifact-commit-v1",
            "status": "committed",
        },
        "best_route": {
            "action_count": 2,
            "action_ids": ["act_a", "act_b"],
            "peak_score": 7,
            "route_id": "route_fixture",
            "success": True,
            "terminal_score": 7,
        },
        "coverage": {
            "coverage_id": "searchcoverage_fixture",
            "coverage_status": "best_observed",
            "schema_version": "search-coverage-v1",
        },
        "elapsed_seconds": 12.5,
        "experiment_digest": "experiment_" + "b" * 64,
        "experiment_id": "fixture_experiment",
        "nodes": 100_000,
        "replays": 100_000,
        "report_schema_version": "search-run-report-v1",
        "route_ranking": {
            "best_route_id": "route_fixture",
            "ranking_id": "routerank_fixture",
            "schema_version": "route-ranking-v1",
        },
        "schema_version": "search-run-result-v5",
        "status": "complete",
        "strategy_evidence": {
            "evidence_id": "strategyevidence_fixture",
            "schema_version": "search-strategy-evidence-v1",
        },
        "strategy_id": "random_search_v1",
        "strategy_parameters": strategy_parameters,
        "strategy_schema_version": "random-search-strategy-v1",
        "termination_reason": "max_nodes",
    }


def _record_input(report: Path, *, pool_size: int = 1) -> dict[str, object]:
    return {
        "node_budget": 100_000,
        "pool_size": pool_size,
        "profile_id": "short_line",
        "repeat_index": 0,
        "replay_budget": 100_000,
        "report_path": str(report),
        "rss_peak_bytes": 512_000_000,
    }


def test_parallel_search_release_gate_accepts_measured_real_core_speedup() -> None:
    evidence = evaluate_parallel_search_release_gate(_passing_records())
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == PARALLEL_SEARCH_RELEASE_GATE_SCHEMA_VERSION
    assert evidence["passed"] is True
    assert evidence["rejection_reasons"] == []
    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="parsearchgate_",
    )
    assert evidence["gate"]["min_committed_nodes"] == 100_000
    assert evidence["gate"]["min_node_budget"] == 100_000
    assert evidence["gate"]["min_replay_budget"] == 100_000
    assert sum(
        1 for profile in evidence["profile_results"] if profile["speedup_pass"]
    ) == 2


def test_parallel_search_release_gate_rejects_synthetic_or_semantic_drift() -> None:
    records = _passing_records()
    records[0]["worker_kind"] = "synthetic_adapter"
    records[-1]["semantic_digest"] = "semantic_drift"

    evidence = evaluate_parallel_search_release_gate(records)

    assert evidence["passed"] is False
    assert any("not real_core evidence" in reason for reason in evidence["rejection_reasons"])
    assert any("semantic_digest differs" in reason for reason in evidence["rejection_reasons"])


def test_parallel_search_release_gate_writes_content_addressed_json(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "parallel-search-gate.json"
    bundle = _records_document(_passing_records())
    evidence = write_parallel_search_release_gate(
        bundle["records"],
        record_bundle=_record_bundle_witness(bundle),
        output_path=destination,
    )
    persisted = json.loads(destination.read_text(encoding="utf-8"))

    assert persisted == evidence
    assert read_parallel_search_release_gate(destination) == evidence
    assert persisted["passed"] is True


def test_parallel_search_release_gate_rejects_tampered_evidence_id() -> None:
    evidence = evaluate_parallel_search_release_gate(_passing_records())
    evidence["records"][0]["wall_seconds"] = 999.0

    with pytest.raises(ValueError, match="evidence_id mismatch"):
        validate_parallel_search_release_gate(evidence)


def test_parallel_search_release_gate_rejects_invalid_input_sources() -> None:
    evidence = evaluate_parallel_search_release_gate(_passing_records())
    evidence["input_sources"] = {"path": "not-a-list"}
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")

    with pytest.raises(ValueError, match="input_sources"):
        validate_parallel_search_release_gate(evidence)


def test_parallel_search_release_gate_rejects_input_source_path_leak() -> None:
    evidence = evaluate_parallel_search_release_gate(
        _passing_records(),
        input_sources=[
            {
                "path_redacted": True,
                "release_record_count": 45,
                "source_path_name": "records.json",
                "source_record_count": 45,
            }
        ],
    )
    evidence["input_sources"][0]["unredacted_path"] = "C:\\benchmarks\\records.json"
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")

    with pytest.raises(ValueError, match="input source path must be redacted"):
        validate_parallel_search_release_gate(evidence)


def test_parallel_search_release_gate_rejects_record_bundle_path_leak() -> None:
    bundle = _records_document(_passing_records())
    witness = _record_bundle_witness(bundle)
    evidence = evaluate_parallel_search_release_gate(
        bundle["records"],
        record_bundle=witness,
    )
    evidence["record_bundle"]["source_path_name"] = "C:records.json"
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")

    with pytest.raises(ValueError, match="record_bundle path must be redacted"):
        validate_parallel_search_release_gate(evidence)


def test_parallel_search_release_gate_rejects_inconsistent_profile_results() -> None:
    evidence = evaluate_parallel_search_release_gate(_passing_records())
    evidence["profile_results"][0]["speedup_pass"] = False
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")

    with pytest.raises(ValueError, match="profile_results"):
        validate_parallel_search_release_gate(evidence)


def test_parallel_search_release_gate_rejects_inconsistent_rejections() -> None:
    evidence = evaluate_parallel_search_release_gate(_passing_records()[:3])
    evidence["rejection_reasons"] = []
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")

    with pytest.raises(ValueError, match="rejection_reasons"):
        validate_parallel_search_release_gate(evidence)


def test_parallel_search_release_gate_rejects_inconsistent_pass_state() -> None:
    evidence = evaluate_parallel_search_release_gate(_passing_records()[:3])
    evidence["passed"] = True
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")

    with pytest.raises(ValueError, match="passed is inconsistent"):
        validate_parallel_search_release_gate(evidence)


def test_parallel_search_release_gate_rejects_passing_inline_record_bundle() -> None:
    evidence = evaluate_parallel_search_release_gate(_passing_records())

    with pytest.raises(ValueError, match="validated record bundle"):
        validate_parallel_search_release_gate(evidence)


def test_parallel_search_release_gate_rejects_non_canonical_record_order() -> None:
    evidence = evaluate_parallel_search_release_gate(_passing_records())
    evidence["records"] = list(reversed(evidence["records"]))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")

    with pytest.raises(ValueError, match="canonical order"):
        validate_parallel_search_release_gate(evidence)


def test_parallel_search_release_record_builder_normalizes_search_report(
    tmp_path: Path,
) -> None:
    report = tmp_path / "search-report.json"
    report.write_text(json.dumps(_search_report(pool_size=4)), encoding="utf-8")

    record = build_parallel_search_release_record(
        _record_input(report, pool_size=4)
    )

    assert record["best_route_id"] == "route_fixture"
    assert record["committed_nodes"] == 100_000
    assert record["node_budget"] == 100_000
    assert record["pool_size"] == 4
    assert record["profile_id"] == "short_line"
    assert record["wall_seconds"] == 12.5
    assert record["worker_kind"] == "real_core"
    assert record["semantic_digest"].startswith("searchsem_")
    assert record["lineage_digest"].startswith("lineage_")


def test_parallel_search_release_record_builder_accepts_report_parallel_policy(
    tmp_path: Path,
) -> None:
    payload = _search_report(pool_size=4)
    payload["parallel_policy"] = payload["strategy_parameters"].pop("parallel")
    report = tmp_path / "search-report.json"
    report.write_text(json.dumps(payload), encoding="utf-8")

    record = build_parallel_search_release_record(
        _record_input(report, pool_size=4)
    )

    assert record["pool_size"] == 4


def test_parallel_search_release_record_builder_rejects_pool_mismatch(
    tmp_path: Path,
) -> None:
    report = tmp_path / "search-report.json"
    report.write_text(json.dumps(_search_report(pool_size=1)), encoding="utf-8")

    with pytest.raises(ValueError, match="pool_size"):
        build_parallel_search_release_record(_record_input(report, pool_size=4))


def test_parallel_search_release_record_builder_rejects_artifact_route_mismatch(
    tmp_path: Path,
) -> None:
    payload = _search_report(pool_size=1)
    payload["artifact_commit"]["route_id"] = "route_other"
    report = tmp_path / "search-report.json"
    report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="artifact_commit route_id mismatch"):
        build_parallel_search_release_record(_record_input(report, pool_size=1))


def test_parallel_search_release_record_builder_rejects_artifact_schema_mismatch(
    tmp_path: Path,
) -> None:
    payload = _search_report(pool_size=1)
    payload["artifact_commit"]["schema_version"] = "search-artifact-commit-v0"
    report = tmp_path / "search-report.json"
    report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="artifact_commit schema_version"):
        build_parallel_search_release_record(_record_input(report, pool_size=1))


def test_parallel_search_release_record_builder_rejects_artifact_hash_mismatch(
    tmp_path: Path,
) -> None:
    report = tmp_path / "search-report.json"
    route = tmp_path / "best-route.yaml"
    report.write_text(json.dumps(_search_report(pool_size=1)), encoding="utf-8")
    route.write_text(
        json.dumps({"lineage": {"parent_route_id": None}, "route_id": "route_fixture"}),
        encoding="utf-8",
    )
    item = _record_input(report, pool_size=1)
    item["route_path"] = str(route)

    with pytest.raises(ValueError, match="Route file sha256"):
        build_parallel_search_release_record(item)


def test_parallel_search_release_record_builder_rejects_ranking_mismatch(
    tmp_path: Path,
) -> None:
    payload = _search_report(pool_size=1)
    payload["route_ranking"]["best_route_id"] = "route_other"
    report = tmp_path / "search-report.json"
    report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="route_ranking best_route_id mismatch"):
        build_parallel_search_release_record(_record_input(report, pool_size=1))


def test_parallel_search_release_record_builder_rejects_lower_budget_than_report(
    tmp_path: Path,
) -> None:
    report = tmp_path / "search-report.json"
    report.write_text(json.dumps(_search_report(pool_size=1)), encoding="utf-8")
    item = _record_input(report, pool_size=1)
    item["node_budget"] = 99_999

    with pytest.raises(ValueError, match="node_budget"):
        build_parallel_search_release_record(item)

    item = _record_input(report, pool_size=1)
    item["replay_budget"] = 99_999

    with pytest.raises(ValueError, match="replay_budget"):
        build_parallel_search_release_record(item)


def test_parallel_search_release_record_builder_rejects_route_file_mismatch(
    tmp_path: Path,
) -> None:
    report = tmp_path / "search-report.json"
    route = tmp_path / "best-route.yaml"
    route.write_text(
        json.dumps({"lineage": {"parent_route_id": None}, "route_id": "route_other"}),
        encoding="utf-8",
    )
    payload = _search_report(pool_size=1)
    payload["artifact_commit"]["route_sha256"] = hashlib.sha256(
        route.read_bytes()
    ).hexdigest()
    report.write_text(json.dumps(payload), encoding="utf-8")
    item = _record_input(report, pool_size=1)
    item["route_path"] = str(route)

    with pytest.raises(ValueError, match="Route file route_id"):
        build_parallel_search_release_record(item)


def test_parallel_search_release_record_builder_uses_matching_route_lineage(
    tmp_path: Path,
) -> None:
    report = tmp_path / "search-report.json"
    route = tmp_path / "best-route.yaml"
    lineage = {"parent_route_id": None, "source": "fixture"}
    route.write_text(
        json.dumps({"lineage": lineage, "route_id": "route_fixture"}),
        encoding="utf-8",
    )
    payload = _search_report(pool_size=1)
    payload["artifact_commit"]["route_sha256"] = hashlib.sha256(
        route.read_bytes()
    ).hexdigest()
    report.write_text(json.dumps(payload), encoding="utf-8")
    item = _record_input(report, pool_size=1)
    item["route_path"] = str(route)

    record = build_parallel_search_release_record(item)

    assert record["lineage_digest"] == stable_digest(lineage, prefix="lineage_")


def test_parallel_search_release_record_builder_requires_parallel_report_for_pool_gt_one(
    tmp_path: Path,
) -> None:
    payload = _search_report(pool_size=1)
    payload["strategy_parameters"] = {}
    report = tmp_path / "search-report.json"
    report.write_text(json.dumps(payload), encoding="utf-8")

    pool1 = build_parallel_search_release_record(_record_input(report, pool_size=1))

    assert pool1["pool_size"] == 1
    with pytest.raises(ValueError, match="parallel SearchRun report"):
        build_parallel_search_release_record(_record_input(report, pool_size=4))


def test_parallel_search_release_records_cli_writes_content_addressed_records(
    tmp_path: Path,
    capsys,
) -> None:
    report = tmp_path / "search-report.json"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "records.json"
    report.write_text(json.dumps(_search_report(pool_size=1)), encoding="utf-8")
    manifest.write_text(
        json.dumps({"inputs": [_record_input(Path("search-report.json"))]}),
        encoding="utf-8",
    )

    status = cmd_parallel_search_records(
        argparse.Namespace(manifest=manifest, out=str(output))
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert status == 0
    assert evidence["schema_version"] == PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION
    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="parsearchrecords_",
    )
    assert evidence["input_manifest"][0]["path_redacted"] is True
    assert evidence["input_manifest"][0]["report_path_name"] == "search-report.json"
    assert len(evidence["input_manifest"][0]["report_sha256"]) == 64
    assert len(evidence["records"]) == 1
    assert "parallel-search-records:" in captured.out
    assert read_parallel_search_release_records(output) == evidence


def test_parallel_search_release_records_cli_expands_grid_manifest(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "runs"
    for pool in (1, 2):
        for repeat in range(2):
            report = (
                artifact_root
                / "short_line"
                / f"pool-{pool}"
                / f"repeat-{repeat}"
                / "search-report.json"
            )
            report.parent.mkdir(parents=True, exist_ok=True)
            payload = _search_report(pool_size=pool)
            payload["elapsed_seconds"] = 10.0 + pool + repeat
            report.write_text(json.dumps(payload), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "records.json"
    manifest.write_text(
        json.dumps(
            {
                "artifact_root": "runs",
                "defaults": {
                    "node_budget": 100_000,
                    "replay_budget": 100_000,
                    "rss_peak_bytes": 512_000_000,
                    "worker_kind": "real_core",
                },
                "grid": {
                    "pool_sizes": [1, 2],
                    "profiles": ["short_line"],
                    "repeat_count": 2,
                    "report_pattern": (
                        "{profile_id}/pool-{pool_size}/repeat-{repeat_index}/"
                        "search-report.json"
                    ),
                },
                "schema_version": PARALLEL_SEARCH_RECORD_INPUT_MANIFEST_SCHEMA_VERSION,
            }
        ),
        encoding="utf-8",
    )

    status = cmd_parallel_search_records(
        argparse.Namespace(manifest=manifest, out=str(output))
    )
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert len(evidence["records"]) == 4
    assert [
        (record["profile_id"], record["pool_size"], record["repeat_index"])
        for record in evidence["records"]
    ] == [
        ("short_line", 1, 0),
        ("short_line", 1, 1),
        ("short_line", 2, 0),
        ("short_line", 2, 1),
    ]
    assert all(
        entry["report_path_name"] == "search-report.json"
        and entry["path_redacted"] is True
        for entry in evidence["input_manifest"]
    )


def test_parallel_search_collect_runs_grid_and_writes_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = REPO_ROOT / "examples" / "experiments" / "general_search_inline.yaml"
    artifact_root = tmp_path / "runs"
    manifest = tmp_path / "inputs.json"
    records = tmp_path / "records.json"

    def _fake_search(args: argparse.Namespace) -> int:
        generated = load_experiment_document(args.experiment_file)
        pool_size = generated["search"]["parameters"]["parallel"]["pool_size"]
        Path(args.out).write_text(
            "route_id: route_fixture\nlineage:\n  parent_route_id: null\n",
            encoding="utf-8",
        )
        payload = _search_report(pool_size=pool_size)
        payload["parallel_policy"] = {
            "base_seed": generated["search"]["parameters"]["parallel"]["base_seed"],
            "max_retries": generated["search"]["parameters"]["parallel"]["max_retries"],
            "policy_id": "parallelpol_fixture",
            "pool_size": pool_size,
            "schema_version": "parallel-search-policy-v1",
        }
        del payload["strategy_parameters"]["parallel"]
        payload["artifact_commit"]["route_sha256"] = sha256_file(args.out)
        Path(args.search_report).write_text(json.dumps(payload), encoding="utf-8")
        return 0

    monkeypatch.setattr(qualification_module, "cmd_experiment_search", _fake_search)

    status = cmd_parallel_search_collect(
        argparse.Namespace(
            artifact_root=artifact_root,
            base_seed=7000,
            experiment=[f"short_line={experiment}"],
            external_root=None,
            manifest_out=manifest,
            max_depth=None,
            max_nodes=100_000,
            max_replays=100_000,
            max_retries=1,
            max_seconds=None,
            parallel_max_retries=1,
            pool_sizes="2",
            records_out=records,
            repeat_count=1,
            worker_timeout=1.0,
        )
    )
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    evidence = read_parallel_search_release_records(records)

    assert status == 0
    assert manifest_payload["schema_version"] == "parallel-search-record-inputs-v1"
    assert len(manifest_payload["inputs"]) == 1
    assert evidence["records"][0]["pool_size"] == 2
    assert evidence["input_manifest"][0]["path_redacted"] is True
    assert "report_path" not in evidence["input_manifest"][0]


def test_parallel_search_collect_rejects_failed_search_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = REPO_ROOT / "examples" / "experiments" / "general_search_inline.yaml"

    def _failed_search(args: argparse.Namespace) -> int:
        return 2

    monkeypatch.setattr(qualification_module, "cmd_experiment_search", _failed_search)

    with pytest.raises(ValueError, match="experiment-search failed"):
        cmd_parallel_search_collect(
            argparse.Namespace(
                artifact_root=tmp_path / "runs",
                base_seed=7000,
                experiment=[f"short_line={experiment}"],
                external_root=None,
                manifest_out=tmp_path / "inputs.json",
                max_depth=None,
                max_nodes=100_000,
                max_replays=100_000,
                max_retries=1,
                max_seconds=None,
                parallel_max_retries=1,
                pool_sizes="2",
                records_out=tmp_path / "records.json",
                repeat_count=1,
                worker_timeout=1.0,
            )
        )


def test_parallel_search_collect_require_release_grid_rejects_incomplete_profiles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = REPO_ROOT / "examples" / "experiments" / "general_search_inline.yaml"

    def _unexpected_search(args: argparse.Namespace) -> int:
        raise AssertionError("release grid validation should run before Search")

    monkeypatch.setattr(qualification_module, "cmd_experiment_search", _unexpected_search)

    with pytest.raises(ValueError, match="requires profiles"):
        cmd_parallel_search_collect(
            argparse.Namespace(
                artifact_root=tmp_path / "runs",
                base_seed=7000,
                experiment=[f"short_line={experiment}"],
                external_root=None,
                manifest_out=tmp_path / "inputs.json",
                max_depth=None,
                max_nodes=100_000,
                max_replays=100_000,
                max_retries=1,
                max_seconds=None,
                parallel_max_retries=1,
                pool_sizes="1,2,4",
                records_out=tmp_path / "records.json",
                repeat_count=5,
                require_release_grid=True,
                worker_timeout=1.0,
            )
        )


def test_parallel_search_collect_marks_max_seconds_timing_censored(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = REPO_ROOT / "examples" / "experiments" / "general_search_inline.yaml"
    manifest = tmp_path / "inputs.json"
    records = tmp_path / "records.json"

    def _censored_search(args: argparse.Namespace) -> int:
        generated = load_experiment_document(args.experiment_file)
        pool_size = generated["search"]["parameters"]["parallel"]["pool_size"]
        Path(args.out).write_text(
            "route_id: route_fixture\nlineage:\n  parent_route_id: null\n",
            encoding="utf-8",
        )
        payload = _search_report(pool_size=pool_size)
        payload["parallel_policy"] = {
            "base_seed": generated["search"]["parameters"]["parallel"]["base_seed"],
            "max_retries": generated["search"]["parameters"]["parallel"]["max_retries"],
            "policy_id": "parallelpol_fixture",
            "pool_size": pool_size,
            "schema_version": "parallel-search-policy-v1",
        }
        payload["termination_reason"] = "max_seconds"
        payload["artifact_commit"]["route_sha256"] = sha256_file(args.out)
        Path(args.search_report).write_text(json.dumps(payload), encoding="utf-8")
        return 0

    monkeypatch.setattr(qualification_module, "cmd_experiment_search", _censored_search)

    status = cmd_parallel_search_collect(
        argparse.Namespace(
            artifact_root=tmp_path / "runs",
            base_seed=7000,
            experiment=[f"short_line={experiment}"],
            external_root=None,
            manifest_out=manifest,
            max_depth=None,
            max_nodes=100_000,
            max_replays=100_000,
            max_retries=1,
            max_seconds=0.01,
            parallel_max_retries=1,
            pool_sizes="2",
            records_out=records,
            repeat_count=1,
            worker_timeout=1.0,
        )
    )
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    evidence = read_parallel_search_release_records(records)

    assert status == 0
    assert manifest_payload["inputs"][0]["timing_censored"] is True
    assert evidence["records"][0]["timing_censored"] is True
    assert evidence["input_manifest"][0]["timing_censored"] is True


def test_parallel_search_record_input_manifest_rejects_bad_grid() -> None:
    with pytest.raises(ValueError, match="grid.profiles"):
        expand_parallel_search_release_record_inputs(
            {
                "grid": {
                    "profiles": ["short_line", "short_line"],
                    "report_pattern": "{profile_id}.json",
                },
                "schema_version": PARALLEL_SEARCH_RECORD_INPUT_MANIFEST_SCHEMA_VERSION,
            }
        )


def test_parallel_search_release_records_reject_tampering(tmp_path: Path) -> None:
    document = _records_document(_passing_records())
    assert validate_parallel_search_release_records(document) == document

    document["records"][0]["wall_seconds"] = 999.0

    with pytest.raises(ValueError, match="evidence_id mismatch"):
        validate_parallel_search_release_records(document)

    tampered_path = tmp_path / "tampered-records.json"
    tampered_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence_id mismatch"):
        cmd_parallel_search_gate(
            argparse.Namespace(
                records=tampered_path,
                out=str(tmp_path / "gate.json"),
                required_repeats=5,
            )
        )


def test_parallel_search_release_records_can_feed_gate(tmp_path: Path) -> None:
    records = []
    for profile, pool_walls in {
        "grave_banish_or_chain": {1: 10.0, 2: 8.0, 4: 7.0},
        "long_line": {1: 12.0, 2: 9.0, 4: 8.0},
        "short_line": {1: 9.0, 2: 8.5, 4: 8.0},
    }.items():
        for pool, wall in pool_walls.items():
            for repeat in range(5):
                report = tmp_path / f"{profile}-{pool}-{repeat}.json"
                payload = _search_report(pool_size=pool)
                payload["elapsed_seconds"] = wall + repeat * 0.01
                payload["best_route"]["route_id"] = f"route_{profile}"
                payload["artifact_commit"]["route_id"] = f"route_{profile}"
                payload["route_ranking"]["best_route_id"] = f"route_{profile}"
                report.write_text(json.dumps(payload), encoding="utf-8")
                item = _record_input(report, pool_size=pool)
                item["profile_id"] = profile
                item["repeat_index"] = repeat
                records.append(item)

    evidence = build_parallel_search_release_records(records)
    gate = evaluate_parallel_search_release_gate(evidence["records"])

    assert evidence["schema_version"] == PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION
    assert gate["passed"] is True


def test_parallel_search_release_records_normalize_record_order(
    tmp_path: Path,
) -> None:
    inputs = []
    for profile in ("short_line", "long_line"):
        for pool in (4, 1):
            report = tmp_path / f"{profile}-{pool}.json"
            payload = _search_report(pool_size=pool)
            payload["best_route"]["route_id"] = f"route_{profile}"
            payload["artifact_commit"]["route_id"] = f"route_{profile}"
            payload["route_ranking"]["best_route_id"] = f"route_{profile}"
            report.write_text(json.dumps(payload), encoding="utf-8")
            item = _record_input(report, pool_size=pool)
            item["profile_id"] = profile
            inputs.append(item)

    forward = build_parallel_search_release_records(inputs)
    reversed_bundle = build_parallel_search_release_records(list(reversed(inputs)))

    assert forward == reversed_bundle
    assert [
        (record["profile_id"], record["pool_size"], record["repeat_index"])
        for record in forward["records"]
    ] == [
        ("long_line", 1, 0),
        ("long_line", 4, 0),
        ("short_line", 1, 0),
        ("short_line", 4, 0),
    ]


def test_parallel_search_release_records_reject_non_canonical_order() -> None:
    document = _records_document(list(reversed(_passing_records())))

    with pytest.raises(ValueError, match="canonical order"):
        validate_parallel_search_release_records(document)


def test_parallel_search_release_records_reject_duplicate_repeats() -> None:
    records = _passing_records()
    records.insert(1, dict(records[0]))
    document = _records_document(records)

    with pytest.raises(ValueError, match="duplicate repeats"):
        validate_parallel_search_release_records(document)


def test_parallel_search_release_records_reject_non_contiguous_repeats() -> None:
    records = _passing_records()
    for record in records:
        if record["profile_id"] == "short_line" and record["pool_size"] == 1:
            record["repeat_index"] += 1
    records = sorted(
        records,
        key=lambda record: (
            record["profile_id"],
            record["pool_size"],
            record["repeat_index"],
            record["best_route_id"],
            record["semantic_digest"],
            record["lineage_digest"],
        ),
    )
    document = _records_document(records)

    with pytest.raises(ValueError, match="repeat_index sequence"):
        validate_parallel_search_release_records(document)


def test_parallel_search_release_records_reject_manifest_path_or_record_mismatch() -> None:
    document = _records_document(_passing_records())
    document["input_manifest"][0]["report_path_name"] = "C:\\leaked\\search-report.json"
    identity = {key: value for key, value in document.items() if key != "evidence_id"}
    document["evidence_id"] = stable_digest(identity, prefix="parsearchrecords_")

    with pytest.raises(ValueError, match="path must be redacted"):
        validate_parallel_search_release_records(document)

    document = _records_document(_passing_records())
    document["input_manifest"][0]["rss_peak_bytes"] += 1
    identity = {key: value for key, value in document.items() if key != "evidence_id"}
    document["evidence_id"] = stable_digest(identity, prefix="parsearchrecords_")

    with pytest.raises(ValueError, match="does not match records"):
        validate_parallel_search_release_records(document)


def test_parallel_search_gate_cli_writes_evidence_and_reports_status(
    tmp_path: Path,
    capsys,
) -> None:
    records = tmp_path / "records.json"
    output = tmp_path / "gate.json"
    records.write_text(json.dumps(_records_document(_passing_records())), encoding="utf-8")

    status = cmd_parallel_search_gate(
        argparse.Namespace(records=records, out=str(output), required_repeats=5)
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert evidence["passed"] is True
    assert "parallel-search-gate: passed" in captured.out
    assert evidence["evidence_id"] in captured.out


def test_parallel_search_gate_cli_rejects_raw_records_input(tmp_path: Path) -> None:
    records = tmp_path / "records.json"
    output = tmp_path / "gate.json"
    records.write_text(json.dumps({"records": _passing_records()}), encoding="utf-8")

    with pytest.raises(ValueError, match="parallel-search-release-records-v1 bundle"):
        cmd_parallel_search_gate(
            argparse.Namespace(records=records, out=str(output), required_repeats=5)
        )


def test_parallel_search_gate_rejects_duplicate_repeat_indices() -> None:
    records = _passing_records()
    records.insert(1, dict(records[0]))

    evidence = evaluate_parallel_search_release_gate(records)

    assert evidence["passed"] is False
    assert any(
        "duplicate repeat_index" in reason
        for reason in evidence["rejection_reasons"]
    )


def test_parallel_search_gate_rejects_non_contiguous_repeat_indices() -> None:
    records = _passing_records()
    for record in records:
        if record["profile_id"] == "short_line" and record["pool_size"] == 1:
            record["repeat_index"] += 1

    evidence = evaluate_parallel_search_release_gate(records)

    assert evidence["passed"] is False
    assert any(
        "repeat_index sequence is not contiguous" in reason
        for reason in evidence["rejection_reasons"]
    )


def test_parallel_search_gate_rejects_non_contiguous_complete_repeats() -> None:
    records = _passing_records()
    extra = dict(records[0])
    extra["repeat_index"] = 5
    extra["wall_seconds"] = 100.5
    records.append(extra)
    records[0]["timing_censored"] = True

    evidence = evaluate_parallel_search_release_gate(records)

    assert evidence["passed"] is False
    assert any(
        "complete repeat_index sequence is not contiguous" in reason
        for reason in evidence["rejection_reasons"]
    )


def test_parallel_search_gate_rejects_budget_or_committed_node_drift() -> None:
    records = _passing_records()
    records[0]["node_budget"] = 90_000
    records[1]["replay_budget"] = 90_000
    records[2]["committed_nodes"] = 90_000

    evidence = evaluate_parallel_search_release_gate(records)

    assert evidence["passed"] is False
    assert any("node_budget differs across pools" in reason for reason in evidence["rejection_reasons"])
    assert any("replay_budget differs across pools" in reason for reason in evidence["rejection_reasons"])
    assert any("committed_nodes differs across pools" in reason for reason in evidence["rejection_reasons"])


def test_parallel_search_gate_rejects_below_release_scale_records() -> None:
    records = _passing_records()
    for record in records:
        record["committed_nodes"] = 50_000
        record["node_budget"] = 50_000
        record["replay_budget"] = 50_000

    evidence = evaluate_parallel_search_release_gate(records)

    assert evidence["passed"] is False
    assert any("committed_nodes below 100000" in reason for reason in evidence["rejection_reasons"])
    assert any("node_budget below 100000" in reason for reason in evidence["rejection_reasons"])
    assert any("replay_budget below 100000" in reason for reason in evidence["rejection_reasons"])


def test_parallel_search_gate_accepts_composite_release_scale_sources() -> None:
    records = _passing_records()
    for record in records:
        record["committed_nodes"] = 50_000
        record["wall_seconds"] = 10.0
        record["best_route_id"] = f"route_{record['profile_id']}_pool_{record['pool_size']}"
        record["semantic_digest"] = (
            f"semantic_{record['profile_id']}_pool_{record['pool_size']}"
        )

    evidence = evaluate_parallel_search_release_gate(
        records,
        extra_rejections=[
            "source real-core-parallel-stress-v2 verifies scheduling/retry "
            "semantics, not per-profile release timing records",
            "source pinned-base-logical-node-workload calibrates logical "
            "executor/cache/artifact behavior, not real_core per-profile "
            "release timing records",
            "source real-core-replay-benchmark-v1 calibrates real_core fresh Replay "
            "timing, not per-profile SearchRun release records",
            "source does not expose release timing records",
            "source contains non-release timing records",
        ],
        input_sources=_source_summaries(),
    )

    assert evidence["passed"] is True
    assert evidence["rejection_reasons"] == []
    assert evidence["supplemental_claims"] == {
        "composite_release_scale_passed": True,
        "general_search_100k_logical_passed": True,
        "real_core_parallel_stress_passed": True,
        "real_core_replay_benchmark_passed": True,
        "schema_version": "parallel-search-supplemental-claims-v1",
    }


def test_parallel_search_gate_cli_returns_failure_for_incomplete_records(
    tmp_path: Path,
    capsys,
) -> None:
    records = tmp_path / "records.json"
    output = tmp_path / "gate.json"
    records.write_text(
        json.dumps(_records_document(_passing_records()[:3])),
        encoding="utf-8",
    )

    status = cmd_parallel_search_gate(
        argparse.Namespace(records=records, out=str(output), required_repeats=5)
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 1
    assert evidence["passed"] is False
    assert "parallel-search-gate: failed" in captured.out


def test_parallel_search_gate_summarizes_stress_source_as_non_release_records() -> None:
    source = json.loads(STRESS_EVIDENCE_PATH.read_text(encoding="utf-8"))

    summary, rejections = summarize_parallel_search_release_source(
        source,
        source_path=STRESS_EVIDENCE_PATH,
    )

    assert summary["source_kind"] == "real_core_parallel_stress"
    assert summary["path_redacted"] is True
    assert summary["source_path_name"] == "real_core_parallel_stress.json"
    assert summary["pool_sizes"] == [1, 2, 4, 8]
    assert summary["verification_passed"] is True
    assert summary["release_record_count"] == 0
    assert any("not per-profile release timing records" in item for item in rejections)


def test_parallel_search_gate_summarizes_logical_100k_as_non_release_records() -> None:
    source = json.loads(LOGICAL_100K_EVIDENCE_PATH.read_text(encoding="utf-8"))

    summary, rejections = summarize_parallel_search_release_source(
        source,
        source_path=LOGICAL_100K_EVIDENCE_PATH,
    )

    assert summary["source_kind"] == "general_search_100k_logical"
    assert summary["path_redacted"] is True
    assert summary["source_path_name"] == "0105_general_search_100k.json"
    assert summary["nodes_per_profile_pool"] == 100_000
    assert summary["pool_sizes"] == [1, 2, 4, 8, 16]
    assert summary["profile_count"] == 3
    assert summary["semantic_invariants_passed"] is True
    assert summary["source_record_count"] == 15
    assert summary["release_record_count"] == 0
    assert any("not real_core per-profile release timing records" in item for item in rejections)


def test_parallel_search_gate_summarizes_real_core_replay_benchmark_source() -> None:
    source = json.loads(REPLAY_BENCHMARK_EVIDENCE_PATH.read_text(encoding="utf-8"))

    summary, rejections = summarize_parallel_search_release_source(
        source,
        source_path=REPLAY_BENCHMARK_EVIDENCE_PATH,
    )

    assert summary["source_kind"] == "real_core_replay_benchmark"
    assert summary["path_redacted"] is True
    assert summary["source_path_name"] == "0128_real_core_replay_pool.json"
    assert summary["pool_sizes"] == [1, 2, 4, 8, 16]
    assert summary["profile_count"] == 3
    assert summary["semantic_invariants_passed"] is True
    assert summary["speedup_passed"] is True
    assert summary["telemetry_complete"] is True
    assert summary["release_record_count"] == 0
    assert any("not per-profile SearchRun release records" in item for item in rejections)


def test_parallel_search_gate_cli_records_source_rejections(
    tmp_path: Path,
) -> None:
    records = tmp_path / "records.json"
    output = tmp_path / "gate.json"
    records.write_text(
        json.dumps(
            {
                "reason": "pending test evidence",
                "records": [],
                "schema_version": PARALLEL_SEARCH_RELEASE_RECORDS_PENDING_SCHEMA_VERSION,
            }
        ),
        encoding="utf-8",
    )

    status = cmd_parallel_search_gate(
        argparse.Namespace(
            records=records,
            out=str(output),
            required_repeats=5,
            source_evidence=[STRESS_EVIDENCE_PATH, LOGICAL_100K_EVIDENCE_PATH],
        )
    )
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 1
    assert evidence["passed"] is False
    assert evidence["input_sources"][0]["source_kind"] == "real_core_parallel_stress"
    assert evidence["input_sources"][0]["path_redacted"] is True
    assert evidence["input_sources"][0]["source_path_name"] == (
        "real_core_parallel_stress.json"
    )
    assert evidence["input_sources"][1]["source_kind"] == "general_search_100k_logical"
    assert any(
        "not per-profile release timing records" in reason
        for reason in evidence["rejection_reasons"]
    )


def test_parallel_search_gate_rejects_unredacted_input_source_path() -> None:
    evidence = evaluate_parallel_search_release_gate(_passing_records()[:3])
    evidence["input_sources"] = [
        {
            "path": "C:\\qualification\\parallel\\records.json",
            "release_record_count": 45,
            "source_record_count": 45,
        }
    ]
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")

    with pytest.raises(ValueError, match="path must be redacted"):
        validate_parallel_search_release_gate(evidence)


def test_committed_parallel_search_gate_is_content_addressed_and_adopted() -> None:
    evidence = read_parallel_search_release_gate(EVIDENCE_PATH)

    assert evidence["schema_version"] == PARALLEL_SEARCH_RELEASE_GATE_SCHEMA_VERSION
    assert evidence["passed"] is True
    assert evidence["gate"]["min_committed_nodes"] == 100_000
    assert evidence["gate"]["min_node_budget"] == 100_000
    assert evidence["gate"]["min_replay_budget"] == 100_000
    assert (
        evidence["record_bundle"]["schema_version"]
        == PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION
    )
    assert evidence["record_bundle"]["record_count"] == 45
    assert evidence["record_bundle"]["evidence_id"].startswith("parsearchrecords_")
    assert len(evidence["records"]) == 45
    assert evidence["rejection_reasons"] == []
    assert any(
        source.get("source_kind") == "real_core_parallel_stress"
        for source in evidence["input_sources"]
    )
    assert any(
        source.get("source_kind") == "general_search_100k_logical"
        for source in evidence["input_sources"]
    )
    assert any(
        source.get("source_kind") == "real_core_replay_benchmark"
        for source in evidence["input_sources"]
    )
    assert evidence["supplemental_claims"] == {
        "composite_release_scale_passed": True,
        "general_search_100k_logical_passed": True,
        "real_core_parallel_stress_passed": True,
        "real_core_replay_benchmark_passed": True,
        "schema_version": "parallel-search-supplemental-claims-v1",
    }
