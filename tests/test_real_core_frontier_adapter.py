from __future__ import annotations

import json
import subprocess

import pytest

from ygo_effect_dsl.engine.search import apply_turn_lifecycle
from ygo_effect_dsl.prototype.frontier import (
    REAL_CORE_FRONTIER_ATTEMPT_SCHEMA_VERSION,
    REAL_CORE_FRONTIER_FAILURE_SCHEMA_VERSION,
    RealCoreFrontierAdapter,
    RealCoreFrontierWorkerError,
)


class _Process:
    _next_pid = 4100

    def __init__(
        self,
        *,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
        timeout: bool = False,
        ipc_error: bool = False,
    ) -> None:
        type(self)._next_pid += 1
        self.pid = type(self)._next_pid
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._timeout = timeout
        self._ipc_error = ipc_error
        self.killed = False
        self.communications = 0

    def communicate(self, *, input: str | None = None, timeout: float | None = None):
        del input, timeout
        self.communications += 1
        if self._ipc_error and not self.killed:
            raise OSError("private worker diagnostic")
        if self._timeout and not self.killed:
            raise subprocess.TimeoutExpired("worker", 1)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True

    def poll(self) -> int:
        return self.returncode


def _failure_envelope(
    *, category: str = "worker_crash", message: str = "worker crashed", retryable: bool
) -> str:
    return json.dumps(
        {
            "failure": {
                "category": category,
                "context": {},
                "disposition": "path_failure",
                "exception_type": "OcgcoreWorkerCrashError",
                "message": message,
                "recovery": "replace_worker",
                "retryable": retryable,
            },
            "schema_version": "real-core-worker-failure-v1",
            "status": "failure",
        }
    )


def _frontier_document(**overrides):
    _, lifecycle = apply_turn_lifecycle(
        (),
        turn=1,
        phase="draw",
        turn_limit=1,
        request_type="select_idle_command",
        process_state="awaiting_response",
        chain_count=0,
        legal_stop=False,
        forced_response=False,
    )
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
        "turn_lifecycle": lifecycle.to_dict(),
    }
    document.update(overrides)
    return document


def test_frontier_adapter_retries_retryable_worker_failure(monkeypatch) -> None:
    failure = _failure_envelope(retryable=True)
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
    assert [attempt["status"] for attempt in adapter.worker_attempts] == [
        "failure",
        "success",
    ]
    assert adapter.worker_attempts[0]["quarantined"] is True
    assert adapter.worker_attempts[1]["quarantined"] is False
    assert adapter.worker_attempts[0]["worker_input_digest"] == (
        adapter.worker_attempts[1]["worker_input_digest"]
    )
    assert adapter.quarantined_attempt_ids == [
        adapter.worker_attempts[0]["attempt_id"]
    ]


def test_frontier_adapter_aggregates_clean_success_without_attempt_growth(
    monkeypatch,
) -> None:
    processes = iter(
        [
            _Process(
                returncode=0,
                stdout=json.dumps({"schema_version": "real-core-frontier-v2"}),
            )
            for _index in range(32)
        ]
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: next(processes))
    adapter = RealCoreFrontierAdapter()

    for index in range(32):
        adapter._invoke({"ordinal": index}, ())

    assert adapter.worker_invocations == 32
    assert adapter.worker_attempts == []
    assert adapter.quarantined_attempt_ids == []


def test_frontier_adapter_retries_timeout_then_reports_failure(monkeypatch) -> None:
    processes = iter(
        [
            _Process(returncode=-9, timeout=True),
            _Process(returncode=-9, timeout=True),
        ]
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: next(processes))
    adapter = RealCoreFrontierAdapter(timeout_seconds=0.01, max_retries=1)

    with pytest.raises(RealCoreFrontierWorkerError, match="deadline") as raised:
        adapter._invoke({}, ())

    assert adapter.worker_invocations == 2
    assert adapter.worker_retries == 1
    assert raised.value.retry_exhausted is True
    assert raised.value.failure.category == "worker_timeout"
    assert raised.value.to_dict()["schema_version"] == (
        REAL_CORE_FRONTIER_FAILURE_SCHEMA_VERSION
    )
    assert all(
        attempt["schema_version"] == REAL_CORE_FRONTIER_ATTEMPT_SCHEMA_VERSION
        for attempt in raised.value.attempts
    )
    assert all(attempt["terminated"] for attempt in raised.value.attempts)
    assert len({attempt["process_id"] for attempt in raised.value.attempts}) == 2
    assert "private" not in json.dumps(raised.value.to_dict())


def test_frontier_adapter_does_not_retry_invalid_json(monkeypatch) -> None:
    process = _Process(returncode=0, stdout="not-json", stderr="private stderr")
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    adapter = RealCoreFrontierAdapter(max_retries=3)

    with pytest.raises(RealCoreFrontierWorkerError) as raised:
        adapter._invoke({}, ())

    assert raised.value.failure.category == "worker_protocol"
    assert raised.value.retry_exhausted is False
    assert adapter.worker_invocations == 1
    assert adapter.worker_retries == 0
    assert adapter.worker_attempts[0]["quarantined"] is True
    assert "private stderr" not in json.dumps(raised.value.to_dict())


def test_frontier_adapter_quarantines_invalid_frontier_shape(monkeypatch) -> None:
    process = _Process(
        returncode=0,
        stdout=json.dumps({"schema_version": "real-core-frontier-v1"}),
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    adapter = RealCoreFrontierAdapter(max_retries=2)

    with pytest.raises(RealCoreFrontierWorkerError) as raised:
        adapter.replay({}, ())

    assert raised.value.failure.category == "worker_protocol"
    assert adapter.worker_invocations == 1
    assert adapter.worker_retries == 0
    assert adapter.worker_attempts[0]["status"] == "failure"
    assert adapter.worker_attempts[0]["quarantined"] is True


def test_frontier_adapter_retries_ipc_failure_with_fresh_process(monkeypatch) -> None:
    failed = _Process(returncode=-9, ipc_error=True)
    recovered = _Process(
        returncode=0,
        stdout=json.dumps({"schema_version": "real-core-frontier-v2"}),
    )
    processes = iter([failed, recovered])
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: next(processes))
    adapter = RealCoreFrontierAdapter(max_retries=1)

    adapter._invoke({}, ())

    assert [attempt["category"] for attempt in adapter.worker_attempts] == [
        "worker_ipc",
        None,
    ]
    assert adapter.worker_retries == 1
    assert len({attempt["process_id"] for attempt in adapter.worker_attempts}) == 2
    assert failed.killed is True
    assert failed.communications == 2


def test_frontier_adapter_exposes_projection_completeness(monkeypatch) -> None:
    adapter = RealCoreFrontierAdapter()
    monkeypatch.setattr(adapter, "_invoke", lambda *_args: _frontier_document())

    frontier = adapter.replay({}, ())

    assert frontier.state_completeness == "query_api_projection"
    assert frontier.request["turn_lifecycle"]["turn_limit_reached"] is True


def test_frontier_adapter_rejects_tampered_turn_lifecycle(monkeypatch) -> None:
    adapter = RealCoreFrontierAdapter()
    document = _frontier_document()
    document["turn_lifecycle"]["turn"] = 2
    monkeypatch.setattr(adapter, "_invoke", lambda *_args: document)

    with pytest.raises(ValueError, match="turn cannot exceed turn_limit"):
        adapter.replay({}, ())


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
