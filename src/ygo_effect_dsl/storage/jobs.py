from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)

JOB_CATALOG_SCHEMA_VERSION = "job-catalog-v2"
JOB_SPEC_SCHEMA_VERSION = "job-spec-v2"
JOB_RECORD_SCHEMA_VERSION = "job-record-v2"
JOB_TRANSITION_SCHEMA_VERSION = "job-transition-v1"
JOB_ARTIFACT_SCHEMA_VERSION = "job-artifact-v1"
JOB_STATE_MACHINE_SCHEMA_VERSION = "job-state-machine-v1"
JOB_RETRY_POLICY_SCHEMA_VERSION = "job-retry-policy-v1"
JOB_CHECKPOINT_SCHEMA_VERSION = "job-checkpoint-v1"
JOB_CHECKPOINT_MAX_BYTES = 1_048_576
JOB_CONTROL_SCHEMA_VERSION = "job-control-v1"


class JobKind(str, Enum):
    SEARCH = "search"
    REPLAY = "replay"
    IMPORT = "import"
    AGGREGATE = "aggregate"
    EXPORT = "export"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    QUARANTINED = "quarantined"


class JobStateTransitionError(ValueError):
    pass


class JobLeaseError(ValueError):
    pass


class JobIdempotencyConflict(ValueError):
    pass


class JobCheckpointConflict(ValueError):
    pass


_ALLOWED_TRANSITIONS: Mapping[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset(
        {
            JobState.RUNNING,
            JobState.CANCELLING,
            JobState.FAILED,
            JobState.QUARANTINED,
        }
    ),
    JobState.RUNNING: frozenset(
        {
            JobState.CANCELLING,
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.RETRYING,
            JobState.QUARANTINED,
        }
    ),
    JobState.CANCELLING: frozenset(
        {JobState.CANCELLED, JobState.FAILED, JobState.QUARANTINED}
    ),
    JobState.CANCELLED: frozenset(),
    JobState.SUCCEEDED: frozenset(),
    JobState.FAILED: frozenset({JobState.RETRYING, JobState.QUARANTINED}),
    JobState.RETRYING: frozenset(
        {
            JobState.RUNNING,
            JobState.CANCELLING,
            JobState.FAILED,
            JobState.QUARANTINED,
        }
    ),
    JobState.QUARANTINED: frozenset(),
}


def job_state_machine_document() -> dict[str, Any]:
    return {
        "schema_version": JOB_STATE_MACHINE_SCHEMA_VERSION,
        "states": [state.value for state in JobState],
        "transitions": {
            state.value: sorted(target.value for target in _ALLOWED_TRANSITIONS[state])
            for state in JobState
        },
    }


def is_job_transition_allowed(
    previous: JobState | str,
    target: JobState | str,
) -> bool:
    return JobState(target) in _ALLOWED_TRANSITIONS[JobState(previous)]


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _content_id(value: Any, name: str, prefix: str) -> str:
    observed = _string(value, name)
    digest = observed.removeprefix(prefix)
    if (
        not observed.startswith(prefix)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a {prefix} content ID")
    return observed


def _sha256(value: Any, name: str) -> str:
    observed = _string(value, name)
    if len(observed) != 64 or any(
        character not in "0123456789abcdef" for character in observed
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return observed


def _timestamp(value: Any, name: str) -> str:
    observed = _string(value, name)
    if not observed.endswith("Z"):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(observed[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(
            f"{name} must be an ISO-8601 UTC timestamp ending in Z"
        ) from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{name} must use UTC")
    return observed


def _parsed_timestamp(value: str) -> datetime:
    _timestamp(value, "timestamp")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _plus_seconds(value: str, seconds: float) -> str:
    parsed = _parsed_timestamp(value) + timedelta(seconds=seconds)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_negative_number(value: Any, name: str, *, positive: bool = False) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} must be a finite number")
    observed = float(value)
    if observed < 0 or (positive and observed == 0):
        comparison = "> 0" if positive else ">= 0"
        raise ValueError(f"{name} must be {comparison}")
    return observed


def _exact_payload(
    payload: Mapping[str, Any],
    expected: set[str],
    kind: JobKind,
) -> dict[str, Any]:
    if set(payload) != expected:
        raise ValueError(
            f"{kind.value} payload fields must be exactly {sorted(expected)}"
        )
    return to_canonical_data(payload)


def _validate_payload(kind: JobKind, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("job payload must be a mapping")
    if kind == JobKind.SEARCH:
        payload = _exact_payload(
            value,
            {"experiment_digest", "experiment_id"},
            kind,
        )
        _string(payload["experiment_id"], "payload.experiment_id")
        _content_id(
            payload["experiment_digest"],
            "payload.experiment_digest",
            "experiment_",
        )
    elif kind == JobKind.REPLAY:
        payload = _exact_payload(
            value,
            {"replay_manifest_hash", "route_id"},
            kind,
        )
        _content_id(payload["route_id"], "payload.route_id", "route_")
        _content_id(
            payload["replay_manifest_hash"],
            "payload.replay_manifest_hash",
            "manifest_",
        )
    elif kind == JobKind.IMPORT:
        payload = _exact_payload(value, {"corpus_item_id", "source_uri"}, kind)
        _content_id(
            payload["corpus_item_id"],
            "payload.corpus_item_id",
            "corpusitem_",
        )
        _string(payload["source_uri"], "payload.source_uri")
    elif kind == JobKind.AGGREGATE:
        payload = _exact_payload(
            value,
            {"corpus_item_ids", "evaluator_id", "evaluator_version"},
            kind,
        )
        raw_ids = payload["corpus_item_ids"]
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValueError("payload.corpus_item_ids must be a non-empty list")
        ids = [
            _content_id(item, "payload.corpus_item_ids[]", "corpusitem_")
            for item in raw_ids
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("payload.corpus_item_ids must be unique")
        payload["corpus_item_ids"] = sorted(ids)
        _string(payload["evaluator_id"], "payload.evaluator_id")
        _string(payload["evaluator_version"], "payload.evaluator_version")
    else:
        payload = _exact_payload(
            value,
            {"format", "query_snapshot_id"},
            kind,
        )
        if payload["format"] not in {"csv", "json", "parquet"}:
            raise ValueError("payload.format must be csv, json, or parquet")
        snapshot_id = payload["query_snapshot_id"]
        try:
            _content_id(
                snapshot_id,
                "payload.query_snapshot_id",
                "analyticssnapshot_",
            )
        except ValueError:
            # Read compatibility for export jobs created before the analytics
            # snapshot contract standardized its content-ID prefix.
            _content_id(
                snapshot_id,
                "payload.query_snapshot_id",
                "querysnapshot_",
            )
    return payload


@dataclass(frozen=True)
class JobRetryPolicy:
    attempt_timeout_seconds: float = 300.0
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 60.0
    retryable_error_codes: tuple[str, ...] = (
        "disk_full",
        "hard_timeout",
        "lease_expired",
        "transient_io",
        "worker_crash",
    )
    schema_version: str = JOB_RETRY_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != JOB_RETRY_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported JobRetryPolicy schema")
        object.__setattr__(
            self,
            "attempt_timeout_seconds",
            _non_negative_number(
                self.attempt_timeout_seconds,
                "attempt_timeout_seconds",
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "initial_backoff_seconds",
            _non_negative_number(
                self.initial_backoff_seconds,
                "initial_backoff_seconds",
            ),
        )
        multiplier = _non_negative_number(
            self.backoff_multiplier,
            "backoff_multiplier",
            positive=True,
        )
        if multiplier < 1:
            raise ValueError("backoff_multiplier must be >= 1")
        object.__setattr__(self, "backoff_multiplier", multiplier)
        maximum = _non_negative_number(
            self.max_backoff_seconds,
            "max_backoff_seconds",
        )
        if maximum < self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= initial_backoff_seconds")
        object.__setattr__(self, "max_backoff_seconds", maximum)
        codes = tuple(
            sorted(
                _string(item, "retryable_error_codes[]")
                for item in self.retryable_error_codes
            )
        )
        if len(codes) != len(set(codes)):
            raise ValueError("retryable_error_codes must be unique")
        object.__setattr__(self, "retryable_error_codes", codes)

    def backoff_after(self, attempt: int) -> float:
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ValueError("attempt must be an integer >= 1")
        if self.initial_backoff_seconds == 0:
            return 0.0
        try:
            value = self.initial_backoff_seconds * (
                self.backoff_multiplier ** (attempt - 1)
            )
        except OverflowError:
            return self.max_backoff_seconds
        return min(value, self.max_backoff_seconds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_timeout_seconds": self.attempt_timeout_seconds,
            "backoff_multiplier": self.backoff_multiplier,
            "initial_backoff_seconds": self.initial_backoff_seconds,
            "max_backoff_seconds": self.max_backoff_seconds,
            "retryable_error_codes": list(self.retryable_error_codes),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> JobRetryPolicy:
        expected = {
            "attempt_timeout_seconds",
            "backoff_multiplier",
            "initial_backoff_seconds",
            "max_backoff_seconds",
            "retryable_error_codes",
            "schema_version",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError(
                f"JobRetryPolicy fields must be exactly {sorted(expected)}"
            )
        codes = value["retryable_error_codes"]
        if not isinstance(codes, list):
            raise ValueError("retryable_error_codes must be a list")
        return cls(
            attempt_timeout_seconds=value["attempt_timeout_seconds"],
            initial_backoff_seconds=value["initial_backoff_seconds"],
            backoff_multiplier=value["backoff_multiplier"],
            max_backoff_seconds=value["max_backoff_seconds"],
            retryable_error_codes=tuple(codes),
            schema_version=value["schema_version"],
        )


@dataclass(frozen=True)
class JobSpec:
    kind: JobKind
    idempotency_key: str
    input_digest: str
    payload: Mapping[str, Any]
    priority: int = 0
    max_attempts: int = 3
    dependency_ids: tuple[str, ...] = ()
    deadline_at: str | None = None
    retry_policy: JobRetryPolicy = JobRetryPolicy()
    schema_version: str = JOB_SPEC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, JobKind):
            object.__setattr__(self, "kind", JobKind(self.kind))
        if self.schema_version != JOB_SPEC_SCHEMA_VERSION:
            raise ValueError("unsupported JobSpec schema")
        if not isinstance(self.retry_policy, JobRetryPolicy):
            object.__setattr__(
                self,
                "retry_policy",
                JobRetryPolicy.from_dict(self.retry_policy),
            )
        if self.deadline_at is not None:
            _timestamp(self.deadline_at, "deadline_at")
        _string(self.idempotency_key, "idempotency_key")
        _content_id(self.input_digest, "input_digest", "jobinput_")
        if (
            not isinstance(self.priority, int)
            or isinstance(self.priority, bool)
            or not -1000 <= self.priority <= 1000
        ):
            raise ValueError("priority must be an integer between -1000 and 1000")
        if (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or self.max_attempts < 1
        ):
            raise ValueError("max_attempts must be an integer >= 1")
        dependencies = tuple(
            _content_id(item, "dependency_ids[]", "job_")
            for item in self.dependency_ids
        )
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("dependency_ids must be unique")
        object.__setattr__(self, "dependency_ids", tuple(sorted(dependencies)))
        object.__setattr__(self, "payload", _validate_payload(self.kind, self.payload))

    @property
    def job_id(self) -> str:
        return stable_digest(
            {
                "dependency_ids": list(self.dependency_ids),
                "deadline_at": self.deadline_at,
                "idempotency_key": self.idempotency_key,
                "input_digest": self.input_digest,
                "kind": self.kind.value,
                "max_attempts": self.max_attempts,
                "payload": self.payload,
                "priority": self.priority,
                "retry_policy": self.retry_policy.to_dict(),
                "schema_version": self.schema_version,
            },
            prefix="job_",
        )

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "dependency_ids": list(self.dependency_ids),
                "deadline_at": self.deadline_at,
                "idempotency_key": self.idempotency_key,
                "input_digest": self.input_digest,
                "job_id": self.job_id,
                "kind": self.kind.value,
                "max_attempts": self.max_attempts,
                "payload": self.payload,
                "priority": self.priority,
                "retry_policy": self.retry_policy.to_dict(),
                "schema_version": self.schema_version,
            }
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> JobSpec:
        expected = {
            "dependency_ids",
            "deadline_at",
            "idempotency_key",
            "input_digest",
            "job_id",
            "kind",
            "max_attempts",
            "payload",
            "priority",
            "retry_policy",
            "schema_version",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            observed = sorted(value) if isinstance(value, Mapping) else type(value)
            raise ValueError(
                f"JobSpec fields must be exactly {sorted(expected)}; "
                f"observed {observed}"
            )
        dependency_ids = value["dependency_ids"]
        if not isinstance(dependency_ids, list):
            raise ValueError("dependency_ids must be a list")
        spec = cls(
            kind=JobKind(value["kind"]),
            idempotency_key=value["idempotency_key"],
            input_digest=value["input_digest"],
            payload=value["payload"],
            priority=value["priority"],
            max_attempts=value["max_attempts"],
            dependency_ids=tuple(dependency_ids),
            deadline_at=value["deadline_at"],
            retry_policy=JobRetryPolicy.from_dict(value["retry_policy"]),
            schema_version=value["schema_version"],
        )
        if value["job_id"] != spec.job_id:
            raise ValueError("JobSpec job_id does not match its semantic content")
        return spec


@dataclass(frozen=True)
class JobArtifact:
    kind: str
    path: str
    sha256: str
    schema_version: str
    row_count: int | None = None

    def __post_init__(self) -> None:
        for name in ("kind", "path", "schema_version"):
            _string(getattr(self, name), name)
        _sha256(self.sha256, "sha256")
        if self.row_count is not None and (
            not isinstance(self.row_count, int)
            or isinstance(self.row_count, bool)
            or self.row_count < 0
        ):
            raise ValueError("row_count must be an integer >= 0 or None")

    @property
    def artifact_id(self) -> str:
        return stable_digest(
            {
                "kind": self.kind,
                "path": self.path,
                "row_count": self.row_count,
                "schema_version": self.schema_version,
                "sha256": self.sha256,
            },
            prefix="jobartifact_",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "path": self.path,
            "row_count": self.row_count,
            "schema_version": self.schema_version,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class JobCheckpoint:
    job_id: str
    attempt: int
    sequence: int
    input_digest: str
    recovery_position: str
    completed_units: int
    total_units: int | None
    payload: Mapping[str, Any]
    created_at: str
    semantic_result_digest: str | None = None
    schema_version: str = JOB_CHECKPOINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _content_id(self.job_id, "job_id", "job_")
        _content_id(self.input_digest, "input_digest", "jobinput_")
        _string(self.recovery_position, "recovery_position")
        _timestamp(self.created_at, "created_at")
        for name in ("attempt", "sequence", "completed_units"):
            value = getattr(self, name)
            minimum = 1 if name == "attempt" else 0
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if self.total_units is not None and (
            not isinstance(self.total_units, int)
            or isinstance(self.total_units, bool)
            or self.total_units < self.completed_units
        ):
            raise ValueError("total_units must be None or >= completed_units")
        if not isinstance(self.payload, Mapping):
            raise ValueError("checkpoint payload must be a mapping")
        object.__setattr__(self, "payload", to_canonical_data(self.payload))
        if self.semantic_result_digest is not None:
            _content_id(
                self.semantic_result_digest,
                "semantic_result_digest",
                "jobsemantic_",
            )
        if self.schema_version != JOB_CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("unsupported JobCheckpoint schema")

    @property
    def checkpoint_id(self) -> str:
        return stable_digest(self.identity_dict(), prefix="jobcheckpoint_")

    def identity_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "attempt": self.attempt,
                "completed_units": self.completed_units,
                "created_at": self.created_at,
                "input_digest": self.input_digest,
                "job_id": self.job_id,
                "payload": self.payload,
                "recovery_position": self.recovery_position,
                "schema_version": self.schema_version,
                "semantic_result_digest": self.semantic_result_digest,
                "sequence": self.sequence,
                "total_units": self.total_units,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity_dict(), "checkpoint_id": self.checkpoint_id}


@dataclass(frozen=True)
class JobControlSignal:
    job_id: str
    attempt: int
    state: JobState
    checked_at: str
    cancel_requested: bool
    lease_expired: bool
    attempt_timeout_exceeded: bool
    job_deadline_exceeded: bool
    recovery_position: str | None
    schema_version: str = JOB_CONTROL_SCHEMA_VERSION

    @property
    def should_stop(self) -> bool:
        return any(
            (
                self.cancel_requested,
                self.lease_expired,
                self.attempt_timeout_exceeded,
                self.job_deadline_exceeded,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "attempt_timeout_exceeded": self.attempt_timeout_exceeded,
            "cancel_requested": self.cancel_requested,
            "checked_at": self.checked_at,
            "job_deadline_exceeded": self.job_deadline_exceeded,
            "job_id": self.job_id,
            "lease_expired": self.lease_expired,
            "recovery_position": self.recovery_position,
            "schema_version": self.schema_version,
            "should_stop": self.should_stop,
            "state": self.state.value,
        }


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    kind: JobKind
    spec: JobSpec
    state: JobState
    priority: int
    max_attempts: int
    attempt: int
    created_at: str
    updated_at: str
    lease_owner: str | None
    lease_token: str | None
    lease_acquired_at: str | None
    heartbeat_at: str | None
    lease_expires_at: str | None
    deadline_at: str | None
    attempt_deadline_at: str | None
    retry_not_before_at: str | None
    latest_checkpoint_id: str | None
    recovery_position: str | None
    artifact_set_id: str | None
    error_code: str | None
    error_message: str | None
    schema_version: str = JOB_RECORD_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "artifact_set_id": self.artifact_set_id,
                "attempt": self.attempt,
                "created_at": self.created_at,
                "error_code": self.error_code,
                "error_message": self.error_message,
                "heartbeat_at": self.heartbeat_at,
                "job_id": self.job_id,
                "kind": self.kind.value,
                "lease_expires_at": self.lease_expires_at,
                "lease_acquired_at": self.lease_acquired_at,
                "lease_owner": self.lease_owner,
                "lease_token": self.lease_token,
                "latest_checkpoint_id": self.latest_checkpoint_id,
                "max_attempts": self.max_attempts,
                "priority": self.priority,
                "recovery_position": self.recovery_position,
                "retry_not_before_at": self.retry_not_before_at,
                "schema_version": self.schema_version,
                "spec": self.spec.to_dict(),
                "state": self.state.value,
                "attempt_deadline_at": self.attempt_deadline_at,
                "deadline_at": self.deadline_at,
                "updated_at": self.updated_at,
            }
        )


@dataclass(frozen=True)
class JobTransitionRecord:
    job_id: str
    sequence: int
    from_state: JobState | None
    to_state: JobState
    attempt: int
    actor: str
    occurred_at: str
    reason: str
    schema_version: str = JOB_TRANSITION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "attempt": self.attempt,
            "from_state": self.from_state.value if self.from_state else None,
            "job_id": self.job_id,
            "occurred_at": self.occurred_at,
            "reason": self.reason,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "to_state": self.to_state.value,
        }


@dataclass(frozen=True)
class JobStatusSnapshot:
    job: JobRecord
    latest_checkpoint: JobCheckpoint | None
    transitions: tuple[JobTransitionRecord, ...]
    artifacts: tuple[JobArtifact, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": [item.to_dict() for item in self.artifacts],
            "job": self.job.to_dict(),
            "latest_checkpoint": (
                self.latest_checkpoint.to_dict()
                if self.latest_checkpoint is not None
                else None
            ),
            "transitions": [item.to_dict() for item in self.transitions],
        }


class JobCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            has_meta = (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
                ).fetchone()
                is not None
            )
            if has_meta:
                row = connection.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()
                if row is None or row[0] != JOB_CATALOG_SCHEMA_VERSION:
                    observed = None if row is None else row[0]
                    raise ValueError(
                        f"job catalog schema {observed!r} requires explicit migration "
                        f"to {JOB_CATALOG_SCHEMA_VERSION!r}"
                    )
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    input_digest TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL CHECK(max_attempts >= 1),
                    attempt INTEGER NOT NULL CHECK(attempt >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_token TEXT,
                    lease_acquired_at TEXT,
                    heartbeat_at TEXT,
                    lease_expires_at TEXT,
                    deadline_at TEXT,
                    attempt_deadline_at TEXT,
                    retry_not_before_at TEXT,
                    latest_checkpoint_id TEXT,
                    recovery_position TEXT,
                    artifact_set_id TEXT,
                    error_code TEXT,
                    error_message TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_runnable
                    ON jobs(state, priority DESC, created_at, job_id);
                CREATE TABLE IF NOT EXISTS job_dependencies (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    dependency_job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    PRIMARY KEY(job_id, dependency_job_id),
                    CHECK(job_id != dependency_job_id)
                );
                CREATE TABLE IF NOT EXISTS job_transitions (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    sequence INTEGER NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    PRIMARY KEY(job_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS job_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    row_count INTEGER,
                    UNIQUE(job_id, path)
                );
                CREATE TABLE IF NOT EXISTS job_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    attempt INTEGER NOT NULL CHECK(attempt >= 1),
                    sequence INTEGER NOT NULL CHECK(sequence >= 0),
                    input_digest TEXT NOT NULL,
                    recovery_position TEXT NOT NULL,
                    completed_units INTEGER NOT NULL CHECK(completed_units >= 0),
                    total_units INTEGER,
                    payload_json TEXT NOT NULL,
                    semantic_result_digest TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(job_id, sequence),
                    UNIQUE(job_id, recovery_position),
                    CHECK(total_units IS NULL OR total_units >= completed_units)
                );
                """)
            if not has_meta:
                connection.execute(
                    "INSERT INTO schema_meta VALUES ('schema_version', ?)",
                    (JOB_CATALOG_SCHEMA_VERSION,),
                )

    def create_job(
        self,
        spec: JobSpec,
        *,
        created_at: str,
        actor: str = "scheduler",
    ) -> JobRecord:
        at = _timestamp(created_at, "created_at")
        _string(actor, "actor")
        self.initialize()
        spec_json = canonical_json(spec.to_dict())
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?",
                (spec.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing["spec_json"] != spec_json:
                    connection.rollback()
                    raise JobIdempotencyConflict(
                        "idempotency key already belongs to another JobSpec"
                    )
                connection.commit()
                return self._record(existing)
            for dependency_id in spec.dependency_ids:
                if (
                    connection.execute(
                        "SELECT 1 FROM jobs WHERE job_id = ?", (dependency_id,)
                    ).fetchone()
                    is None
                ):
                    connection.rollback()
                    raise ValueError(f"dependency job {dependency_id!r} does not exist")
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, idempotency_key, kind, input_digest, spec_json,
                    state, priority, max_attempts, attempt, created_at,
                    updated_at, deadline_at
                ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, 0, ?, ?, ?)
                """,
                (
                    spec.job_id,
                    spec.idempotency_key,
                    spec.kind.value,
                    spec.input_digest,
                    spec_json,
                    spec.priority,
                    spec.max_attempts,
                    at,
                    at,
                    spec.deadline_at,
                ),
            )
            connection.executemany(
                "INSERT INTO job_dependencies VALUES (?, ?)",
                ((spec.job_id, item) for item in spec.dependency_ids),
            )
            self._insert_transition(
                connection,
                spec.job_id,
                from_state=None,
                to_state=JobState.QUEUED,
                attempt=0,
                actor=actor,
                occurred_at=at,
                reason="created",
            )
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (spec.job_id,)
            ).fetchone()
            connection.commit()
        return self._record(row)

    def claim_next(
        self,
        *,
        worker_id: str,
        now: str,
        lease_seconds: float,
        kinds: Sequence[JobKind | str] | None = None,
    ) -> JobRecord | None:
        owner = _string(worker_id, "worker_id")
        at = _timestamp(now, "now")
        if not isinstance(lease_seconds, (int, float)) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be > 0")
        accepted_kinds = (
            tuple(JobKind(item) for item in kinds)
            if kinds is not None
            else tuple(JobKind)
        )
        if not accepted_kinds:
            raise ValueError("kinds must contain at least one JobKind")
        if len(accepted_kinds) != len(set(accepted_kinds)):
            raise ValueError("kinds must not contain duplicates")
        kind_placeholders = ", ".join("?" for _ in accepted_kinds)
        self.initialize()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT candidate.* FROM jobs AS candidate
                WHERE candidate.state IN ('queued', 'retrying')
                  AND candidate.kind IN ("""
                + kind_placeholders
                + """)
                  AND candidate.attempt < candidate.max_attempts
                  AND (
                    candidate.deadline_at IS NULL
                    OR julianday(candidate.deadline_at) > julianday(?)
                  )
                  AND (
                    candidate.retry_not_before_at IS NULL
                    OR julianday(candidate.retry_not_before_at) <= julianday(?)
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM job_dependencies AS dependency
                    JOIN jobs AS parent
                      ON parent.job_id = dependency.dependency_job_id
                    WHERE dependency.job_id = candidate.job_id
                      AND parent.state != 'succeeded'
                  )
                ORDER BY candidate.priority DESC,
                         julianday(candidate.created_at),
                         candidate.created_at,
                         candidate.job_id
                LIMIT 1
                """,
                (*[item.value for item in accepted_kinds], at, at),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            previous = JobState(row["state"])
            attempt = int(row["attempt"]) + 1
            spec = JobSpec.from_dict(json.loads(row["spec_json"]))
            lease_token = stable_digest(
                {
                    "attempt": attempt,
                    "job_id": row["job_id"],
                    "lease_acquired_at": at,
                    "worker_id": owner,
                },
                prefix="lease_",
            )
            expires_at = _plus_seconds(at, float(lease_seconds))
            attempt_deadline_at = _plus_seconds(
                at,
                spec.retry_policy.attempt_timeout_seconds,
            )
            if spec.deadline_at is not None and _parsed_timestamp(
                spec.deadline_at
            ) < _parsed_timestamp(attempt_deadline_at):
                attempt_deadline_at = spec.deadline_at
            connection.execute(
                """
                UPDATE jobs
                SET state='running', attempt=?, updated_at=?,
                    lease_owner=?, lease_token=?, lease_acquired_at=?,
                    heartbeat_at=?, lease_expires_at=?,
                    attempt_deadline_at=?, retry_not_before_at=NULL,
                    error_code=NULL, error_message=NULL
                WHERE job_id=?
                """,
                (
                    attempt,
                    at,
                    owner,
                    lease_token,
                    at,
                    at,
                    expires_at,
                    attempt_deadline_at,
                    row["job_id"],
                ),
            )
            self._insert_transition(
                connection,
                row["job_id"],
                from_state=previous,
                to_state=JobState.RUNNING,
                attempt=attempt,
                actor=owner,
                occurred_at=at,
                reason="lease_acquired",
            )
            claimed = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            connection.commit()
        return self._record(claimed)

    def heartbeat(
        self,
        job_id: str,
        *,
        lease_token: str,
        now: str,
        lease_seconds: float,
    ) -> JobRecord:
        at = _timestamp(now, "now")
        if not isinstance(lease_seconds, (int, float)) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be > 0")
        self.initialize()
        with closing(self._connect()) as connection, connection:
            row = self._job_row(connection, job_id)
            self._assert_lease(row, lease_token, at)
            if JobState(row["state"]) not in {
                JobState.RUNNING,
                JobState.CANCELLING,
            }:
                raise JobLeaseError("heartbeat requires a running or cancelling job")
            attempt_deadline_at = row["attempt_deadline_at"]
            if attempt_deadline_at is not None and _parsed_timestamp(
                at
            ) >= _parsed_timestamp(attempt_deadline_at):
                raise JobLeaseError("job attempt deadline has expired")
            lease_expires_at = _plus_seconds(at, float(lease_seconds))
            if attempt_deadline_at is not None and _parsed_timestamp(
                attempt_deadline_at
            ) < _parsed_timestamp(lease_expires_at):
                lease_expires_at = attempt_deadline_at
            connection.execute(
                """
                UPDATE jobs SET heartbeat_at=?, lease_expires_at=?, updated_at=?
                WHERE job_id=?
                """,
                (at, lease_expires_at, at, job_id),
            )
            updated = self._job_row(connection, job_id)
        return self._record(updated)

    def control_signal(
        self,
        job_id: str,
        *,
        lease_token: str,
        now: str,
    ) -> JobControlSignal:
        at = _timestamp(now, "now")
        self.initialize()
        with closing(self._connect()) as connection:
            row = self._job_row(connection, job_id)
        if row["lease_token"] != lease_token:
            raise JobLeaseError("job lease token does not match the active attempt")
        state = JobState(row["state"])
        if state not in {JobState.RUNNING, JobState.CANCELLING}:
            raise JobLeaseError("job no longer has an active attempt")
        if row["lease_acquired_at"] is not None and _parsed_timestamp(
            at
        ) < _parsed_timestamp(row["lease_acquired_at"]):
            raise JobLeaseError("control timestamp predates the active lease")

        def reached(value: str | None) -> bool:
            return value is not None and _parsed_timestamp(at) >= _parsed_timestamp(
                value
            )

        return JobControlSignal(
            job_id=job_id,
            attempt=int(row["attempt"]),
            state=state,
            checked_at=at,
            cancel_requested=state == JobState.CANCELLING,
            lease_expired=reached(row["lease_expires_at"]),
            attempt_timeout_exceeded=reached(row["attempt_deadline_at"]),
            job_deadline_exceeded=reached(row["deadline_at"]),
            recovery_position=row["recovery_position"],
        )

    def overdue_attempts(self, *, now: str) -> tuple[JobRecord, ...]:
        at = _timestamp(now, "now")
        self.initialize()
        with closing(self._connect()) as connection:
            rows = connection.execute("""
                SELECT * FROM jobs
                WHERE state IN ('running', 'cancelling')
                ORDER BY job_id
                """).fetchall()

        def reached(value: str | None) -> bool:
            return value is not None and _parsed_timestamp(at) >= _parsed_timestamp(
                value
            )

        return tuple(
            self._record(row)
            for row in rows
            if reached(row["attempt_deadline_at"]) or reached(row["deadline_at"])
        )

    def expire_pending_deadlines(
        self,
        *,
        now: str,
        actor: str = "scheduler",
    ) -> tuple[JobRecord, ...]:
        at = _timestamp(now, "now")
        _string(actor, "actor")
        self.initialize()
        expired: list[JobRecord] = []
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("""
                SELECT * FROM jobs
                WHERE state IN ('queued', 'retrying')
                  AND deadline_at IS NOT NULL
                ORDER BY job_id
                """).fetchall()
            for row in rows:
                if _parsed_timestamp(at) < _parsed_timestamp(row["deadline_at"]):
                    continue
                previous = JobState(row["state"])
                self._assert_transition(previous, JobState.FAILED)
                connection.execute(
                    """
                    UPDATE jobs
                    SET state='failed', updated_at=?, retry_not_before_at=NULL,
                        error_code='deadline_exceeded',
                        error_message='job deadline expired before execution'
                    WHERE job_id=?
                    """,
                    (at, row["job_id"]),
                )
                self._insert_transition(
                    connection,
                    row["job_id"],
                    from_state=previous,
                    to_state=JobState.FAILED,
                    attempt=int(row["attempt"]),
                    actor=actor,
                    occurred_at=at,
                    reason="deadline_exceeded",
                )
                expired.append(self._record(self._job_row(connection, row["job_id"])))
            connection.commit()
        return tuple(expired)

    def recover_timed_out_attempt(
        self,
        job_id: str,
        *,
        lease_token: str,
        now: str,
        actor: str = "scheduler",
    ) -> JobRecord:
        at = _timestamp(now, "now")
        _string(actor, "actor")
        self.initialize()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._job_row(connection, job_id)
            if row["lease_token"] != lease_token:
                raise JobLeaseError(
                    "job lease token does not match the timed-out attempt"
                )
            previous = JobState(row["state"])
            if previous not in {JobState.RUNNING, JobState.CANCELLING}:
                raise JobStateTransitionError("job has no active attempt to recover")
            deadline_exceeded = row["deadline_at"] is not None and (
                _parsed_timestamp(at) >= _parsed_timestamp(row["deadline_at"])
            )
            attempt_timeout = row["attempt_deadline_at"] is not None and (
                _parsed_timestamp(at) >= _parsed_timestamp(row["attempt_deadline_at"])
            )
            if not deadline_exceeded and not attempt_timeout:
                raise JobStateTransitionError("job attempt has not timed out")
            spec = JobSpec.from_dict(json.loads(row["spec_json"]))
            retry_not_before_at = None
            if previous == JobState.CANCELLING:
                target = JobState.CANCELLED
                error_code = None
                error_message = None
                reason = "cancel_timeout"
            elif deadline_exceeded:
                target = JobState.FAILED
                error_code = "deadline_exceeded"
                error_message = "job deadline exceeded"
                reason = error_code
            elif (
                int(row["attempt"]) < int(row["max_attempts"])
                and "hard_timeout" in spec.retry_policy.retryable_error_codes
            ):
                candidate_retry = _plus_seconds(
                    at,
                    spec.retry_policy.backoff_after(int(row["attempt"])),
                )
                if spec.deadline_at is not None and _parsed_timestamp(
                    candidate_retry
                ) >= _parsed_timestamp(spec.deadline_at):
                    target = JobState.FAILED
                    error_code = "deadline_exceeded"
                    error_message = "hard-timeout retry exceeds the job deadline"
                    reason = error_code
                else:
                    target = JobState.RETRYING
                    error_code = "hard_timeout"
                    error_message = "attempt exceeded its hard timeout"
                    retry_not_before_at = candidate_retry
                    reason = error_code
            else:
                target = JobState.FAILED
                error_code = (
                    "attempts_exhausted"
                    if int(row["attempt"]) >= int(row["max_attempts"])
                    else "hard_timeout"
                )
                error_message = "hard timeout is not retryable"
                if error_code == "attempts_exhausted":
                    error_message = "hard timeout exhausted the final attempt"
                reason = error_code
            self._assert_transition(previous, target)
            connection.execute(
                """
                UPDATE jobs
                SET state=?, updated_at=?, lease_owner=NULL, lease_token=NULL,
                    lease_acquired_at=NULL, heartbeat_at=NULL,
                    lease_expires_at=NULL, attempt_deadline_at=NULL,
                    retry_not_before_at=?, error_code=?, error_message=?
                WHERE job_id=?
                """,
                (
                    target.value,
                    at,
                    retry_not_before_at,
                    error_code,
                    error_message,
                    job_id,
                ),
            )
            self._insert_transition(
                connection,
                job_id,
                from_state=previous,
                to_state=target,
                attempt=int(row["attempt"]),
                actor=actor,
                occurred_at=at,
                reason=reason,
            )
            updated = self._job_row(connection, job_id)
            connection.commit()
        return self._record(updated)

    def request_cancel(
        self,
        job_id: str,
        *,
        actor: str,
        now: str,
        reason: str,
    ) -> JobRecord:
        return self._simple_transition(
            job_id,
            JobState.CANCELLING,
            actor=actor,
            now=now,
            reason=reason,
            clear_lease=False,
        )

    def finish_cancelled(
        self,
        job_id: str,
        *,
        actor: str,
        now: str,
        reason: str,
        lease_token: str | None = None,
    ) -> JobRecord:
        return self._simple_transition(
            job_id,
            JobState.CANCELLED,
            actor=actor,
            now=now,
            reason=reason,
            lease_token=lease_token,
            clear_lease=True,
        )

    def fail_job(
        self,
        job_id: str,
        *,
        actor: str,
        now: str,
        error_code: str,
        error_message: str,
        lease_token: str | None = None,
    ) -> JobRecord:
        return self._simple_transition(
            job_id,
            JobState.FAILED,
            actor=actor,
            now=now,
            reason=error_code,
            lease_token=lease_token,
            clear_lease=True,
            error_code=_string(error_code, "error_code"),
            error_message=_string(error_message, "error_message"),
        )

    def schedule_retry(
        self,
        job_id: str,
        *,
        actor: str,
        now: str,
        reason: str,
        error_code: str | None = None,
        lease_token: str | None = None,
    ) -> JobRecord:
        record = self.get_job(job_id)
        if record is None:
            raise ValueError(f"job {job_id!r} does not exist")
        if record.attempt >= record.max_attempts:
            raise JobStateTransitionError("job has exhausted max_attempts")
        self._assert_transition(record.state, JobState.RETRYING)
        retry_code = _string(error_code or reason, "error_code")
        if retry_code not in record.spec.retry_policy.retryable_error_codes:
            raise JobStateTransitionError(
                f"error code {retry_code!r} is not retryable by policy"
            )
        retry_not_before_at = _plus_seconds(
            _timestamp(now, "now"),
            record.spec.retry_policy.backoff_after(record.attempt),
        )
        if record.deadline_at is not None and _parsed_timestamp(
            retry_not_before_at
        ) >= _parsed_timestamp(record.deadline_at):
            raise JobStateTransitionError("retry backoff exceeds the job deadline")
        return self._simple_transition(
            job_id,
            JobState.RETRYING,
            actor=actor,
            now=now,
            reason=reason,
            lease_token=lease_token,
            clear_lease=True,
            error_code=retry_code,
            error_message=reason,
            retry_not_before_at=retry_not_before_at,
        )

    def quarantine_job(
        self,
        job_id: str,
        *,
        actor: str,
        now: str,
        reason: str,
        lease_token: str | None = None,
    ) -> JobRecord:
        return self._simple_transition(
            job_id,
            JobState.QUARANTINED,
            actor=actor,
            now=now,
            reason=reason,
            lease_token=lease_token,
            clear_lease=True,
            error_code="quarantined",
            error_message=reason,
        )

    def succeed_job(
        self,
        job_id: str,
        *,
        actor: str,
        now: str,
        lease_token: str,
        artifacts: Sequence[JobArtifact],
    ) -> JobRecord:
        at = _timestamp(now, "now")
        _string(actor, "actor")
        ordered = tuple(sorted(artifacts, key=lambda item: item.artifact_id))
        if not ordered:
            raise ValueError("a succeeded job must commit at least one artifact")
        artifact_set_id = stable_digest(
            [item.to_dict() for item in ordered], prefix="jobartifacts_"
        )
        self.initialize()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._job_row(connection, job_id)
            state = JobState(row["state"])
            if state == JobState.SUCCEEDED:
                if row["artifact_set_id"] != artifact_set_id:
                    connection.rollback()
                    raise JobIdempotencyConflict(
                        "succeeded job cannot commit a different artifact set"
                    )
                connection.commit()
                return self._record(row)
            self._assert_transition(state, JobState.SUCCEEDED)
            self._assert_lease(row, lease_token, at)
            for artifact in ordered:
                connection.execute(
                    "INSERT INTO job_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        artifact.artifact_id,
                        job_id,
                        artifact.kind,
                        artifact.path,
                        artifact.sha256,
                        artifact.schema_version,
                        artifact.row_count,
                    ),
                )
            connection.execute(
                """
                UPDATE jobs
                SET state='succeeded', updated_at=?, artifact_set_id=?,
                    lease_owner=NULL, lease_token=NULL, lease_acquired_at=NULL,
                    heartbeat_at=NULL, lease_expires_at=NULL,
                    attempt_deadline_at=NULL, retry_not_before_at=NULL,
                    error_code=NULL, error_message=NULL
                WHERE job_id=?
                """,
                (at, artifact_set_id, job_id),
            )
            self._insert_transition(
                connection,
                job_id,
                from_state=state,
                to_state=JobState.SUCCEEDED,
                attempt=int(row["attempt"]),
                actor=actor,
                occurred_at=at,
                reason="artifact_commit",
            )
            updated = self._job_row(connection, job_id)
            connection.commit()
        return self._record(updated)

    def reclaim_orphans(
        self,
        *,
        now: str,
        actor: str = "scheduler",
    ) -> tuple[JobRecord, ...]:
        at = _timestamp(now, "now")
        _string(actor, "actor")
        self.initialize()
        reclaimed: list[JobRecord] = []
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("""
                SELECT * FROM jobs
                WHERE state IN ('running', 'cancelling')
                  AND lease_expires_at IS NOT NULL
                ORDER BY job_id
                """).fetchall()
            for row in rows:
                if _parsed_timestamp(row["lease_expires_at"]) > _parsed_timestamp(at):
                    continue
                previous = JobState(row["state"])
                spec = JobSpec.from_dict(json.loads(row["spec_json"]))
                retry_not_before_at = None
                if previous == JobState.CANCELLING:
                    target = JobState.CANCELLED
                    error_code = None
                    error_message = None
                elif spec.deadline_at is not None and _parsed_timestamp(
                    at
                ) >= _parsed_timestamp(spec.deadline_at):
                    target = JobState.FAILED
                    error_code = "deadline_exceeded"
                    error_message = "job deadline expired while the worker was lost"
                elif (
                    int(row["attempt"]) < int(row["max_attempts"])
                    and "lease_expired" in spec.retry_policy.retryable_error_codes
                ):
                    candidate_retry = _plus_seconds(
                        at,
                        spec.retry_policy.backoff_after(int(row["attempt"])),
                    )
                    if spec.deadline_at is not None and _parsed_timestamp(
                        candidate_retry
                    ) >= _parsed_timestamp(spec.deadline_at):
                        target = JobState.FAILED
                        error_code = "deadline_exceeded"
                        error_message = "retry backoff exceeds the job deadline"
                    else:
                        target = JobState.RETRYING
                        error_code = "lease_expired"
                        error_message = "worker lease expired; job is retryable"
                        retry_not_before_at = candidate_retry
                else:
                    target = JobState.FAILED
                    error_code = (
                        "attempts_exhausted"
                        if int(row["attempt"]) >= int(row["max_attempts"])
                        else "lease_expired"
                    )
                    error_message = (
                        "worker lease expired after the final attempt"
                        if error_code == "attempts_exhausted"
                        else "worker lease expiry is not retryable by policy"
                    )
                self._assert_transition(previous, target)
                connection.execute(
                    """
                    UPDATE jobs SET state=?, updated_at=?,
                        lease_owner=NULL, lease_token=NULL,
                        lease_acquired_at=NULL, heartbeat_at=NULL,
                        lease_expires_at=NULL, attempt_deadline_at=NULL,
                        retry_not_before_at=?, error_code=?, error_message=?
                    WHERE job_id=?
                    """,
                    (
                        target.value,
                        at,
                        retry_not_before_at,
                        error_code,
                        error_message,
                        row["job_id"],
                    ),
                )
                self._insert_transition(
                    connection,
                    row["job_id"],
                    from_state=previous,
                    to_state=target,
                    attempt=int(row["attempt"]),
                    actor=actor,
                    occurred_at=at,
                    reason=(
                        "cancel_after_lease_expired"
                        if target == JobState.CANCELLED
                        else error_code or "lease_expired"
                    ),
                )
                reclaimed.append(self._record(self._job_row(connection, row["job_id"])))
            connection.commit()
        return tuple(reclaimed)

    def get_job(self, job_id: str) -> JobRecord | None:
        self.initialize()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return self._record(row) if row is not None else None

    def status_snapshot(self, job_id: str) -> JobStatusSnapshot:
        self.initialize()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            job_row = self._job_row(connection, job_id)
            checkpoint_row = connection.execute(
                """
                SELECT * FROM job_checkpoints
                WHERE job_id=? ORDER BY sequence DESC LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            transition_rows = connection.execute(
                """
                SELECT * FROM job_transitions
                WHERE job_id=? ORDER BY sequence
                """,
                (job_id,),
            ).fetchall()
            artifact_rows = connection.execute(
                """
                SELECT kind, path, sha256, schema_version, row_count
                FROM job_artifacts WHERE job_id=? ORDER BY artifact_id
                """,
                (job_id,),
            ).fetchall()
            snapshot = JobStatusSnapshot(
                job=self._record(job_row),
                latest_checkpoint=(
                    self._checkpoint(checkpoint_row)
                    if checkpoint_row is not None
                    else None
                ),
                transitions=tuple(self._transition(row) for row in transition_rows),
                artifacts=tuple(JobArtifact(*row) for row in artifact_rows),
            )
            connection.commit()
        return snapshot

    def transitions(self, job_id: str) -> tuple[JobTransitionRecord, ...]:
        self.initialize()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM job_transitions
                WHERE job_id=? ORDER BY sequence
                """,
                (job_id,),
            ).fetchall()
        return tuple(self._transition(row) for row in rows)

    def artifacts(self, job_id: str) -> tuple[JobArtifact, ...]:
        self.initialize()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT kind, path, sha256, schema_version, row_count
                FROM job_artifacts WHERE job_id=? ORDER BY artifact_id
                """,
                (job_id,),
            ).fetchall()
        return tuple(JobArtifact(*row) for row in rows)

    def artifact_references(self) -> tuple[tuple[str, JobArtifact], ...]:
        self.initialize()
        with closing(self._connect()) as connection:
            rows = connection.execute("""
                SELECT job_id, kind, path, sha256, schema_version, row_count
                FROM job_artifacts ORDER BY job_id, artifact_id
                """).fetchall()
        return tuple(
            (
                row["job_id"],
                JobArtifact(
                    kind=row["kind"],
                    path=row["path"],
                    sha256=row["sha256"],
                    schema_version=row["schema_version"],
                    row_count=(
                        int(row["row_count"]) if row["row_count"] is not None else None
                    ),
                ),
            )
            for row in rows
        )

    def save_checkpoint(
        self,
        job_id: str,
        *,
        lease_token: str,
        now: str,
        recovery_position: str,
        completed_units: int,
        total_units: int | None,
        payload: Mapping[str, Any],
        semantic_result_digest: str | None = None,
    ) -> JobCheckpoint:
        at = _timestamp(now, "now")
        position = _string(recovery_position, "recovery_position")
        canonical_payload = to_canonical_data(payload)
        payload_json = canonical_json(canonical_payload)
        if len(payload_json.encode("utf-8")) > JOB_CHECKPOINT_MAX_BYTES:
            raise ValueError("checkpoint payload exceeds the 1 MiB limit")
        self.initialize()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = self._job_row(connection, job_id)
            self._assert_lease(job, lease_token, at)
            if JobState(job["state"]) not in {
                JobState.RUNNING,
                JobState.CANCELLING,
            }:
                raise JobStateTransitionError(
                    "checkpoint requires a running or cancelling job"
                )
            existing_row = connection.execute(
                """
                SELECT * FROM job_checkpoints
                WHERE job_id=? AND recovery_position=?
                """,
                (job_id, position),
            ).fetchone()
            if existing_row is not None:
                existing = self._checkpoint(existing_row)
                if (
                    existing.completed_units != completed_units
                    or existing.total_units != total_units
                    or existing.payload != canonical_payload
                    or existing.semantic_result_digest != semantic_result_digest
                ):
                    connection.rollback()
                    raise JobCheckpointConflict(
                        "recovery position already has different checkpoint content"
                    )
                connection.commit()
                return existing
            latest_row = connection.execute(
                """
                SELECT * FROM job_checkpoints
                WHERE job_id=? ORDER BY sequence DESC LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            latest = self._checkpoint(latest_row) if latest_row is not None else None
            if latest is not None and completed_units < latest.completed_units:
                connection.rollback()
                raise JobCheckpointConflict("checkpoint progress cannot move backwards")
            if (
                latest is not None
                and latest.total_units is not None
                and total_units != latest.total_units
            ):
                connection.rollback()
                raise JobCheckpointConflict(
                    "known checkpoint total_units cannot change"
                )
            sequence = 0 if latest is None else latest.sequence + 1
            checkpoint = JobCheckpoint(
                job_id=job_id,
                attempt=int(job["attempt"]),
                sequence=sequence,
                input_digest=job["input_digest"],
                recovery_position=position,
                completed_units=completed_units,
                total_units=total_units,
                payload=canonical_payload,
                created_at=at,
                semantic_result_digest=semantic_result_digest,
            )
            connection.execute(
                """
                INSERT INTO job_checkpoints VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    checkpoint.checkpoint_id,
                    checkpoint.job_id,
                    checkpoint.attempt,
                    checkpoint.sequence,
                    checkpoint.input_digest,
                    checkpoint.recovery_position,
                    checkpoint.completed_units,
                    checkpoint.total_units,
                    payload_json,
                    checkpoint.semantic_result_digest,
                    checkpoint.created_at,
                ),
            )
            connection.execute(
                """
                UPDATE jobs
                SET latest_checkpoint_id=?, recovery_position=?, updated_at=?
                WHERE job_id=?
                """,
                (checkpoint.checkpoint_id, position, at, job_id),
            )
            connection.commit()
        return checkpoint

    def checkpoints(self, job_id: str) -> tuple[JobCheckpoint, ...]:
        self.initialize()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM job_checkpoints
                WHERE job_id=? ORDER BY sequence
                """,
                (job_id,),
            ).fetchall()
        return tuple(self._checkpoint(row) for row in rows)

    def latest_checkpoint(self, job_id: str) -> JobCheckpoint | None:
        self.initialize()
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT * FROM job_checkpoints
                WHERE job_id=? ORDER BY sequence DESC LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        return self._checkpoint(row) if row is not None else None

    def resume_checkpoint(
        self,
        job_id: str,
        *,
        expected_input_digest: str,
    ) -> JobCheckpoint | None:
        expected = _content_id(
            expected_input_digest,
            "expected_input_digest",
            "jobinput_",
        )
        job = self.get_job(job_id)
        if job is None:
            raise ValueError(f"job {job_id!r} does not exist")
        if job.spec.input_digest != expected:
            raise JobCheckpointConflict(
                "resume input digest does not match the immutable JobSpec"
            )
        checkpoint = self.latest_checkpoint(job_id)
        if checkpoint is not None and checkpoint.input_digest != expected:
            raise JobCheckpointConflict(
                "checkpoint input digest does not match the requested resume input"
            )
        return checkpoint

    def _simple_transition(
        self,
        job_id: str,
        target: JobState,
        *,
        actor: str,
        now: str,
        reason: str,
        lease_token: str | None = None,
        clear_lease: bool,
        error_code: str | None = None,
        error_message: str | None = None,
        retry_not_before_at: str | None = None,
    ) -> JobRecord:
        at = _timestamp(now, "now")
        _string(actor, "actor")
        _string(reason, "reason")
        self.initialize()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._job_row(connection, job_id)
            previous = JobState(row["state"])
            self._assert_transition(previous, target)
            if row["lease_token"] is not None and target not in {JobState.CANCELLING}:
                if lease_token is None:
                    connection.rollback()
                    raise JobLeaseError("lease token is required for worker transition")
                self._assert_lease(row, lease_token, at)
            lease_values = (
                (None, None, None, None, None)
                if clear_lease
                else (
                    row["lease_owner"],
                    row["lease_token"],
                    row["lease_acquired_at"],
                    row["heartbeat_at"],
                    row["lease_expires_at"],
                )
            )
            attempt_deadline_at = None if clear_lease else row["attempt_deadline_at"]
            connection.execute(
                """
                UPDATE jobs SET state=?, updated_at=?,
                    lease_owner=?, lease_token=?, lease_acquired_at=?,
                    heartbeat_at=?, lease_expires_at=?,
                    attempt_deadline_at=?, retry_not_before_at=?,
                    error_code=?, error_message=?
                WHERE job_id=?
                """,
                (
                    target.value,
                    at,
                    *lease_values,
                    attempt_deadline_at,
                    retry_not_before_at,
                    error_code,
                    error_message,
                    job_id,
                ),
            )
            self._insert_transition(
                connection,
                job_id,
                from_state=previous,
                to_state=target,
                attempt=int(row["attempt"]),
                actor=actor,
                occurred_at=at,
                reason=reason,
            )
            updated = self._job_row(connection, job_id)
            connection.commit()
        return self._record(updated)

    @staticmethod
    def _assert_transition(previous: JobState, target: JobState) -> None:
        if target not in _ALLOWED_TRANSITIONS[previous]:
            raise JobStateTransitionError(
                f"invalid job transition {previous.value!r} -> {target.value!r}"
            )

    @staticmethod
    def _assert_lease(row: sqlite3.Row, lease_token: str, now: str) -> None:
        if row["lease_token"] != lease_token:
            raise JobLeaseError("job lease token does not match the active attempt")
        expires_at = row["lease_expires_at"]
        if expires_at is None or _parsed_timestamp(now) >= _parsed_timestamp(
            expires_at
        ):
            raise JobLeaseError("job lease has expired")

    @staticmethod
    def _job_row(connection: sqlite3.Connection, job_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"job {job_id!r} does not exist")
        return row

    @staticmethod
    def _record(row: sqlite3.Row) -> JobRecord:
        spec = JobSpec.from_dict(json.loads(row["spec_json"]))
        if spec.job_id != row["job_id"] or spec.kind.value != row["kind"]:
            raise ValueError("stored JobSpec does not match its job catalog row")
        return JobRecord(
            job_id=row["job_id"],
            kind=JobKind(row["kind"]),
            spec=spec,
            state=JobState(row["state"]),
            priority=int(row["priority"]),
            max_attempts=int(row["max_attempts"]),
            attempt=int(row["attempt"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            lease_owner=row["lease_owner"],
            lease_token=row["lease_token"],
            lease_acquired_at=row["lease_acquired_at"],
            heartbeat_at=row["heartbeat_at"],
            lease_expires_at=row["lease_expires_at"],
            deadline_at=row["deadline_at"],
            attempt_deadline_at=row["attempt_deadline_at"],
            retry_not_before_at=row["retry_not_before_at"],
            latest_checkpoint_id=row["latest_checkpoint_id"],
            recovery_position=row["recovery_position"],
            artifact_set_id=row["artifact_set_id"],
            error_code=row["error_code"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _checkpoint(row: sqlite3.Row) -> JobCheckpoint:
        checkpoint = JobCheckpoint(
            job_id=row["job_id"],
            attempt=int(row["attempt"]),
            sequence=int(row["sequence"]),
            input_digest=row["input_digest"],
            recovery_position=row["recovery_position"],
            completed_units=int(row["completed_units"]),
            total_units=(
                int(row["total_units"]) if row["total_units"] is not None else None
            ),
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
            semantic_result_digest=row["semantic_result_digest"],
        )
        if checkpoint.checkpoint_id != row["checkpoint_id"]:
            raise ValueError("stored checkpoint ID does not match its content")
        return checkpoint

    @staticmethod
    def _transition(row: sqlite3.Row) -> JobTransitionRecord:
        return JobTransitionRecord(
            job_id=row["job_id"],
            sequence=int(row["sequence"]),
            from_state=(
                JobState(row["from_state"]) if row["from_state"] is not None else None
            ),
            to_state=JobState(row["to_state"]),
            attempt=int(row["attempt"]),
            actor=row["actor"],
            occurred_at=row["occurred_at"],
            reason=row["reason"],
        )

    @staticmethod
    def _insert_transition(
        connection: sqlite3.Connection,
        job_id: str,
        *,
        from_state: JobState | None,
        to_state: JobState,
        attempt: int,
        actor: str,
        occurred_at: str,
        reason: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), -1) + 1
            FROM job_transitions WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()
        connection.execute(
            "INSERT INTO job_transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                int(row[0]),
                from_state.value if from_state else None,
                to_state.value,
                attempt,
                actor,
                occurred_at,
                reason,
            ),
        )
