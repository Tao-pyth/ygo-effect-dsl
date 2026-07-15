from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ygo_effect_dsl.engine.bridge import (
    DecisionRequest,
    InvalidBridgeMessageError,
    InvalidBridgeResponseError,
    UnsupportedBridgeMessageError,
)
from ygo_effect_dsl.engine.bridge.ocgcore.errors import (
    OcgcoreArchitectureError,
    OcgcoreAssetError,
    OcgcoreBridgeError,
    OcgcoreLuaError,
    OcgcoreTimeoutError,
    OcgcoreVersionMismatchError,
    OcgcoreWorkerCrashError,
    OcgcoreWorkerProtocolError,
    OcgcoreWorkerTimeoutError,
)
from ygo_effect_dsl.engine.canonical import to_canonical_data
from ygo_effect_dsl.engine.interruption.adapter import (
    InterruptionCandidatePolicyError,
)
from ygo_effect_dsl.engine.interruption.composition import (
    MultiInterruptionRuntimeError,
)
from ygo_effect_dsl.engine.replay import (
    ReplayEnvironmentMismatchError,
    ReplayFormatError,
    ReplayManifestIncompleteError,
    ReplaySignatureMismatchError,
)


class FailureDisposition(str, Enum):
    LEGAL_DEAD_END = "legal_dead_end"
    PATH_FAILURE = "path_failure"
    EXPERIMENT_FAILURE = "experiment_failure"


class RecoveryAction(str, Enum):
    NONE = "none"
    STOP_PATH = "stop_path"
    REPLACE_WORKER = "replace_worker"
    ABORT_EXPERIMENT = "abort_experiment"


@dataclass(frozen=True)
class FailureRecord:
    category: str
    disposition: FailureDisposition
    recovery: RecoveryAction
    retryable: bool
    message: str
    exception_type: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.category, str) or not self.category:
            raise ValueError("FailureRecord category must be a non-empty string")
        if not isinstance(self.disposition, FailureDisposition):
            object.__setattr__(
                self, "disposition", FailureDisposition(self.disposition)
            )
        if not isinstance(self.recovery, RecoveryAction):
            object.__setattr__(self, "recovery", RecoveryAction(self.recovery))
        if not isinstance(self.retryable, bool):
            raise ValueError("FailureRecord retryable must be a boolean")
        if not isinstance(self.message, str):
            raise ValueError("FailureRecord message must be a string")
        if self.exception_type is not None and (
            not isinstance(self.exception_type, str) or not self.exception_type
        ):
            raise ValueError(
                "FailureRecord exception_type must be a non-empty string or None"
            )
        if not isinstance(self.context, Mapping):
            raise ValueError("FailureRecord context must be a mapping")

        allowed_recoveries = {
            FailureDisposition.LEGAL_DEAD_END: {RecoveryAction.NONE},
            FailureDisposition.PATH_FAILURE: {
                RecoveryAction.STOP_PATH,
                RecoveryAction.REPLACE_WORKER,
            },
            FailureDisposition.EXPERIMENT_FAILURE: {
                RecoveryAction.ABORT_EXPERIMENT
            },
        }
        if self.recovery not in allowed_recoveries[self.disposition]:
            raise ValueError(
                "FailureRecord recovery is incompatible with disposition"
            )
        if self.retryable and not (
            self.disposition == FailureDisposition.PATH_FAILURE
            and self.recovery == RecoveryAction.REPLACE_WORKER
        ):
            raise ValueError(
                "retryable FailureRecord must be path_failure + replace_worker"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "context": to_canonical_data(self.context),
            "disposition": self.disposition.value,
            "exception_type": self.exception_type,
            "message": self.message,
            "recovery": self.recovery.value,
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FailureRecord":
        if not isinstance(data, Mapping):
            raise ValueError("FailureRecord must be a mapping")
        required = {
            "category",
            "context",
            "disposition",
            "exception_type",
            "message",
            "recovery",
            "retryable",
        }
        if set(data) != required:
            raise ValueError(
                "FailureRecord fields must be exactly " + repr(sorted(required))
            )
        return cls(
            category=data["category"],
            disposition=FailureDisposition(str(data["disposition"])),
            recovery=RecoveryAction(str(data["recovery"])),
            retryable=data["retryable"],
            message=data["message"],
            exception_type=data["exception_type"],
            context=data["context"],
        )


class FailureRecordError(RuntimeError):
    """Carries a classified child-process failure across the worker boundary."""

    def __init__(self, failure: FailureRecord) -> None:
        self.failure = failure
        self.category = failure.category
        self.context = failure.context
        super().__init__(failure.message)


def legal_dead_end(reason: str, *, context: Mapping[str, Any] | None = None) -> FailureRecord:
    return FailureRecord(
        category="legal_dead_end",
        disposition=FailureDisposition.LEGAL_DEAD_END,
        recovery=RecoveryAction.NONE,
        retryable=False,
        message=reason,
        context=dict(context or {}),
    )


def classify_request_outcome(request: DecisionRequest) -> FailureRecord | None:
    if request.candidates:
        return None
    context = {
        "request_signature": request.request_signature,
        "request_type": request.request_type,
    }
    if request.constraints.min_selections == 0 and not request.constraints.required:
        return legal_dead_end("core request has no selectable candidates", context=context)
    return FailureRecord(
        category="invalid_message",
        disposition=FailureDisposition.PATH_FAILURE,
        recovery=RecoveryAction.STOP_PATH,
        retryable=False,
        message="required core request has no selectable candidates",
        context=context,
    )


def _is_runtime_candidate_mismatch(
    error: InterruptionCandidatePolicyError,
) -> bool:
    # CoreInterruptionStep.select() attaches both snapshots; config parsing does not.
    error_context = error.context
    return "request" in error_context and "step" in error_context


def classify_failure(
    error: BaseException, *, context: Mapping[str, Any] | None = None
) -> FailureRecord:
    if isinstance(error, FailureRecordError):
        if not context:
            return error.failure
        return FailureRecord(
            category=error.failure.category,
            disposition=error.failure.disposition,
            recovery=error.failure.recovery,
            retryable=error.failure.retryable,
            message=error.failure.message,
            exception_type=error.failure.exception_type,
            context={**error.failure.context, **context},
        )
    category = str(getattr(error, "category", "internal_error"))
    combined_context = dict(getattr(error, "context", {}))
    combined_context.update(context or {})
    shared = {
        "category": category,
        "message": str(error),
        "exception_type": type(error).__name__,
        "context": combined_context,
    }
    if isinstance(error, InterruptionCandidatePolicyError):
        if _is_runtime_candidate_mismatch(error):
            return FailureRecord(
                **shared,
                disposition=FailureDisposition.PATH_FAILURE,
                recovery=RecoveryAction.STOP_PATH,
                retryable=False,
            )
        return FailureRecord(
            **shared,
            disposition=FailureDisposition.EXPERIMENT_FAILURE,
            recovery=RecoveryAction.ABORT_EXPERIMENT,
            retryable=False,
        )
    if isinstance(error, MultiInterruptionRuntimeError):
        if error.path_failure:
            return FailureRecord(
                **shared,
                disposition=FailureDisposition.PATH_FAILURE,
                recovery=RecoveryAction.STOP_PATH,
                retryable=False,
            )
        return FailureRecord(
            **shared,
            disposition=FailureDisposition.EXPERIMENT_FAILURE,
            recovery=RecoveryAction.ABORT_EXPERIMENT,
            retryable=False,
        )
    if category == "multi_turn_lifecycle":
        if getattr(error, "path_failure", False):
            return FailureRecord(
                **shared,
                disposition=FailureDisposition.PATH_FAILURE,
                recovery=RecoveryAction.STOP_PATH,
                retryable=False,
            )
        return FailureRecord(
            **shared,
            disposition=FailureDisposition.EXPERIMENT_FAILURE,
            recovery=RecoveryAction.ABORT_EXPERIMENT,
            retryable=False,
        )
    if isinstance(
        error,
        (
            OcgcoreWorkerTimeoutError,
            OcgcoreWorkerCrashError,
            OcgcoreTimeoutError,
        ),
    ):
        return FailureRecord(
            **shared,
            disposition=FailureDisposition.PATH_FAILURE,
            recovery=RecoveryAction.REPLACE_WORKER,
            retryable=True,
        )
    if isinstance(error, OcgcoreWorkerProtocolError):
        return FailureRecord(
            **shared,
            disposition=FailureDisposition.PATH_FAILURE,
            recovery=RecoveryAction.REPLACE_WORKER,
            retryable=False,
        )
    if isinstance(
        error,
        (
            OcgcoreArchitectureError,
            OcgcoreVersionMismatchError,
            OcgcoreAssetError,
            OcgcoreLuaError,
            ReplayEnvironmentMismatchError,
            ReplayManifestIncompleteError,
        ),
    ):
        return FailureRecord(
            **shared,
            disposition=FailureDisposition.EXPERIMENT_FAILURE,
            recovery=RecoveryAction.ABORT_EXPERIMENT,
            retryable=False,
        )
    if isinstance(error, (ReplaySignatureMismatchError, ReplayFormatError)):
        return FailureRecord(
            **shared,
            disposition=FailureDisposition.EXPERIMENT_FAILURE,
            recovery=RecoveryAction.ABORT_EXPERIMENT,
            retryable=False,
        )
    if isinstance(
        error,
        (
            InvalidBridgeMessageError,
            InvalidBridgeResponseError,
            UnsupportedBridgeMessageError,
        ),
    ):
        return FailureRecord(
            **shared,
            disposition=FailureDisposition.PATH_FAILURE,
            recovery=RecoveryAction.STOP_PATH,
            retryable=False,
        )
    if isinstance(error, OcgcoreBridgeError):
        return FailureRecord(
            **shared,
            disposition=FailureDisposition.PATH_FAILURE,
            recovery=RecoveryAction.REPLACE_WORKER,
            retryable=False,
        )
    return FailureRecord(
        **shared,
        disposition=FailureDisposition.EXPERIMENT_FAILURE,
        recovery=RecoveryAction.ABORT_EXPERIMENT,
        retryable=False,
    )
