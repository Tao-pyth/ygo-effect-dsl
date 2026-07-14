from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.action import Action, action_from_dict
from ygo_effect_dsl.engine.canonical import canonical_json
from ygo_effect_dsl.engine.search import SearchFrontier
from ygo_effect_dsl.prototype.real_core import REAL_CORE_FRONTIER_SCHEMA_VERSION
from ygo_effect_dsl.prototype.real_core import RealCoreVerificationResult
from ygo_effect_dsl.runtime_imports import current_checkout_environment


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

    def replay(
        self,
        experiment: Mapping[str, Any],
        action_prefix: Sequence[Action],
    ) -> SearchFrontier:
        document = self._invoke(experiment, action_prefix)
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
        can_stop = bool(legal_stop.get("can_stop")) and route is not None
        request = dict(document["request"])
        request["interruption_taxonomy"] = document.get(
            "interruption_taxonomy", []
        )
        return SearchFrontier(
            state_id=str(document["state_id"]),
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
        last_diagnostic = ""
        for attempt in range(self.max_retries + 1):
            self.worker_invocations += 1
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
            try:
                stdout, stderr = process.communicate(
                    input=worker_input, timeout=self.timeout_seconds
                )
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                last_diagnostic = (
                    f"real-core frontier worker timed out after {self.timeout_seconds}s"
                )
                retryable = True
            else:
                retryable = process.returncode < 0
                last_diagnostic = stderr.strip() or stdout.strip()
                if process.returncode == 0:
                    try:
                        document = json.loads(stdout)
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            "real-core frontier worker emitted invalid JSON"
                        ) from exc
                    if not isinstance(document, Mapping):
                        raise ValueError("real-core frontier worker output must be a mapping")
                    return document
                try:
                    failure_envelope = json.loads(stdout)
                except json.JSONDecodeError:
                    failure_envelope = None
                if isinstance(failure_envelope, Mapping):
                    failure = failure_envelope.get("failure")
                    if isinstance(failure, Mapping):
                        retryable = bool(failure.get("retryable"))
                        last_diagnostic = str(failure.get("message", last_diagnostic))
            if attempt < self.max_retries and retryable:
                self.worker_retries += 1
                continue
            break
        raise RuntimeError(last_diagnostic or "real-core frontier worker failed")


def verify_general_search_route(
    route_document: Mapping[str, Any],
    *,
    external_root: str | Path | None = None,
    experiment_path: str | Path | None = None,
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
