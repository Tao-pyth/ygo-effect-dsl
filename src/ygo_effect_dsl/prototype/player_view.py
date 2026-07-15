from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from ygo_effect_dsl.engine.action import action_from_dict
from ygo_effect_dsl.engine.canonical import canonical_json
from ygo_effect_dsl.engine.replay import assert_valid_player_view_replay
from ygo_effect_dsl.prototype.real_core import (
    PLAYER_VIEW_LINEAGE_SCHEMA_VERSION,
    PLAYER_VIEW_VERIFICATION_SCHEMA_VERSION,
    REAL_CORE_PLAYER_VIEW_RESULT_SCHEMA_VERSION,
    WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION,
)
from ygo_effect_dsl.runtime_imports import current_checkout_environment


@dataclass(frozen=True)
class RealCorePlayerViewResult:
    player_view: Mapping[str, Any]
    verification: Mapping[str, Any]
    private_lineage: Mapping[str, Any]


class RealCorePlayerViewWorkerError(RuntimeError):
    def __init__(self, code: str, *, retry_exhausted: bool) -> None:
        self.code = code
        self.retry_exhausted = retry_exhausted
        super().__init__(f"PlayerView worker failed with {code}")


@dataclass(frozen=True)
class RealCorePlayerViewAdapter:
    external_root: str | Path | None = None
    experiment_path: str | Path | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 1

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ValueError("max_retries must be an integer >= 0")

    def project(
        self,
        source_route: Mapping[str, Any],
        *,
        viewer: int,
    ) -> RealCorePlayerViewResult:
        if viewer not in (0, 1):
            raise ValueError("viewer must be 0 or 1")
        experiment = source_route.get("experiment")
        replay = source_route.get("replay")
        if not isinstance(experiment, Mapping) or not isinstance(replay, Mapping):
            raise ValueError("source Route is missing experiment or replay")
        raw_events = replay.get("events")
        if not isinstance(raw_events, list) or not raw_events:
            raise ValueError("source Route must contain replay events")
        actions = []
        for index, event in enumerate(raw_events):
            if not isinstance(event, Mapping) or not isinstance(
                event.get("action"), Mapping
            ):
                raise ValueError(f"source Route event {index} has no Action")
            actions.append(action_from_dict(event["action"]).to_dict())
        envelope = {
            "action_prefix": actions,
            "document_kind": "player_view",
            "experiment": experiment,
            "source_route": source_route,
            "viewer": viewer,
        }
        document = self._invoke(envelope)
        expected_fields = {
            "player_view",
            "private_lineage",
            "schema_version",
            "verification",
        }
        if set(document) != expected_fields:
            raise RealCorePlayerViewWorkerError(
                "worker_protocol", retry_exhausted=False
            )
        if document.get("schema_version") != REAL_CORE_PLAYER_VIEW_RESULT_SCHEMA_VERSION:
            raise RealCorePlayerViewWorkerError(
                "worker_protocol", retry_exhausted=False
            )
        player_view = document.get("player_view")
        verification = document.get("verification")
        lineage = document.get("private_lineage")
        if not all(isinstance(value, Mapping) for value in (player_view, verification, lineage)):
            raise RealCorePlayerViewWorkerError(
                "worker_protocol", retry_exhausted=False
            )
        assert_valid_player_view_replay(player_view)
        if (
            verification.get("schema_version")
            != PLAYER_VIEW_VERIFICATION_SCHEMA_VERSION
            or verification.get("player_view_id") != player_view.get("player_view_id")
            or verification.get("status") != "verified"
        ):
            raise RealCorePlayerViewWorkerError(
                "worker_protocol", retry_exhausted=False
            )
        if (
            lineage.get("schema_version") != PLAYER_VIEW_LINEAGE_SCHEMA_VERSION
            or lineage.get("player_view_id") != player_view.get("player_view_id")
            or lineage.get("verification_id") != verification.get("verification_id")
        ):
            raise RealCorePlayerViewWorkerError(
                "worker_protocol", retry_exhausted=False
            )
        return RealCorePlayerViewResult(
            player_view=dict(player_view),
            verification=dict(verification),
            private_lineage=dict(lineage),
        )

    def _invoke(self, envelope: Mapping[str, Any]) -> Mapping[str, Any]:
        command = [
            sys.executable,
            "-m",
            "ygo_effect_dsl.prototype._real_core_frontier_worker",
        ]
        if self.external_root is not None:
            command.extend(["--external-root", str(self.external_root)])
        if self.experiment_path is not None:
            command.extend(["--experiment-path", str(self.experiment_path)])
        worker_input = canonical_json(envelope)
        last_code = "worker_crash"
        for attempt in range(self.max_retries + 1):
            try:
                completed = subprocess.run(
                    command,
                    input=worker_input,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=current_checkout_environment(),
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                last_code = "worker_timeout"
                continue
            except OSError:
                last_code = "worker_ipc"
                continue
            if completed.returncode != 0:
                last_code = self._failure_code(completed.stdout)
                continue
            try:
                document = json.loads(completed.stdout)
            except json.JSONDecodeError:
                last_code = "worker_protocol"
                continue
            if isinstance(document, Mapping):
                return document
            last_code = "worker_protocol"
        raise RealCorePlayerViewWorkerError(
            last_code,
            retry_exhausted=self.max_retries > 0,
        )

    @staticmethod
    def _failure_code(stdout: str) -> str:
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            return "worker_crash"
        if not isinstance(envelope, Mapping):
            return "worker_crash"
        if envelope.get("schema_version") != WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION:
            return "worker_protocol"
        failure = envelope.get("failure")
        if not isinstance(failure, Mapping):
            return "worker_protocol"
        category = failure.get("category")
        return str(category) if isinstance(category, str) and category else "worker_failure"
