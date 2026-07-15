from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.bridge import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
    DecisionResponse,
    InvalidBridgeResponseError,
    UnsupportedBridgeMessageError,
    validate_decision_response,
)
from ygo_effect_dsl.engine.bridge.ocgcore import (
    MissingCardDataError,
    OcgcoreTimeoutError,
    OcgcoreVersionMismatchError,
    OcgcoreWorkerCrashError,
    OcgcoreWorkerProtocolError,
    OcgcoreWorkerTimeoutError,
)
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    FailureRecord,
    FailureRecordError,
    RecoveryAction,
    classify_failure,
    classify_request_outcome,
)
from ygo_effect_dsl.engine.interruption import (
    CORE_INTERRUPTION_CANDIDATE_POLICY_SCHEMA_VERSION,
    CoreInterruptionCandidatePolicy,
    CoreInterruptionStep,
    CandidateSelector,
    InterruptionCandidatePolicyError,
    MultiInterruptionRuntimeError,
)
from ygo_effect_dsl.engine.replay import (
    ReplayEnvironmentMismatchError,
    ReplaySignatureMismatchError,
)
from ygo_effect_dsl.prototype import real_core


def test_failure_record_round_trips_across_process_boundary() -> None:
    original = FailureRecord(
        category="interruption_candidate_policy",
        disposition=FailureDisposition.PATH_FAILURE,
        recovery=RecoveryAction.STOP_PATH,
        retryable=False,
        message="candidate disappeared",
        exception_type="InterruptionCandidatePolicyError",
        context={"step": 5},
    )

    restored = FailureRecord.from_dict(original.to_dict())
    assert restored == original
    assert classify_failure(FailureRecordError(restored)) == original


@pytest.mark.parametrize(
    ("disposition", "recovery", "retryable"),
    [
        (
            FailureDisposition.LEGAL_DEAD_END,
            RecoveryAction.STOP_PATH,
            False,
        ),
        (
            FailureDisposition.PATH_FAILURE,
            RecoveryAction.ABORT_EXPERIMENT,
            False,
        ),
        (
            FailureDisposition.PATH_FAILURE,
            RecoveryAction.STOP_PATH,
            True,
        ),
        (
            FailureDisposition.EXPERIMENT_FAILURE,
            RecoveryAction.REPLACE_WORKER,
            False,
        ),
        (
            FailureDisposition.EXPERIMENT_FAILURE,
            RecoveryAction.ABORT_EXPERIMENT,
            True,
        ),
    ],
)
def test_failure_record_rejects_incompatible_recovery_contracts(
    disposition: FailureDisposition,
    recovery: RecoveryAction,
    retryable: bool,
) -> None:
    with pytest.raises(ValueError):
        FailureRecord(
            category="invalid_contract",
            disposition=disposition,
            recovery=recovery,
            retryable=retryable,
            message="invalid",
        )


def test_build_real_core_route_raises_classified_worker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = FailureRecord(
        category="interruption_candidate_policy",
        disposition=FailureDisposition.EXPERIMENT_FAILURE,
        recovery=RecoveryAction.ABORT_EXPERIMENT,
        retryable=False,
        message="invalid candidate policy",
        exception_type="InterruptionCandidatePolicyError",
        context={"path": "$.interruption.definitions[0].candidate_policy"},
    )
    monkeypatch.setattr(
        real_core,
        "invoke_real_core_worker_process",
        lambda **_kwargs: real_core.RealCoreWorkerProcessResult(
            document=None,
            process_id=1234,
            returncode=1,
            timed_out=False,
            terminated=True,
            failure_category=failure.category,
            stdout_digest="workerstdout_test",
            stderr_digest="workerstderr_test",
            diagnostic=failure.message,
            failure_record=failure,
        ),
    )

    with pytest.raises(FailureRecordError) as captured:
        real_core.build_real_core_route()

    assert classify_failure(captured.value).to_dict() == failure.to_dict()


@pytest.mark.parametrize(
    ("error", "disposition", "recovery", "retryable"),
    [
        (
            OcgcoreWorkerCrashError(-1, "access violation"),
            FailureDisposition.PATH_FAILURE,
            RecoveryAction.REPLACE_WORKER,
            True,
        ),
        (
            OcgcoreWorkerTimeoutError(1.0),
            FailureDisposition.PATH_FAILURE,
            RecoveryAction.REPLACE_WORKER,
            True,
        ),
        (
            OcgcoreTimeoutError("step budget"),
            FailureDisposition.PATH_FAILURE,
            RecoveryAction.REPLACE_WORKER,
            True,
        ),
        (
            UnsupportedBridgeMessageError("message 20"),
            FailureDisposition.PATH_FAILURE,
            RecoveryAction.STOP_PATH,
            False,
        ),
        (
            MissingCardDataError(123),
            FailureDisposition.EXPERIMENT_FAILURE,
            RecoveryAction.ABORT_EXPERIMENT,
            False,
        ),
        (
            OcgcoreVersionMismatchError("API mismatch"),
            FailureDisposition.EXPERIMENT_FAILURE,
            RecoveryAction.ABORT_EXPERIMENT,
            False,
        ),
        (
            ReplayEnvironmentMismatchError("core.api", "11.0", "12.0"),
            FailureDisposition.EXPERIMENT_FAILURE,
            RecoveryAction.ABORT_EXPERIMENT,
            False,
        ),
        (
            ReplaySignatureMismatchError("request mismatch"),
            FailureDisposition.EXPERIMENT_FAILURE,
            RecoveryAction.ABORT_EXPERIMENT,
            False,
        ),
    ],
)
def test_failure_taxonomy_defines_search_disposition_and_recovery(
    error: BaseException,
    disposition: FailureDisposition,
    recovery: RecoveryAction,
    retryable: bool,
) -> None:
    failure = classify_failure(error, context={"step": 3})
    assert failure.disposition == disposition
    assert failure.recovery == recovery
    assert failure.retryable is retryable
    assert failure.to_dict()["context"] == {"step": 3}
    assert failure.exception_type == type(error).__name__


def test_runtime_interruption_candidate_mismatch_stops_only_current_path() -> None:
    step = CoreInterruptionStep(
        role="activation",
        request_type="select_chain",
        player=1,
        selector=CandidateSelector(candidate_id="effect:expected"),
    )
    request = DecisionRequest(
        request_id="interruption-runtime-mismatch",
        request_type="select_chain",
        player=1,
        candidates=(Candidate(candidate_id="effect:actual", kind="effect"),),
        constraints=DecisionConstraints(),
        context=DecisionContext(),
    )

    with pytest.raises(InterruptionCandidatePolicyError) as captured:
        step.select(request, path="$.candidate_policy.activation")

    failure = classify_failure(captured.value)
    assert failure.disposition == FailureDisposition.PATH_FAILURE
    assert failure.recovery == RecoveryAction.STOP_PATH
    assert failure.retryable is False
    assert failure.context["request"] == request.to_dict()
    assert failure.context["step"] == step.to_dict()


def test_invalid_interruption_policy_config_aborts_experiment() -> None:
    invalid_policy = {
        "schema_version": CORE_INTERRUPTION_CANDIDATE_POLICY_SCHEMA_VERSION,
        "activation": {
            "role": "activation",
            "request_type": "select_chain",
            "player": 1,
            "selector": {
                "candidate_id": "effect:expected",
                "python_rule": "guess-legality",
            },
        },
        "responses": [],
    }

    with pytest.raises(InterruptionCandidatePolicyError) as captured:
        CoreInterruptionCandidatePolicy.from_dict(invalid_policy)

    failure = classify_failure(
        captured.value,
        context={
            "request": "caller context must not change error origin",
            "step": "caller context must not change error origin",
        },
    )
    assert failure.disposition == FailureDisposition.EXPERIMENT_FAILURE
    assert failure.recovery == RecoveryAction.ABORT_EXPERIMENT
    assert failure.retryable is False


@pytest.mark.parametrize(
    ("path_failure", "disposition", "recovery"),
    [
        (
            True,
            FailureDisposition.PATH_FAILURE,
            RecoveryAction.STOP_PATH,
        ),
        (
            False,
            FailureDisposition.EXPERIMENT_FAILURE,
            RecoveryAction.ABORT_EXPERIMENT,
        ),
    ],
)
def test_multi_interruption_runtime_failure_preserves_failure_scope(
    path_failure: bool,
    disposition: FailureDisposition,
    recovery: RecoveryAction,
) -> None:
    error = MultiInterruptionRuntimeError(
        "candidate_disappeared",
        "the recorded core candidate is no longer offered",
        path_failure=path_failure,
        context={"opportunity_id": "interruptionopportunity_test"},
    )

    failure = classify_failure(error)

    assert failure.category == "multi_interruption_runtime"
    assert failure.disposition == disposition
    assert failure.recovery == recovery
    assert failure.retryable is False
    assert failure.context == {
        "code": "candidate_disappeared",
        "opportunity_id": "interruptionopportunity_test",
    }


def test_empty_optional_request_is_legal_dead_end_not_search_failure() -> None:
    request = DecisionRequest(
        request_id="empty",
        request_type="optional_empty",
        player=0,
        candidates=(),
        constraints=DecisionConstraints(
            min_selections=0,
            max_selections=0,
            required=False,
        ),
        context=DecisionContext(),
    )
    outcome = classify_request_outcome(request)
    assert outcome is not None
    assert outcome.disposition == FailureDisposition.LEGAL_DEAD_END
    assert outcome.recovery == RecoveryAction.NONE
    assert outcome.category == "legal_dead_end"


def test_empty_required_request_is_invalid_path_not_legal_dead_end() -> None:
    request = DecisionRequest(
        request_id="invalid-empty",
        request_type="required_empty",
        player=0,
        candidates=(),
        constraints=DecisionConstraints(),
        context=DecisionContext(),
    )
    outcome = classify_request_outcome(request)
    assert outcome is not None
    assert outcome.disposition == FailureDisposition.PATH_FAILURE
    assert outcome.category == "invalid_message"


def test_invalid_response_failure_records_original_request_and_response() -> None:
    request = DecisionRequest(
        request_id="request-1",
        request_type="select_card",
        player=0,
        candidates=(Candidate(candidate_id="card:0", kind="card"),),
        constraints=DecisionConstraints(),
        context=DecisionContext(),
    )
    response = DecisionResponse(
        request_id=request.request_id,
        request_signature=request.request_signature,
        selected_candidate_ids=("unknown",),
    )

    with pytest.raises(InvalidBridgeResponseError) as captured:
        validate_decision_response(request, response)

    failure = classify_failure(captured.value, context={"step": 2})
    serialized = failure.to_dict()
    assert serialized["disposition"] == "path_failure"
    assert serialized["recovery"] == "stop_path"
    assert serialized["context"]["request"] == request.to_dict()
    assert serialized["context"]["response"] == response.to_dict()
    assert serialized["context"]["step"] == 2


def test_real_core_worker_timeout_crash_and_protocol_errors_are_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_process(category: str, diagnostic: str, returncode: int):
        return real_core.RealCoreWorkerProcessResult(
            document=None,
            process_id=1234,
            returncode=returncode,
            timed_out=category == "worker_timeout",
            terminated=True,
            failure_category=category,
            stdout_digest="workerstdout_test",
            stderr_digest="workerstderr_test",
            diagnostic=diagnostic,
        )

    monkeypatch.setattr(
        real_core,
        "invoke_real_core_worker_process",
        lambda **_kwargs: failed_process("worker_timeout", "deadline", -9),
    )
    with pytest.raises(OcgcoreWorkerTimeoutError):
        real_core.build_real_core_route()

    monkeypatch.setattr(
        real_core,
        "invoke_real_core_worker_process",
        lambda **_kwargs: failed_process(
            "worker_crash", "access violation", -1073741819
        ),
    )
    with pytest.raises(OcgcoreWorkerCrashError) as crash:
        real_core.build_real_core_route()
    assert crash.value.returncode == -1073741819
    assert "access violation" in crash.value.diagnostic

    monkeypatch.setattr(
        real_core,
        "invoke_real_core_worker_process",
        lambda **_kwargs: failed_process(
            "worker_protocol", "invalid JSON", 0
        ),
    )
    with pytest.raises(OcgcoreWorkerProtocolError):
        real_core.build_real_core_route()
