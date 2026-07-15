from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from ygo_effect_dsl.engine.interruption import (
    BRANCHING_POLICY,
    MULTI_INTERRUPTION_COMPOSITION_SCHEMA_VERSION,
    OPPONENT_ACTION_SCOPE,
    OPPORTUNITY_POLICY,
    PRIORITY_POLICY,
    build_multi_interruption_composition,
    validate_multi_interruption_composition,
)
from ygo_effect_dsl.experiment import load_experiment_document, validate_experiment


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
