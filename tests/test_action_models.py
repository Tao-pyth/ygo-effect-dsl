from ygo_effect_dsl.engine.action import (
    Action,
    ActionKind,
    CardRef,
    EffectRef,
    Selection,
    action_from_dict,
)


def test_action_from_dict_preserves_effect_references_and_identity() -> None:
    card = CardRef(
        controller=0,
        owner=0,
        location="monster_zone",
        sequence=1,
        public_card_id=12345678,
        instance_id="corecard_example",
    )
    effect = EffectRef(
        card_ref=card,
        effect_index=2,
        effect_label="display-only label",
        once_per_turn_key="example-opt",
    )
    action = Action(
        kind=ActionKind.ACTIVATE_EFFECT,
        player=0,
        selections=(
            Selection(
                candidate_id="candidate:effect",
                card_ref=card,
                effect_ref=effect,
                payload_ref="candidate.payload",
            ),
        ),
        request_signature="request_signature",
        source=card,
        effect_ref=effect,
    )

    restored = action_from_dict(action.to_dict())

    assert restored == action
    assert restored.action_id == action.action_id
