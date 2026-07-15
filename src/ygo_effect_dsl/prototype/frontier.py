from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.action import Action, action_from_dict
from ygo_effect_dsl.engine.bridge.ocgcore.errors import (
    OcgcoreWorkerCrashError,
    OcgcoreWorkerProtocolError,
    OcgcoreWorkerTimeoutError,
)
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    FailureRecord,
    FailureRecordError,
    RecoveryAction,
    classify_failure,
)
from ygo_effect_dsl.engine.search import (
    MultiTurnLifecycleDecision,
    SearchFrontier,
)
from ygo_effect_dsl.prototype.real_core import (
    REAL_CORE_FRONTIER_SCHEMA_VERSION,
    WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION,
    RealCoreVerificationResult,
)
from ygo_effect_dsl.runtime_imports import current_checkout_environment


REAL_CORE_FRONTIER_ATTEMPT_SCHEMA_VERSION = "real-core-frontier-worker-attempt-v1"
REAL_CORE_FRONTIER_FAILURE_SCHEMA_VERSION = "real-core-frontier-worker-failure-v1"


class RealCoreFrontierWorkerError(FailureRecordError):
    """Carries exhausted frontier worker attempts without raw worker output."""

    def __init__(
        self,
        failure: FailureRecord,
        *,
        attempts: Sequence[Mapping[str, Any]],
        retry_exhausted: bool,
    ) -> None:
        canonical_attempts = tuple(to_canonical_data(attempt) for attempt in attempts)
        attempt_ids = [str(attempt["attempt_id"]) for attempt in canonical_attempts]
        contextual_failure = FailureRecord(
            category=failure.category,
            disposition=failure.disposition,
            recovery=failure.recovery,
            retryable=failure.retryable,
            message=failure.message,
            exception_type=failure.exception_type,
            context={
                **failure.context,
                "attempt_count": len(canonical_attempts),
                "attempt_ids": attempt_ids,
                "retry_exhausted": retry_exhausted,
            },
        )
        self.attempts = canonical_attempts
        self.retry_exhausted = retry_exhausted
        self.quarantined_attempt_ids = tuple(
            str(attempt["attempt_id"])
            for attempt in canonical_attempts
            if attempt.get("quarantined") is True
        )
        super().__init__(contextual_failure)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": list(self.attempts),
            "failure": self.failure.to_dict(),
            "quarantined_attempt_ids": list(self.quarantined_attempt_ids),
            "retry_exhausted": self.retry_exhausted,
            "schema_version": REAL_CORE_FRONTIER_FAILURE_SCHEMA_VERSION,
        }


def _ipc_failure(message: str) -> FailureRecord:
    return FailureRecord(
        category="worker_ipc",
        disposition=FailureDisposition.PATH_FAILURE,
        recovery=RecoveryAction.REPLACE_WORKER,
        retryable=True,
        message=message,
        exception_type="OSError",
    )


def _process_terminated(process: Any) -> bool:
    poll = getattr(process, "poll", None)
    if callable(poll):
        return poll() is not None
    return getattr(process, "returncode", None) is not None


@dataclass
class RealCoreFrontierAdapter:
    external_root: str | Path | None = None
    experiment_path: str | Path | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 1

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ValueError("max_retries must be an integer >= 0")
        self.worker_invocations = 0
        self.worker_retries = 0
        self.worker_attempts: list[dict[str, Any]] = []
        self.quarantined_attempt_ids: list[str] = []
        self._last_replay_attempts: list[Mapping[str, Any]] = []
        self._last_attempt_retained = False

    def replay(
        self,
        experiment: Mapping[str, Any],
        action_prefix: Sequence[Action],
    ) -> SearchFrontier:
        document = self._invoke(experiment, action_prefix)
        try:
            if document.get("schema_version") != REAL_CORE_FRONTIER_SCHEMA_VERSION:
                raise ValueError("real-core worker returned an unsupported frontier schema")
            raw_actions = document.get("actions")
            if not isinstance(raw_actions, list):
                raise ValueError("real-core frontier actions must be a list")
            actions = tuple(action_from_dict(value) for value in raw_actions)
            legal_stop = document.get("legal_stop")
            if not isinstance(legal_stop, Mapping):
                raise ValueError("real-core frontier is missing legal_stop")
            route = document.get("route_document")
            if route is not None and not isinstance(route, Mapping):
                raise ValueError("real-core route_document must be a mapping or null")
            state_completeness = document.get("state_completeness")
            if not isinstance(state_completeness, str):
                raise ValueError("real-core frontier is missing state_completeness")
            can_stop = bool(legal_stop.get("can_stop")) and route is not None
            request = dict(document["request"])
            request["interruption_taxonomy"] = document.get(
                "interruption_taxonomy", []
            )
            request["interruption_composition"] = document.get(
                "interruption_composition"
            )
            request["interruption_opportunities"] = document.get(
                "interruption_opportunities"
            )
            raw_turn_lifecycle = document.get("turn_lifecycle")
            if not isinstance(raw_turn_lifecycle, Mapping):
                raise ValueError("real-core frontier is missing turn_lifecycle")
            request["turn_lifecycle"] = MultiTurnLifecycleDecision.from_dict(
                raw_turn_lifecycle
            ).to_dict()
            return SearchFrontier(
                state_id=str(document["state_id"]),
                state_completeness=state_completeness,
                request=request,
                actions=actions,
                score=document["score"],
                peak_score=document["peak_score"],
                success=bool(document["success"]),
                legal_stop=can_stop,
                legal_stop_reason=str(legal_stop.get("reason", "unknown")),
                route_document=route if can_stop else None,
                replay_count=int(document.get("replay_count", 1)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if not self._last_replay_attempts:
                raise
            failure = classify_failure(OcgcoreWorkerProtocolError(str(exc)))
            self._mark_last_attempt_failed(failure)
            raise RealCoreFrontierWorkerError(
                failure,
                attempts=self._last_replay_attempts,
                retry_exhausted=False,
            ) from None

    def _invoke(
        self,
        experiment: Mapping[str, Any],
        action_prefix: Sequence[Action],
    ) -> Mapping[str, Any]:
        command = [
            sys.executable,
            "-m",
            "ygo_effect_dsl.prototype._real_core_frontier_worker",
        ]
        if self.external_root is not None:
            command.extend(["--external-root", str(self.external_root)])
        if self.experiment_path is not None:
            command.extend(["--experiment-path", str(self.experiment_path)])
        worker_input = canonical_json(
            {
                "action_prefix": [action.to_dict() for action in action_prefix],
                "experiment": experiment,
            }
        )
        worker_input_digest = stable_digest(worker_input, prefix="workerinput_")
        replay_attempts: list[Mapping[str, Any]] = []
        self._last_replay_attempts = replay_attempts
        self._last_attempt_retained = False
        last_failure: FailureRecord | None = None
        for attempt in range(self.max_retries + 1):
            self.worker_invocations += 1
            invocation_index = self.worker_invocations
            attempt_id = stable_digest(
                {
                    "attempt_index": attempt,
                    "worker_input_digest": worker_input_digest,
                },
                prefix="frontierattempt_",
            )
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=current_checkout_environment(),
                )
            except OSError:
                failure = _ipc_failure("real-core frontier worker could not be started")
                record = self._attempt_record(
                    attempt_id=attempt_id,
                    attempt_index=attempt,
                    invocation_index=invocation_index,
                    worker_input_digest=worker_input_digest,
                    process=None,
                    stdout="",
                    stderr="",
                    failure=failure,
                )
                self._append_attempt(record, replay_attempts)
                last_failure = failure
                if attempt < self.max_retries:
                    self.worker_retries += 1
                    continue
                break
            try:
                stdout, stderr = process.communicate(
                    input=worker_input, timeout=self.timeout_seconds
                )
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    stdout, stderr = process.communicate(timeout=1.0)
                except (OSError, subprocess.TimeoutExpired):
                    stdout, stderr = "", ""
                failure = classify_failure(
                    OcgcoreWorkerTimeoutError(self.timeout_seconds)
                )
                record = self._attempt_record(
                    attempt_id=attempt_id,
                    attempt_index=attempt,
                    invocation_index=invocation_index,
                    worker_input_digest=worker_input_digest,
                    process=process,
                    stdout=stdout,
                    stderr=stderr,
                    failure=failure,
                )
                self._append_attempt(record, replay_attempts)
                last_failure = failure
            except OSError:
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.communicate(timeout=1.0)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                failure = _ipc_failure(
                    "real-core frontier worker IPC failed during communication"
                )
                record = self._attempt_record(
                    attempt_id=attempt_id,
                    attempt_index=attempt,
                    invocation_index=invocation_index,
                    worker_input_digest=worker_input_digest,
                    process=process,
                    stdout="",
                    stderr="",
                    failure=failure,
                )
                self._append_attempt(record, replay_attempts)
                last_failure = failure
            else:
                if process.returncode == 0:
                    try:
                        document = json.loads(stdout)
                        if not isinstance(document, Mapping):
                            raise ValueError("worker output must be a mapping")
                    except (json.JSONDecodeError, ValueError) as exc:
                        failure = classify_failure(
                            OcgcoreWorkerProtocolError(str(exc))
                        )
                        record = self._attempt_record(
                            attempt_id=attempt_id,
                            attempt_index=attempt,
                            invocation_index=invocation_index,
                            worker_input_digest=worker_input_digest,
                            process=process,
                            stdout=stdout,
                            stderr=stderr,
                            failure=failure,
                        )
                        self._append_attempt(record, replay_attempts)
                        raise RealCoreFrontierWorkerError(
                            failure,
                            attempts=replay_attempts,
                            retry_exhausted=False,
                        ) from None
                    record = self._attempt_record(
                        attempt_id=attempt_id,
                        attempt_index=attempt,
                        invocation_index=invocation_index,
                        worker_input_digest=worker_input_digest,
                        process=process,
                        stdout=stdout,
                        stderr=stderr,
                        failure=None,
                    )
                    self._append_attempt(
                        record,
                        replay_attempts,
                        retain_global=bool(replay_attempts),
                    )
                    return document
                failure = self._failure_from_worker_output(
                    returncode=int(process.returncode),
                    stdout=stdout,
                )
                record = self._attempt_record(
                    attempt_id=attempt_id,
                    attempt_index=attempt,
                    invocation_index=invocation_index,
                    worker_input_digest=worker_input_digest,
                    process=process,
                    stdout=stdout,
                    stderr=stderr,
                    failure=failure,
                )
                self._append_attempt(record, replay_attempts)
                last_failure = failure
            assert last_failure is not None
            if attempt < self.max_retries and last_failure.retryable:
                self.worker_retries += 1
                continue
            break
        assert last_failure is not None
        retry_exhausted = (
            last_failure.retryable and len(replay_attempts) == self.max_retries + 1
        )
        raise RealCoreFrontierWorkerError(
            last_failure,
            attempts=replay_attempts,
            retry_exhausted=retry_exhausted,
        )

    def _failure_from_worker_output(
        self, *, returncode: int, stdout: str
    ) -> FailureRecord:
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            envelope = None
        if isinstance(envelope, Mapping) and (
            "failure" in envelope
            or envelope.get("schema_version") == WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION
        ):
            try:
                if set(envelope) != {"failure", "schema_version", "status"}:
                    raise ValueError("worker failure envelope has unexpected fields")
                if (
                    envelope["schema_version"]
                    != WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION
                    or envelope["status"] != "failure"
                    or not isinstance(envelope["failure"], Mapping)
                ):
                    raise ValueError("worker failure envelope is malformed")
                return FailureRecord.from_dict(envelope["failure"])
            except (KeyError, TypeError, ValueError) as exc:
                return classify_failure(OcgcoreWorkerProtocolError(str(exc)))
        return classify_failure(
            OcgcoreWorkerCrashError(returncode, "diagnostic digests recorded")
        )

    def _attempt_record(
        self,
        *,
        attempt_id: str,
        attempt_index: int,
        invocation_index: int,
        worker_input_digest: str,
        process: Any | None,
        stdout: str,
        stderr: str,
        failure: FailureRecord | None,
    ) -> dict[str, Any]:
        return to_canonical_data(
            {
                "attempt_id": attempt_id,
                "attempt_index": attempt_index,
                "category": failure.category if failure is not None else None,
                "invocation_index": invocation_index,
                "process_id": getattr(process, "pid", None),
                "quarantined": failure is not None,
                "retryable": failure.retryable if failure is not None else False,
                "returncode": getattr(process, "returncode", None),
                "schema_version": REAL_CORE_FRONTIER_ATTEMPT_SCHEMA_VERSION,
                "status": "failure" if failure is not None else "success",
                "stderr_digest": stable_digest(stderr, prefix="workerstderr_"),
                "stdout_digest": stable_digest(stdout, prefix="workerstdout_"),
                "terminated": process is None or _process_terminated(process),
                "worker_input_digest": worker_input_digest,
            }
        )

    def _append_attempt(
        self,
        record: Mapping[str, Any],
        replay_attempts: list[Mapping[str, Any]],
        *,
        retain_global: bool = True,
    ) -> None:
        canonical = to_canonical_data(record)
        if retain_global:
            self.worker_attempts.append(canonical)
        replay_attempts.append(canonical)
        self._last_attempt_retained = retain_global
        if canonical["quarantined"]:
            self.quarantined_attempt_ids.append(str(canonical["attempt_id"]))

    def _mark_last_attempt_failed(self, failure: FailureRecord) -> None:
        previous = dict(self._last_replay_attempts[-1])
        previous.update(
            {
                "category": failure.category,
                "quarantined": True,
                "retryable": failure.retryable,
                "status": "failure",
            }
        )
        canonical = to_canonical_data(previous)
        self._last_replay_attempts[-1] = canonical
        if self._last_attempt_retained:
            self.worker_attempts[-1] = canonical
        else:
            self.worker_attempts.append(canonical)
            self._last_attempt_retained = True
        attempt_id = str(canonical["attempt_id"])
        if attempt_id not in self.quarantined_attempt_ids:
            self.quarantined_attempt_ids.append(attempt_id)


def verify_general_search_route(
    route_document: Mapping[str, Any],
    *,
    external_root: str | Path | None = None,
    experiment_path: str | Path | None = None,
    timeout_seconds: float = 30.0,
) -> RealCoreVerificationResult:
    experiment = route_document.get("experiment")
    replay = route_document.get("replay")
    if not isinstance(experiment, Mapping) or not isinstance(replay, Mapping):
        raise ValueError("General Search Route is missing experiment or replay")
    raw_events = replay.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise ValueError("General Search Route must contain replay events")
    actions = []
    for index, event in enumerate(raw_events):
        if not isinstance(event, Mapping) or not isinstance(event.get("action"), Mapping):
            raise ValueError(f"General Search replay event {index} has no Action")
        actions.append(action_from_dict(event["action"]))
    frontier = RealCoreFrontierAdapter(
        external_root=external_root,
        experiment_path=experiment_path,
        timeout_seconds=timeout_seconds,
    ).replay(experiment, actions)
    if not frontier.legal_stop or frontier.route_document is None:
        raise ValueError("fresh Replay did not reach the recorded legal stop")
    if canonical_json(frontier.route_document) != canonical_json(route_document):
        raise ValueError("General Search Route differs from fresh worker Replay")
    terminal = route_document["result"]["terminal_board"]
    return RealCoreVerificationResult(
        route_id=str(route_document["route_id"]),
        event_count=len(raw_events),
        final_state_hash=str(terminal["state_hash"]),
    )
