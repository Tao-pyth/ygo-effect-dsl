from __future__ import annotations

import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.bridge.decision import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
)
from ygo_effect_dsl.engine.bridge.ocgcore import (
    CARD_INSTANCE_AUTHORITY,
    CARD_INSTANCE_TRACE_LOG_PREFIX,
    CARD_INSTANCE_TRACE_SCHEMA_VERSION,
    CardInstanceTracker,
    CoreLog,
    build_card_instance_scope_id,
    parse_card_instance_log,
    project_card_instance_observations,
)
from ygo_effect_dsl.engine.bridge.ocgcore.types import LogType
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.state import InformationMode
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.spikes.card_instance_authority_evidence import (
    CARD_INSTANCE_EVIDENCE_SCHEMA_VERSION,
    CARD_INSTANCE_ROUTE_SCHEMA_VERSION,
    UPSTREAM_CORE_COMMIT,
    build_card_instance_authority_evidence,
)


EVIDENCE = (
    Path(__file__).parents[1]
    / "docs"
    / "ocgcore"
    / "evidence"
    / "card_instance_identity.json"
)
PINNED_CORE_COMMIT = "158aebe758be3c46249c75d602e3f16d63d2ef31"


def _scope_id() -> str:
    return build_card_instance_scope_id({"fixture": "unit"})


def _log(
    *,
    log_sequence: int,
    observation_index: int,
    card_id: int,
    owner: int,
    controller: int,
    location: int,
    sequence: int,
    position: int = 1,
    label: str = "scan",
    card_code: int = 123,
    is_token: int = 0,
) -> CoreLog:
    values = (
        observation_index,
        label,
        card_id,
        card_code,
        owner,
        controller,
        location,
        sequence,
        position,
        0,
        0,
        0,
        0,
        is_token,
    )
    return CoreLog(
        sequence=log_sequence,
        log_type=LogType.FROM_SCRIPT,
        message=CARD_INSTANCE_TRACE_LOG_PREFIX
        + "|"
        + "|".join(str(value) for value in values),
    )


def _evidence() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_tracker_enriches_duplicate_code_candidates_from_card_id_authority() -> None:
    tracker = CardInstanceTracker(scope_id=_scope_id())
    observations = tracker.consume(
        (
            _log(
                log_sequence=0,
                observation_index=1,
                card_id=10,
                owner=0,
                controller=0,
                location=2,
                sequence=0,
            ),
            _log(
                log_sequence=1,
                observation_index=2,
                card_id=11,
                owner=0,
                controller=0,
                location=2,
                sequence=1,
            ),
        )
    )
    request = DecisionRequest(
        request_id="duplicate",
        request_type="select_card",
        player=0,
        candidates=tuple(
            Candidate(
                candidate_id=f"card:{index}",
                kind="card",
                card_ref={
                    "controller": 0,
                    "location": 2,
                    "public_card_id": 123,
                    "sequence": index,
                },
                payload={
                    "response_codec": "card_indices",
                    "response_index": index,
                },
            )
            for index in range(2)
        ),
        constraints=DecisionConstraints(min_selections=1, max_selections=1),
        context=DecisionContext(),
    )

    enriched = tracker.enrich_request(request)

    instance_ids = [
        candidate.card_ref["instance_id"] for candidate in enriched.candidates
    ]
    assert len(set(instance_ids)) == 2
    assert instance_ids == [item.instance_id for item in observations]
    assert all(candidate.card_ref["owner"] == 0 for candidate in enriched.candidates)
    assert enriched.request_signature != request.request_signature


def test_tracker_fails_closed_for_missing_or_tampered_authority() -> None:
    scope_id = _scope_id()
    tracker = CardInstanceTracker(scope_id=scope_id)
    tracker.consume(
        (
            _log(
                log_sequence=0,
                observation_index=1,
                card_id=10,
                owner=0,
                controller=0,
                location=2,
                sequence=0,
            ),
        )
    )
    with pytest.raises(ValueError, match="exactly one authority record"):
        tracker.resolve(controller=0, location=2, sequence=1)
    with pytest.raises(ValueError, match="observation_index must be contiguous"):
        tracker.consume(
            (
                _log(
                    log_sequence=1,
                    observation_index=3,
                    card_id=11,
                    owner=0,
                    controller=0,
                    location=2,
                    sequence=1,
                ),
            )
        )
    malformed = _log(
        log_sequence=2,
        observation_index=2,
        card_id=11,
        owner=0,
        controller=0,
        location=2,
        sequence=1,
    )
    malformed = CoreLog(
        sequence=malformed.sequence,
        log_type=malformed.log_type,
        message=malformed.message + "|extra",
    )
    with pytest.raises(ValueError, match="must contain 15 fields"):
        parse_card_instance_log(malformed, scope_id=scope_id)


def test_hidden_projection_omits_raw_and_opponent_hand_identity() -> None:
    tracker = CardInstanceTracker(scope_id=_scope_id())
    own, opponent = tracker.consume(
        (
            _log(
                log_sequence=0,
                observation_index=1,
                card_id=10,
                owner=0,
                controller=0,
                location=2,
                sequence=0,
            ),
            _log(
                log_sequence=1,
                observation_index=2,
                card_id=20,
                owner=1,
                controller=1,
                location=2,
                sequence=0,
            ),
        )
    )

    complete = project_card_instance_observations(
        (own, opponent),
        information_mode=InformationMode.COMPLETE_INFORMATION,
    )
    visible = project_card_instance_observations(
        (own, opponent),
        information_mode=InformationMode.PLAYER_VIEW,
        viewer=0,
    )
    sampled = project_card_instance_observations(
        (own, opponent),
        information_mode=InformationMode.SAMPLED_PRIVATE_STATE,
        viewer=0,
    )

    assert {item["card_id"] for item in complete} == {10, 20}
    assert [item["instance_id"] for item in visible] == [own.instance_id]
    assert sampled == visible
    assert all("card_id" not in item and "log_sequence" not in item for item in visible)


def test_checked_card_instance_evidence_satisfies_issue_acceptance() -> None:
    evidence = _evidence()
    evidence_id = evidence.pop("evidence_id")

    assert evidence_id == stable_digest(evidence, prefix="cardinstev_")
    assert evidence["schema_version"] == CARD_INSTANCE_EVIDENCE_SCHEMA_VERSION
    assert evidence["trace_schema_version"] == CARD_INSTANCE_TRACE_SCHEMA_VERSION
    assert evidence["authority"]["primary"] == CARD_INSTANCE_AUTHORITY
    assert all(evidence["checks"].values())
    replay = evidence["fresh_worker_replay"]
    assert replay["process_count"] == 2
    assert replay["runs_identical"] is True
    assert len(replay["action_ids"]) == 2
    assert replay["route_id"].startswith("route_")
    route = evidence["run"]["route_identity"]
    assert route["schema_version"] == CARD_INSTANCE_ROUTE_SCHEMA_VERSION
    assert replay["route_id"] == stable_digest(route, prefix="route_")
    action_instance_ids = [
        action["selections"][0]["card_ref"]["instance_id"]
        for action in evidence["run"]["actions"]
    ]
    assert len(set(action_instance_ids)) == 2


def test_checked_source_audit_pins_card_id_authority() -> None:
    source = _evidence()["source_audit"]

    assert source["pinned"]["commit"] == PINNED_CORE_COMMIT
    assert source["upstream"]["commit"] == UPSTREAM_CORE_COMMIT
    for audit in source.values():
        assert audit["status"] == (
            "lua_card_id_authority_available_query_card_id_unavailable"
        )
        assert all(audit["checks"].values())
        assert len(audit["files"]) == 8


def test_card_instance_evidence_matches_fresh_workers() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")

    assert build_card_instance_authority_evidence() == _evidence()
