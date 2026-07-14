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


def _frontier_document(**overrides):
    document = {
        "actions": [],
        "legal_stop": {"can_stop": False, "reason": "pending_request"},
        "peak_score": 0,
        "request": {"request_signature": "req_fixture"},
        "route_document": None,
        "schema_version": "real-core-frontier-v2",
        "score": 0,
        "state_completeness": "query_api_projection",
        "state_id": "state_fixture",
        "success": False,
    }
    document.update(overrides)
    return document


def test_frontier_adapter_retries_retryable_worker_failure(monkeypatch) -> None:
    failure = json.dumps(
        {
            "failure": {
                "message": "worker crashed",
                "retryable": True,
            }
        }
    )
    success = json.dumps({"schema_version": "real-core-frontier-v2"})
    processes = iter(
        [
            _Process(returncode=1, stdout=failure),
            _Process(returncode=0, stdout=success),
        ]
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: next(processes))
    adapter = RealCoreFrontierAdapter(max_retries=1)

    document = adapter._invoke({}, ())

    assert document["schema_version"] == "real-core-frontier-v2"
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


def test_frontier_adapter_exposes_projection_completeness(monkeypatch) -> None:
    adapter = RealCoreFrontierAdapter()
    monkeypatch.setattr(adapter, "_invoke", lambda *_args: _frontier_document())

    frontier = adapter.replay({}, ())

    assert frontier.state_completeness == "query_api_projection"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"schema_version": "real-core-frontier-v1"}, "unsupported frontier schema"),
        ({"state_completeness": None}, "missing state_completeness"),
        ({"state_completeness": "partial"}, "state_completeness must be"),
    ],
)
def test_frontier_adapter_rejects_unsafe_state_identity_contracts(
    monkeypatch, overrides, message
) -> None:
    adapter = RealCoreFrontierAdapter()
    monkeypatch.setattr(
        adapter,
        "_invoke",
        lambda *_args: _frontier_document(**overrides),
    )

    with pytest.raises(ValueError, match=message):
        adapter.replay({}, ())
