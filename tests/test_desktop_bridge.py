from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import yaml

from ygo_effect_dsl.desktop.lifecycle import DesktopSearchWorker, ValidatedSearchArtifacts
from ygo_effect_dsl.desktop import desktop_bridge_contract_document
from ygo_effect_dsl.desktop.bridge import (
    DESKTOP_BRIDGE_CONTRACT_VERSION,
    DesktopBridge,
)
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest
from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.engine.evaluation import (
    RouteRankingPolicy,
    TerminalPreferenceProfile,
    build_terminal_board_projection,
    build_route_randomness_summary,
    evaluate_terminal_preferences,
    rank_route_candidates,
)
from ygo_effect_dsl.experiment import (
    build_fresh_replay_verification_report,
    write_fresh_replay_verification_report,
)
from ygo_effect_dsl.presentation import CARD_PRESENTATION_PROVIDER_VERSION
from ygo_effect_dsl.presentation.cards import CARD_PRESENTATION_QUERY_VERSION
from ygo_effect_dsl.storage.jobs import JobState
from ygo_effect_dsl.storage.query import ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION


def _request(
    method: str, payload: Mapping[str, Any], **overrides: Any
) -> dict[str, Any]:
    return {
        "method": method,
        "payload": dict(payload),
        "request_id": "test-request-1",
        "version": DESKTOP_BRIDGE_CONTRACT_VERSION,
        **overrides,
    }


def _codes() -> list[int]:
    return list(range(10_000, 10_040))


@dataclass(frozen=True)
class _Preflight:
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagnostics": [],
            "manifest": {"schema_version": "scenario-manifest-v1"},
            "ok": self.ok,
            "schema_version": "scenario-preflight-v1",
        }


def _preflight(*_: Any, **__: Any) -> _Preflight:
    return _Preflight()


def _published_result_launcher(command: list[str], *, cwd: Path) -> Any:
    del cwd
    route_path = Path(command[command.index("--out") + 1])
    report_path = Path(command[command.index("--search-report") + 1])
    route_id = "route_" + "a" * 64
    preference_profile = TerminalPreferenceProfile.from_mapping(
        {
            "name": "desktop fixture profile",
            "rules": [
                {
                    "card_code": _codes()[0],
                    "controller": 0,
                    "enabled": True,
                    "location": "HAND",
                    "max_count": None,
                    "min_count": 1,
                    "position": "ANY",
                    "rule_id": "hand-copy",
                    "scoring_mode": "once",
                    "weight": 5,
                }
            ],
            "schema_version": "terminal-preference-profile-v1",
        }
    )
    terminal_state = "state_" + "1" * 64
    replay_manifest_hash = "manifest_" + "d" * 64
    board_summary = {
        "public_cards": [
            {
                "code": _codes()[0],
                "controller": 0,
                "location": "hand",
                "position": 1,
                "slot": 0,
            }
        ],
        "state_hash": terminal_state,
    }
    route_document = {
        "experiment": {
            "experiment_id": "desktop_fixture_experiment",
            "schema_version": "0.4",
            "search": {"strategy": "random_search_v1"},
            "terminal_preference_profile": preference_profile.to_dict(),
        },
        "replay": {
            "events": [
                {
                    "action": {"action_id": "action_normal_summon"},
                    "request": {"kind": "normal_summon"},
                    "state_hash_after": terminal_state,
                }
            ],
            "manifest": {
                "environment": {
                    "assets": {"lock_id": "assets_fixture"},
                    "core": {
                        "api": "11.0",
                        "binary_sha256": "a" * 64,
                        "lock_id": "core_fixture",
                        "source_commit": "b" * 40,
                    },
                    "scenario_manifest": {
                        "asset_lock_id": "assets_fixture",
                        "deck_id": "deck_fixture",
                        "deck_sha256": "c" * 64,
                        "deck_source": "inline",
                        "schema_version": "scenario-manifest-v1",
                        "source_sha256": None,
                    },
                },
                "manifest_hash": replay_manifest_hash,
                "schema_version": "ygo-replay-manifest-v1",
            },
            "random_events": [],
        },
        "result": {
            "lua_script_resolution": {
                "loads": [
                    {
                        "outcome": "loaded",
                        "requested_name": "c1.lua",
                        "sha256": "e" * 64,
                    }
                ],
                "profile_id": "card-scripts-official-v1",
                "schema_version": 1,
            },
            "terminal_board": {
                "board_summary": board_summary,
                "score": 14,
                "state_hash": terminal_state,
            }
        },
        "route_id": route_id,
        "schema_version": "0.3a",
    }
    route_content = yaml.safe_dump(route_document, sort_keys=True)
    route_path.write_text(route_content, encoding="utf-8", newline="\n")
    randomness_summary = build_route_randomness_summary(route_document)
    preference_evaluation = evaluate_terminal_preferences(
        build_terminal_board_projection(board_summary),
        preference_profile,
        base_score=14,
    )
    route_summary = {
        "action_count": 1,
        "action_ids": ["action_normal_summon"],
        "peak_score": 18,
        "randomness_summary": randomness_summary,
        "route_id": route_id,
        "success": True,
        "terminal_preference_evaluation": preference_evaluation,
        "terminal_score": 19,
    }
    route_ranking = rank_route_candidates(
        [
            {
                "action_count": 1,
                "peak_score": 18,
                "randomness_summary": randomness_summary,
                "route_id": route_id,
                "success": True,
                "terminal_composite_score": 19,
            }
        ],
        policy=RouteRankingPolicy(),
    )
    candidate_counts = {
        "censored": 0,
        "explored": 1,
        "failed": 0,
        "pruned": 0,
        "total": 1,
        "unexplored": 0,
    }
    search_evidence_identity = {
        "candidate_counts": candidate_counts,
        "candidates": [
            {
                "action_id": "action_normal_summon",
                "action_ids": ["action_normal_summon"],
                "depth": 1,
                "duplicate": False,
                "legal_stop": True,
                "node_id": "searchnode_fixture",
                "parent_prefix_id": "searchprefix_root",
                "prefix_id": "searchprefix_child",
                "route_id": route_id,
                "state_completeness": "exact",
                "state_id": terminal_state,
                "status": "explored",
                "success": True,
            }
        ],
        "schema_version": "search-candidate-evidence-v1",
    }
    search_evidence = {
        **search_evidence_identity,
        "evidence_id": stable_digest(
            search_evidence_identity,
            prefix="searchev_",
        ),
    }
    coverage_identity = {
        "candidate_accounting_complete": True,
        "candidate_counts": candidate_counts,
        "coverage_status": "best_observed",
        "frontier_exhausted": False,
        "pending_frontier_count": 0,
        "schema_version": "search-coverage-v1",
        "termination_reason": "goal_reached",
        "unknown_candidate_count": 0,
    }
    coverage = {
        **coverage_identity,
        "coverage_id": stable_digest(
            coverage_identity,
            prefix="searchcoverage_",
        ),
    }
    report = {
        "artifact_commit": {
            "route_id": route_id,
            "route_sha256": hashlib.sha256(route_content.encode("utf-8")).hexdigest(),
            "schema_version": "search-artifact-commit-v1",
            "status": "committed",
        },
        "best_route": {
            "peak_score": 18,
            "randomness_summary": randomness_summary,
            "route_id": route_id,
            "score": 14,
            "success": True,
            "terminal_preference_evaluation": preference_evaluation,
            "terminal_score": 19,
        },
        "coverage": coverage,
        "nodes": 7,
        "replays": 7,
        "report_schema_version": "search-run-report-v1",
        "route_ranking": route_ranking,
        "routes": [route_summary],
        "run_id": "searchrun_" + "b" * 64,
        "search_evidence": search_evidence,
        "status": "complete",
        "termination_reason": "goal_reached",
    }
    report_path.write_text(canonical_json(report) + "\n", encoding="utf-8")

    class _Process:
        returncode = 0
        pid = 501

        def poll(self) -> int:
            return 0

        def communicate(self) -> tuple[str, str]:
            return ("", "")

    class _Tree:
        containment = "test"
        process = _Process()

        def active_process_count(self) -> int:
            return 0

        def terminate(self, *, grace_seconds: float = 2.0) -> None:
            del grace_seconds

        def close(self) -> None:
            pass

    return _Tree()


def _published_invalid_frontier_exhausted_launcher(
    command: list[str],
    *,
    cwd: Path,
) -> Any:
    tree = _published_result_launcher(command, cwd=cwd)
    report_path = Path(command[command.index("--search-report") + 1])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    coverage = dict(report["coverage"])
    coverage.update(
        {
            "coverage_status": "frontier_exhausted",
            "frontier_exhausted": True,
            "termination_reason": "goal_reached",
        }
    )
    coverage_identity = {
        key: value for key, value in coverage.items() if key != "coverage_id"
    }
    coverage["coverage_id"] = stable_digest(
        coverage_identity,
        prefix="searchcoverage_",
    )
    report["coverage"] = coverage
    report_path.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return tree


def _published_invalid_candidate_counts_launcher(
    command: list[str],
    *,
    cwd: Path,
) -> Any:
    tree = _published_result_launcher(command, cwd=cwd)
    report_path = Path(command[command.index("--search-report") + 1])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    search_evidence = dict(report["search_evidence"])
    candidate_counts = dict(search_evidence["candidate_counts"])
    candidate_counts["total"] = 2
    search_evidence["candidate_counts"] = candidate_counts
    evidence_identity = {
        key: value for key, value in search_evidence.items() if key != "evidence_id"
    }
    search_evidence["evidence_id"] = stable_digest(
        evidence_identity,
        prefix="searchev_",
    )
    report["search_evidence"] = search_evidence
    report_path.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return tree


def _published_ranking_summary_drift_launcher(
    command: list[str],
    *,
    cwd: Path,
) -> Any:
    tree = _published_result_launcher(command, cwd=cwd)
    report_path = Path(command[command.index("--search-report") + 1])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["routes"][0]["terminal_score"] = report["best_route"]["terminal_score"] + 10
    report["route_ranking"] = rank_route_candidates(
        [
            {
                "action_count": item.get("action_count"),
                "peak_score": item.get("peak_score"),
                "randomness_summary": item.get("randomness_summary"),
                "route_id": item.get("route_id"),
                "success": item.get("success"),
                "terminal_composite_score": item.get("terminal_score"),
            }
            for item in report["routes"]
        ],
        policy=RouteRankingPolicy(),
    )
    report_path.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return tree


def _published_terminal_score_drift_launcher(
    command: list[str],
    *,
    cwd: Path,
) -> Any:
    tree = _published_result_launcher(command, cwd=cwd)
    report_path = Path(command[command.index("--search-report") + 1])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    drifted_score = report["best_route"]["terminal_score"] + 10
    report["best_route"]["terminal_score"] = drifted_score
    report["routes"][0]["terminal_score"] = drifted_score
    report["route_ranking"] = rank_route_candidates(
        [
            {
                "action_count": item.get("action_count"),
                "peak_score": item.get("peak_score"),
                "randomness_summary": item.get("randomness_summary"),
                "route_id": item.get("route_id"),
                "success": item.get("success"),
                "terminal_composite_score": item.get("terminal_score"),
            }
            for item in report["routes"]
        ],
        policy=RouteRankingPolicy(),
    )
    report_path.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return tree


def _accept_result_artifacts(
    *,
    experiment: dict[str, Any],
    route_path: Path,
    report_path: Path,
    max_nodes: int,
) -> ValidatedSearchArtifacts:
    del experiment, max_nodes
    route_content = route_path.read_bytes()
    report_content = report_path.read_bytes()
    report = json.loads(report_content.decode("utf-8"))
    return ValidatedSearchArtifacts(
        route_content=route_content,
        report_content=report_content,
        report=report,
        nodes=report["nodes"],
        replays=report["replays"],
        route_id=report["best_route"]["route_id"],
        semantic_result_digest="jobsemantic_" + "c" * 64,
    )


def _replay_verification_launcher(command: list[str], *, cwd: Path) -> Any:
    del cwd
    replay_index = command.index("experiment-replay")
    route_path = Path(command[replay_index + 2])
    run_id = command[command.index("--run-id") + 1]
    report_path = Path(command[command.index("--verification-report") + 1])
    route_document = yaml.safe_load(route_path.read_text(encoding="utf-8"))
    terminal_board = route_document["result"]["terminal_board"]
    report = build_fresh_replay_verification_report(
        route_document,
        run_id=run_id,
        route_id=route_document["route_id"],
        event_count=len(route_document["replay"]["events"]),
        final_state_hash=terminal_board["state_hash"],
    )
    write_fresh_replay_verification_report(report_path, report)

    class _Process:
        returncode = 0
        pid = 502

        def poll(self) -> int:
            return 0

        def communicate(self) -> tuple[str, str]:
            return ("", "")

    class _Tree:
        containment = "test"
        process = _Process()

        def active_process_count(self) -> int:
            return 0

        def terminate(self, *, grace_seconds: float = 2.0) -> None:
            del grace_seconds

        def close(self) -> None:
            pass

    return _Tree()


def _resign_replay_verification_report(report: dict[str, Any]) -> dict[str, Any]:
    identity = dict(report)
    identity.pop("verification_id", None)
    return {
        **report,
        "verification_id": stable_digest(identity, prefix="replayverify_"),
    }


def _replay_route_digest_drift_launcher(command: list[str], *, cwd: Path) -> Any:
    tree = _replay_verification_launcher(command, cwd=cwd)
    report_path = Path(command[command.index("--verification-report") + 1])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["route"]["route_document_digest"] = "routedoc_" + "e" * 64
    write_fresh_replay_verification_report(
        report_path,
        _resign_replay_verification_report(report),
    )
    return tree


def _queue_replay_verification_job(
    tmp_path: Path,
    *,
    replay_key: str,
    search_key: str,
) -> tuple[DesktopApplicationService, str]:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Replay Source", "side": []},
        )
    )["result"]["deck"]
    experiment = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 7,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )["result"]["experiment"]
    queued_search = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": deck["deck_id"],
                "experiment": experiment,
                "idempotency_key": search_key,
                "priority": 0,
            },
        )
    )
    search_job_id = queued_search["result"]["job"]["job_id"]
    search_worker = DesktopSearchWorker(
        tmp_path,
        launcher=_published_result_launcher,
        artifact_validator=_accept_result_artifacts,
    )
    assert search_worker.run_once().status == "succeeded"
    queued_replay = bridge.invoke(
        _request(
            "job.enqueue_replay_verification",
            {
                "idempotency_key": replay_key,
                "priority": 5,
                "search_job_id": search_job_id,
            },
        )
    )
    return service, queued_replay["result"]["job"]["job_id"]


def test_machine_contract_matches_the_single_method_allowlist(tmp_path: Path) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    contract = desktop_bridge_contract_document()
    bridge = DesktopBridge(service.handlers())

    assert contract["schema_version"] == DESKTOP_BRIDGE_CONTRACT_VERSION
    assert tuple(sorted(contract["methods"])) == bridge.methods
    assert contract["security"] == {
        "generic_python_object": False,
        "local_rest_api": False,
        "public_python_methods": ["invoke"],
        "remote_content": False,
    }
    public_callables = [
        name
        for name in dir(bridge)
        if not name.startswith("_") and callable(getattr(bridge, name))
    ]
    assert public_callables == ["invoke"]


def test_invalid_bridge_requests_fail_before_dispatch() -> None:
    calls: list[Mapping[str, Any]] = []
    bridge = DesktopBridge(
        {"system.describe": lambda payload: calls.append(payload) or {}}
    )

    cases = (
        ({"not": "a request"}, "invalid_request_fields"),
        (_request("system.describe", {}, version="old"), "bridge_version_mismatch"),
        (_request("missing", {}), "unsupported_method"),
        (
            _request("system.describe", {"file_path": "C:/secret"}),
            "renderer_path_forbidden",
        ),
        (_request("system.describe", {"value": float("inf")}), "non_finite_number"),
    )
    for request, code in cases:
        response = bridge.invoke(request)
        assert response["ok"] is False
        assert response["diagnostics"][0]["code"] == code
    assert calls == []


def test_bridge_enforces_request_and_response_byte_limits() -> None:
    request_bridge = DesktopBridge(
        {"echo": lambda payload: payload},
        max_request_bytes=180,
    )
    response = request_bridge.invoke(_request("echo", {"value": "x" * 500}))
    assert response["diagnostics"][0]["code"] == "request_too_large"

    response_bridge = DesktopBridge(
        {"large": lambda _: {"value": "x" * 500}},
        max_response_bytes=200,
    )
    response = response_bridge.invoke(_request("large", {}))
    assert response["diagnostics"][0]["code"] == "response_too_large"


def test_inline_and_native_ydk_registration_are_content_addressed(
    tmp_path: Path,
) -> None:
    ydk = tmp_path / "research.ydk"
    ydk.write_text(
        "#created by test\n#main\n"
        + "\n".join(str(code) for code in _codes())
        + "\n#extra\n!side\n",
        encoding="utf-8",
    )
    service = DesktopApplicationService(
        tmp_path / "state",
        ydk_picker=lambda: ydk,
        preflight=_preflight,
    )
    bridge = DesktopBridge(service.handlers())
    inline = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Inline", "side": []},
        )
    )
    imported = bridge.invoke(_request("deck.import_ydk", {}))
    catalog = bridge.invoke(_request("deck.catalog", {}))

    assert inline["ok"] is True
    assert imported["ok"] is True
    assert imported["result"]["cancelled"] is False
    assert catalog["result"]["total"] == 2
    persisted = json.loads(
        (tmp_path / "state" / "decks.json").read_text(encoding="utf-8")
    )
    assert persisted["schema_version"] == "desktop-deck-catalog-v1"
    assert all("path" not in deck for deck in persisted["decks"])

    persisted["decks"][0]["main"][0] += 1
    (tmp_path / "state" / "decks.json").write_text(
        json.dumps(persisted),
        encoding="utf-8",
    )
    corrupt = bridge.invoke(_request("deck.catalog", {}))
    assert corrupt["ok"] is False
    assert corrupt["diagnostics"][0]["code"] == "deck_catalog_corrupt"


def test_preflight_search_queue_status_and_cancel_use_existing_catalog(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    registered = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Queue", "side": []},
        )
    )["result"]["deck"]
    experiment = {"experiment_id": "desktop-search", "schema_version": "0.4"}
    checked = bridge.invoke(
        _request(
            "scenario.preflight",
            {"deck_id": registered["deck_id"], "experiment": experiment},
        )
    )
    queued = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": registered["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-test-search",
                "priority": 0,
            },
        )
    )
    job_id = queued["result"]["job"]["job_id"]
    status = bridge.invoke(_request("job.status", {"job_id": job_id}))
    cancelled = bridge.invoke(_request("job.cancel", {"job_id": job_id}))

    assert checked["result"]["experiment"]["deck"]["source"] == "inline"
    assert queued["result"]["job"]["state"] == "queued"
    assert status["result"]["job"]["state"] == "queued"
    assert cancelled["result"]["job"]["state"] == "cancelled"
    experiment_files = tuple((tmp_path / "experiments").glob("experiment_*.json"))
    assert len(experiment_files) == 1


def test_result_view_reads_only_verified_committed_job_artifacts(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Result", "side": []},
        )
    )["result"]["deck"]
    experiment = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 7,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )["result"]["experiment"]
    queued = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": deck["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-result-test",
                "priority": 0,
            },
        )
    )
    job_id = queued["result"]["job"]["job_id"]
    worker = DesktopSearchWorker(
        tmp_path,
        launcher=_published_result_launcher,
        artifact_validator=_accept_result_artifacts,
    )

    assert worker.run_once().status == "succeeded"
    result = bridge.invoke(_request("job.result", {"job_id": job_id}))

    assert result["ok"] is True
    view = result["result"]
    assert view["schema_version"] == "desktop-result-view-v1"
    assert view["result_truth"]["source"] == "committed_job_artifacts"
    assert view["result_truth"]["synthetic"] is False
    assert view["result_truth"]["verification_state"] == "unverified"
    assert view["result_truth"]["randomness_summary_id"].startswith("rngsum_")
    assert view["result_truth"]["ranking_id"].startswith("routerank_")
    assert view["route"]["route_id"] == "route_" + "a" * 64
    assert view["route"]["action_count"] == 1
    assert view["route"]["randomness_summary"]["reliability_class"] == "deterministic"
    assert view["score"]["base"] == 14
    assert view["score"]["preference"][0]["applied_value"] == 5
    assert view["score"]["preference_evaluation"]["preference_score"] == 5
    assert view["score"]["terminal_composite"] == 19
    assert view["search_run"]["candidate_evidence"]["candidate_counts"] == {
        "censored": 0,
        "explored": 1,
        "failed": 0,
        "pruned": 0,
        "total": 1,
        "unexplored": 0,
    }
    assert view["search_run"]["candidate_evidence"]["evidence_id"].startswith(
        "searchev_"
    )
    assert view["search_run"]["candidate_evidence"]["total"] == 1
    assert view["search_run"]["coverage"]["coverage_id"].startswith(
        "searchcoverage_"
    )
    assert view["search_run"]["coverage"]["coverage_status"] == "best_observed"
    assert view["search_run"]["route_ranking"]["best_route_id"] == view["route"]["route_id"]
    assert view["search_run"]["best_observed"] is True

    route_artifact = next(
        artifact
        for artifact in service.job_catalog.status_snapshot(job_id).artifacts
        if artifact.kind == "route-dsl"
    )
    (tmp_path / "job-store" / route_artifact.path).write_text(
        "schema_version: 0.3a\nroute_id: route_tampered\n",
        encoding="utf-8",
    )
    corrupt = bridge.invoke(_request("job.result", {"job_id": job_id}))
    assert corrupt["ok"] is False
    assert corrupt["diagnostics"][0]["code"] == "artifact_hash_mismatch"


def test_result_view_rejects_invalid_frontier_exhausted_claim(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Coverage", "side": []},
        )
    )["result"]["deck"]
    experiment = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 7,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )["result"]["experiment"]
    queued = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": deck["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-result-coverage-test",
                "priority": 0,
            },
        )
    )
    job_id = queued["result"]["job"]["job_id"]
    worker = DesktopSearchWorker(
        tmp_path,
        launcher=_published_invalid_frontier_exhausted_launcher,
        artifact_validator=_accept_result_artifacts,
    )

    assert worker.run_once().status == "succeeded"
    result = bridge.invoke(_request("job.result", {"job_id": job_id}))

    assert result["ok"] is False
    assert result["diagnostics"][0]["code"] == "artifact_identity_mismatch"
    assert "frontier exhausted" in result["diagnostics"][0]["message"]


def test_result_view_rejects_candidate_count_mismatch(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Candidates", "side": []},
        )
    )["result"]["deck"]
    experiment = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 7,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )["result"]["experiment"]
    queued = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": deck["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-result-candidate-test",
                "priority": 0,
            },
        )
    )
    job_id = queued["result"]["job"]["job_id"]
    worker = DesktopSearchWorker(
        tmp_path,
        launcher=_published_invalid_candidate_counts_launcher,
        artifact_validator=_accept_result_artifacts,
    )

    assert worker.run_once().status == "succeeded"
    result = bridge.invoke(_request("job.result", {"job_id": job_id}))

    assert result["ok"] is False
    assert result["diagnostics"][0]["code"] == "artifact_identity_mismatch"
    assert "candidate evidence counts" in result["diagnostics"][0]["message"]


def test_result_view_rejects_ranking_summary_drift_from_best_route(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Ranking", "side": []},
        )
    )["result"]["deck"]
    experiment = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 7,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )["result"]["experiment"]
    queued = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": deck["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-result-ranking-test",
                "priority": 0,
            },
        )
    )
    job_id = queued["result"]["job"]["job_id"]
    worker = DesktopSearchWorker(
        tmp_path,
        launcher=_published_ranking_summary_drift_launcher,
        artifact_validator=_accept_result_artifacts,
    )

    assert worker.run_once().status == "succeeded"
    result = bridge.invoke(_request("job.result", {"job_id": job_id}))

    assert result["ok"] is False
    assert result["diagnostics"][0]["code"] == "artifact_identity_mismatch"
    assert "ranking summary" in result["diagnostics"][0]["message"]


def test_result_view_rejects_terminal_score_drift_from_preference_evaluation(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Score", "side": []},
        )
    )["result"]["deck"]
    experiment = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 7,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )["result"]["experiment"]
    queued = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": deck["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-result-score-test",
                "priority": 0,
            },
        )
    )
    job_id = queued["result"]["job"]["job_id"]
    worker = DesktopSearchWorker(
        tmp_path,
        launcher=_published_terminal_score_drift_launcher,
        artifact_validator=_accept_result_artifacts,
    )

    assert worker.run_once().status == "succeeded"
    result = bridge.invoke(_request("job.result", {"job_id": job_id}))

    assert result["ok"] is False
    assert result["diagnostics"][0]["code"] == "artifact_identity_mismatch"
    assert "terminal score" in result["diagnostics"][0]["message"]


def test_service_enqueues_independent_replay_verification_from_committed_route(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Verify", "side": []},
        )
    )["result"]["deck"]
    experiment = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 7,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )["result"]["experiment"]
    queued = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": deck["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-replay-source",
                "priority": 0,
            },
        )
    )
    search_job_id = queued["result"]["job"]["job_id"]
    worker = DesktopSearchWorker(
        tmp_path,
        launcher=_published_result_launcher,
        artifact_validator=_accept_result_artifacts,
    )

    assert worker.run_once().status == "succeeded"
    response = bridge.invoke(
        _request(
            "job.enqueue_replay_verification",
            {
                "idempotency_key": "desktop-replay-verification",
                "priority": 5,
                "search_job_id": search_job_id,
            },
        )
    )

    assert response["ok"] is True
    job = response["result"]["job"]
    assert job["kind"] == "replay"
    assert job["spec"]["dependency_ids"] == [search_job_id]
    assert job["spec"]["payload"] == {
        "replay_manifest_hash": "manifest_" + "d" * 64,
        "route_id": "route_" + "a" * 64,
    }
    assert response["result"]["source"]["search_job_id"] == search_job_id
    assert response["result"]["source"]["verification_state"] == "queued"


def test_worker_publishes_fresh_replay_verification_artifact_from_queued_job(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Verify Worker", "side": []},
        )
    )["result"]["deck"]
    experiment = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 7,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )["result"]["experiment"]
    queued_search = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": deck["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-replay-worker-source",
                "priority": 0,
            },
        )
    )
    search_job_id = queued_search["result"]["job"]["job_id"]
    search_worker = DesktopSearchWorker(
        tmp_path,
        launcher=_published_result_launcher,
        artifact_validator=_accept_result_artifacts,
    )
    assert search_worker.run_once().status == "succeeded"
    queued_replay = bridge.invoke(
        _request(
            "job.enqueue_replay_verification",
            {
                "idempotency_key": "desktop-replay-worker-verification",
                "priority": 5,
                "search_job_id": search_job_id,
            },
        )
    )
    replay_job_id = queued_replay["result"]["job"]["job_id"]
    replay_worker = DesktopSearchWorker(
        tmp_path,
        launcher=_replay_verification_launcher,
        artifact_validator=_accept_result_artifacts,
    )

    outcome = replay_worker.run_once()
    snapshot = service.job_catalog.status_snapshot(replay_job_id)
    verification_artifact = next(
        artifact
        for artifact in snapshot.artifacts
        if artifact.kind == "fresh-replay-verification"
    )
    report = json.loads(
        (tmp_path / "job-store" / verification_artifact.path).read_text(
            encoding="utf-8"
        )
    )

    assert outcome.status == "succeeded"
    assert snapshot.job.state == JobState.SUCCEEDED
    assert snapshot.latest_checkpoint is not None
    assert snapshot.latest_checkpoint.payload == {
        "route_id": "route_" + "a" * 64,
        "status": "verified",
        "verification_id": report["verification_id"],
    }
    assert verification_artifact.schema_version == "fresh-replay-verification-v1"
    assert report["route"]["route_id"] == "route_" + "a" * 64
    assert report["replay"]["manifest_hash"] == "manifest_" + "d" * 64
    assert report["status"] == "verified"


def test_worker_quarantines_replay_report_with_route_document_digest_drift(
    tmp_path: Path,
) -> None:
    service, replay_job_id = _queue_replay_verification_job(
        tmp_path,
        replay_key="desktop-replay-route-drift",
        search_key="desktop-replay-route-drift-source",
    )
    replay_worker = DesktopSearchWorker(
        tmp_path,
        launcher=_replay_route_digest_drift_launcher,
        artifact_validator=_accept_result_artifacts,
    )

    outcome = replay_worker.run_once()
    snapshot = service.job_catalog.status_snapshot(replay_job_id)

    assert outcome.status == "quarantined"
    assert snapshot.job.state == JobState.QUARANTINED
    assert not [
        artifact
        for artifact in snapshot.artifacts
        if artifact.kind == "fresh-replay-verification"
    ]


def test_service_rejects_replay_verification_until_search_artifacts_are_committed(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Queued Verify", "side": []},
        )
    )["result"]["deck"]
    experiment = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 7,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )["result"]["experiment"]
    queued = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": deck["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-replay-source-queued",
                "priority": 0,
            },
        )
    )
    response = bridge.invoke(
        _request(
            "job.enqueue_replay_verification",
            {
                "idempotency_key": "desktop-replay-verification-rejected",
                "priority": 0,
                "search_job_id": queued["result"]["job"]["job_id"],
            },
        )
    )

    assert response["ok"] is False
    assert response["diagnostics"][0]["code"] == "verification_not_available"


def test_service_composes_valid_versioned_experiments_for_each_strategy(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Compose", "side": []},
        )
    )["result"]["deck"]

    for strategy in ("random_search_v1", "beam_search_v1", "mcts_v1"):
        response = bridge.invoke(
            _request(
                "scenario.compose_search",
                {
                    "configuration": {
                        "interruption_card_code": 97268402,
                        "max_depth": 32,
                        "max_nodes": 1000,
                        "max_seconds": 120,
                        "pool_size": 4,
                        "scenario_preset_id": "terminal_board_min_monster_v1",
                        "seed": 42017,
                        "strategy": strategy,
                    },
                    "deck_id": deck["deck_id"],
                },
            )
        )
        experiment = response["result"]["experiment"]

        assert response["ok"] is True
        assert experiment["schema_version"] == "0.4"
        assert experiment["deck"]["source"] == "inline"
        assert experiment["scenario"]["opening_hand"] == {
            "mode": "random",
            "seed": 42017,
            "size": 5,
        }
        assert experiment["search"]["strategy"] == strategy
        assert experiment["search"]["parameters"]["parallel"] == {
            "base_seed": 42017,
            "max_retries": 1,
            "pool_size": 4,
        }
        assert experiment["objective"] == "maximize_terminal_board"
        assert experiment["evaluator"]["id"] == "real_core_board_count"
        assert experiment["success_predicate"]["id"] == "real_core_min_monster_count"
        assert experiment["interruption"]["mode"] == "specified"
        assert experiment["terminal_preference_profile"]["profile_id"].startswith(
            "termpref_"
        )
        assert experiment["terminal_preference_profile"]["rules"] == []


def test_service_composes_fixed_and_conditional_opening_hand(tmp_path: Path) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Opening", "side": []},
        )
    )["result"]["deck"]
    fixed = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "opening_hand": {
                        "cards": _codes()[:5],
                        "mode": "fixed",
                    },
                    "seed": 9,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )
    conditional = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "opening_hand": {
                        "conditions": [
                            {"code": _codes()[0], "max_count": 1, "min_count": 1}
                        ],
                        "max_attempts": 250,
                        "mode": "conditional",
                        "seed": 11,
                        "size": 5,
                    },
                    "seed": 9,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )

    assert fixed["ok"] is True
    assert fixed["result"]["experiment"]["scenario"]["opening_hand"] == {
        "cards": _codes()[:5],
        "mode": "fixed",
    }
    assert conditional["ok"] is True
    assert conditional["result"]["experiment"]["scenario"]["opening_hand"] == {
        "conditions": [{"code": _codes()[0], "max_count": 1, "min_count": 1}],
        "max_attempts": 250,
        "mode": "conditional",
        "seed": 11,
        "size": 5,
    }


def test_service_clones_and_binds_terminal_preference_profile(tmp_path: Path) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Profile", "side": []},
        )
    )["result"]["deck"]
    listed = bridge.invoke(_request("profile.list", {}))
    default_profile = listed["result"]["profiles"][0]["profile"]["profile_id"]
    cloned = bridge.invoke(
        _request(
            "profile.clone",
            {
                "name": "Hand preference",
                "profile_id": default_profile,
                "rules": [
                    {
                        "card_code": _codes()[0],
                        "controller": 0,
                        "enabled": True,
                        "location": "HAND",
                        "max_count": None,
                        "min_count": 1,
                        "position": "ANY",
                        "rule_id": "opening-copy",
                        "scoring_mode": "once",
                        "weight": 5,
                    }
                ],
            },
        )
    )
    profile_id = cloned["result"]["profile"]["profile_id"]

    response = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "preference_profile_id": profile_id,
                    "seed": 1,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck["deck_id"],
            },
        )
    )
    experiment = response["result"]["experiment"]

    assert response["ok"] is True
    assert profile_id != default_profile
    assert experiment["terminal_preference_profile"]["profile_id"] == profile_id
    assert experiment["terminal_preference_profile"]["rules"][0]["weight"] == 5


def test_service_rejects_unknown_strategy_before_preflight(tmp_path: Path) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = service.deck_catalog.register(
        name="Reject",
        source="inline",
        sections={"extra": (), "main": tuple(_codes()), "side": ()},
    )
    response = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "seed": 1,
                    "strategy": "future_strategy",
                },
                "deck_id": deck.deck_id,
            },
        )
    )

    assert response["ok"] is False
    assert response["diagnostics"][0]["code"] == "unsupported_search_strategy"


def test_service_rejects_unknown_scenario_preset_before_preflight(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = service.deck_catalog.register(
        name="Preset",
        source="inline",
        sections={"extra": (), "main": tuple(_codes()), "side": ()},
    )
    response = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "scenario_preset_id": "renderer_defined_expression",
                    "seed": 1,
                    "strategy": "random_search_v1",
                },
                "deck_id": deck.deck_id,
            },
        )
    )

    assert response["ok"] is False
    assert response["diagnostics"][0]["code"] == "unsupported_scenario_preset"
    assert response["diagnostics"][0]["path"] == (
        "$.payload.configuration.scenario_preset_id"
    )


def test_service_rejects_pool_size_outside_desktop_limit(tmp_path: Path) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    deck = service.deck_catalog.register(
        name="Pool",
        source="inline",
        sections={"extra": (), "main": tuple(_codes()), "side": ()},
    )
    response = bridge.invoke(
        _request(
            "scenario.compose_search",
            {
                "configuration": {
                    "interruption_card_code": None,
                    "max_depth": 8,
                    "max_nodes": 10,
                    "max_seconds": 30,
                    "pool_size": 9,
                    "seed": 1,
                    "strategy": "beam_search_v1",
                },
                "deck_id": deck.deck_id,
            },
        )
    )

    assert response["ok"] is False
    assert response["diagnostics"][0]["code"] == "invalid_search_configuration"
    assert response["diagnostics"][0]["path"] == "$.payload.configuration.pool_size"


def test_cancel_does_not_finish_a_job_claimed_during_the_request(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path)

    class RacingCatalog:
        def get_job(self, _: str) -> Any:
            return SimpleNamespace(state=JobState.QUEUED)

        def request_cancel(self, *_: Any, **__: Any) -> Any:
            return SimpleNamespace(
                attempt=1,
                lease_token="worker-lease",
                to_dict=lambda: {"state": "cancelling"},
            )

        def finish_cancelled(self, *_: Any, **__: Any) -> Any:
            raise AssertionError("a claimed worker must finish its own cancellation")

    service.job_catalog = RacingCatalog()  # type: ignore[assignment]
    result = service.job_cancel({"job_id": "job_race"})

    assert result["job"]["state"] == "cancelling"


def test_analytics_and_card_capabilities_fail_closed_or_use_typed_contracts(
    tmp_path: Path,
) -> None:
    bridge = DesktopBridge(DesktopApplicationService(tmp_path).handlers())
    description = bridge.invoke(_request("system.describe", {}))
    query = bridge.invoke(
        _request(
            "analytics.query",
            {
                "request": {
                    "cursor": None,
                    "fields": ["run", "success"],
                    "filters": [],
                    "limit": 20,
                    "schema_version": ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION,
                    "snapshot_id": None,
                    "sort": [],
                }
            },
        )
    )
    card = bridge.invoke(
        _request(
            "card.get",
            {
                "query": {
                    "card_code": 10000,
                    "expected_asset_lock_id": None,
                    "expected_provider_version": CARD_PRESENTATION_PROVIDER_VERSION,
                    "fallback_locales": ["en"],
                    "redacted": False,
                    "requested_locale": "ja",
                    "schema_version": CARD_PRESENTATION_QUERY_VERSION,
                }
            },
        )
    )

    assert description["result"]["capabilities"]["card_presentation"] is False
    assert description["result"]["capabilities"]["analytics_export"] is True
    assert description["result"]["capabilities"]["analytics_export_formats"] == [
        "json",
        "csv",
        "parquet",
    ]
    assert description["result"]["capabilities"]["export_worker_health"] == "unknown"
    assert description["result"]["capabilities"]["worker_health"] == "unknown"
    assert query["ok"] is True
    assert query["result"]["rows"] == []
    assert card["ok"] is False
    assert card["diagnostics"][0]["code"] == "card_presentation_source_unavailable"


def test_export_bridge_queues_a_path_free_background_job(tmp_path: Path) -> None:
    service = DesktopApplicationService(tmp_path)
    bridge = DesktopBridge(service.handlers())

    response = bridge.invoke(
        _request(
            "analytics.export.enqueue",
            {
                "format": "csv",
                "idempotency_key": None,
                "priority": 0,
                "source": {
                    "cursor": None,
                    "fields": ["run"],
                    "filters": [],
                    "limit": 20,
                    "schema_version": ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION,
                    "snapshot_id": None,
                    "sort": [],
                },
                "source_kind": "query",
            },
        )
    )

    assert response["ok"] is True
    assert response["result"]["job"]["spec"]["kind"] == "export"
    assert service.analytics_export_worker.run_once().status == "succeeded"
    status = bridge.invoke(
        _request(
            "job.status",
            {"job_id": response["result"]["job"]["job_id"]},
        )
    )
    assert status["result"]["job"]["state"] == "succeeded"
    assert {item["kind"] for item in status["result"]["artifacts"]} == {
        "analytics_export_data",
        "analytics_export_manifest",
    }
