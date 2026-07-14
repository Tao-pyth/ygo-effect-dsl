from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind, CardRef, EffectRef
from ygo_effect_dsl.engine.interruption import (
    InterruptionTarget,
    InterruptionTargetResolutionError,
    resolve_interruption_target,
)
from ygo_effect_dsl.engine.replay import ReplayEventV03a
from ygo_effect_dsl.experiment import validate_experiment
from ygo_effect_dsl.route_dsl import load_route_document


REPO_ROOT = Path(__file__).resolve().parents[1]


def _event(
    step: int,
    *,
    instance_id: str = "instance-a",
    state_hash_before: str = "state_before",
    turn_action_index: int = 0,
    chain_index: int = 1,
    effect_label: str = "Draw effect",
) -> dict[str, object]:
    card = CardRef(
        controller=0,
        owner=0,
        location="monster_zone",
        sequence=0,
        public_card_id=12345678,
        instance_id=instance_id,
    )
    effect = EffectRef(card_ref=card, effect_index=2, effect_label=effect_label)
    action = Action(
        kind=ActionKind.ACTIVATE_EFFECT,
        player=0,
        selections=(),
        request_signature="req_activate_draw",
        source=card,
        effect_ref=effect,
    )
    return ReplayEventV03a(
        step=step,
        request_signature=action.request_signature,
        action=action,
        state_hash_before=state_hash_before,
        state_hash_after=f"state_after_{step}",
        turn=1,
        turn_action_index=turn_action_index,
        chain_index=chain_index,
    ).to_dict()


def test_repeated_same_effect_has_distinct_occurrence_target() -> None:
    first = InterruptionTarget.from_replay_event(_event(0, turn_action_index=0))
    repeated = InterruptionTarget.from_replay_event(_event(1, turn_action_index=1))

    assert first.action_id == repeated.action_id
    assert first.effect_ref == repeated.effect_ref
    assert first.action_occurrence_id != repeated.action_occurrence_id
    assert first.target_id != repeated.target_id


def test_same_card_code_different_instance_has_distinct_target() -> None:
    first = InterruptionTarget.from_replay_event(_event(0, instance_id="copy-a"))
    second = InterruptionTarget.from_replay_event(_event(0, instance_id="copy-b"))

    assert first.source["public_card_id"] == second.source["public_card_id"]
    assert first.source["instance_id"] != second.source["instance_id"]
    assert first.target_id != second.target_id


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("state_hash_before", "state_other"),
        ("turn_action_index", 3),
        ("chain_index", 2),
    ),
)
def test_target_signature_covers_state_and_duel_coordinates(
    field: str, value: object
) -> None:
    baseline_event = _event(0)
    changed = {
        "state_hash_before": "state_before",
        "turn_action_index": 0,
        "chain_index": 1,
    }
    changed[field] = value

    baseline = InterruptionTarget.from_replay_event(baseline_event)
    different = InterruptionTarget.from_replay_event(_event(0, **changed))

    assert baseline.target_id != different.target_id


def test_display_effect_label_is_not_part_of_target_identity() -> None:
    original = InterruptionTarget.from_replay_event(
        _event(0, effect_label="Original localized label")
    )
    renamed = InterruptionTarget.from_replay_event(
        _event(0, effect_label="Renamed localized label")
    )

    assert original.target_id == renamed.target_id
    assert "effect_label" not in original.effect_ref


def test_target_round_trip_and_replay_resolution_select_exact_occurrence() -> None:
    events = [_event(0, turn_action_index=0), _event(1, turn_action_index=1)]
    target = InterruptionTarget.from_replay_event(events[1])
    parsed = InterruptionTarget.from_dict(target.to_dict())

    resolution = resolve_interruption_target({"events": events}, parsed)

    assert resolution.replay_step == 1
    assert resolution.target.action_occurrence_id == events[1]["action_occurrence_id"]
    assert resolution.to_dict()["resolution_id"].startswith("intresolve_")


def test_tampered_or_missing_target_cannot_be_silently_resolved() -> None:
    event = _event(0)
    target = InterruptionTarget.from_replay_event(event)
    tampered = deepcopy(target.to_dict())
    tampered["request_signature"] = "req_other"

    with pytest.raises(ValueError, match="target_id or fields"):
        InterruptionTarget.from_dict(tampered)
    with pytest.raises(InterruptionTargetResolutionError, match="was not found"):
        resolve_interruption_target([_event(1, turn_action_index=1)], target)


def test_request_signature_is_part_of_target_identity() -> None:
    event = _event(0)
    changed = deepcopy(event)
    changed["request_signature"] = "req_changed"
    changed["action"]["request_signature"] = "req_changed"
    changed["action"]["action_id"] = "act_changed_request_signature"
    changed.pop("action_occurrence_id")

    baseline = InterruptionTarget.from_replay_event(event)
    different = InterruptionTarget.from_replay_event(changed)

    assert baseline.request_signature != different.request_signature
    assert baseline.target_id != different.target_id


def test_real_core_replay_target_resolves_and_fits_experiment_definition() -> None:
    route = load_route_document(
        REPO_ROOT
        / "examples"
        / "prototype"
        / "real_core_effect_veiler.route.yaml"
    )
    replay = route["replay"]
    target = InterruptionTarget.from_replay_event(replay["events"][0])

    resolution = resolve_interruption_target(replay, target)
    experiment = deepcopy(route["experiment"])
    experiment["interruption"] = {
        "mode": "scripted",
        "definitions": [{"id": "veiler_at_first_action", "target": target.to_dict()}],
    }

    assert resolution.replay_step == 0
    assert validate_experiment(experiment) == ()
