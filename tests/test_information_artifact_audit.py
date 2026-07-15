from __future__ import annotations

import json

import pytest

from ygo_effect_dsl.engine.bridge.ocgcore.state import CompleteSnapshot
from ygo_effect_dsl.engine.information import (
    InformationArtifactLeakError,
    InformationAuditAllowlist,
    InformationAuditAllowlistEntry,
    InformationCanary,
    InformationCanaryRegistry,
    assert_information_artifact_safe,
    audit_information_artifact,
    build_player_view_canary_registry,
)


PRIVATE_CANARY = "private-card-instance-canary-451"


def _registry(artifact_kind: str = "player_view_replay") -> InformationCanaryRegistry:
    return InformationCanaryRegistry(
        artifact_kind=artifact_kind,
        viewer=0,
        canaries=(
            InformationCanary(
                canary_id="canary_private_identity",
                classification="persistent_card_identity",
                matcher_kind="substring",
                source_path="snapshots[0].zones[8].cards[0]",
                value=PRIVATE_CANARY,
            ),
            InformationCanary(
                canary_id="canary_deck_order",
                classification="hidden_deck_order",
                matcher_kind="sequence",
                source_path="snapshots[0].zones[0].deck_order",
                value=[111, 222, 333],
            ),
            InformationCanary(
                canary_id="canary_hidden_code",
                classification="hidden_card_code",
                matcher_kind="exact",
                source_path="snapshots[0].zones[8].cards[0].code",
                value=111,
            ),
        ),
    )


def test_safe_public_artifact_passes_and_report_contains_no_canary_value() -> None:
    artifact = {
        "schema_version": "player-view-replay-v1",
        "player_view_id": "playerview_public",
        "viewer": 0,
        "events": [{"actor": 1, "action_category": "OPPONENT_ACTION"}],
        "zones": [{"controller": 1, "location_name": "hand", "count": 2}],
    }

    report = audit_information_artifact(
        artifact,
        artifact_kind="player_view_replay",
        registry=_registry(),
    )

    assert report["status"] == "passed"
    assert report["findings"] == []
    assert report["side_channel_findings"] == []
    assert PRIVATE_CANARY not in json.dumps(report, sort_keys=True)
    assert_information_artifact_safe(report)


@pytest.mark.parametrize(
    ("surface", "artifact"),
    [
        ("event", {"events": [{"response": PRIVATE_CANARY}]}),
        ("state", {"initial_observation": {"debug": PRIVATE_CANARY}}),
        ("replay", {"replay": {"identity": PRIVATE_CANARY}}),
        ("report", {"diagnostics": [{"message": PRIVATE_CANARY}]}),
        ("exception", {"exception": f"failed for {PRIVATE_CANARY}"}),
        ("log", {"log": f"selected={PRIVATE_CANARY}"}),
        ("parquet", {"rows": [{"value": PRIVATE_CANARY}]}),
        ("ui_export", {"view_model": {"tooltip": PRIVATE_CANARY}}),
    ],
)
def test_private_canary_is_detected_across_every_export_surface(
    surface: str, artifact: dict
) -> None:
    report = audit_information_artifact(
        artifact,
        artifact_kind=surface,
        registry=_registry(surface),
    )

    assert report["status"] == "failed"
    assert report["findings"][0]["rule"] == "private_canary_match"
    assert PRIVATE_CANARY not in json.dumps(report, sort_keys=True)
    with pytest.raises(InformationArtifactLeakError):
        assert_information_artifact_safe(report)


@pytest.mark.parametrize(
    ("fixture_name", "artifact", "expected_rule"),
    [
        (
            "actor_switch",
            {"viewer": 1, "events": [{"private_alias": PRIVATE_CANARY}]},
            "private_canary_match",
        ),
        (
            "shuffle",
            {"zones": [{"ordering_hint": [0, 111, 222, 333, 999]}]},
            "private_canary_match",
        ),
        (
            "draw",
            {"before_after_join": PRIVATE_CANARY},
            "private_canary_match",
        ),
        (
            "search",
            {"unused_target": PRIVATE_CANARY},
            "private_canary_match",
        ),
        (
            "set",
            {"set_card": PRIVATE_CANARY},
            "private_canary_match",
        ),
        (
            "random_selection",
            {"selected_private_index": 2},
            "forbidden_side_channel",
        ),
        (
            "worker_crash",
            {"stderr": f"worker failed for {PRIVATE_CANARY}"},
            "forbidden_field_name",
        ),
    ],
)
def test_leak_fixture_matrix_fails_closed(
    fixture_name: str, artifact: dict, expected_rule: str
) -> None:
    report = audit_information_artifact(
        artifact,
        artifact_kind="player_view_replay",
        registry=_registry(),
    )
    all_findings = report["findings"] + report["side_channel_findings"]

    assert report["status"] == "failed", fixture_name
    assert expected_rule in {finding["rule"] for finding in all_findings}


def test_complete_identifiers_and_side_channels_are_rejected_by_field_name() -> None:
    artifact = {
        "state_hash": "renamed-value-is-not-required",
        "candidate_count": 4,
        "payload_length": 80,
        "private_state_hash": "state_private",
        "raw_query": "private-query",
        "route_id": "route_private",
        "worker_input_digest": "worker_private",
    }
    report = audit_information_artifact(
        artifact,
        artifact_kind="player_view_replay",
        registry=_registry(),
    )

    assert report["status"] == "failed"
    assert {finding["json_path"] for finding in report["findings"]} == {
        "$.route_id",
        "$.private_state_hash",
        "$.raw_query",
        "$.state_hash",
        "$.worker_input_digest",
    }
    assert {finding["json_path"] for finding in report["side_channel_findings"]} == {
        "$.candidate_count",
        "$.payload_length",
    }


def test_private_canary_embedded_in_json_field_name_is_rejected() -> None:
    report = audit_information_artifact(
        {f"column_{PRIVATE_CANARY}": "redacted-value"},
        artifact_kind="player_view_replay",
        registry=_registry(),
    )

    assert report["status"] == "failed"
    assert report["findings"][0]["rule"] == "private_canary_in_field_name"
    assert PRIVATE_CANARY not in json.dumps(report, sort_keys=True)
    assert report["findings"][0]["json_path"] == "$.column_<private-canary>"

    numeric = audit_information_artifact(
        {"card_111": "redacted-value"},
        artifact_kind="player_view_replay",
        registry=_registry(),
    )
    assert numeric["status"] == "failed"
    assert "111" not in numeric["findings"][0]["json_path"]


def test_false_positive_allowlist_is_exact_and_versioned() -> None:
    artifact = {"legacy": {"state_hash": "public-test-fixture"}}
    allowlist = InformationAuditAllowlist(
        entries=(
            InformationAuditAllowlistEntry(
                artifact_kind="test_fixture",
                json_path="$.legacy.state_hash",
                matcher_kind="field_name",
                reason="compatibility fixture has no complete engine state",
                review_issue=151,
            ),
        )
    )
    report = audit_information_artifact(
        artifact,
        artifact_kind="test_fixture",
        registry=_registry("test_fixture"),
        allowlist=allowlist,
    )

    assert report["status"] == "passed"
    assert report["allowlist_id"].startswith("auditallowlist_")
    assert report["allowlist_applications"] == [
        {
            "canary_id": None,
            "json_path": "$.legacy.state_hash",
            "matcher_kind": "field_name",
            "rule": "forbidden_field_name",
        }
    ]

    wrong_path = InformationAuditAllowlist(
        entries=(
            InformationAuditAllowlistEntry(
                artifact_kind="test_fixture",
                json_path="$.other.state_hash",
                matcher_kind="field_name",
                reason="intentionally wrong path",
                review_issue=151,
            ),
        )
    )
    failed = audit_information_artifact(
        artifact,
        artifact_kind="test_fixture",
        registry=_registry("test_fixture"),
        allowlist=wrong_path,
    )
    assert failed["status"] == "failed"


def test_registry_round_trip_validates_private_identity() -> None:
    registry = _registry()
    restored = InformationCanaryRegistry.from_private_dict(
        registry.to_private_dict()
    )

    assert restored == registry
    assert restored.registry_id == registry.registry_id


def test_player_view_registry_tracks_hidden_only_values_and_complete_identities() -> None:
    def card(code: int, *, controller: int, location: int, slot: int, persistent: str) -> dict:
        return {
            "controller": controller,
            "fields": [
                {"flag": 1, "name": "code", "value": code},
                {"flag": 2, "name": "position", "value": 1},
                {"flag": 3, "name": "is_hidden", "value": 0},
            ],
            "instance_key": f"{controller}:{location}:{slot}",
            "location": location,
            "persistent_instance_id": persistent,
            "slot": slot,
        }

    snapshot = CompleteSnapshot(
        environment={"core_seed": [1, 2, 3, 4]},
        field_state={"chain": [], "chain_count": 0},
        zones=(
            {
                "cards": [
                    card(789, controller=0, location=1, slot=0, persistent="corecard_deck_a"),
                    card(790, controller=0, location=1, slot=1, persistent="corecard_deck_b"),
                ],
                "controller": 0,
                "location": 1,
                "location_name": "deck",
            },
            {
                "cards": [
                    card(456, controller=0, location=2, slot=0, persistent="corecard_own_hand")
                ],
                "controller": 0,
                "location": 2,
                "location_name": "hand",
            },
            {
                "cards": [
                    card(123, controller=1, location=2, slot=0, persistent="corecard_hidden_hand"),
                    card(456, controller=1, location=2, slot=1, persistent="corecard_duplicate_code"),
                ],
                "controller": 1,
                "location": 2,
                "location_name": "hand",
            },
        ),
        process_state="awaiting_response",
        pending_request=None,
    )
    source_route = {
        "route_id": "route_complete_private",
        "replay": {
            "manifest": {"randomness": {"core_seed": [1, 2, 3, 4]}},
            "events": [{"request_signature": "req_complete_private"}],
        },
    }

    registry = build_player_view_canary_registry(
        source_route=source_route,
        snapshots=(snapshot,),
        viewer=0,
    )
    private_entries = registry.to_private_dict()["canaries"]
    values = [entry["value"] for entry in private_entries]
    classifications = {entry["classification"] for entry in private_entries}

    assert 123 in values
    assert 456 not in values
    assert [789, 790] in values
    assert "corecard_hidden_hand" in values
    assert "route_complete_private" in values
    assert "req_complete_private" in values
    assert [1, 2, 3, 4] in values
    assert "hidden_card_code" in classifications
    assert "hidden_deck_order" in classifications
