from __future__ import annotations

import io
from pathlib import Path

import pytest

from ygo_effect_dsl.external.ocgcore import OcgcoreBootstrapError, resolve_ocgcore_runtime
from ygo_effect_dsl.spikes.ocgcore_isolation import (
    MAX_FRAME_BYTES,
    SpikeError,
    WorkerClient,
    WorkerRemoteError,
    _decode_frame,
    _write_frame,
    deterministic_worker_slot,
    fixture_hash,
)


def test_fixture_hash_is_canonical_and_worker_assignment_is_deterministic() -> None:
    assert fixture_hash({"b": 2, "a": 1}) == fixture_hash({"a": 1, "b": 2})
    assert [deterministic_worker_slot(index, 3) for index in range(7)] == [0, 1, 2, 0, 1, 2, 0]


def test_ipc_frame_rejects_wrong_schema_and_oversized_payload() -> None:
    with pytest.raises(SpikeError, match="invalid IPC schema"):
        _decode_frame(b'{"schema_version":99}\n')

    stream = io.BytesIO()
    with pytest.raises(SpikeError, match="exceeds"):
        _write_frame(
            stream,
            {"schema_version": 1, "payload": "x" * MAX_FRAME_BYTES},
        )


def test_real_worker_lifecycle_and_callback_quarantine() -> None:
    try:
        runtime = resolve_ocgcore_runtime()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"verified local ocgcore runtime is unavailable: {exc}")

    with WorkerClient(Path(runtime), (11, 0)) as worker:
        assert worker.request("lifecycle")["destroyed"] is True
        with pytest.raises(WorkerRemoteError, match="callback_error") as captured:
            worker.request("callback_error")
        assert captured.value.code == "callback_error"
        assert worker.request("lifecycle")["destroyed"] is True
