from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from ygo_effect_dsl.cli import cmd_experiment as command_module
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    FailureRecord,
    RecoveryAction,
)
from ygo_effect_dsl.engine.search import BeamSearchStrategyV1
from ygo_effect_dsl.io_atomic import atomic_write_text, sha256_file
from ygo_effect_dsl.prototype.frontier import RealCoreFrontierWorkerError


class _Preflight:
    ok = True

    def to_dict(self) -> dict[str, object]:
        return {"diagnostics": [], "ok": True}


class _Adapter:
    worker_invocations = 1
    worker_retries = 0
    quarantined_attempt_ids = ["frontierattempt_failed"]
    worker_attempts = [
        {
            "attempt_id": "frontierattempt_failed",
            "quarantined": True,
            "schema_version": "real-core-frontier-worker-attempt-v1",
            "status": "failure",
        }
    ]


def _args(tmp_path) -> argparse.Namespace:
    return argparse.Namespace(
        experiment_file=tmp_path / "experiment.yaml",
        external_root=None,
        max_depth=None,
        max_nodes=None,
        max_replays=None,
        max_retries=1,
        max_seconds=None,
        evaluator_id=None,
        evaluator_version=None,
        interruption_mode=None,
        out=tmp_path / "best.route.yaml",
        search_report=tmp_path / "search-report.json",
        worker_timeout=1.0,
    )


def _experiment() -> dict[str, object]:
    return {
        "experiment_id": "search_cli_artifact_test",
        "search": {
            "budget": {"max_nodes": 1},
            "parameters": {"seed": 1},
            "strategy": "random_search_v1",
        },
    }


def _patch_inputs(monkeypatch, adapter: _Adapter) -> None:
    monkeypatch.setattr(command_module, "_resolved_experiment", lambda _args: _experiment())
    monkeypatch.setattr(command_module, "preflight_scenario", lambda *_args, **_kwargs: _Preflight())
    monkeypatch.setattr(command_module, "RealCoreFrontierAdapter", lambda **_kwargs: adapter)


def test_search_cli_publishes_route_before_commit_report(tmp_path, monkeypatch) -> None:
    args = _args(tmp_path)
    adapter = _Adapter()
    adapter.worker_attempts = []
    adapter.quarantined_attempt_ids = []
    order: list[str] = []
    result = SimpleNamespace(
        best_route=SimpleNamespace(
            route_document={"route_id": "route_fixture"},
            route_id="route_fixture",
        ),
        nodes=1,
        replays=1,
        run_id="searchrun_fixture",
        to_dict=lambda: {
            "best_route": {"route_id": "route_fixture"},
            "schema_version": "search-run-result-v5",
            "termination_reason": "max_nodes",
        },
    )

    class _Executor:
        def __init__(self, *_args):
            pass

        def run(self, _experiment):
            return result

    _patch_inputs(monkeypatch, adapter)
    monkeypatch.setattr(command_module, "SearchExecutor", _Executor)
    monkeypatch.setattr(
        command_module,
        "dump_route_document",
        lambda _document, path: (order.append("route"), atomic_write_text(path, "route\n")),
    )
    write_report = command_module._write_search_report

    def _write_report(path, report):
        order.append("report")
        write_report(path, report)

    monkeypatch.setattr(command_module, "_write_search_report", _write_report)

    assert command_module.cmd_experiment_search(args) == 0

    report = json.loads(args.search_report.read_text(encoding="utf-8"))
    assert order == ["route", "report"]
    assert report["status"] == "complete"
    assert report["report_schema_version"] == "search-run-report-v1"
    assert report["artifact_commit"] == {
        "route_id": "route_fixture",
        "route_sha256": sha256_file(args.out),
        "schema_version": "search-artifact-commit-v1",
        "status": "committed",
    }


def test_search_cli_records_structured_worker_failure_without_route_publish(
    tmp_path, monkeypatch
) -> None:
    args = _args(tmp_path)
    args.out.write_text("previous route\n", encoding="utf-8")
    adapter = _Adapter()
    failure = FailureRecord(
        category="worker_timeout",
        disposition=FailureDisposition.PATH_FAILURE,
        recovery=RecoveryAction.REPLACE_WORKER,
        retryable=True,
        message="worker deadline exceeded",
        exception_type="OcgcoreWorkerTimeoutError",
    )
    error = RealCoreFrontierWorkerError(
        failure,
        attempts=adapter.worker_attempts,
        retry_exhausted=True,
    )

    class _Executor:
        def __init__(self, *_args):
            pass

        def run(self, _experiment):
            raise error

    _patch_inputs(monkeypatch, adapter)
    monkeypatch.setattr(command_module, "SearchExecutor", _Executor)

    with pytest.raises(RealCoreFrontierWorkerError):
        command_module.cmd_experiment_search(args)

    report = json.loads(args.search_report.read_text(encoding="utf-8"))
    assert args.out.read_text(encoding="utf-8") == "previous route\n"
    assert report["schema_version"] == "search-run-failure-v2"
    assert report["status"] == "worker_failure"
    assert report["failure"]["category"] == "worker_timeout"
    assert report["artifact_commit"]["status"] == "not_published"
    assert report["quarantined_attempt_ids"] == ["frontierattempt_failed"]


def test_search_cli_rejects_shared_route_and_report_path(tmp_path, monkeypatch) -> None:
    args = _args(tmp_path)
    args.search_report = args.out
    monkeypatch.setattr(command_module, "_resolved_experiment", lambda _args: _experiment())

    with pytest.raises(ValueError, match="different paths"):
        command_module.cmd_experiment_search(args)


def test_search_cli_selects_beam_strategy(tmp_path, monkeypatch) -> None:
    args = _args(tmp_path)
    adapter = _Adapter()
    adapter.worker_attempts = []
    adapter.quarantined_attempt_ids = []
    experiment = _experiment()
    experiment["search"]["strategy"] = "beam_search_v1"
    experiment["search"]["parameters"] = {
        "beam_width": 2,
        "seed": 7,
        "termination": {"stop_on_success": True},
    }
    result = SimpleNamespace(
        best_route=SimpleNamespace(
            route_document={"route_id": "route_fixture"},
            route_id="route_fixture",
        ),
        nodes=2,
        replays=2,
        run_id="searchrun_fixture",
        to_dict=lambda: {
            "best_route": {"route_id": "route_fixture"},
            "schema_version": "search-run-result-v5",
            "strategy_id": "beam_search_v1",
            "termination_reason": "goal_reached",
        },
    )
    captured = {}

    class _Executor:
        def __init__(self, _adapter, strategy, _budget):
            captured["strategy"] = strategy

        def run(self, _experiment):
            return result

    monkeypatch.setattr(command_module, "_resolved_experiment", lambda _args: experiment)
    monkeypatch.setattr(
        command_module, "preflight_scenario", lambda *_args, **_kwargs: _Preflight()
    )
    monkeypatch.setattr(
        command_module, "RealCoreFrontierAdapter", lambda **_kwargs: adapter
    )
    monkeypatch.setattr(command_module, "SearchExecutor", _Executor)
    monkeypatch.setattr(
        command_module,
        "dump_route_document",
        lambda _document, path: atomic_write_text(path, "route\n"),
    )

    assert command_module.cmd_experiment_search(args) == 0
    assert isinstance(captured["strategy"], BeamSearchStrategyV1)
    assert captured["strategy"].parameters == {"beam_width": 2, "seed": 7}
