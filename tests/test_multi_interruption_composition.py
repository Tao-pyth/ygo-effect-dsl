from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind, CardRef, Selection
from ygo_effect_dsl.engine.interruption import (
    BRANCHING_POLICY,
    MULTI_INTERRUPTION_COMPOSITION_SCHEMA_VERSION,
    OPPONENT_ACTION_SCOPE,
    OPPORTUNITY_POLICY,
    PRIORITY_POLICY,
    MultiInterruptionRuntimeError,
    build_multi_interruption_frontier,
    build_multi_interruption_composition,
    resolve_multi_interruption_definition,
    validate_multi_interruption_composition,
)
from ygo_effect_dsl.experiment import load_experiment_document, validate_experiment
from ygo_effect_dsl.prototype.real_core import _specified_interruption_trace


ROOT = Path(__file__).parents[1]
BASE_EXPERIMENT = ROOT / "examples/experiments/general_search_inline.yaml"


def _definition(
    definition_id: str,
    code: int,
    *,
    priority: int | None,
    player: int = 1,
) -> dict:
    definition = {
        "id": definition_id,
        "max_activations": 1,
        "response_roles": [],
        "source_card_code": code,
        "source_player": player,
        "source_zone": "hand",
    }
    if priority is not None:
        definition["priority"] = priority
    return definition


def _interruption() -> dict:
    return {
        "composition": {
            "branching_policy": BRANCHING_POLICY,
            "opponent_action_scope": OPPONENT_ACTION_SCOPE,
            "opportunity_policy": OPPORTUNITY_POLICY,
            "priority_policy": PRIORITY_POLICY,
            "schema_version": MULTI_INTERRUPTION_COMPOSITION_SCHEMA_VERSION,
        },
        "definitions": [
            _definition("late", 97268402, priority=20),
            _definition("early", 2511, priority=10),
        ],
        "mode": "specified",
    }


def _chain_action(
    kind: ActionKind,
    *,
    code: int | None = None,
    candidate_id: str = "pass",
    request_signature: str = "request-select-chain",
    sequence: int | None = None,
) -> Action:
    selections = ()
    if code is not None:
        card = CardRef(
            controller=1,
            owner=1,
            location="hand",
            sequence=code % 5 if sequence is None else sequence,
            public_card_id=code,
            instance_id=f"card-{code}",
        )
        selections = (Selection(candidate_id=candidate_id, card_ref=card),)
    return Action(
        kind=kind,
        player=1,
        selections=selections,
        request_signature=request_signature,
    )


def test_composition_is_ordered_by_explicit_semantic_priority() -> None:
    interruption = _interruption()
    first = build_multi_interruption_composition(interruption)
    reversed_input = deepcopy(interruption)
    reversed_input["definitions"].reverse()
    second = build_multi_interruption_composition(reversed_input)

    assert [definition.definition_id for definition in first.definitions] == [
        "early",
        "late",
    ]
    assert first.composition_id == second.composition_id
    assert first.to_dict()["opportunity_policy"] == "all_core_offered"
    assert first.to_dict()["branching_policy"] == (
        "pass_or_one_activation_per_core_request"
    )


def test_single_definition_keeps_backward_compatible_defaults() -> None:
    interruption = {
        "mode": "specified",
        "definitions": [_definition("single", 2511, priority=None)],
    }

    composition = build_multi_interruption_composition(interruption)

    assert composition.definitions[0].priority == 0
    assert composition.definitions[0].max_activations == 1


def test_multiple_definitions_require_unique_priority_and_source_authority() -> None:
    interruption = _interruption()
    interruption["definitions"][0].pop("priority")
    interruption["definitions"][1]["priority"] = 0
    interruption["definitions"][1]["id"] = "late"
    interruption["definitions"][1]["source_card_code"] = 97268402

    diagnostics = validate_multi_interruption_composition(interruption)
    codes = {diagnostic.code for diagnostic in diagnostics}

    assert "missing_multi_interruption_priority" in codes
    assert "duplicate_interruption_priority" in codes
    assert "duplicate_definition_id" in codes
    assert "ambiguous_source_authority" in codes


def test_invalid_activation_limit_and_unknown_policy_fail_closed() -> None:
    interruption = _interruption()
    interruption["definitions"][0]["max_activations"] = 0
    interruption["composition"]["opportunity_policy"] = "python_inferred"
    interruption["composition"]["unknown"] = True

    diagnostics = validate_multi_interruption_composition(interruption)
    codes = {diagnostic.code for diagnostic in diagnostics}

    assert "invalid_max_activations" in codes
    assert "unsupported_opportunity_policy" in codes
    assert "unknown_composition_fields" in codes


def test_experiment_validator_exposes_composition_diagnostics() -> None:
    experiment = load_experiment_document(BASE_EXPERIMENT)
    experiment["interruption"] = _interruption()
    assert validate_experiment(experiment) == ()

    invalid = deepcopy(experiment)
    invalid["interruption"]["definitions"][1].pop("priority")
    issues = validate_experiment(invalid)

    assert any(
        issue.code == "missing_multi_interruption_priority" for issue in issues
    )


def test_runtime_frontier_keeps_shared_pass_and_all_specified_sources() -> None:
    composition = build_multi_interruption_composition(_interruption())
    pass_action = _chain_action(ActionKind.PASS)
    early = _chain_action(
        ActionKind.ACTIVATE_EFFECT,
        code=2511,
        candidate_id="effect:early",
    )
    late = _chain_action(
        ActionKind.ACTIVATE_EFFECT,
        code=97268402,
        candidate_id="effect:late",
    )
    unspecified = _chain_action(
        ActionKind.ACTIVATE_EFFECT,
        code=14558127,
        candidate_id="effect:unspecified",
    )

    frontier = build_multi_interruption_frontier(
        composition=composition,
        request_signature="request-select-chain",
        actions=(late, unspecified, pass_action, early),
        action_prefix=(),
    )
    reversed_frontier = build_multi_interruption_frontier(
        composition=composition,
        request_signature="request-select-chain",
        actions=(early, pass_action, unspecified, late),
        action_prefix=(),
    )

    assert frontier.actions == (pass_action, early, late)
    assert [item.definition_id for item in frontier.opportunities] == [
        "early",
        "late",
    ]
    assert [item.opportunity_id for item in frontier.opportunities] == [
        item.opportunity_id for item in reversed_frontier.opportunities
    ]
    assert frontier.activation_counts == {"early": 0, "late": 0}
    assert frontier.pass_action_id == pass_action.action_id


def test_runtime_frontier_enforces_definition_activation_limit() -> None:
    composition = build_multi_interruption_composition(_interruption())
    pass_action = _chain_action(ActionKind.PASS)
    early = _chain_action(
        ActionKind.ACTIVATE_EFFECT,
        code=2511,
        candidate_id="effect:early",
    )
    late = _chain_action(
        ActionKind.ACTIVATE_EFFECT,
        code=97268402,
        candidate_id="effect:late",
    )

    frontier = build_multi_interruption_frontier(
        composition=composition,
        request_signature="request-select-chain",
        actions=(pass_action, early, late),
        action_prefix=(early,),
    )

    assert frontier.actions == (pass_action, late)
    assert [item.definition_id for item in frontier.opportunities] == ["late"]
    assert frontier.activation_counts == {"early": 1, "late": 0}


def test_runtime_definition_resolution_uses_full_source_authority() -> None:
    interruption = {
        "mode": "specified",
        "definitions": [
            {
                **_definition("first", 2511, priority=10),
                "sequence": 0,
            },
            {
                **_definition("second", 2511, priority=20),
                "sequence": 1,
            },
        ],
    }
    composition = build_multi_interruption_composition(interruption)
    second = _chain_action(
        ActionKind.ACTIVATE_EFFECT,
        code=2511,
        candidate_id="effect:second",
        sequence=1,
    )

    resolved = resolve_multi_interruption_definition(composition, second)

    assert resolved is not None
    assert resolved.definition_id == "second"

    trace = _specified_interruption_trace(
        {"interruption": interruption},
        {"events": [{"action": second.to_dict(), "step": 0}]},
    )
    assert len(trace) == 1
    assert trace[0]["definition_id"] == "second"
    assert trace[0]["opportunity_id"].startswith("interruptionopportunity_")


@pytest.mark.parametrize(
    ("actions", "code"),
    [
        ((), "shared_pass_shape_mismatch"),
        (
            (
                _chain_action(ActionKind.PASS),
                _chain_action(ActionKind.DECLINE),
            ),
            "shared_pass_shape_mismatch",
        ),
        (
            (
                _chain_action(ActionKind.PASS),
                _chain_action(ActionKind.ATTACK),
            ),
            "unsupported_chain_action_shape",
        ),
    ],
)
def test_runtime_frontier_fails_closed_for_unknown_chain_shapes(
    actions: tuple[Action, ...],
    code: str,
) -> None:
    composition = build_multi_interruption_composition(_interruption())

    with pytest.raises(MultiInterruptionRuntimeError) as captured:
        build_multi_interruption_frontier(
            composition=composition,
            request_signature="request-select-chain",
            actions=actions,
            action_prefix=(),
        )

    assert captured.value.code == code
    assert captured.value.path_failure is True
