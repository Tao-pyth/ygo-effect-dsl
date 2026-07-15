from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import pytest

from ygo_effect_dsl.desktop.lifecycle import (
    DesktopSearchWorker,
    DesktopWorkerSupervisor,
    ValidatedSearchArtifacts,
    launch_process_tree,
    process_containment_contract,
)
from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.storage import JobState


class _Preflight:
    ok = True

    def to_dict(self) -> dict[str, Any]:
        return {"diagnostics": [], "ok": True}


class _FakeProcess:
    def __init__(self, return_code: int, *, remains_running: bool = False) -> None:
        self._final_return_code = return_code
        self._running = remains_running
        self.returncode: int | None = None if remains_running else return_code
        self.pid = 501
        self.terminated = False

    def poll(self) -> int | None:
        return None if self._running else self.returncode

    def communicate(self) -> tuple[str, str]:
        if self._running:
            self._running = False
            self.returncode = self._final_return_code
        return ("worker stdout", "worker stderr")

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        self._running = False
        self.returncode = self._final_return_code
        return self.returncode


class _FakeTree:
    containment = "test-process-tree"

    def __init__(self, process: _FakeProcess) -> None:
        self.process = process
        self.closed = False

    def active_process_count(self) -> int:
        return 1 if self.process.poll() is None else 0

    def terminate(self, *, grace_seconds: float = 2.0) -> None:
        del grace_seconds
        self.process.terminated = True
        self.process._running = False
        self.process.returncode = self.process._final_return_code

    def close(self) -> None:
        self.closed = True


def _codes() -> list[int]:
    return list(range(10_001, 10_041))


def _queued_search(tmp_path: Path) -> tuple[DesktopApplicationService, str]:
    service = DesktopApplicationService(
        tmp_path, preflight=lambda *_a, **_k: _Preflight()
    )
    deck = service.deck_catalog.register(
        name="Lifecycle",
        source="inline",
        sections={"extra": (), "main": tuple(_codes()), "side": ()},
    )
    experiment = service.scenario_compose_search(
        {
            "configuration": {
                "interruption_card_code": None,
                "max_depth": 8,
                "max_nodes": 10,
                "max_seconds": 30,
                "seed": 7,
                "strategy": "random_search_v1",
            },
            "deck_id": deck.deck_id,
        }
    )["experiment"]
    queued = service.job_enqueue_search(
        {
            "deck_id": deck.deck_id,
            "experiment": experiment,
            "idempotency_key": "desktop-lifecycle-test",
            "priority": 0,
        }
    )
    return service, queued["job"]["job_id"]


def _success_launcher(command: list[str], *, cwd: Path) -> _FakeTree:
    del cwd
    route = Path(command[command.index("--out") + 1])
    report = Path(command[command.index("--search-report") + 1])
    route.write_text(
        "schema_version: 0.3a\nroute_id: route_fixture\n", encoding="utf-8"
    )
    report.write_text(
        json.dumps(
            {
                "best_route": {"route_id": "route_fixture"},
                "nodes": 7,
                "report_schema_version": "search-run-report-v1",
                "run_id": "searchrun_fixture",
                "status": "complete",
                "termination_reason": "goal_reached",
            }
        ),
        encoding="utf-8",
    )
    return _FakeTree(_FakeProcess(0))


def _accept_fixture_artifacts(
    *,
    experiment: dict[str, Any],
    route_path: Path,
    report_path: Path,
    max_nodes: int,
) -> ValidatedSearchArtifacts:
    del experiment, max_nodes
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return ValidatedSearchArtifacts(
        route_content=route_path.read_bytes(),
        report_content=report_path.read_bytes(),
        report=report,
        nodes=report["nodes"],
        route_id=report["best_route"]["route_id"],
        semantic_result_digest="jobsemantic_" + "a" * 64,
    )


def test_desktop_worker_publishes_only_complete_search_artifacts(
    tmp_path: Path,
) -> None:
    service, job_id = _queued_search(tmp_path)
    worker = DesktopSearchWorker(
        tmp_path,
        launcher=_success_launcher,
        artifact_validator=_accept_fixture_artifacts,
    )

    outcome = worker.run_once()
    snapshot = service.job_catalog.status_snapshot(job_id)

    assert outcome.status == "succeeded"
    assert snapshot.job.state == JobState.SUCCEEDED
    assert snapshot.latest_checkpoint is not None
    assert snapshot.latest_checkpoint.completed_units == 7
    assert snapshot.latest_checkpoint.semantic_result_digest is not None
    assert {artifact.kind for artifact in snapshot.artifacts} == {
        "route-dsl",
        "search-run-report",
    }
    for artifact in snapshot.artifacts:
        assert (tmp_path / "job-store" / artifact.path).is_file()


def test_desktop_worker_rejects_unvalidated_success_artifacts(tmp_path: Path) -> None:
    service, job_id = _queued_search(tmp_path)
    worker = DesktopSearchWorker(tmp_path, launcher=_success_launcher)

    outcome = worker.run_once()
    snapshot = service.job_catalog.status_snapshot(job_id)

    assert outcome.status == "quarantined"
    assert snapshot.job.state == JobState.QUARANTINED
    assert snapshot.artifacts == ()


def test_desktop_worker_crash_retries_without_success_artifacts(tmp_path: Path) -> None:
    service, job_id = _queued_search(tmp_path)
    tree = _FakeTree(_FakeProcess(86))
    worker = DesktopSearchWorker(tmp_path, launcher=lambda *_a, **_k: tree)

    outcome = worker.run_once()
    snapshot = service.job_catalog.status_snapshot(job_id)

    assert outcome.status == "retrying"
    assert snapshot.job.state == JobState.RETRYING
    assert snapshot.job.error_code == "worker_crash"
    assert snapshot.artifacts == ()
    assert tree.closed


def test_desktop_host_stop_terminates_tree_and_checkpoints_retry(
    tmp_path: Path,
) -> None:
    service, job_id = _queued_search(tmp_path)
    tree = _FakeTree(_FakeProcess(1, remains_running=True))
    worker = DesktopSearchWorker(tmp_path, launcher=lambda *_a, **_k: tree)

    outcome = worker.run_once(stop_requested=lambda: True)
    snapshot = service.job_catalog.status_snapshot(job_id)

    assert outcome.status == "retrying"
    assert outcome.process_count_before_cleanup == 1
    assert tree.process.terminated
    assert tree.closed
    assert snapshot.job.state == JobState.RETRYING
    assert snapshot.latest_checkpoint is not None
    assert snapshot.latest_checkpoint.recovery_position.endswith(":host-stop")


def test_desktop_cancel_ack_terminates_tree_and_never_retries(tmp_path: Path) -> None:
    service, job_id = _queued_search(tmp_path)
    tree = _FakeTree(_FakeProcess(1, remains_running=True))
    worker = DesktopSearchWorker(tmp_path, launcher=lambda *_a, **_k: tree)
    requested = False

    def sleep(_: float) -> None:
        nonlocal requested
        if not requested:
            service.job_catalog.request_cancel(
                job_id,
                actor="renderer",
                now=worker.now(),
                reason="test_cancel",
            )
            requested = True

    worker.sleep = sleep
    outcome = worker.run_once()
    snapshot = service.job_catalog.status_snapshot(job_id)

    assert outcome.status == "cancelled"
    assert tree.process.terminated
    assert snapshot.job.state == JobState.CANCELLED
    assert snapshot.artifacts == ()


def test_supervisor_failure_is_observable_without_raising_in_host_thread(
    tmp_path: Path,
) -> None:
    class FailingWorker:
        def run_once(self, **_: Any) -> None:
            raise RuntimeError("fixture worker failure")

    supervisor = DesktopWorkerSupervisor(
        tmp_path,
        worker_factory=lambda *_a, **_k: FailingWorker(),
    )
    supervisor.start()
    assert supervisor._thread is not None
    supervisor._thread.join(2)

    assert supervisor.health == "failed"
    assert isinstance(supervisor.failure, RuntimeError)
    supervisor.stop()


def test_unexpected_worker_failure_still_terminates_process_tree(
    tmp_path: Path,
) -> None:
    service, job_id = _queued_search(tmp_path)
    tree = _FakeTree(_FakeProcess(1, remains_running=True))
    worker = DesktopSearchWorker(tmp_path, launcher=lambda *_a, **_k: tree)

    def fail_control_signal(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("catalog unavailable")

    worker.catalog.control_signal = fail_control_signal  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="catalog unavailable"):
        worker.run_once()

    assert tree.process.terminated
    assert tree.closed
    snapshot = worker.catalog.status_snapshot(job_id)
    assert snapshot.job.state == JobState.RUNNING


def test_process_containment_contract_and_real_tree_cleanup(tmp_path: Path) -> None:
    contract = process_containment_contract()
    assert contract["windows_containment"] == "windows-job-object-kill-on-close-v1"
    command = [
        sys.executable,
        "-c",
        (
            "import subprocess,sys,time; "
            "time.sleep(0.5); "
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            "time.sleep(60)"
        ),
    ]
    tree = launch_process_tree(command, cwd=tmp_path)
    try:
        for _ in range(50):
            count = tree.active_process_count()
            if count is not None and count >= (2 if os.name == "nt" else 1):
                break
            time.sleep(0.1)
        if os.name == "nt":
            assert tree.active_process_count() is not None
            assert tree.active_process_count() >= 2
        tree.terminate(grace_seconds=3)
        assert tree.process.poll() is not None
        if os.name == "nt":
            assert tree.active_process_count() == 0
    finally:
        tree.terminate(grace_seconds=3)
        tree.close()
