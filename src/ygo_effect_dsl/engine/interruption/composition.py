from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


MULTI_INTERRUPTION_COMPOSITION_SCHEMA_VERSION = "multi-interruption-composition-v1"
MULTI_INTERRUPTION_LINEAGE_SCHEMA_VERSION = "multi-interruption-lineage-v1"
MULTI_INTERRUPTION_OPPORTUNITY_SCHEMA_VERSION = "multi-interruption-opportunity-v1"

OPPORTUNITY_POLICY = "all_core_offered"
BRANCHING_POLICY = "pass_or_one_activation_per_core_request"
PRIORITY_POLICY = "ascending_priority_then_definition_id"
OPPONENT_ACTION_SCOPE = "specified_sources_only"

_COMPOSITION_FIELDS = frozenset(
    {
        "branching_policy",
        "opponent_action_scope",
        "opportunity_policy",
        "priority_policy",
        "schema_version",
    }
)


@dataclass(frozen=True)
class MultiInterruptionDiagnostic:
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "path": self.path}


@dataclass(frozen=True)
class MultiInterruptionDefinition:
    definition_id: str
    priority: int
    max_activations: int
    source_card_code: int
    source_player: int
    source_zone: str
    core_location: int | None
    sequence: int | None

    @property
    def source_authority(self) -> tuple[int, int, str, int | None, int | None]:
        return (
            self.source_card_code,
            self.source_player,
            self.source_zone,
            self.core_location,
            self.sequence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "definition_id": self.definition_id,
            "max_activations": self.max_activations,
            "priority": self.priority,
            "source_authority": {
                "card_code": self.source_card_code,
                "core_location": self.core_location,
                "player": self.source_player,
                "sequence": self.sequence,
                "zone": self.source_zone,
            },
        }


@dataclass(frozen=True)
class MultiInterruptionComposition:
    definitions: tuple[MultiInterruptionDefinition, ...]
    opportunity_policy: str = OPPORTUNITY_POLICY
    branching_policy: str = BRANCHING_POLICY
    priority_policy: str = PRIORITY_POLICY
    opponent_action_scope: str = OPPONENT_ACTION_SCOPE
    schema_version: str = MULTI_INTERRUPTION_COMPOSITION_SCHEMA_VERSION

    @property
    def composition_id(self) -> str:
        return stable_digest(self.to_identity_dict(), prefix="interruptioncomposition_")

    def to_identity_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "branching_policy": self.branching_policy,
                "definitions": [definition.to_dict() for definition in self.definitions],
                "opponent_action_scope": self.opponent_action_scope,
                "opportunity_policy": self.opportunity_policy,
                "priority_policy": self.priority_policy,
                "schema_version": self.schema_version,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {"composition_id": self.composition_id, **self.to_identity_dict()}


def _composition_config(interruption: Mapping[str, Any]) -> Mapping[str, Any]:
    value = interruption.get("composition", {})
    return value if isinstance(value, Mapping) else {}


def validate_multi_interruption_composition(
    interruption: Mapping[str, Any],
) -> tuple[MultiInterruptionDiagnostic, ...]:
    diagnostics: list[MultiInterruptionDiagnostic] = []
    if interruption.get("mode") != "specified":
        return tuple(diagnostics)
    raw_definitions = interruption.get("definitions")
    if not isinstance(raw_definitions, Sequence) or isinstance(
        raw_definitions, (str, bytes)
    ):
        return (
            MultiInterruptionDiagnostic(
                "$.interruption.definitions",
                "expected_list",
                "specified interruption definitions must be a list",
            ),
        )
    config = interruption.get("composition", {})
    if not isinstance(config, Mapping):
        diagnostics.append(
            MultiInterruptionDiagnostic(
                "$.interruption.composition",
                "expected_mapping",
                "composition must be a mapping",
            )
        )
        config = {}
    unknown_fields = sorted(set(config) - _COMPOSITION_FIELDS)
    if unknown_fields:
        diagnostics.append(
            MultiInterruptionDiagnostic(
                "$.interruption.composition",
                "unknown_composition_fields",
                f"unsupported fields: {unknown_fields}",
            )
        )
    expected_values = {
        "branching_policy": BRANCHING_POLICY,
        "opponent_action_scope": OPPONENT_ACTION_SCOPE,
        "opportunity_policy": OPPORTUNITY_POLICY,
        "priority_policy": PRIORITY_POLICY,
        "schema_version": MULTI_INTERRUPTION_COMPOSITION_SCHEMA_VERSION,
    }
    for field, expected in expected_values.items():
        actual = config.get(field, expected)
        if actual != expected:
            diagnostics.append(
                MultiInterruptionDiagnostic(
                    f"$.interruption.composition.{field}",
                    f"unsupported_{field}",
                    f"must be {expected!r}",
                )
            )
    definition_ids: dict[str, int] = {}
    priorities: dict[int, int] = {}
    source_authorities: dict[tuple[Any, ...], int] = {}
    multiple = len(raw_definitions) > 1
    for index, raw_definition in enumerate(raw_definitions):
        path = f"$.interruption.definitions[{index}]"
        if not isinstance(raw_definition, Mapping):
            continue
        definition_id = raw_definition.get("id")
        if isinstance(definition_id, str) and definition_id:
            if definition_id in definition_ids:
                diagnostics.append(
                    MultiInterruptionDiagnostic(
                        f"{path}.id",
                        "duplicate_definition_id",
                        f"duplicates definitions[{definition_ids[definition_id]}].id",
                    )
                )
            else:
                definition_ids[definition_id] = index
        if multiple and "priority" not in raw_definition:
            diagnostics.append(
                MultiInterruptionDiagnostic(
                    f"{path}.priority",
                    "missing_multi_interruption_priority",
                    "multiple definitions require an explicit priority",
                )
            )
        priority = raw_definition.get("priority", index)
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
            diagnostics.append(
                MultiInterruptionDiagnostic(
                    f"{path}.priority",
                    "invalid_interruption_priority",
                    "priority must be an integer >= 0",
                )
            )
        elif priority in priorities:
            diagnostics.append(
                MultiInterruptionDiagnostic(
                    f"{path}.priority",
                    "duplicate_interruption_priority",
                    f"duplicates definitions[{priorities[priority]}].priority",
                )
            )
        else:
            priorities[priority] = index
        max_activations = raw_definition.get("max_activations", 1)
        if (
            not isinstance(max_activations, int)
            or isinstance(max_activations, bool)
            or max_activations < 1
        ):
            diagnostics.append(
                MultiInterruptionDiagnostic(
                    f"{path}.max_activations",
                    "invalid_max_activations",
                    "max_activations must be an integer >= 1",
                )
            )
        source_authority = (
            raw_definition.get("source_card_code"),
            raw_definition.get("source_player"),
            raw_definition.get("source_zone", "hand"),
            raw_definition.get("core_location"),
            raw_definition.get("sequence"),
        )
        if source_authority in source_authorities:
            diagnostics.append(
                MultiInterruptionDiagnostic(
                    path,
                    "ambiguous_source_authority",
                    "source authority duplicates "
                    f"definitions[{source_authorities[source_authority]}]",
                )
            )
        else:
            source_authorities[source_authority] = index
    return tuple(diagnostics)


def build_multi_interruption_composition(
    interruption: Mapping[str, Any],
) -> MultiInterruptionComposition:
    diagnostics = validate_multi_interruption_composition(interruption)
    if diagnostics:
        first = diagnostics[0]
        raise ValueError(f"{first.code} at {first.path}: {first.message}")
    if interruption.get("mode") != "specified":
        raise ValueError("multi-interruption composition requires specified mode")
    raw_definitions = interruption["definitions"]
    definitions = []
    for index, raw_definition in enumerate(raw_definitions):
        definitions.append(
            MultiInterruptionDefinition(
                definition_id=str(raw_definition["id"]),
                priority=int(raw_definition.get("priority", index)),
                max_activations=int(raw_definition.get("max_activations", 1)),
                source_card_code=int(raw_definition["source_card_code"]),
                source_player=int(raw_definition["source_player"]),
                source_zone=str(raw_definition.get("source_zone", "hand")),
                core_location=(
                    int(raw_definition["core_location"])
                    if raw_definition.get("core_location") is not None
                    else None
                ),
                sequence=(
                    int(raw_definition["sequence"])
                    if raw_definition.get("sequence") is not None
                    else None
                ),
            )
        )
    definitions.sort(key=lambda definition: (definition.priority, definition.definition_id))
    config = _composition_config(interruption)
    return MultiInterruptionComposition(
        definitions=tuple(definitions),
        opportunity_policy=str(config.get("opportunity_policy", OPPORTUNITY_POLICY)),
        branching_policy=str(config.get("branching_policy", BRANCHING_POLICY)),
        priority_policy=str(config.get("priority_policy", PRIORITY_POLICY)),
        opponent_action_scope=str(
            config.get("opponent_action_scope", OPPONENT_ACTION_SCOPE)
        ),
        schema_version=str(
            config.get(
                "schema_version", MULTI_INTERRUPTION_COMPOSITION_SCHEMA_VERSION
            )
        ),
    )
