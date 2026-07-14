from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import queue
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence

from ygo_effect_dsl.external.ocgcore import (
    load_ocgcore_lock,
    resolve_ocgcore_runtime,
)


SCHEMA_VERSION = 1
MAX_FRAME_BYTES = 1024 * 1024
MODULE_NAME = "ygo_effect_dsl.spikes.ocgcore_isolation"
_EOF = object()


class SpikeError(RuntimeError):
    """Base class for isolated-worker spike failures."""


class WorkerDiedError(SpikeError):
    """Raised when the worker exits before returning a response."""


class WorkerTimeoutError(SpikeError):
    """Raised when a worker request exceeds its caller-owned deadline."""


class WorkerStartupError(SpikeError):
    """Raised when the worker cannot satisfy its startup handshake."""


class WorkerRemoteError(SpikeError):
    """Structured error returned by a live worker."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class CallbackQuarantinedError(SpikeError):
    """A Python callback failed but the exception did not cross the C ABI."""


class _OCGPlayer(ctypes.Structure):
    _fields_ = [
        ("startingLP", ctypes.c_uint32),
        ("startingDrawCount", ctypes.c_uint32),
        ("drawCountPerTurn", ctypes.c_uint32),
    ]


class _OCGCardData(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_uint32),
        ("alias", ctypes.c_uint32),
        ("setcodes", ctypes.POINTER(ctypes.c_uint16)),
        ("type", ctypes.c_uint32),
        ("level", ctypes.c_uint32),
        ("attribute", ctypes.c_uint32),
        ("race", ctypes.c_uint64),
        ("attack", ctypes.c_int32),
        ("defense", ctypes.c_int32),
        ("lscale", ctypes.c_uint32),
        ("rscale", ctypes.c_uint32),
        ("link_marker", ctypes.c_uint32),
    ]


_DataReader = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_OCGCardData)
)
_ScriptReader = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
)
_LogHandler = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int)
_DataReaderDone = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.POINTER(_OCGCardData)
)


class _OCGDuelOptions(ctypes.Structure):
    _fields_ = [
        ("seed", ctypes.c_uint64 * 4),
        ("flags", ctypes.c_uint64),
        ("team1", _OCGPlayer),
        ("team2", _OCGPlayer),
        ("cardReader", _DataReader),
        ("payload1", ctypes.c_void_p),
        ("scriptReader", _ScriptReader),
        ("payload2", ctypes.c_void_p),
        ("logHandler", _LogHandler),
        ("payload3", ctypes.c_void_p),
        ("cardReaderDone", _DataReaderDone),
        ("payload4", ctypes.c_void_p),
        ("enableUnsafeLibraries", ctypes.c_uint8),
    ]


class _OCGNewCardInfo(ctypes.Structure):
    _fields_ = [
        ("team", ctypes.c_uint8),
        ("duelist", ctypes.c_uint8),
        ("code", ctypes.c_uint32),
        ("con", ctypes.c_uint8),
        ("loc", ctypes.c_uint32),
        ("seq", ctypes.c_uint32),
        ("pos", ctypes.c_uint32),
    ]


class _LoadedCore:
    def __init__(self, runtime: Path) -> None:
        self.runtime = runtime
        self.library = ctypes.CDLL(str(runtime))
        self._configure_api()
        self._default_card_reader = _DataReader(self._read_card)
        self._script_reader = _ScriptReader(self._read_script)
        self._log_handler = _LogHandler(self._log)
        self._data_reader_done = _DataReaderDone(self._read_card_done)

    def _configure_api(self) -> None:
        self.library.OCG_GetVersion.argtypes = [
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        self.library.OCG_GetVersion.restype = None
        self.library.OCG_CreateDuel.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(_OCGDuelOptions),
        ]
        self.library.OCG_CreateDuel.restype = ctypes.c_int
        self.library.OCG_DestroyDuel.argtypes = [ctypes.c_void_p]
        self.library.OCG_DestroyDuel.restype = None
        self.library.OCG_DuelNewCard.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_OCGNewCardInfo),
        ]
        self.library.OCG_DuelNewCard.restype = None

    @staticmethod
    def _read_card(
        _payload: int | None, code: int, data: ctypes.POINTER(_OCGCardData)
    ) -> None:
        data.contents.code = code

    @staticmethod
    def _read_script(
        _payload: int | None, _duel: int | None, _name: bytes | None
    ) -> int:
        return 0

    @staticmethod
    def _log(_payload: int | None, _message: bytes | None, _kind: int) -> None:
        return None

    @staticmethod
    def _read_card_done(
        _payload: int | None, _data: ctypes.POINTER(_OCGCardData)
    ) -> None:
        return None

    def version(self) -> tuple[int, int]:
        major = ctypes.c_int()
        minor = ctypes.c_int()
        self.library.OCG_GetVersion(ctypes.byref(major), ctypes.byref(minor))
        return major.value, minor.value

    def _options(self, card_reader: _DataReader | None = None) -> _OCGDuelOptions:
        options = _OCGDuelOptions()
        options.seed = (ctypes.c_uint64 * 4)(1, 2, 3, 4)
        options.flags = 0
        options.team1 = _OCGPlayer(8000, 5, 1)
        options.team2 = _OCGPlayer(8000, 5, 1)
        options.cardReader = card_reader or self._default_card_reader
        options.scriptReader = self._script_reader
        options.logHandler = self._log_handler
        options.cardReaderDone = self._data_reader_done
        options.enableUnsafeLibraries = 0
        return options

    def lifecycle_fixture(self) -> dict[str, Any]:
        duel = ctypes.c_void_p()
        options = self._options()
        status = self.library.OCG_CreateDuel(ctypes.byref(duel), ctypes.byref(options))
        if status != 0 or not duel.value:
            raise SpikeError(f"OCG_CreateDuel failed with status={status}")
        try:
            return {
                "api": list(self.version()),
                "creation_status": status,
                "created": True,
                "destroyed": True,
                "seed": [1, 2, 3, 4],
            }
        finally:
            self.library.OCG_DestroyDuel(duel)

    def callback_error_fixture(self) -> None:
        captured: list[str] = []

        def failing_reader(
            _payload: int | None,
            code: int,
            data: ctypes.POINTER(_OCGCardData),
        ) -> None:
            try:
                raise RuntimeError("forced cardReader failure")
            except BaseException as exc:
                captured.append(f"{type(exc).__name__}: {exc}")
                data.contents.code = code

        callback = _DataReader(failing_reader)
        options = self._options(callback)
        duel = ctypes.c_void_p()
        status = self.library.OCG_CreateDuel(ctypes.byref(duel), ctypes.byref(options))
        if status != 0 or not duel.value:
            raise SpikeError(f"OCG_CreateDuel failed with status={status}")
        try:
            card = _OCGNewCardInfo(0, 0, 1, 0, 0x1, 0, 0x8)
            self.library.OCG_DuelNewCard(duel, ctypes.byref(card))
        finally:
            self.library.OCG_DestroyDuel(duel)
        if not captured:
            raise SpikeError("forced cardReader callback was not invoked")
        raise CallbackQuarantinedError(captured[0])

    def close(self) -> None:
        if self.library is None:
            return
        if os.name == "nt":
            free_library = ctypes.WinDLL("kernel32", use_last_error=True).FreeLibrary
            free_library.argtypes = [ctypes.c_void_p]
            free_library.restype = ctypes.c_int
            handle = self.library._handle
            if free_library(handle) == 0:
                raise SpikeError(f"FreeLibrary failed for {self.runtime}")
            self.library._handle = 0
        self.library = None

    def __enter__(self) -> "_LoadedCore":
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def fixture_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def deterministic_worker_slot(task_ordinal: int, pool_size: int) -> int:
    if task_ordinal < 0:
        raise ValueError("task_ordinal must be non-negative")
    if pool_size <= 0:
        raise ValueError("pool_size must be positive")
    return task_ordinal % pool_size


def _write_frame(stream: BinaryIO, frame: Mapping[str, Any]) -> None:
    payload = _canonical_bytes(frame)
    if len(payload) > MAX_FRAME_BYTES:
        raise SpikeError(f"IPC frame exceeds {MAX_FRAME_BYTES} bytes")
    stream.write(payload + b"\n")
    stream.flush()


def _decode_frame(line: bytes) -> dict[str, Any]:
    if len(line) > MAX_FRAME_BYTES + 1:
        raise SpikeError(f"IPC frame exceeds {MAX_FRAME_BYTES} bytes")
    value = json.loads(line.decode("utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise SpikeError("invalid IPC schema version")
    return value


def _worker_loop(runtime: Path, expected_api: tuple[int, int]) -> int:
    core: _LoadedCore | None = None
    try:
        core = _LoadedCore(runtime)
        actual_api = core.version()
        if actual_api != expected_api:
            _write_frame(
                sys.stdout.buffer,
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "startup_error",
                    "error": {
                        "code": "version_mismatch",
                        "message": (
                            f"expected {expected_api[0]}.{expected_api[1]}, "
                            f"got {actual_api[0]}.{actual_api[1]}"
                        ),
                    },
                },
            )
            return 2
        _write_frame(
            sys.stdout.buffer,
            {
                "schema_version": SCHEMA_VERSION,
                "kind": "ready",
                "pid": os.getpid(),
                "api": {"major": actual_api[0], "minor": actual_api[1]},
            },
        )
        for line in sys.stdin.buffer:
            request = _decode_frame(line)
            request_id = request.get("id")
            operation = request.get("op")
            should_stop = False
            try:
                if operation == "version":
                    result: Mapping[str, Any] = {
                        "api": list(core.version()),
                    }
                elif operation == "lifecycle":
                    result = core.lifecycle_fixture()
                elif operation == "callback_error":
                    core.callback_error_fixture()
                    raise SpikeError("callback error fixture unexpectedly succeeded")
                elif operation == "hang":
                    while True:
                        time.sleep(60)
                elif operation == "crash":
                    _force_native_abort()
                    raise SpikeError("native abort fixture unexpectedly returned")
                elif operation == "shutdown":
                    result = {"stopped": True}
                    should_stop = True
                else:
                    raise SpikeError(f"unsupported operation: {operation!r}")
                response = {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "response",
                    "id": request_id,
                    "ok": True,
                    "result": result,
                }
            except CallbackQuarantinedError as exc:
                response = {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "response",
                    "id": request_id,
                    "ok": False,
                    "error": {"code": "callback_error", "message": str(exc)},
                }
            except Exception as exc:
                response = {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "response",
                    "id": request_id,
                    "ok": False,
                    "error": {"code": "worker_error", "message": str(exc)},
                }
            _write_frame(sys.stdout.buffer, response)
            if should_stop:
                break
        return 0
    finally:
        if core is not None:
            core.close()


def _development_environment() -> dict[str, str]:
    environment = os.environ.copy()
    src_root = str(Path(__file__).resolve().parents[2])
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join([src_root, existing]) if existing else src_root
    return environment


def _worker_command(
    runtime: Path,
    expected_api: tuple[int, int],
    worker_executable: Path | None,
) -> list[str]:
    prefix = [str(worker_executable)] if worker_executable is not None else [sys.executable, "-m", MODULE_NAME]
    return [
        *prefix,
        "--worker",
        "--runtime",
        str(runtime),
        "--expected-api",
        f"{expected_api[0]}.{expected_api[1]}",
    ]


class WorkerClient:
    def __init__(
        self,
        runtime: Path,
        expected_api: tuple[int, int],
        *,
        worker_executable: Path | None = None,
        startup_timeout: float = 10.0,
    ) -> None:
        self.runtime = runtime
        self.expected_api = expected_api
        self.worker_executable = worker_executable
        self.startup_timeout = startup_timeout
        self.process: subprocess.Popen[bytes] | None = None
        self._responses: queue.Queue[object] = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._next_id = 1
        self.startup_ns: int | None = None

    def start(self) -> None:
        if self.process is not None:
            raise SpikeError("worker is already started")
        started = time.perf_counter_ns()
        self.process = subprocess.Popen(
            _worker_command(self.runtime, self.expected_api, self.worker_executable),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_development_environment(),
        )
        self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
        self._reader_thread.start()
        ready = self._get_response(self.startup_timeout)
        if ready is _EOF:
            raise WorkerStartupError(self._death_detail())
        if not isinstance(ready, dict):
            raise WorkerStartupError("worker returned an invalid ready frame")
        if ready.get("kind") == "startup_error":
            error = ready.get("error", {})
            raise WorkerStartupError(f"{error.get('code')}: {error.get('message')}")
        if ready.get("kind") != "ready":
            raise WorkerStartupError(f"unexpected worker startup frame: {ready}")
        self.startup_ns = time.perf_counter_ns() - started

    def _read_responses(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                try:
                    self._responses.put(_decode_frame(line))
                except Exception as exc:
                    self._responses.put(exc)
        finally:
            self._responses.put(_EOF)

    def _get_response(self, timeout: float) -> object:
        try:
            response = self._responses.get(timeout=timeout)
        except queue.Empty as exc:
            raise WorkerTimeoutError(f"worker did not respond within {timeout:.3f}s") from exc
        if isinstance(response, Exception):
            raise SpikeError(f"worker protocol error: {response}") from response
        return response

    def _death_detail(self) -> str:
        if self.process is None:
            return "worker was not started"
        try:
            return_code = self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            return_code = self.process.poll()
        stderr = b""
        if self.process.stderr is not None and return_code is not None:
            stderr = self.process.stderr.read(MAX_FRAME_BYTES)
        diagnostic = stderr.decode("utf-8", errors="replace").strip()
        return f"worker exited with code {return_code}: {diagnostic or 'no stderr'}"

    @property
    def pid(self) -> int:
        if self.process is None:
            raise SpikeError("worker is not started")
        return self.process.pid

    def request(self, operation: str, *, timeout: float = 5.0) -> Mapping[str, Any]:
        if self.process is None or self.process.stdin is None:
            raise SpikeError("worker is not started")
        if self.process.poll() is not None:
            raise WorkerDiedError(self._death_detail())
        request_id = self._next_id
        self._next_id += 1
        try:
            _write_frame(
                self.process.stdin,
                {
                    "schema_version": SCHEMA_VERSION,
                    "id": request_id,
                    "op": operation,
                },
            )
        except (BrokenPipeError, OSError) as exc:
            raise WorkerDiedError(self._death_detail()) from exc
        response = self._get_response(timeout)
        if response is _EOF:
            raise WorkerDiedError(self._death_detail())
        if not isinstance(response, dict) or response.get("id") != request_id:
            raise SpikeError(f"unexpected worker response: {response}")
        if not response.get("ok"):
            error = response.get("error", {})
            raise WorkerRemoteError(str(error.get("code")), str(error.get("message")))
        result = response.get("result")
        if not isinstance(result, dict):
            raise SpikeError("worker result must be an object")
        return result

    def kill(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                self.request("shutdown", timeout=2)
                self.process.wait(timeout=2)
            except (SpikeError, subprocess.TimeoutExpired):
                self.kill()

    def __enter__(self) -> "WorkerClient":
        self.start()
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()


def _force_native_abort() -> None:
    if os.name == "nt":
        ctypes.WinDLL("kernel32").SetErrorMode(0x0001 | 0x0002)
    os.abort()


def _process_rss_bytes(process_id: int) -> int | None:
    if os.name != "nt":
        return None

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_uint32),
            ("PageFaultCount", ctypes.c_uint32),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_uint32,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = kernel32.OpenProcess(0x1000 | 0x0400, 0, process_id)
    if not handle:
        return None
    try:
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    finally:
        kernel32.CloseHandle(handle)


def _latency_summary(samples_ns: Sequence[int]) -> dict[str, float | int]:
    ordered = sorted(samples_ns)
    p95_index = max(0, int((len(ordered) - 1) * 0.95))
    return {
        "runs": len(ordered),
        "min_us": round(ordered[0] / 1000, 3),
        "median_us": round(statistics.median(ordered) / 1000, 3),
        "p95_us": round(ordered[p95_index] / 1000, 3),
        "max_us": round(ordered[-1] / 1000, 3),
    }


def _probe_command(mode: str, runtime: Path) -> list[str]:
    return [sys.executable, "-m", MODULE_NAME, mode, "--runtime", str(runtime)]


def _run_termination_probes(runtime: Path) -> dict[str, Any]:
    crash = subprocess.run(
        _probe_command("--crash-probe", runtime),
        check=False,
        capture_output=True,
        env=_development_environment(),
        timeout=10,
    )
    hang_timed_out = False
    try:
        subprocess.run(
            _probe_command("--hang-probe", runtime),
            check=False,
            capture_output=True,
            env=_development_environment(),
            timeout=0.25,
        )
    except subprocess.TimeoutExpired:
        hang_timed_out = True
    return {
        "in_process_native_crash_probe": {
            "caller_process_terminated": crash.returncode != 0,
            "return_code": crash.returncode,
        },
        "in_process_hang_probe": {
            "caller_blocked_until_external_timeout": hang_timed_out,
            "timeout_ms": 250,
        },
    }


def _worker_recovery_probes(
    runtime: Path,
    expected_api: tuple[int, int],
    worker_executable: Path | None,
) -> dict[str, Any]:
    crash_worker = WorkerClient(runtime, expected_api, worker_executable=worker_executable)
    crash_worker.start()
    crash_error = "none"
    try:
        crash_worker.request("crash", timeout=5)
    except (WorkerDiedError, WorkerTimeoutError) as exc:
        crash_error = type(exc).__name__
    finally:
        crash_worker.kill()
    with WorkerClient(runtime, expected_api, worker_executable=worker_executable) as recovered:
        crash_recovered = recovered.request("lifecycle")["destroyed"] is True

    hang_worker = WorkerClient(runtime, expected_api, worker_executable=worker_executable)
    hang_worker.start()
    hang_error = "none"
    try:
        hang_worker.request("hang", timeout=0.25)
    except WorkerTimeoutError as exc:
        hang_error = type(exc).__name__
    finally:
        hang_worker.kill()
    with WorkerClient(runtime, expected_api, worker_executable=worker_executable) as recovered:
        hang_recovered = recovered.request("lifecycle")["destroyed"] is True

    with WorkerClient(runtime, expected_api, worker_executable=worker_executable) as callback_worker:
        callback_error = "none"
        try:
            callback_worker.request("callback_error")
        except WorkerRemoteError as exc:
            callback_error = exc.code
        callback_worker_alive = callback_worker.request("lifecycle")["destroyed"] is True

    mismatch_worker = WorkerClient(runtime, (99, 99), worker_executable=worker_executable)
    mismatch_error = "none"
    try:
        mismatch_worker.start()
    except WorkerStartupError as exc:
        mismatch_error = str(exc)
    finally:
        mismatch_worker.kill()

    return {
        "worker_native_crash": {
            "main_process_survived": True,
            "error": crash_error,
            "replacement_worker_succeeded": crash_recovered,
        },
        "worker_hang": {
            "main_process_survived": True,
            "error": hang_error,
            "timeout_ms": 250,
            "replacement_worker_succeeded": hang_recovered,
        },
        "callback_error": {
            "error_code": callback_error,
            "exception_crossed_c_abi": False,
            "worker_remained_usable": callback_worker_alive,
        },
        "api_mismatch": {
            "failed_before_ready": "version_mismatch" in mismatch_error,
            "diagnostic": mismatch_error,
        },
    }


def run_spike(
    runtime: Path,
    *,
    runs: int = 100,
    worker_executable: Path | None = None,
) -> dict[str, Any]:
    if runs < 100:
        raise ValueError("architecture spike requires at least 100 runs")
    lock = load_ocgcore_lock()
    expected_api = (int(lock.api["major"]), int(lock.api["minor"]))
    direct_samples: list[int] = []
    direct_hashes: list[str] = []
    direct_started = time.perf_counter_ns()
    with _LoadedCore(runtime) as direct_core:
        direct_startup_ns = time.perf_counter_ns() - direct_started
        direct_rss = _process_rss_bytes(os.getpid())
        for _ in range(runs):
            started = time.perf_counter_ns()
            result = direct_core.lifecycle_fixture()
            direct_samples.append(time.perf_counter_ns() - started)
            direct_hashes.append(fixture_hash(result))

    worker_samples: list[int] = []
    worker_hashes: list[str] = []
    with WorkerClient(
        runtime,
        expected_api,
        worker_executable=worker_executable,
        startup_timeout=30 if worker_executable is not None else 10,
    ) as worker:
        worker_rss = _process_rss_bytes(worker.pid)
        worker_startup_ns = worker.startup_ns
        for _ in range(runs):
            started = time.perf_counter_ns()
            result = worker.request("lifecycle")
            worker_samples.append(time.perf_counter_ns() - started)
            worker_hashes.append(fixture_hash(result))

    direct_unique = sorted(set(direct_hashes))
    worker_unique = sorted(set(worker_hashes))
    if len(direct_unique) != 1 or direct_unique != worker_unique:
        raise SpikeError("in-process and worker lifecycle fixture hashes differ")

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
        "runtime": {
            "binary": runtime.name,
            "sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
            "api": {"major": expected_api[0], "minor": expected_api[1]},
        },
        "fixture": {
            "name": "create_destroy_fixed_seed",
            "runs_per_mode": runs,
            "final_state_hash": direct_unique[0],
        },
        "in_process": {
            "startup_us": round(direct_startup_ns / 1000, 3),
            "process_rss_bytes": direct_rss,
            "one_action_latency": _latency_summary(direct_samples),
        },
        "isolated_worker": {
            "startup_us": round((worker_startup_ns or 0) / 1000, 3),
            "process_rss_bytes": worker_rss,
            "one_action_latency": _latency_summary(worker_samples),
            "ipc": {
                "schema_version": SCHEMA_VERSION,
                "framing": "newline-delimited canonical JSON (spike only)",
                "max_frame_bytes": MAX_FRAME_BYTES,
            },
            "worker_kind": "packaged_executable" if worker_executable else "python_module",
        },
        "termination": _run_termination_probes(runtime),
        "recovery": _worker_recovery_probes(runtime, expected_api, worker_executable),
        "deterministic_pool_assignment": {
            "formula": "task_ordinal % pool_size",
            "example_pool_size": 4,
            "first_eight_slots": [deterministic_worker_slot(index, 4) for index in range(8)],
        },
    }
    if worker_executable is not None:
        evidence["packaging_smoke"] = {
            "ok": True,
            "executable": worker_executable.name,
            "size": worker_executable.stat().st_size,
            "sha256": hashlib.sha256(worker_executable.read_bytes()).hexdigest(),
        }
    else:
        evidence["packaging_smoke"] = {"ok": False, "reason": "worker executable not supplied"}
    return evidence


def _parse_api(value: str) -> tuple[int, int]:
    try:
        major, minor = value.split(".", 1)
        return int(major), int(minor)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("API version must be MAJOR.MINOR") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Spike ocgcore in-process and worker isolation")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--worker", action="store_true")
    mode.add_argument("--probe", action="store_true")
    mode.add_argument("--crash-probe", action="store_true")
    mode.add_argument("--hang-probe", action="store_true")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--expected-api", type=_parse_api, default=(11, 0))
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--worker-executable", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    runtime = args.runtime or resolve_ocgcore_runtime()
    runtime = runtime.resolve()
    if args.worker:
        return _worker_loop(runtime, args.expected_api)
    if args.probe:
        with _LoadedCore(runtime) as core:
            print(json.dumps({"api": list(core.version()), "fixture": core.lifecycle_fixture()}))
        return 0
    if args.crash_probe:
        with _LoadedCore(runtime) as core:
            core.version()
            _force_native_abort()
        return 99
    if args.hang_probe:
        with _LoadedCore(runtime) as core:
            core.version()
            while True:
                time.sleep(60)

    evidence = run_spike(
        runtime,
        runs=args.runs,
        worker_executable=args.worker_executable.resolve() if args.worker_executable else None,
    )
    serialized = json.dumps(evidence, ensure_ascii=True, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(f"ocgcore-isolation-spike: wrote {args.out}")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
