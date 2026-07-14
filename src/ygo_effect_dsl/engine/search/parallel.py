from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    FailureRecord,
    FailureRecordError,
    RecoveryAction,
)


PARALLEL_SEARCH_POLICY_SCHEMA_VERSION = "parallel-search-policy-v1"
PARALLEL_SEARCH_PLAN_SCHEMA_VERSION = "parallel-search-plan-v1"
PARALLEL_TASK_SCHEMA_VERSION = "parallel-search-task-v1"
PARALLEL_ATTEMPT_SCHEMA_VERSION = "parallel-search-attempt-v1"
LEGACY_PARALLEL_RESULT_SCHEMA_VERSION = "parallel-search-result-v1"
PARALLEL_RESULT_SCHEMA_VERSION = "parallel-search-result-v2"
PARALLEL_AGGREGATE_SCHEMA_VERSION = "parallel-search-aggregate-v2"


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _non_negative_integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{path} must be a non-negative integer")
    return value


def _finite_number(value: Any, path: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{path} must be a finite number")
    return value


def _seed_word(value: Mapping[str, Any]) -> int:
    digest = stable_digest(value).split("_", 1)[-1]
    return int(digest[:16], 16)


def _seed_words(base_seed: int, namespace: str, identity: str) -> tuple[int, ...]:
    return tuple(
        _seed_word(
            {
                "base_seed": base_seed,
                "identity": identity,
                "namespace": namespace,
                "word": index,
            }
        )
        for index in range(4)
    )


class ParallelResultStatus(str, Enum):
    SUCCESS = "success"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"


class ParallelOutcomeStatus(str, Enum):
    SUCCESS = "success"
    PENDING_INITIAL = "pending_initial"
    PENDING_RETRY = "pending_retry"
    FAILED_PERMANENT = "failed_permanent"
    FAILED_RETRY_EXHAUSTED = "failed_retry_exhausted"


@dataclass(frozen=True)
class ParallelSearchPolicy:
    pool_size: int
    base_seed: int
    max_retries: int = 1
    schema_version: str = PARALLEL_SEARCH_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if _non_negative_integer(self.pool_size, "pool_size") < 1:
            raise ValueError("pool_size must be an integer >= 1")
        _non_negative_integer(self.base_seed, "base_seed")
        _non_negative_integer(self.max_retries, "max_retries")
        if self.schema_version != PARALLEL_SEARCH_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported parallel search policy schema")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ParallelSearchPolicy":
        if not isinstance(value, Mapping):
            raise ValueError("parallel search policy must be a mapping")
        known = {"base_seed", "max_retries", "pool_size"}
        unknown = sorted(set(value) - known)
        if unknown:
            raise ValueError(f"unknown parallel search policy fields: {unknown}")
        missing = sorted({"base_seed", "pool_size"} - set(value))
        if missing:
            raise ValueError(f"missing parallel search policy fields: {missing}")
        return cls(**dict(value))

    @classmethod
    def from_experiment(cls, experiment: Mapping[str, Any]) -> "ParallelSearchPolicy":
        search = experiment.get("search")
        if not isinstance(search, Mapping):
            raise ValueError("experiment.search must be a mapping")
        parameters = search.get("parameters")
        if not isinstance(parameters, Mapping):
            raise ValueError("search.parameters must be a mapping")
        parallel = parameters.get("parallel")
        if not isinstance(parallel, Mapping):
            raise ValueError("search.parameters.parallel must be a mapping")
        return cls.from_mapping(parallel)

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "base_seed": self.base_seed,
                "max_retries": self.max_retries,
                "pool_size": self.pool_size,
                "schema_version": self.schema_version,
            }
        )
        return {**identity, "policy_id": stable_digest(identity, prefix="parallelpol_")}


def build_search_node_id(
    *,
    experiment_id: str,
    state_id: str,
    depth: int,
    parent_node_id: str | None = None,
    action_id: str | None = None,
) -> str:
    _string(experiment_id, "experiment_id")
    _string(state_id, "state_id")
    depth = _non_negative_integer(depth, "depth")
    if depth == 0:
        if parent_node_id is not None or action_id is not None:
            raise ValueError("root node must not have parent_node_id or action_id")
    elif parent_node_id is None or action_id is None:
        raise ValueError("non-root node requires parent_node_id and action_id")
    else:
        _string(parent_node_id, "parent_node_id")
        _string(action_id, "action_id")
    return stable_digest(
        {
            "action_id": action_id,
            "depth": depth,
            "experiment_id": experiment_id,
            "parent_node_id": parent_node_id,
            "state_id": state_id,
        },
        prefix="searchnode_",
    )


@dataclass(frozen=True)
class ParallelCandidate:
    candidate_id: str
    node_id: str
    work_key: str
    payload_ref: str

    def __post_init__(self) -> None:
        for name in ("candidate_id", "node_id", "work_key", "payload_ref"):
            _string(getattr(self, name), name)

    @classmethod
    def from_prefix(
        cls,
        *,
        node_id: str,
        prefix_key_id: str,
        action_id: str,
        payload_ref: str,
    ) -> "ParallelCandidate":
        work_identity = {
            "action_id": _string(action_id, "action_id"),
            "prefix_key_id": _string(prefix_key_id, "prefix_key_id"),
        }
        work_key = stable_digest(work_identity, prefix="work_")
        return cls(
            candidate_id=stable_digest(
                {
                    "node_id": _string(node_id, "node_id"),
                    "payload_ref": _string(payload_ref, "payload_ref"),
                    "work_key": work_key,
                },
                prefix="candidate_",
            ),
            node_id=node_id,
            work_key=work_key,
            payload_ref=payload_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "node_id": self.node_id,
            "payload_ref": self.payload_ref,
            "work_key": self.work_key,
        }


@dataclass(frozen=True)
class ParallelTask:
    task_id: str
    task_ordinal: int
    logical_worker_slot: int
    candidate: ParallelCandidate
    core_seed: tuple[int, int, int, int]
    python_seed: int
    worker_seed: int
    schema_version: str = PARALLEL_TASK_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "candidate": self.candidate.to_dict(),
                "core_seed": list(self.core_seed),
                "logical_worker_slot": self.logical_worker_slot,
                "python_seed": self.python_seed,
                "schema_version": self.schema_version,
                "task_id": self.task_id,
                "task_ordinal": self.task_ordinal,
                "worker_seed": self.worker_seed,
            }
        )
        return identity


@dataclass(frozen=True)
class ParallelTaskAttempt:
    task: ParallelTask
    attempt: int
    attempt_id: str
    replacement_generation: int
    schema_version: str = PARALLEL_ATTEMPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "attempt": self.attempt,
                "attempt_id": self.attempt_id,
                "core_seed": list(self.task.core_seed),
                "logical_worker_slot": self.task.logical_worker_slot,
                "python_seed": self.task.python_seed,
                "replacement_generation": self.replacement_generation,
                "schema_version": self.schema_version,
                "task_id": self.task.task_id,
                "worker_seed": self.task.worker_seed,
            }
        )


@dataclass(frozen=True)
class ParallelTaskResult:
    task_id: str
    attempt: int
    attempt_id: str
    node_id: str
    score: int | float | None
    result_ref: str | None
    result_digest: str | None
    failure: FailureRecord | None
    logs: tuple[Mapping[str, Any], ...] = ()
    schema_version: str = PARALLEL_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("task_id", "attempt_id", "node_id"):
            _string(getattr(self, name), name)
        _non_negative_integer(self.attempt, "attempt")
        if self.failure is None:
            _finite_number(self.score, "score")
            _string(self.result_ref, "result_ref")
            _string(self.result_digest, "result_digest")
        else:
            if not isinstance(self.failure, FailureRecord):
                raise ValueError("failure must be a FailureRecord or None")
            if (
                self.score is not None
                or self.result_ref is not None
                or self.result_digest is not None
            ):
                raise ValueError(
                    "failed result must not have score or result reference"
                )
        if not isinstance(self.logs, tuple):
            raise ValueError("logs must be a tuple")
        for expected, raw_log in enumerate(self.logs):
            if not isinstance(raw_log, Mapping):
                raise ValueError("each log record must be a mapping")
            if raw_log.get("local_sequence") != expected:
                raise ValueError("log local_sequence must be contiguous from 0")
            _string(raw_log.get("event_type"), "log.event_type")
            if not isinstance(raw_log.get("payload"), Mapping):
                raise ValueError("log.payload must be a mapping")
        if self.schema_version != PARALLEL_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported parallel result schema")

    @property
    def status(self) -> ParallelResultStatus:
        if self.failure is None:
            return ParallelResultStatus.SUCCESS
        if self.failure.retryable:
            return ParallelResultStatus.RETRYABLE_FAILURE
        return ParallelResultStatus.PERMANENT_FAILURE

    @property
    def failure_category(self) -> str | None:
        return self.failure.category if self.failure is not None else None

    @property
    def retryable(self) -> bool:
        return self.failure.retryable if self.failure is not None else False

    @classmethod
    def success(
        cls,
        attempt: ParallelTaskAttempt,
        *,
        score: int | float,
        result_ref: str,
        result_digest: str,
        logs: tuple[Mapping[str, Any], ...] = (),
    ) -> "ParallelTaskResult":
        return cls(
            task_id=attempt.task.task_id,
            attempt=attempt.attempt,
            attempt_id=attempt.attempt_id,
            node_id=attempt.task.candidate.node_id,
            score=score,
            result_ref=result_ref,
            result_digest=result_digest,
            failure=None,
            logs=logs,
        )

    @classmethod
    def from_failure(
        cls,
        attempt: ParallelTaskAttempt,
        *,
        failure: FailureRecord,
        logs: tuple[Mapping[str, Any], ...] = (),
    ) -> "ParallelTaskResult":
        return cls(
            task_id=attempt.task.task_id,
            attempt=attempt.attempt,
            attempt_id=attempt.attempt_id,
            node_id=attempt.task.candidate.node_id,
            score=None,
            result_ref=None,
            result_digest=None,
            failure=failure,
            logs=logs,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ParallelTaskResult":
        if not isinstance(value, Mapping):
            raise ValueError("parallel task result must be a mapping")
        schema_version = value.get("schema_version")
        if schema_version == LEGACY_PARALLEL_RESULT_SCHEMA_VERSION:
            return cls._from_v1_dict(value)
        if schema_version != PARALLEL_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported parallel result schema")
        required = {
            "attempt",
            "attempt_id",
            "failure",
            "logs",
            "node_id",
            "result_digest",
            "result_id",
            "result_ref",
            "schema_version",
            "score",
            "status",
            "task_id",
        }
        if set(value) != required:
            raise ValueError(
                "parallel result v2 fields must be exactly "
                + repr(sorted(required))
            )
        raw_failure = value["failure"]
        failure = (
            FailureRecord.from_dict(raw_failure)
            if isinstance(raw_failure, Mapping)
            else None
        )
        if raw_failure is not None and failure is None:
            raise ValueError("parallel result failure must be a mapping or None")
        raw_logs = value["logs"]
        if not isinstance(raw_logs, list):
            raise ValueError("parallel result logs must be a list")
        result = cls(
            task_id=value["task_id"],
            attempt=value["attempt"],
            attempt_id=value["attempt_id"],
            node_id=value["node_id"],
            score=value["score"],
            result_ref=value["result_ref"],
            result_digest=value["result_digest"],
            failure=failure,
            logs=tuple(raw_logs),
        )
        try:
            stored_status = ParallelResultStatus(value["status"])
        except (TypeError, ValueError) as error:
            raise ValueError("parallel result status is invalid") from error
        if stored_status != result.status:
            raise ValueError("parallel result status does not match failure")
        if result.to_dict() != to_canonical_data(value):
            raise ValueError("parallel result v2 is not canonical")
        return result

    @classmethod
    def _from_v1_dict(cls, value: Mapping[str, Any]) -> "ParallelTaskResult":
        required = {
            "attempt",
            "attempt_id",
            "failure_category",
            "logs",
            "node_id",
            "result_digest",
            "result_id",
            "result_ref",
            "schema_version",
            "score",
            "status",
            "task_id",
        }
        if set(value) != required:
            raise ValueError(
                "parallel result v1 fields must be exactly "
                + repr(sorted(required))
            )
        identity = to_canonical_data(
            {key: value[key] for key in required if key != "result_id"}
        )
        expected_id = stable_digest(identity, prefix="taskresult_")
        if value["result_id"] != expected_id:
            raise ValueError("parallel result v1 result_id does not match content")
        try:
            stored_status = ParallelResultStatus(value["status"])
        except (TypeError, ValueError) as error:
            raise ValueError("parallel result v1 status is invalid") from error
        raw_logs = value["logs"]
        if not isinstance(raw_logs, list):
            raise ValueError("parallel result v1 logs must be a list")
        if stored_status == ParallelResultStatus.SUCCESS:
            if value["failure_category"] is not None:
                raise ValueError("successful v1 result must not have failure_category")
            failure = None
        else:
            category = _string(value["failure_category"], "failure_category")
            retryable = stored_status == ParallelResultStatus.RETRYABLE_FAILURE
            failure = FailureRecord(
                category=category,
                disposition=FailureDisposition.PATH_FAILURE,
                recovery=(
                    RecoveryAction.REPLACE_WORKER
                    if retryable
                    else RecoveryAction.STOP_PATH
                ),
                retryable=retryable,
                message=f"migrated v1 parallel failure: {category}",
                context={
                    "inferred_disposition": FailureDisposition.PATH_FAILURE.value,
                    "inferred_recovery": (
                        RecoveryAction.REPLACE_WORKER.value
                        if retryable
                        else RecoveryAction.STOP_PATH.value
                    ),
                    "source_schema_version": (
                        LEGACY_PARALLEL_RESULT_SCHEMA_VERSION
                    ),
                    "source_status": stored_status.value,
                },
            )
        result = cls(
            task_id=value["task_id"],
            attempt=value["attempt"],
            attempt_id=value["attempt_id"],
            node_id=value["node_id"],
            score=value["score"],
            result_ref=value["result_ref"],
            result_digest=value["result_digest"],
            failure=failure,
            logs=tuple(raw_logs),
        )
        if result.status != stored_status:
            raise ValueError("parallel result v1 status is inconsistent")
        return result

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "attempt": self.attempt,
                "attempt_id": self.attempt_id,
                "failure": self.failure.to_dict() if self.failure else None,
                "logs": list(self.logs),
                "node_id": self.node_id,
                "result_digest": self.result_digest,
                "result_ref": self.result_ref,
                "schema_version": self.schema_version,
                "score": self.score,
                "status": self.status.value,
                "task_id": self.task_id,
            }
        )
        return {**identity, "result_id": stable_digest(identity, prefix="taskresult_")}


@dataclass(frozen=True)
class ParallelExecutionPlan:
    experiment_id: str
    run_id: str
    policy: ParallelSearchPolicy
    tasks: tuple[ParallelTask, ...]
    duplicates: tuple[Mapping[str, Any], ...]
    schema_version: str = PARALLEL_SEARCH_PLAN_SCHEMA_VERSION

    @classmethod
    def build(
        cls,
        *,
        experiment_id: str,
        run_id: str,
        policy: ParallelSearchPolicy,
        candidates: Sequence[ParallelCandidate],
    ) -> "ParallelExecutionPlan":
        experiment_id = _string(experiment_id, "experiment_id")
        run_id = _string(run_id, "run_id")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise ValueError("candidates must be a sequence")
        by_work_key: dict[str, list[ParallelCandidate]] = {}
        for candidate in candidates:
            if not isinstance(candidate, ParallelCandidate):
                raise ValueError("candidates must contain ParallelCandidate")
            by_work_key.setdefault(candidate.work_key, []).append(candidate)
        selected: list[ParallelCandidate] = []
        duplicates: list[dict[str, Any]] = []
        for work_key in sorted(by_work_key):
            grouped = sorted(by_work_key[work_key], key=lambda item: item.candidate_id)
            node_ids = {candidate.node_id for candidate in grouped}
            if len(node_ids) != 1:
                raise ValueError(
                    "duplicate work_key candidates must reference the same node_id"
                )
            kept = grouped[0]
            selected.append(kept)
            for duplicate in grouped[1:]:
                duplicates.append(
                    {
                        "dropped_candidate_id": duplicate.candidate_id,
                        "kept_candidate_id": kept.candidate_id,
                        "work_key": work_key,
                    }
                )
        tasks: list[ParallelTask] = []
        for ordinal, candidate in enumerate(selected):
            task_id = stable_digest(
                {
                    "experiment_id": experiment_id,
                    "node_id": candidate.node_id,
                    "work_key": candidate.work_key,
                },
                prefix="task_",
            )
            slot = ordinal % policy.pool_size
            task_seed = _seed_words(policy.base_seed, "task", task_id)
            tasks.append(
                ParallelTask(
                    task_id=task_id,
                    task_ordinal=ordinal,
                    logical_worker_slot=slot,
                    candidate=candidate,
                    core_seed=task_seed,
                    python_seed=_seed_word(
                        {
                            "base_seed": policy.base_seed,
                            "namespace": "python_task",
                            "task_id": task_id,
                        }
                    ),
                    worker_seed=_seed_word(
                        {
                            "base_seed": policy.base_seed,
                            "experiment_id": experiment_id,
                            "logical_worker_slot": slot,
                            "namespace": "logical_worker",
                        }
                    ),
                )
            )
        return cls(
            experiment_id=experiment_id,
            run_id=run_id,
            policy=policy,
            tasks=tuple(tasks),
            duplicates=tuple(duplicates),
        )

    @property
    def plan_id(self) -> str:
        return str(self.to_dict()["plan_id"])

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "duplicates": list(self.duplicates),
                "experiment_id": self.experiment_id,
                "policy": self.policy.to_dict(),
                "run_id": self.run_id,
                "schema_version": self.schema_version,
                "tasks": [task.to_dict() for task in self.tasks],
            }
        )
        return {**identity, "plan_id": stable_digest(identity, prefix="plan_")}

    def task(self, task_id: str) -> ParallelTask:
        task = next(
            (task for task in self.tasks if task.task_id == task_id),
            None,
        )
        if task is None:
            raise ValueError(f"unknown task_id {task_id!r}")
        return task

    def attempt(self, task_id: str, attempt: int = 0) -> ParallelTaskAttempt:
        task = self.task(task_id)
        attempt = _non_negative_integer(attempt, "attempt")
        if attempt > self.policy.max_retries:
            raise ValueError("attempt exceeds max_retries")
        attempt_id = stable_digest(
            {
                "attempt": attempt,
                "run_id": self.run_id,
                "task_id": task.task_id,
            },
            prefix="attempt_",
        )
        return ParallelTaskAttempt(
            task=task,
            attempt=attempt,
            attempt_id=attempt_id,
            replacement_generation=attempt,
        )

    def aggregate(
        self, results: Sequence[ParallelTaskResult]
    ) -> dict[str, Any]:
        if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
            raise ValueError("results must be a sequence")
        grouped: dict[str, dict[int, ParallelTaskResult]] = {
            task.task_id: {} for task in self.tasks
        }
        for result in results:
            if not isinstance(result, ParallelTaskResult):
                raise ValueError("results must contain ParallelTaskResult")
            if (
                result.failure is not None
                and result.failure.disposition
                == FailureDisposition.EXPERIMENT_FAILURE
            ):
                raise FailureRecordError(result.failure)
            task = self.task(result.task_id)
            expected_attempt = self.attempt(task.task_id, result.attempt)
            if result.attempt_id != expected_attempt.attempt_id:
                raise ValueError("result attempt_id does not match plan")
            if result.node_id != task.candidate.node_id:
                raise ValueError("result node_id does not match task")
            if result.attempt in grouped[task.task_id]:
                raise ValueError("duplicate result for task attempt")
            grouped[task.task_id][result.attempt] = result

        outcomes: list[dict[str, Any]] = []
        merged_logs: list[dict[str, Any]] = []
        successful: list[tuple[ParallelTask, ParallelTaskResult]] = []
        for task in self.tasks:
            attempts = grouped[task.task_id]
            ordered_attempts = [attempts[index] for index in sorted(attempts)]
            if ordered_attempts and [item.attempt for item in ordered_attempts] != list(
                range(len(ordered_attempts))
            ):
                raise ValueError("task result attempts must be contiguous from 0")
            for index, result in enumerate(ordered_attempts[:-1]):
                if result.status != ParallelResultStatus.RETRYABLE_FAILURE:
                    raise ValueError("results must stop after success or permanent failure")
            last = ordered_attempts[-1] if ordered_attempts else None
            if last is None:
                status = ParallelOutcomeStatus.PENDING_INITIAL
            elif last.status == ParallelResultStatus.SUCCESS:
                status = ParallelOutcomeStatus.SUCCESS
                successful.append((task, last))
            elif last.status == ParallelResultStatus.PERMANENT_FAILURE:
                status = ParallelOutcomeStatus.FAILED_PERMANENT
            elif last.attempt < self.policy.max_retries:
                status = ParallelOutcomeStatus.PENDING_RETRY
            else:
                status = ParallelOutcomeStatus.FAILED_RETRY_EXHAUSTED
            for result in ordered_attempts:
                for raw_log in result.logs:
                    merged_logs.append(
                        to_canonical_data(
                            {
                                "attempt": result.attempt,
                                "event_type": raw_log["event_type"],
                                "local_sequence": raw_log["local_sequence"],
                                "logical_worker_slot": task.logical_worker_slot,
                                "payload": raw_log["payload"],
                                "task_id": task.task_id,
                                "task_ordinal": task.task_ordinal,
                            }
                        )
                    )
            attempt_history = [
                to_canonical_data(
                    {
                        "attempt": result.attempt,
                        "attempt_id": result.attempt_id,
                        "failure": (
                            result.failure.to_dict()
                            if result.failure is not None
                            else None
                        ),
                        "result_id": result.to_dict()["result_id"],
                        "status": result.status.value,
                    }
                )
                for result in ordered_attempts
            ]
            terminal_failure = (
                last.failure.to_dict()
                if last is not None and last.failure is not None
                else None
            )
            outcomes.append(
                to_canonical_data(
                    {
                        "attempt_count": len(ordered_attempts),
                        "attempt_history": attempt_history,
                        "failure": terminal_failure,
                        "node_id": task.candidate.node_id,
                        "result_digest": (
                            last.result_digest
                            if last is not None
                            and last.status == ParallelResultStatus.SUCCESS
                            else None
                        ),
                        "result_ref": (
                            last.result_ref
                            if last is not None
                            and last.status == ParallelResultStatus.SUCCESS
                            else None
                        ),
                        "score": (
                            last.score
                            if last is not None
                            and last.status == ParallelResultStatus.SUCCESS
                            else None
                        ),
                        "status": status.value,
                        "task_id": task.task_id,
                        "task_ordinal": task.task_ordinal,
                    }
                )
            )
        best = (
            min(
                successful,
                key=lambda item: (
                    -float(item[1].score),
                    item[0].task_ordinal,
                    item[0].candidate.node_id,
                ),
            )
            if successful
            else None
        )
        summary = to_canonical_data(
            {
                "best_node_id": best[0].candidate.node_id if best else None,
                "best_task_id": best[0].task_id if best else None,
                "failed": sum(
                    outcome["status"]
                    in {
                        ParallelOutcomeStatus.FAILED_PERMANENT.value,
                        ParallelOutcomeStatus.FAILED_RETRY_EXHAUSTED.value,
                    }
                    for outcome in outcomes
                ),
                "pending": sum(
                    outcome["status"]
                    in {
                        ParallelOutcomeStatus.PENDING_INITIAL.value,
                        ParallelOutcomeStatus.PENDING_RETRY.value,
                    }
                    for outcome in outcomes
                ),
                "success": len(successful),
                "total_score": math.fsum(
                    float(result.score) for _, result in successful
                ),
            }
        )
        semantic_logs = [
            {key: value for key, value in log.items() if key != "logical_worker_slot"}
            for log in merged_logs
        ]
        semantic_identity = to_canonical_data(
            {
                "logs": semantic_logs,
                "outcomes": outcomes,
                "schema_version": PARALLEL_AGGREGATE_SCHEMA_VERSION,
                "summary": summary,
            }
        )
        semantic_result = {
            **semantic_identity,
            "semantic_result_id": stable_digest(
                semantic_identity, prefix="parallelresult_"
            ),
        }
        execution_identity = to_canonical_data(
            {
                "logs": merged_logs,
                "outcomes": outcomes,
                "plan_id": self.plan_id,
                "schema_version": PARALLEL_AGGREGATE_SCHEMA_VERSION,
                "semantic_result_id": semantic_result["semantic_result_id"],
                "summary": summary,
            }
        )
        return {
            **execution_identity,
            "aggregate_id": semantic_result["semantic_result_id"],
            "execution_id": stable_digest(
                execution_identity, prefix="parallelexec_"
            ),
            "semantic": semantic_result,
        }
