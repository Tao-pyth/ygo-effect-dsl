from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Any

from ygo_effect_dsl.storage.jobs import (
    JobArtifact,
    JobCatalog,
    JobCheckpoint,
    JobLeaseError,
    JobRecord,
    JobState,
)


JOB_ARTIFACT_PUBLICATION_SCHEMA_VERSION = "job-artifact-publication-v1"
JOB_RECOVERY_REPORT_SCHEMA_VERSION = "job-recovery-report-v1"
JOB_STATUS_SCHEMA_VERSION = "job-status-v1"


class JobFaultPoint(str, Enum):
    BEFORE_CHECKPOINT_COMMIT = "before_checkpoint_commit"
    AFTER_CHECKPOINT_COMMIT = "after_checkpoint_commit"
    BEFORE_ARTIFACT_WRITE = "before_artifact_write"
    DURING_ARTIFACT_WRITE = "during_artifact_write"
    AFTER_ARTIFACT_RENAME = "after_artifact_rename"
    AFTER_CATALOG_COMMIT = "after_catalog_commit"


class InjectedJobFault(RuntimeError):
    def __init__(self, point: JobFaultPoint) -> None:
        self.point = point
        super().__init__(f"injected job fault at {point.value}")


class JobArtifactIntegrityError(ValueError):
    pass


JobFaultInjector = Callable[[JobFaultPoint], None]


def fault_at(expected: JobFaultPoint) -> JobFaultInjector:
    def inject(observed: JobFaultPoint) -> None:
        if observed == expected:
            raise InjectedJobFault(observed)

    return inject


def _inject(injector: JobFaultInjector | None, point: JobFaultPoint) -> None:
    if injector is not None:
        injector(point)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_logical_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("logical artifact path must be a non-empty POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("logical artifact path must be relative and traversal-free")
    return path


@dataclass(frozen=True)
class StagedJobArtifact:
    job_id: str
    attempt: int
    artifact: JobArtifact
    staging_path: Path
    final_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "attempt": self.attempt,
            "final_path": str(self.final_path),
            "job_id": self.job_id,
            "staging_path": str(self.staging_path),
        }


@dataclass(frozen=True)
class JobArtifactReconciliationReport:
    removed_paths: tuple[str, ...]
    preserved_active_paths: tuple[str, ...]
    referenced_artifact_count: int
    schema_version: str = JOB_ARTIFACT_PUBLICATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "preserved_active_paths": list(self.preserved_active_paths),
            "referenced_artifact_count": self.referenced_artifact_count,
            "removed_paths": list(self.removed_paths),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class JobRecoveryReport:
    expired_pending_job_ids: tuple[str, ...]
    recovered_attempt_job_ids: tuple[str, ...]
    schema_version: str = JOB_RECOVERY_REPORT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "expired_pending_job_ids": list(self.expired_pending_job_ids),
            "recovered_attempt_job_ids": list(self.recovered_attempt_job_ids),
            "schema_version": self.schema_version,
        }


class JobArtifactPublisher:
    def __init__(self, root: str | Path, catalog: JobCatalog) -> None:
        self.root = Path(root).resolve()
        self.catalog = catalog

    def _owned_path(self, relative: PurePosixPath) -> Path:
        root = self.root.resolve()
        candidate = (root / Path(*relative.parts)).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("artifact path escapes the configured job artifact root")
        return candidate

    def stage_bytes(
        self,
        job: JobRecord,
        *,
        lease_token: str,
        now: str,
        logical_path: str,
        kind: str,
        artifact_schema_version: str,
        content: bytes,
        row_count: int | None = None,
        injector: JobFaultInjector | None = None,
    ) -> StagedJobArtifact:
        if not isinstance(content, bytes):
            raise ValueError("artifact content must be bytes")
        logical = _safe_logical_path(logical_path)
        signal = self.catalog.control_signal(
            job.job_id,
            lease_token=lease_token,
            now=now,
        )
        if signal.should_stop:
            raise JobLeaseError("job control requested the active writer to stop")
        if signal.attempt != job.attempt:
            raise JobLeaseError("job record does not match the active attempt")
        sha256 = _sha256_bytes(content)
        final_relative = (
            PurePosixPath("artifacts") / job.job_id / sha256 / logical
        )
        staging_relative = (
            PurePosixPath("staging")
            / job.job_id
            / str(job.attempt)
            / sha256
            / logical
        )
        final_path = self._owned_path(final_relative)
        staging_path = self._owned_path(staging_relative)
        staging_path = staging_path.with_name(staging_path.name + ".staged")
        temporary_path = staging_path.with_name(staging_path.name + ".partial")
        artifact = JobArtifact(
            kind=kind,
            path=final_relative.as_posix(),
            sha256=sha256,
            schema_version=artifact_schema_version,
            row_count=row_count,
        )
        _inject(injector, JobFaultPoint.BEFORE_ARTIFACT_WRITE)
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        with temporary_path.open("wb") as stream:
            midpoint = len(content) // 2
            stream.write(content[:midpoint])
            stream.flush()
            os.fsync(stream.fileno())
            _inject(injector, JobFaultPoint.DURING_ARTIFACT_WRITE)
            stream.write(content[midpoint:])
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, staging_path)
        if _sha256_file(staging_path) != sha256:
            raise JobArtifactIntegrityError("staged artifact checksum mismatch")
        return StagedJobArtifact(
            job_id=job.job_id,
            attempt=job.attempt,
            artifact=artifact,
            staging_path=staging_path,
            final_path=final_path,
        )

    def publish(
        self,
        job: JobRecord,
        *,
        actor: str,
        now: str,
        lease_token: str,
        staged_artifacts: Sequence[StagedJobArtifact],
        injector: JobFaultInjector | None = None,
    ) -> JobRecord:
        ordered = tuple(
            sorted(staged_artifacts, key=lambda item: item.artifact.artifact_id)
        )
        if not ordered:
            raise ValueError("publication requires at least one staged artifact")
        signal = self.catalog.control_signal(
            job.job_id,
            lease_token=lease_token,
            now=now,
        )
        if signal.should_stop or signal.attempt != job.attempt:
            raise JobLeaseError("job control rejected artifact publication")
        for staged in ordered:
            if staged.job_id != job.job_id or staged.attempt != job.attempt:
                raise JobLeaseError("staged artifact belongs to another attempt")
            expected_final = self._owned_path(
                _safe_logical_path(staged.artifact.path)
            )
            if staged.final_path.resolve() != expected_final:
                raise ValueError("staged artifact final path does not match metadata")
            expected_staging_root = self._owned_path(
                PurePosixPath("staging") / job.job_id / str(job.attempt)
            )
            if not staged.staging_path.resolve().is_relative_to(
                expected_staging_root
            ):
                raise ValueError("staged artifact path escapes the active attempt")
            if not staged.staging_path.is_file():
                raise JobArtifactIntegrityError("staged artifact is missing")
            if _sha256_file(staged.staging_path) != staged.artifact.sha256:
                raise JobArtifactIntegrityError("staged artifact checksum mismatch")
            staged.final_path.parent.mkdir(parents=True, exist_ok=True)
            if staged.final_path.exists():
                if _sha256_file(staged.final_path) != staged.artifact.sha256:
                    raise JobArtifactIntegrityError(
                        "published artifact path has conflicting content"
                    )
                staged.staging_path.unlink()
            else:
                os.replace(staged.staging_path, staged.final_path)
            _inject(injector, JobFaultPoint.AFTER_ARTIFACT_RENAME)
        record = self.catalog.succeed_job(
            job.job_id,
            actor=actor,
            now=now,
            lease_token=lease_token,
            artifacts=[item.artifact for item in ordered],
        )
        _inject(injector, JobFaultPoint.AFTER_CATALOG_COMMIT)
        self._remove_empty_directories()
        return record

    def reconcile(self) -> JobArtifactReconciliationReport:
        self.root.mkdir(parents=True, exist_ok=True)
        references = {
            artifact.path: (job_id, artifact)
            for job_id, artifact in self.catalog.artifact_references()
            if PurePosixPath(artifact.path).parts[:1] == ("artifacts",)
        }
        removed: list[str] = []
        preserved: list[str] = []
        for relative, (_, artifact) in references.items():
            path = self._owned_path(_safe_logical_path(relative))
            if not path.is_file():
                raise JobArtifactIntegrityError(
                    f"catalog references missing artifact {relative!r}"
                )
            if _sha256_file(path) != artifact.sha256:
                raise JobArtifactIntegrityError(
                    f"catalog artifact checksum mismatch for {relative!r}"
                )
        artifact_root = self.root / "artifacts"
        if artifact_root.exists():
            artifact_files = (
                item for item in artifact_root.rglob("*") if item.is_file()
            )
            for path in sorted(artifact_files):
                relative = path.relative_to(self.root).as_posix()
                if relative in references:
                    continue
                parts = PurePosixPath(relative).parts
                job = self.catalog.get_job(parts[1]) if len(parts) > 1 else None
                if job is not None and job.state in {
                    JobState.RUNNING,
                    JobState.CANCELLING,
                }:
                    preserved.append(relative)
                    continue
                path.unlink()
                removed.append(relative)
        staging_root = self.root / "staging"
        if staging_root.exists():
            staging_files = (
                item for item in staging_root.rglob("*") if item.is_file()
            )
            for path in sorted(staging_files):
                relative = path.relative_to(self.root).as_posix()
                parts = PurePosixPath(relative).parts
                job = self.catalog.get_job(parts[1]) if len(parts) > 2 else None
                attempt = (
                    int(parts[2])
                    if len(parts) > 2 and parts[2].isdigit()
                    else -1
                )
                if (
                    job is not None
                    and job.state in {JobState.RUNNING, JobState.CANCELLING}
                    and job.attempt == attempt
                ):
                    preserved.append(relative)
                    continue
                path.unlink()
                removed.append(relative)
        self._remove_empty_directories()
        return JobArtifactReconciliationReport(
            removed_paths=tuple(sorted(removed)),
            preserved_active_paths=tuple(sorted(preserved)),
            referenced_artifact_count=len(references),
        )

    def _remove_empty_directories(self) -> None:
        if not self.root.exists():
            return
        directories = sorted(
            (item for item in self.root.rglob("*") if item.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                pass


class JobRecoverySupervisor:
    def __init__(self, catalog: JobCatalog) -> None:
        self.catalog = catalog

    def enforce_timeouts(
        self,
        *,
        now: str,
        terminate_attempt: Callable[[JobRecord], None],
        actor: str = "scheduler",
    ) -> JobRecoveryReport:
        pending = self.catalog.expire_pending_deadlines(now=now, actor=actor)
        recovered: list[JobRecord] = []
        for attempt in self.catalog.overdue_attempts(now=now):
            terminate_attempt(attempt)
            if attempt.lease_token is None:
                raise JobLeaseError("overdue attempt has no lease token")
            recovered.append(
                self.catalog.recover_timed_out_attempt(
                    attempt.job_id,
                    lease_token=attempt.lease_token,
                    now=now,
                    actor=actor,
                )
            )
        return JobRecoveryReport(
            expired_pending_job_ids=tuple(item.job_id for item in pending),
            recovered_attempt_job_ids=tuple(item.job_id for item in recovered),
        )


def save_checkpoint_with_fault(
    catalog: JobCatalog,
    *,
    injector: JobFaultInjector | None = None,
    **checkpoint_fields: Any,
) -> JobCheckpoint:
    _inject(injector, JobFaultPoint.BEFORE_CHECKPOINT_COMMIT)
    checkpoint = catalog.save_checkpoint(**checkpoint_fields)
    _inject(injector, JobFaultPoint.AFTER_CHECKPOINT_COMMIT)
    return checkpoint


def job_status_document(catalog: JobCatalog, job_id: str) -> dict[str, Any]:
    return {
        **catalog.status_snapshot(job_id).to_dict(),
        "schema_version": JOB_STATUS_SCHEMA_VERSION,
    }


__all__ = [
    "JOB_ARTIFACT_PUBLICATION_SCHEMA_VERSION",
    "JOB_RECOVERY_REPORT_SCHEMA_VERSION",
    "JOB_STATUS_SCHEMA_VERSION",
    "InjectedJobFault",
    "JobArtifactIntegrityError",
    "JobArtifactPublisher",
    "JobArtifactReconciliationReport",
    "JobFaultInjector",
    "JobFaultPoint",
    "JobRecoveryReport",
    "JobRecoverySupervisor",
    "StagedJobArtifact",
    "fault_at",
    "job_status_document",
    "save_checkpoint_with_fault",
]
