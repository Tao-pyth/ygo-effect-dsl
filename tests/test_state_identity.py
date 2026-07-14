from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.engine.state import (
    CanonicalState,
    InformationMode,
    StateIdentityCompleteness,
)


FIXTURE = Path(__file__).parent / "fixtures" / "state" / "minimal_complete_state.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_minimal_canonical_state_fixture_is_stable_and_round_trips() -> None:
    state = CanonicalState.from_dict(_fixture())

    assert state.state_id.startswith("state_")
    assert CanonicalState.from_dict(state.to_dict()).to_dict() == state.to_dict()
    assert set(state.to_identity_dict()) == {
        "completeness",
        "constraints",
        "engine_state",
        "history",
        "information_mode",
        "missing_fields",
        "pending_request",
        "private_state",
        "public_state",
        "sampling_reference",
        "schema_version",
        "viewer",
    }


def test_state_id_is_canonical_and_changes_with_identity_sections() -> None:
    first_payload = _fixture()
    reordered_payload = {
        key: first_payload[key] for key in reversed(tuple(first_payload))
    }
    first = CanonicalState.from_dict(first_payload)
    reordered = CanonicalState.from_dict(reordered_payload)

    assert first.state_id == reordered.state_id

    for section, key, value in (
        ("public_state", "turn", 2),
        ("constraints", "normal_summon_available", False),
        ("history", "used_effect_keys", ["effect:100:0"]),
        ("engine_state", "random_state_reference", "seed:other"),
    ):
        changed = deepcopy(first_payload)
        changed[section][key] = value
        assert CanonicalState.from_dict(changed).state_id != first.state_id


def test_information_mode_and_completeness_are_validated() -> None:
    payload = _fixture()
    payload["information_mode"] = InformationMode.PLAYER_VIEW.value
    payload["viewer"] = 0
    payload["completeness"] = StateIdentityCompleteness.QUERY_API_PROJECTION.value
    payload["missing_fields"] = ["opponent_private_hand"]
    state = CanonicalState.from_dict(payload)

    assert state.viewer == 0
    assert state.missing_fields == ("opponent_private_hand",)

    payload["completeness"] = StateIdentityCompleteness.EXACT.value
    with pytest.raises(ValueError, match="exact State identity"):
        CanonicalState.from_dict(payload)


def test_state_id_rejects_unsupported_schema_and_tampering() -> None:
    payload = _fixture()
    payload["schema_version"] = "future-state-schema"
    with pytest.raises(ValueError, match="unsupported State ID schema"):
        CanonicalState.from_dict(payload)

    payload = _fixture()
    payload["state_id"] = "state_tampered"
    with pytest.raises(ValueError, match="does not match"):
        CanonicalState.from_dict(payload)
