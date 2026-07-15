from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Protocol

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.search import SEARCH_RUN_REPORT_SCHEMA_VERSION
from ygo_effect_dsl.experiment import assert_experiment_matches_route
from ygo_effect_dsl.route_dsl import (
    assert_valid_route_document,
    load_route_document,
)
from ygo_effect_dsl.storage import (
    JobArtifactPublisher,
    JobCatalog,
    JobKind,
    JobLeaseError,
    JobRecord,
    JobStateTransitionError,
)

DESKTOP_WORKER_SCHEMA_VERSION = "desktop-search-worker-v1"
DESKTOP_PROCESS_CONTAINMENT_SCHEMA_VERSION = "desktop-process-containment-v1"
DEFAULT_LEASE_SECONDS = 6.0
DEFAULT_POLL_SECONDS = 0.1
MAX_DIAGNOSTIC_BYTES = 8_192


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProcessTree(Protocol):
    process: subprocess.Popen[str]
    containment: str

    def active_process_count(self) -> int | None: ...

    def metrics(self) -> Mapping[str, int | str | None]: ...

    def terminate(self, *, grace_seconds: float = 2.0) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class DesktopWorkerOutcome:
    status: str
    job_id: str | None
    attempt: int | None
    return_code: int | None = None
    process_count_before_cleanup: int | None = None
    schema_version: str = DESKTOP_WORKER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "job_id": self.job_id,
            "process_count_before_cleanup": self.process_count_before_cleanup,
            "return_code": self.return_code,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True)
class ValidatedSearchArtifacts:
    route_content: bytes
    report_content: bytes
    report: Mapping[str, Any]
    nodes: int
    route_id: str
    semantic_result_digest: str


def validate_search_artifacts(
    *,
    experiment: Mapping[str, Any],
    route_path: Path,
    report_path: Path,
    max_nodes: int,
) -> ValidatedSearchArtifacts:
    route_content = route_path.read_bytes()
    report_content = report_path.read_bytes()
    route = load_route_document(route_path)
    assert_valid_route_document(route)
    assert_experiment_matches_route(experiment, route)
    report = json.loads(report_content.decode("utf-8"))
    if not isinstance(report, Mapping):
        raise ValueError("search report root must be an object")
    if report.get("report_schema_version") != SEARCH_RUN_REPORT_SCHEMA_VERSION:
        raise ValueError("search report schema is incompatible")
    if report.get("status") != "complete":
        raise ValueError("search report is not complete")
    nodes_value = report.get("nodes")
    if not isinstance(nodes_value, int) or isinstance(nodes_value, bool):
        raise ValueError("search report node count must be an integer")
    if nodes_value < 0 or nodes_value > max_nodes:
        raise ValueError("search report node count is outside its budget")
    best_route = report.get("best_route")
    if not isinstance(best_route, Mapping):
        raise ValueError("search report is missing best_route")
    route_id = best_route.get("route_id")
    if not isinstance(route_id, str) or not route_id.startswith("route_"):
        raise ValueError("search report route_id is invalid")
    if route.get("route_id") != route_id:
        raise ValueError("Route and SearchRun route IDs differ")
    artifact_commit = report.get("artifact_commit")
    if not isinstance(artifact_commit, Mapping):
        raise ValueError("search report is missing artifact_commit")
    if (
        artifact_commit.get("schema_version") != "search-artifact-commit-v1"
        or artifact_commit.get("status") != "committed"
        or artifact_commit.get("route_id") != route_id
        or artifact_commit.get("route_sha256")
        != hashlib.sha256(route_content).hexdigest()
    ):
        raise ValueError("search report artifact commit does not match Route bytes")
    run_id = report.get("run_id")
    termination_reason = report.get("termination_reason")
    if not isinstance(run_id, str) or not run_id.startswith("searchrun_"):
        raise ValueError("search report run_id is invalid")
    if not isinstance(termination_reason, str) or not termination_reason:
        raise ValueError("search report termination reason is invalid")
    semantic_digest = stable_digest(
        {
            "route_id": route_id,
            "run_id": run_id,
            "termination_reason": termination_reason,
        },
        prefix="jobsemantic_",
    )
    return ValidatedSearchArtifacts(
        route_content=route_content,
        report_content=report_content,
        report=report,
        nodes=nodes_value,
        route_id=route_id,
        semantic_result_digest=semantic_digest,
    )


class _JobBasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("total_user_time", ctypes.c_longlong),
        ("total_kernel_time", ctypes.c_longlong),
        ("this_period_total_user_time", ctypes.c_longlong),
        ("this_period_total_kernel_time", ctypes.c_longlong),
        ("total_page_fault_count", wintypes.DWORD),
        ("total_processes", wintypes.DWORD),
        ("active_processes", wintypes.DWORD),
        ("total_terminated_processes", wintypes.DWORD),
    ]


class _JobBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("per_process_user_time_limit", ctypes.c_longlong),
        ("per_job_user_time_limit", ctypes.c_longlong),
        ("limit_flags", wintypes.DWORD),
        ("minimum_working_set_size", ctypes.c_size_t),
        ("maximum_working_set_size", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("read_operation_count", ctypes.c_ulonglong),
        ("write_operation_count", ctypes.c_ulonglong),
        ("other_operation_count", ctypes.c_ulonglong),
        ("read_transfer_count", ctypes.c_ulonglong),
        ("write_transfer_count", ctypes.c_ulonglong),
        ("other_transfer_count", ctypes.c_ulonglong),
    ]


class _JobExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("basic_limit_information", _JobBasicLimitInformation),
        ("io_info", _IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory_used", ctypes.c_size_t),
        ("peak_job_memory_used", ctypes.c_size_t),
    ]


class _ThreadEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


def _windows_kernel32() -> Any:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    kernel32.QueryInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32First.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ThreadEntry32),
    )
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ThreadEntry32),
    )
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.ResumeThread.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    return kernel32


def _resume_suspended_process(kernel32: Any, process_id: int) -> None:
    thread_snapshot = 0x00000004
    thread_suspend_resume = 0x0002
    invalid_handle = ctypes.c_void_p(-1).value
    snapshot = kernel32.CreateToolhelp32Snapshot(thread_snapshot, 0)
    if snapshot == invalid_handle:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    try:
        entry = _ThreadEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while found:
            if int(entry.th32OwnerProcessID) == process_id:
                thread = kernel32.OpenThread(
                    thread_suspend_resume,
                    False,
                    entry.th32ThreadID,
                )
                if not thread:
                    raise OSError(ctypes.get_last_error(), "OpenThread failed")
                try:
                    previous_count = kernel32.ResumeThread(thread)
                    if previous_count == 0xFFFFFFFF:
                        raise OSError(ctypes.get_last_error(), "ResumeThread failed")
                    return
                finally:
                    kernel32.CloseHandle(thread)
            entry.dwSize = ctypes.sizeof(entry)
            found = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    raise OSError("suspended process primary thread was not found")


class _WindowsProcessTree:
    containment = "windows-job-object-kill-on-close-v1"
    _CREATE_SUSPENDED = 0x00000004
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

    def __init__(
        self, process: subprocess.Popen[str], handle: int, launch_mode: str
    ) -> None:
        self.process = process
        self._handle = handle
        self.launch_mode = launch_mode

    @classmethod
    def launch(cls, command: Sequence[str], *, cwd: Path) -> "_WindowsProcessTree":
        kernel32 = _windows_kernel32()
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        limits = _JobExtendedLimitInformation()
        limits.basic_limit_information.limit_flags = (
            cls._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        configured = kernel32.SetInformationJobObject(
            handle,
            cls._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        if not configured:
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise OSError(error, "SetInformationJobObject failed")
        arguments = {
            "cwd": cwd,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        try:
            process = subprocess.Popen(
                list(command),
                **arguments,
                creationflags=subprocess.CREATE_NO_WINDOW
                | subprocess.CREATE_BREAKAWAY_FROM_JOB
                | cls._CREATE_SUSPENDED,
            )
            launch_mode = "breakaway"
        except OSError as exc:
            if exc.winerror != 5:
                kernel32.CloseHandle(handle)
                raise
            process = subprocess.Popen(
                list(command),
                **arguments,
                creationflags=subprocess.CREATE_NO_WINDOW | cls._CREATE_SUSPENDED,
            )
            launch_mode = "nested-fallback"
        assigned = kernel32.AssignProcessToJobObject(
            handle,
            wintypes.HANDLE(process._handle),  # type: ignore[attr-defined]
        )
        if not assigned:
            error = ctypes.get_last_error()
            process.kill()
            process.communicate()
            kernel32.CloseHandle(handle)
            raise OSError(error, "AssignProcessToJobObject failed")
        try:
            _resume_suspended_process(kernel32, process.pid)
        except OSError:
            process.kill()
            process.communicate()
            kernel32.CloseHandle(handle)
            raise
        return cls(process, handle, launch_mode)

    def active_process_count(self) -> int | None:
        return self.metrics()["active_processes"]  # type: ignore[return-value]

    def metrics(self) -> Mapping[str, int | str | None]:
        if not self._handle:
            return {
                "active_processes": 0,
                "containment": self.containment,
                "launch_mode": self.launch_mode,
                "peak_job_memory_bytes": None,
                "total_processes": None,
            }
        kernel32 = _windows_kernel32()
        accounting = _JobBasicAccountingInformation()
        accounting_ok = kernel32.QueryInformationJobObject(
            self._handle,
            self._JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            None,
        )
        limits = _JobExtendedLimitInformation()
        limits_ok = kernel32.QueryInformationJobObject(
            self._handle,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
            None,
        )
        return {
            "active_processes": (
                int(accounting.active_processes) if accounting_ok else None
            ),
            "containment": self.containment,
            "launch_mode": self.launch_mode,
            "peak_job_memory_bytes": (
                int(limits.peak_job_memory_used) if limits_ok else None
            ),
            "total_processes": (
                int(accounting.total_processes) if accounting_ok else None
            ),
        }

    def terminate(self, *, grace_seconds: float = 2.0) -> None:
        if self.process.poll() is not None:
            return
        kernel32 = _windows_kernel32()
        if not kernel32.TerminateJobObject(self._handle, 1):
            self.process.kill()
        try:
            self.process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=grace_seconds)

    def close(self) -> None:
        if self._handle:
            _windows_kernel32().CloseHandle(self._handle)
            self._handle = 0


class _PosixProcessTree:
    containment = "posix-process-group-v1"

    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process

    @classmethod
    def launch(cls, command: Sequence[str], *, cwd: Path) -> "_PosixProcessTree":
        return cls(
            subprocess.Popen(
                list(command),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,
            )
        )

    def active_process_count(self) -> int | None:
        return 0 if self.process.poll() is not None else 1

    def metrics(self) -> Mapping[str, int | str | None]:
        return {
            "active_processes": self.active_process_count(),
            "containment": self.containment,
            "peak_job_memory_bytes": None,
            "total_processes": None,
        }

    def terminate(self, *, grace_seconds: float = 2.0) -> None:
        if self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=grace_seconds)

    def close(self) -> None:
        return None


def launch_process_tree(command: Sequence[str], *, cwd: Path) -> ProcessTree:
    if os.name == "nt":
        return _WindowsProcessTree.launch(command, cwd=cwd)
    return _PosixProcessTree.launch(command, cwd=cwd)


class DesktopSearchWorker:
    def __init__(
        self,
        data_root: str | Path,
        *,
        external_root: str | Path | None = None,
        worker_id: str | None = None,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        now: Callable[[], str] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        launcher: Callable[..., ProcessTree] = launch_process_tree,
        artifact_validator: Callable[..., ValidatedSearchArtifacts] = (
            validate_search_artifacts
        ),
    ) -> None:
        if lease_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("desktop worker timing values must be positive")
        self.data_root = Path(data_root).expanduser().resolve()
        self.external_root = (
            Path(external_root).expanduser().resolve()
            if external_root is not None
            else None
        )
        self.catalog = JobCatalog(self.data_root / "jobs.sqlite3")
        self.publisher = JobArtifactPublisher(
            self.data_root / "job-store", self.catalog
        )
        self.worker_id = worker_id or (f"desktop-{os.getpid()}-{threading.get_ident()}")
        self.lease_seconds = float(lease_seconds)
        self.poll_seconds = float(poll_seconds)
        self.now = now
        self.monotonic = monotonic
        self.sleep = sleep
        self.launcher = launcher
        self.artifact_validator = artifact_validator

    def recover(self) -> tuple[str, ...]:
        reclaimed = self.catalog.reclaim_orphans(now=self.now(), actor=self.worker_id)
        self.publisher.reconcile()
        return tuple(item.job_id for item in reclaimed)

    def run_once(
        self,
        *,
        stop_requested: Callable[[], bool] = lambda: False,
    ) -> DesktopWorkerOutcome:
        self.recover()
        job = self.catalog.claim_next(
            worker_id=self.worker_id,
            now=self.now(),
            lease_seconds=self.lease_seconds,
            kinds=(JobKind.SEARCH,),
        )
        if job is None:
            return DesktopWorkerOutcome("idle", None, None)
        if job.kind.value != "search" or job.lease_token is None:
            self.catalog.quarantine_job(
                job.job_id,
                actor=self.worker_id,
                now=self.now(),
                reason="desktop worker only accepts search jobs",
                lease_token=job.lease_token,
            )
            return DesktopWorkerOutcome("quarantined", job.job_id, job.attempt)
        return self._run_search(job, stop_requested=stop_requested)

    def _experiment_path(self, job: JobRecord) -> Path:
        digest = str(job.spec.payload["experiment_digest"])
        path = (self.data_root / "experiments" / f"{digest}.json").resolve()
        if not path.is_relative_to((self.data_root / "experiments").resolve()):
            raise ValueError("experiment path escaped the desktop data root")
        if not path.is_file():
            raise FileNotFoundError("content-addressed desktop Experiment is missing")
        observed = stable_digest(
            json.loads(path.read_text(encoding="utf-8")), prefix="experiment_"
        )
        if observed != digest:
            raise ValueError("desktop Experiment digest does not match its content")
        return path

    def _command(self, experiment: Path, route: Path, report: Path) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "ygo_effect_dsl",
            "experiment-search",
            str(experiment),
            "--out",
            str(route),
            "--search-report",
            str(report),
        ]
        if self.external_root is not None:
            command.extend(("--external-root", str(self.external_root)))
        return command

    def _save_checkpoint(
        self,
        job: JobRecord,
        *,
        position: str,
        completed: int,
        total: int,
        payload: Mapping[str, Any],
        semantic_result_digest: str | None = None,
    ) -> None:
        if job.lease_token is None:
            raise JobLeaseError("desktop worker job has no lease token")
        self.catalog.save_checkpoint(
            job.job_id,
            lease_token=job.lease_token,
            now=self.now(),
            recovery_position=position,
            completed_units=completed,
            total_units=total,
            payload=payload,
            semantic_result_digest=semantic_result_digest,
        )

    def _retry_or_fail(self, job: JobRecord, *, reason: str) -> str:
        if job.lease_token is None:
            raise JobLeaseError("desktop worker job has no lease token")
        try:
            self.catalog.schedule_retry(
                job.job_id,
                actor=self.worker_id,
                now=self.now(),
                reason=reason,
                error_code="worker_crash",
                lease_token=job.lease_token,
            )
            return "retrying"
        except JobStateTransitionError:
            self.catalog.fail_job(
                job.job_id,
                actor=self.worker_id,
                now=self.now(),
                error_code="worker_crash",
                error_message="desktop search worker exhausted retry policy",
                lease_token=job.lease_token,
            )
            return "failed"

    def _run_search(
        self,
        job: JobRecord,
        *,
        stop_requested: Callable[[], bool],
    ) -> DesktopWorkerOutcome:
        assert job.lease_token is not None
        try:
            experiment_path = self._experiment_path(job)
            experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
            max_nodes = int(experiment["search"]["budget"]["max_nodes"])
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
            self.catalog.quarantine_job(
                job.job_id,
                actor=self.worker_id,
                now=self.now(),
                reason="desktop Experiment is missing, corrupt, or incompatible",
                lease_token=job.lease_token,
            )
            return DesktopWorkerOutcome("quarantined", job.job_id, job.attempt)

        checkpoint = self.catalog.resume_checkpoint(
            job.job_id, expected_input_digest=job.spec.input_digest
        )
        self._save_checkpoint(
            job,
            position=f"search:attempt:{job.attempt}:claimed",
            completed=checkpoint.completed_units if checkpoint else 0,
            total=max_nodes,
            payload={
                "attempt": job.attempt,
                "experiment_digest": job.spec.payload["experiment_digest"],
                "resume_from": checkpoint.recovery_position if checkpoint else None,
            },
        )
        work = self.data_root / "work" / job.job_id / f"attempt-{job.attempt}"
        work.mkdir(parents=True, exist_ok=True)
        route_path = work / "best-route.yaml"
        report_path = work / "search-report.json"
        route_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        try:
            tree = self.launcher(
                self._command(experiment_path, route_path, report_path), cwd=work
            )
        except (OSError, subprocess.SubprocessError):
            status = self._retry_or_fail(job, reason="desktop worker launch failed")
            return DesktopWorkerOutcome(status, job.job_id, job.attempt)

        last_heartbeat = self.monotonic()
        cleanup_count: int | None = None
        try:
            while tree.process.poll() is None:
                if stop_requested():
                    cleanup_count = tree.active_process_count()
                    tree.terminate()
                    self._save_checkpoint(
                        job,
                        position=f"search:attempt:{job.attempt}:host-stop",
                        completed=0,
                        total=max_nodes,
                        payload={"restart_required": True},
                    )
                    status = self._retry_or_fail(
                        job, reason="desktop host stopped the active worker"
                    )
                    tree.process.communicate()
                    return DesktopWorkerOutcome(
                        status,
                        job.job_id,
                        job.attempt,
                        tree.process.returncode,
                        cleanup_count,
                    )
                now = self.now()
                signal_value = self.catalog.control_signal(
                    job.job_id, lease_token=job.lease_token, now=now
                )
                if signal_value.cancel_requested:
                    cleanup_count = tree.active_process_count()
                    tree.terminate()
                    tree.process.communicate()
                    self._save_checkpoint(
                        job,
                        position=f"search:attempt:{job.attempt}:cancelled",
                        completed=0,
                        total=max_nodes,
                        payload={"cancel_acknowledged": True},
                    )
                    self.catalog.finish_cancelled(
                        job.job_id,
                        actor=self.worker_id,
                        now=self.now(),
                        reason="desktop_worker_cancel_ack",
                        lease_token=job.lease_token,
                    )
                    return DesktopWorkerOutcome(
                        "cancelled",
                        job.job_id,
                        job.attempt,
                        tree.process.returncode,
                        cleanup_count,
                    )
                if (
                    signal_value.attempt_timeout_exceeded
                    or signal_value.job_deadline_exceeded
                ):
                    cleanup_count = tree.active_process_count()
                    tree.terminate()
                    tree.process.communicate()
                    recovered = self.catalog.recover_timed_out_attempt(
                        job.job_id,
                        lease_token=job.lease_token,
                        now=now,
                        actor=self.worker_id,
                    )
                    return DesktopWorkerOutcome(
                        recovered.state.value,
                        job.job_id,
                        job.attempt,
                        tree.process.returncode,
                        cleanup_count,
                    )
                if self.monotonic() - last_heartbeat >= self.lease_seconds / 3:
                    self.catalog.heartbeat(
                        job.job_id,
                        lease_token=job.lease_token,
                        now=now,
                        lease_seconds=self.lease_seconds,
                    )
                    last_heartbeat = self.monotonic()
                self.sleep(self.poll_seconds)
            stdout, stderr = tree.process.communicate()
            return_code = tree.process.returncode
            cleanup_count = tree.active_process_count()
        finally:
            try:
                if tree.process.poll() is None:
                    tree.terminate()
            finally:
                tree.close()

        if return_code != 0:
            status = ""
            if report_path.is_file():
                try:
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    status = str(report.get("status", ""))
                except (OSError, ValueError, json.JSONDecodeError):
                    status = ""
            if status in {"configuration_failure", "artifact_failure", "no_route"}:
                self.catalog.fail_job(
                    job.job_id,
                    actor=self.worker_id,
                    now=self.now(),
                    error_code=status,
                    error_message="desktop search completed without a publishable Route",
                    lease_token=job.lease_token,
                )
                outcome = "failed"
            else:
                diagnostic = (stderr or stdout).encode("utf-8")[:MAX_DIAGNOSTIC_BYTES]
                reason = "desktop search subprocess failed: " + stable_digest(
                    diagnostic.hex(), prefix="workerlog_"
                )
                outcome = self._retry_or_fail(job, reason=reason)
            return DesktopWorkerOutcome(
                outcome, job.job_id, job.attempt, return_code, cleanup_count
            )

        try:
            validated = self.artifact_validator(
                experiment=experiment,
                route_path=route_path,
                report_path=report_path,
                max_nodes=max_nodes,
            )
        except (KeyError, TypeError, ValueError, OSError, UnicodeDecodeError):
            self.catalog.quarantine_job(
                job.job_id,
                actor=self.worker_id,
                now=self.now(),
                reason="desktop worker returned invalid success artifacts",
                lease_token=job.lease_token,
            )
            return DesktopWorkerOutcome(
                "quarantined", job.job_id, job.attempt, return_code, cleanup_count
            )

        self._save_checkpoint(
            job,
            position=f"search:attempt:{job.attempt}:complete",
            completed=validated.nodes,
            total=max_nodes,
            payload={"route_id": validated.route_id, "status": "complete"},
            semantic_result_digest=validated.semantic_result_digest,
        )
        now = self.now()
        staged = [
            self.publisher.stage_bytes(
                job,
                lease_token=job.lease_token,
                now=now,
                logical_path="best-route.yaml",
                kind="route-dsl",
                artifact_schema_version="route-dsl-v0.3a",
                content=validated.route_content,
            ),
            self.publisher.stage_bytes(
                job,
                lease_token=job.lease_token,
                now=now,
                logical_path="search-report.json",
                kind="search-run-report",
                artifact_schema_version=str(
                    validated.report.get(
                        "report_schema_version", SEARCH_RUN_REPORT_SCHEMA_VERSION
                    )
                ),
                content=validated.report_content,
            ),
        ]
        self.publisher.publish(
            job,
            actor=self.worker_id,
            now=self.now(),
            lease_token=job.lease_token,
            staged_artifacts=staged,
        )
        route_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        return DesktopWorkerOutcome(
            "succeeded", job.job_id, job.attempt, return_code, cleanup_count
        )


class DesktopWorkerSupervisor:
    def __init__(
        self,
        data_root: str | Path,
        *,
        external_root: str | Path | None = None,
        idle_seconds: float = 0.25,
        worker_factory: Callable[..., DesktopSearchWorker] = DesktopSearchWorker,
    ) -> None:
        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        self.worker = worker_factory(data_root, external_root=external_root)
        self.idle_seconds = float(idle_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failure: BaseException | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def failure(self) -> BaseException | None:
        return self._failure

    @property
    def health(self) -> str:
        if self._failure is not None:
            return "failed"
        if self.running:
            return "running"
        return "stopped"

    def start(self) -> None:
        if self.running:
            raise RuntimeError("desktop worker supervisor is already running")
        self._stop.clear()
        self._failure = None
        self._thread = threading.Thread(
            target=self._run,
            name="ygo-desktop-worker-supervisor",
            daemon=False,
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                outcome = self.worker.run_once(stop_requested=self._stop.is_set)
                if outcome.status == "idle":
                    self._stop.wait(self.idle_seconds)
        except BaseException as exc:
            self._failure = exc

    def stop(self, *, timeout: float = 15.0) -> None:
        self._stop.set()
        if self._thread is None:
            return
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise RuntimeError("desktop worker supervisor did not stop cleanly")
        self._thread = None


def process_containment_contract() -> dict[str, Any]:
    return {
        "descendant_policy": "inherit-and-terminate-as-one-tree",
        "outer_job_policy": "breakaway-when-allowed-otherwise-nested",
        "linux_test_containment": "posix-process-group-v1",
        "schema_version": DESKTOP_PROCESS_CONTAINMENT_SCHEMA_VERSION,
        "windows_containment": "windows-job-object-kill-on-close-v1",
        "worker_contract": DESKTOP_WORKER_SCHEMA_VERSION,
    }


__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_POLL_SECONDS",
    "DESKTOP_PROCESS_CONTAINMENT_SCHEMA_VERSION",
    "DESKTOP_WORKER_SCHEMA_VERSION",
    "DesktopSearchWorker",
    "DesktopWorkerOutcome",
    "DesktopWorkerSupervisor",
    "ProcessTree",
    "ValidatedSearchArtifacts",
    "launch_process_tree",
    "process_containment_contract",
    "validate_search_artifacts",
]
