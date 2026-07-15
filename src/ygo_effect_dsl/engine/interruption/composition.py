from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ygo_effect_dsl.engine.action import Action, ActionKind
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


class MultiInterruptionRuntimeError(ValueError):
    category = "multi_interruption_runtime"

    def __init__(
        self,
        code: str,
        message: str,
        *,
        path_failure: bool,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.path_failure = path_failure
        self.context = to_canonical_data(
            {"code": code, **dict(context or {})}
        )
        super().__init__(f"{code}: {message}")


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


@dataclass(frozen=True)
class MultiInterruptionOpportunity:
    composition_id: str
    definition_id: str
    priority: int
    occurrence_index: int
    request_signature: str
    candidate_id: str
    action_id: str
    prefix_action_ids: tuple[str, ...]
    schema_version: str = MULTI_INTERRUPTION_OPPORTUNITY_SCHEMA_VERSION

    @property
    def opportunity_id(self) -> str:
        return build_interruption_opportunity_id(
            composition_id=self.composition_id,
            definition_id=self.definition_id,
            occurrence_index=self.occurrence_index,
            request_signature=self.request_signature,
            candidate_id=self.candidate_id,
            prefix_action_ids=self.prefix_action_ids,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "candidate_id": self.candidate_id,
            "composition_id": self.composition_id,
            "definition_id": self.definition_id,
            "occurrence_index": self.occurrence_index,
            "opportunity_id": self.opportunity_id,
            "prefix_action_ids": list(self.prefix_action_ids),
            "priority": self.priority,
            "request_signature": self.request_signature,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class MultiInterruptionFrontier:
    actions: tuple[Action, ...]
    opportunities: tuple[MultiInterruptionOpportunity, ...]
    activation_counts: Mapping[str, int]
    pass_action_id: str

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "activation_counts": self.activation_counts,
                "opportunities": [
                    opportunity.to_dict() for opportunity in self.opportunities
                ],
                "pass_action_id": self.pass_action_id,
                "schema_version": MULTI_INTERRUPTION_OPPORTUNITY_SCHEMA_VERSION,
            }
        )


def build_interruption_opportunity_id(
    *,
    composition_id: str,
    definition_id: str,
    occurrence_index: int,
    request_signature: str,
    candidate_id: str,
    prefix_action_ids: Sequence[str],
) -> str:
    return stable_digest(
        {
            "candidate_id": candidate_id,
            "composition_id": composition_id,
            "definition_id": definition_id,
            "occurrence_index": occurrence_index,
            "prefix_action_ids": list(prefix_action_ids),
            "request_signature": request_signature,
            "schema_version": MULTI_INTERRUPTION_OPPORTUNITY_SCHEMA_VERSION,
        },
        prefix="interruptionopportunity_",
    )


def _action_document(value: Action | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(value, Action):
        return value.to_dict()
    if isinstance(value, Mapping):
        return value
    raise MultiInterruptionRuntimeError(
        "unprojectable_action_shape",
        "Action must be a mapping or Action instance",
        path_failure=True,
    )


def _action_source_ref(action: Mapping[str, Any]) -> Mapping[str, Any] | None:
    selections = action.get("selections")
    if not isinstance(selections, list) or len(selections) != 1:
        raise MultiInterruptionRuntimeError(
            "ambiguous_activation_selection",
            "an activation Action must select exactly one core candidate",
            path_failure=True,
            context={"action_id": action.get("action_id")},
        )
    selection = selections[0]
    if not isinstance(selection, Mapping):
        raise MultiInterruptionRuntimeError(
            "unprojectable_action_shape",
            "activation selection must be a mapping",
            path_failure=True,
            context={"action_id": action.get("action_id")},
        )
    card_ref = selection.get("card_ref")
    if card_ref is None:
        return None
    if not isinstance(card_ref, Mapping):
        raise MultiInterruptionRuntimeError(
            "unprojectable_source_shape",
            "activation card_ref must be a mapping",
            path_failure=True,
            context={"action_id": action.get("action_id")},
        )
    return card_ref


def _source_matches(
    definition: MultiInterruptionDefinition,
    card_ref: Mapping[str, Any],
) -> bool:
    if (
        card_ref.get("public_card_id") != definition.source_card_code
        or card_ref.get("controller") != definition.source_player
    ):
        return False
    location = card_ref.get("location")
    if definition.source_zone == "hand":
        if location != "hand":
            return False
    elif location not in {
        "monster_zone",
        "spell_trap_zone",
        "core_location_4",
        "core_location_8",
    }:
        return False
    if definition.core_location is not None:
        expected_locations = {
            4: {"monster_zone", "core_location_4"},
            8: {"spell_trap_zone", "core_location_8"},
        }[definition.core_location]
        if location not in expected_locations:
            return False
    if (
        definition.sequence is not None
        and card_ref.get("sequence") != definition.sequence
    ):
        return False
    return True


def _matching_definitions(
    composition: MultiInterruptionComposition,
    action: Mapping[str, Any],
) -> tuple[MultiInterruptionDefinition, ...]:
    card_ref = _action_source_ref(action)
    if card_ref is None:
        return ()
    return tuple(
        definition
        for definition in composition.definitions
        if _source_matches(definition, card_ref)
    )


def resolve_multi_interruption_definition(
    composition: MultiInterruptionComposition,
    action: Action | Mapping[str, Any],
) -> MultiInterruptionDefinition | None:
    document = _action_document(action)
    if document.get("kind") != ActionKind.ACTIVATE_EFFECT.value:
        return None
    matches = _matching_definitions(composition, document)
    if len(matches) > 1:
        raise MultiInterruptionRuntimeError(
            "ambiguous_definition_match",
            "activation matches multiple specified definitions",
            path_failure=False,
            context={"action_id": document.get("action_id")},
        )
    return matches[0] if matches else None


def _prefix_action_ids(
    action_prefix: Sequence[Action | Mapping[str, Any]],
) -> tuple[str, ...]:
    action_ids = []
    for index, raw_action in enumerate(action_prefix):
        action = _action_document(raw_action)
        action_id = action.get("action_id")
        if not isinstance(action_id, str) or not action_id:
            raise MultiInterruptionRuntimeError(
                "unprojectable_action_shape",
                f"prefix Action {index} has no action_id",
                path_failure=True,
            )
        action_ids.append(action_id)
    return tuple(action_ids)


def _activation_counts(
    composition: MultiInterruptionComposition,
    action_prefix: Sequence[Action | Mapping[str, Any]],
) -> dict[str, int]:
    counts = {definition.definition_id: 0 for definition in composition.definitions}
    for raw_action in action_prefix:
        action = _action_document(raw_action)
        if action.get("kind") != ActionKind.ACTIVATE_EFFECT.value:
            continue
        definition = resolve_multi_interruption_definition(composition, action)
        if definition is not None:
            counts[definition.definition_id] += 1
            if counts[definition.definition_id] > definition.max_activations:
                raise MultiInterruptionRuntimeError(
                    "activation_limit_exceeded",
                    "recorded prefix exceeds max_activations",
                    path_failure=True,
                    context={
                        "definition_id": definition.definition_id,
                        "max_activations": definition.max_activations,
                    },
                )
    return counts


def build_multi_interruption_frontier(
    *,
    composition: MultiInterruptionComposition,
    request_signature: str,
    actions: Sequence[Action],
    action_prefix: Sequence[Action | Mapping[str, Any]],
) -> MultiInterruptionFrontier:
    if not isinstance(request_signature, str) or not request_signature:
        raise MultiInterruptionRuntimeError(
            "unprojectable_request_shape",
            "request_signature must be a non-empty string",
            path_failure=True,
        )
    pass_actions = tuple(
        action
        for action in actions
        if action.kind in {ActionKind.PASS, ActionKind.DECLINE}
    )
    if len(pass_actions) != 1:
        raise MultiInterruptionRuntimeError(
            "shared_pass_shape_mismatch",
            f"select_chain must expose exactly one shared PASS, got {len(pass_actions)}",
            path_failure=True,
        )
    unexpected = tuple(
        action
        for action in actions
        if action.kind
        not in {ActionKind.ACTIVATE_EFFECT, ActionKind.PASS, ActionKind.DECLINE}
    )
    if unexpected:
        raise MultiInterruptionRuntimeError(
            "unsupported_chain_action_shape",
            "select_chain exposed an unsupported Action kind",
            path_failure=True,
            context={"action_ids": [action.action_id for action in unexpected]},
        )
    prefix_ids = _prefix_action_ids(action_prefix)
    activation_counts = _activation_counts(composition, action_prefix)
    selected_actions: list[tuple[MultiInterruptionDefinition, Action]] = []
    opportunities: list[MultiInterruptionOpportunity] = []
    for action in actions:
        if action.kind != ActionKind.ACTIVATE_EFFECT:
            continue
        action_document = action.to_dict()
        definition = resolve_multi_interruption_definition(
            composition, action_document
        )
        if definition is None:
            continue
        if activation_counts[definition.definition_id] >= definition.max_activations:
            continue
        selection = action_document["selections"][0]
        candidate_id = selection.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise MultiInterruptionRuntimeError(
                "unprojectable_action_shape",
                "activation selection has no candidate_id",
                path_failure=True,
                context={"action_id": action.action_id},
            )
        opportunity = MultiInterruptionOpportunity(
            composition_id=composition.composition_id,
            definition_id=definition.definition_id,
            priority=definition.priority,
            occurrence_index=activation_counts[definition.definition_id] + 1,
            request_signature=request_signature,
            candidate_id=candidate_id,
            action_id=action.action_id,
            prefix_action_ids=prefix_ids,
        )
        selected_actions.append((definition, action))
        opportunities.append(opportunity)
    ordered = sorted(
        zip(selected_actions, opportunities, strict=True),
        key=lambda value: (
            value[0][0].priority,
            value[0][0].definition_id,
            value[1].opportunity_id,
        ),
    )
    return MultiInterruptionFrontier(
        actions=(pass_actions[0], *(value[0][1] for value in ordered)),
        opportunities=tuple(value[1] for value in ordered),
        activation_counts=activation_counts,
        pass_action_id=pass_actions[0].action_id,
    )


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
