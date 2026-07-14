from __future__ import annotations

import json
import subprocess

import pytest

from ygo_effect_dsl.prototype.frontier import RealCoreFrontierAdapter


class _Process:
    def __init__(
        self,
        *,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
        timeout: bool = False,
    ) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._timeout = timeout
        self.killed = False

    def communicate(self, *, input: str | None = None, timeout: float | None = None):
        del input, timeout
        if self._timeout and not self.killed:
            raise subprocess.TimeoutExpired("worker", 1)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True


def test_frontier_adapter_retries_retryable_worker_failure(monkeypatch) -> None:
    failure = json.dumps(
        {
            "failure": {
                "message": "worker crashed",
                "retryable": True,
            }
        }
    )
    success = json.dumps({"schema_version": "real-core-frontier-v1"})
    processes = iter(
        [
            _Process(returncode=1, stdout=failure),
            _Process(returncode=0, stdout=success),
        ]
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: next(processes))
    adapter = RealCoreFrontierAdapter(max_retries=1)

    document = adapter._invoke({}, ())

    assert document["schema_version"] == "real-core-frontier-v1"
    assert adapter.worker_invocations == 2
    assert adapter.worker_retries == 1


def test_frontier_adapter_retries_timeout_then_reports_failure(monkeypatch) -> None:
    processes = iter(
        [
            _Process(returncode=-9, timeout=True),
            _Process(returncode=-9, timeout=True),
        ]
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: next(processes))
    adapter = RealCoreFrontierAdapter(timeout_seconds=0.01, max_retries=1)

    with pytest.raises(RuntimeError, match="timed out"):
        adapter._invoke({}, ())

    assert adapter.worker_invocations == 2
    assert adapter.worker_retries == 1
