from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from enum import Enum
from itertools import combinations
from typing import Any

from ygo_effect_dsl.engine.bridge.ocgcore import CompleteSnapshot
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.interruption.comparison import (
    build_interruption_comparison,
)
from ygo_effect_dsl.route_dsl.analysis import RouteTargetBoard
from ygo_effect_dsl.route_dsl.validator import assert_valid_route_document


ADDITIONAL_CARD_ATTRIBUTION_SCHEMA_VERSION = "additional-card-attribution-v1"
CARD_INSTANCE_PROVENANCE_SCHEMA_VERSION = "card-instance-provenance-v1"
ADDITIONAL_CARD_ATTRIBUTION_V2_SCHEMA_VERSION = "additional-card-attribution-v2"
CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION = "card-instance-provenance-v2"
COUNTERFACTUAL_METHOD = "paired-exact-replay-2x2-v1"


class CardOriginKind(str, Enum):
    FIXED_OPENING_HAND = "fixed_opening_hand"
    DRAW = "draw"
    SEARCH = "search"
    SALVAGE = "salvage"
    GENERATED_TOKEN = "generated_token"
    OPPONENT = "opponent"


def classify_card_origin(
    *,
    owner: int,
    perspective: int,
    initial_fixed_hand: bool = False,
    previous_location: int | None = None,
    current_location: int | None = None,
    draw_message_present: bool = False,
    generated_token: bool = False,
) -> CardOriginKind:
    """Classify a card's first observed origin without guessing ambiguous moves."""

    if owner != perspective:
        return CardOriginKind.OPPONENT
    if generated_token:
        if previous_location not in {None, 0}:
            raise ValueError("generated token must not have a previous duel location")
        return CardOriginKind.GENERATED_TOKEN
    if initial_fixed_hand:
        return CardOriginKind.FIXED_OPENING_HAND
    if previous_location == 0x01 and current_location == 0x02:
        return CardOriginKind.DRAW if draw_message_present else CardOriginKind.SEARCH
    if previous_location == 0x10 and current_location == 0x02:
        return CardOriginKind.SALVAGE
    raise ValueError("card origin is not distinguishable from the supplied evidence")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _success(route: Mapping[str, Any], path: str) -> bool:
    value = _mapping(route.get("result"), f"{path}.result").get("success")
    if not isinstance(value, bool):
        raise ValueError(f"{path}.result.success must be boolean")
    return value


def _fixed_hands(route: Mapping[str, Any], path: str) -> dict[str, list[int]]:
    replay = _mapping(route.get("replay"), f"{path}.replay")
    manifest = _mapping(replay.get("manifest"), f"{path}.replay.manifest")
    initial = _mapping(
        manifest.get("initial_conditions"),
        f"{path}.replay.manifest.initial_conditions",
    )
    hands = _mapping(initial.get("fixed_hands"), f"{path}.fixed_hands")
    result: dict[str, list[int]] = {}
    for player in ("0", "1"):
        raw_cards = hands.get(player)
        if not isinstance(raw_cards, list) or not all(
            isinstance(code, int) and not isinstance(code, bool) and code > 0
            for code in raw_cards
        ):
            raise ValueError(f"{path}.fixed_hands[{player!r}] must contain card codes")
        result[player] = list(raw_cards)
    snapshot = _mapping(replay.get("initial_snapshot"), f"{path}.initial_snapshot")
    raw_zones = snapshot.get("zones")
    if not isinstance(raw_zones, list) or not all(
        isinstance(zone, Mapping) for zone in raw_zones
    ):
        raise ValueError(f"{path}.initial_snapshot.zones must be a list of mappings")
    raw_missing = snapshot.get("missing_identity_fields")
    if not isinstance(raw_missing, list) or not all(
        isinstance(field, str) and field for field in raw_missing
    ):
        raise ValueError(
            f"{path}.initial_snapshot.missing_identity_fields must be strings"
        )
    pending_request = snapshot.get("pending_request")
    if pending_request is not None and not isinstance(pending_request, Mapping):
        raise ValueError(f"{path}.initial_snapshot.pending_request must be a mapping")
    reconstructed = CompleteSnapshot(
        environment=_mapping(
            snapshot.get("environment"), f"{path}.initial_snapshot.environment"
        ),
        field_state=_mapping(
            snapshot.get("field_state"), f"{path}.initial_snapshot.field_state"
        ),
        zones=tuple(raw_zones),
        process_state=_string(
            snapshot.get("process_state"), f"{path}.initial_snapshot.process_state"
        ),
        pending_request=pending_request,
        identity_completeness=_string(
            snapshot.get("identity_completeness"),
            f"{path}.initial_snapshot.identity_completeness",
        ),
        missing_identity_fields=tuple(raw_missing),
        display_metadata=(
            snapshot["display_metadata"]
            if isinstance(snapshot.get("display_metadata"), Mapping)
            else {}
        ),
        card_instance_schema_version=(
            snapshot["card_instance_schema_version"]
            if isinstance(snapshot.get("card_instance_schema_version"), str)
            else None
        ),
    )
    if snapshot.get("state_hash") != reconstructed.state_hash:
        raise ValueError(f"{path}.initial_snapshot.state_hash is not canonical")
    if to_canonical_data(snapshot.get("state_identity")) != to_canonical_data(
        reconstructed.to_state_identity().to_dict()
    ):
        raise ValueError(f"{path}.initial_snapshot.state_identity is not canonical")
    if initial.get("snapshot_hash") != reconstructed.state_hash:
        raise ValueError(f"{path}.manifest snapshot_hash does not match initial_snapshot")
    events = replay.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError(f"{path}.replay.events must be a non-empty list")
    first_event = _mapping(events[0], f"{path}.replay.events[0]")
    if first_event.get("state_hash_before") != reconstructed.state_hash:
        raise ValueError(f"{path}.first event does not start from initial_snapshot")
    observed: dict[str, list[int]] = {"0": [], "1": []}
    for zone in raw_zones:
        if not isinstance(zone, Mapping) or zone.get("location") != 0x02:
            continue
        controller = zone.get("controller")
        if controller not in {0, 1}:
            raise ValueError(f"{path}.initial_snapshot hand has invalid controller")
        cards = zone.get("cards")
        if not isinstance(cards, list):
            raise ValueError(f"{path}.initial_snapshot hand cards must be a list")
        for card in cards:
            card_map = _mapping(card, f"{path}.initial_snapshot hand card")
            fields = card_map.get("fields")
            if not isinstance(fields, list):
                raise ValueError(f"{path}.initial_snapshot card fields must be a list")
            codes = [
                field.get("value")
                for field in fields
                if isinstance(field, Mapping) and field.get("name") == "code"
            ]
            if len(codes) != 1 or not isinstance(codes[0], int):
                raise ValueError(f"{path}.initial_snapshot card requires one code")
            observed[str(controller)].append(codes[0])
    if observed != result:
        raise ValueError(
            f"{path}.fixed_hands does not match initial_snapshot hand identities"
        )
    return result


def _normalized_experiment(route: Mapping[str, Any]) -> dict[str, Any]:
    experiment = deepcopy(dict(_mapping(route.get("experiment"), "route.experiment")))
    experiment.pop("experiment_id", None)
    experiment["interruption"] = {"definitions": [], "mode": "none"}
    runner = experiment.get("runner")
    if isinstance(runner, dict):
        runner.pop("recovery_card_present", None)
    return to_canonical_data(experiment)


def _usage_evidence(
    route: Mapping[str, Any],
    *,
    card_code: int,
) -> list[dict[str, Any]]:
    replay = _mapping(route.get("replay"), "route.replay")
    events = replay.get("events")
    if not isinstance(events, list):
        raise ValueError("route.replay.events must be a list")
    evidence: list[dict[str, Any]] = []
    for event in events:
        event_map = _mapping(event, "route.replay.events[]")
        action = _mapping(event_map.get("action"), "route.replay.events[].action")
        refs: list[tuple[str, Mapping[str, Any]]] = []
        source = action.get("source")
        if isinstance(source, Mapping):
            refs.append(("source", source))
        selections = action.get("selections")
        if isinstance(selections, list):
            for selection in selections:
                if not isinstance(selection, Mapping):
                    continue
                card_ref = selection.get("card_ref")
                if isinstance(card_ref, Mapping):
                    refs.append(("selection", card_ref))
        for role, card_ref in refs:
            if card_ref.get("public_card_id") != card_code:
                continue
            evidence.append(
                to_canonical_data(
                    {
                        "action_id": action.get("action_id"),
                        "action_kind": action.get("kind"),
                        "card_ref": card_ref,
                        "reference_role": role,
                        "step": event_map.get("step"),
                    }
                )
            )
    unique = {
        stable_digest(item, prefix="usage_"): item
        for item in evidence
    }
    return [unique[key] for key in sorted(unique)]


def _usage_evidence_by_instance(
    route: Mapping[str, Any],
    *,
    instance_id: str,
) -> list[dict[str, Any]]:
    replay = _mapping(route.get("replay"), "route.replay")
    events = replay.get("events")
    if not isinstance(events, list):
        raise ValueError("route.replay.events must be a list")
    evidence: list[dict[str, Any]] = []
    for event in events:
        event_map = _mapping(event, "route.replay.events[]")
        action = _mapping(event_map.get("action"), "route.replay.events[].action")
        refs: list[tuple[str, Mapping[str, Any]]] = []
        source = action.get("source")
        if isinstance(source, Mapping):
            refs.append(("source", source))
        selections = action.get("selections")
        if isinstance(selections, list):
            for selection in selections:
                if isinstance(selection, Mapping) and isinstance(
                    selection.get("card_ref"), Mapping
                ):
                    refs.append(("selection", selection["card_ref"]))
        for role, card_ref in refs:
            if card_ref.get("instance_id") != instance_id:
                continue
            evidence.append(
                to_canonical_data(
                    {
                        "action_id": action.get("action_id"),
                        "action_kind": action.get("kind"),
                        "card_ref": card_ref,
                        "reference_role": role,
                        "step": event_map.get("step"),
                    }
                )
            )
    unique = {stable_digest(item, prefix="usage_"): item for item in evidence}
    return [unique[key] for key in sorted(unique)]


def _snapshot_hand_instances(
    route: Mapping[str, Any],
    *,
    perspective: int,
    path: str,
) -> list[dict[str, Any]]:
    replay = _mapping(route.get("replay"), f"{path}.replay")
    snapshot = _mapping(replay.get("initial_snapshot"), f"{path}.initial_snapshot")
    raw_zones = snapshot.get("zones")
    if not isinstance(raw_zones, list):
        raise ValueError(f"{path}.initial_snapshot.zones must be a list")
    result: list[dict[str, Any]] = []
    for zone in raw_zones:
        if not isinstance(zone, Mapping) or zone.get("controller") != perspective:
            continue
        if zone.get("location") != 0x02:
            continue
        cards = zone.get("cards")
        if not isinstance(cards, list):
            raise ValueError(f"{path}.initial hand cards must be a list")
        for card in cards:
            card_map = _mapping(card, f"{path}.initial hand card")
            instance_id = _string(
                card_map.get("persistent_instance_id"),
                f"{path}.initial hand persistent_instance_id",
            )
            owner = card_map.get("owner")
            slot = card_map.get("slot")
            if owner not in (0, 1) or not isinstance(slot, int) or isinstance(slot, bool):
                raise ValueError(f"{path}.initial hand identity fields are invalid")
            fields = card_map.get("fields")
            if not isinstance(fields, list):
                raise ValueError(f"{path}.initial hand fields must be a list")
            codes = [
                field.get("value")
                for field in fields
                if isinstance(field, Mapping) and field.get("name") == "code"
            ]
            if len(codes) != 1 or not isinstance(codes[0], int):
                raise ValueError(f"{path}.initial hand requires one code")
            result.append(
                {
                    "card_code": codes[0],
                    "instance_id": instance_id,
                    "owner": owner,
                    "sequence": slot,
                }
            )
    result.sort(key=lambda item: int(item["sequence"]))
    if [item["sequence"] for item in result] != list(range(len(result))):
        raise ValueError(f"{path}.initial hand sequence must be contiguous")
    return result


def _proper_subsets(values: frozenset[str]) -> tuple[frozenset[str], ...]:
    ordered = sorted(values)
    return tuple(
        frozenset(subset)
        for size in range(len(ordered))
        for subset in combinations(ordered, size)
    )


def _classify_minimal_sets(
    evaluated: Mapping[frozenset[str], Mapping[str, Any]],
) -> tuple[list[frozenset[str]], list[frozenset[str]]]:
    successful_sets = {
        candidate_set
        for candidate_set, trial in evaluated.items()
        if candidate_set and trial["control_success"] and trial["interrupted_success"]
    }
    minimal_sets: list[frozenset[str]] = []
    incomplete_sets: list[frozenset[str]] = []
    for candidate_set in successful_sets:
        proper_subsets = _proper_subsets(candidate_set)
        if any(subset not in evaluated for subset in proper_subsets):
            incomplete_sets.append(candidate_set)
            continue
        if all(
            not evaluated[subset]["interrupted_success"]
            for subset in proper_subsets
        ):
            minimal_sets.append(candidate_set)
    minimal_sets.sort(key=lambda item: (len(item), sorted(item)))
    incomplete_sets.sort(key=lambda item: (len(item), sorted(item)))
    return minimal_sets, incomplete_sets


def _candidate_instances(
    baseline_hand: Sequence[int],
    treatment_hand: Sequence[int],
    *,
    perspective: int,
    control_route: Mapping[str, Any],
    interrupted_route: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if list(treatment_hand[: len(baseline_hand)]) != list(baseline_hand):
        raise ValueError(
            "treatment fixed hand must append candidates without reordering "
            "baseline cards"
        )
    added = list(treatment_hand[len(baseline_hand) :])
    baseline_counts = Counter(baseline_hand)
    added_counts = Counter(added)
    ambiguous_codes = sorted(
        code
        for code, count in added_counts.items()
        if count > 1 or baseline_counts[code] > 0
    )
    if ambiguous_codes:
        raise ValueError(
            "same-code card instances are not distinguishable in ocgcore v11 "
            "query evidence: "
            f"{ambiguous_codes}"
        )
    result: list[dict[str, Any]] = []
    for sequence, card_code in enumerate(added, start=len(baseline_hand)):
        identity = {
            "card_code": card_code,
            "origin_kind": classify_card_origin(
                owner=perspective,
                perspective=perspective,
                initial_fixed_hand=True,
            ).value,
            "owner": perspective,
            "schema_version": CARD_INSTANCE_PROVENANCE_SCHEMA_VERSION,
        }
        instance_id = stable_digest(identity, prefix="cardinst_")
        result.append(
            {
                **to_canonical_data(identity),
                "instance_id": instance_id,
                "initial_observations": [
                    {
                        "control_route_id": control_route["route_id"],
                        "initial_location": "hand",
                        "initial_sequence": sequence,
                        "interrupted_route_id": interrupted_route["route_id"],
                    }
                ],
                "matching_method": "unique-card-code-within-candidate-scope-v1",
                "manifest_evidence": [
                    {
                        "control_route_id": control_route["route_id"],
                        "interrupted_route_id": interrupted_route["route_id"],
                        "source": "replay.manifest.initial_conditions.fixed_hands",
                    }
                ],
                "usage_evidence": _usage_evidence(
                    interrupted_route,
                    card_code=card_code,
                ),
            }
        )
    return result


def _candidate_instances_v2(
    baseline_hand: Sequence[int],
    treatment_hand: Sequence[int],
    *,
    perspective: int,
    control_route: Mapping[str, Any],
    interrupted_route: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if list(treatment_hand[: len(baseline_hand)]) != list(baseline_hand):
        raise ValueError(
            "treatment fixed hand must append candidates without reordering baseline cards"
        )
    control = _snapshot_hand_instances(
        control_route,
        perspective=perspective,
        path="control_route",
    )
    interrupted = _snapshot_hand_instances(
        interrupted_route,
        perspective=perspective,
        path="interrupted_route",
    )
    if len(control) != len(treatment_hand) or len(interrupted) != len(treatment_hand):
        raise ValueError("v2 initial hand provenance does not match fixed_hands")
    result: list[dict[str, Any]] = []
    for sequence in range(len(baseline_hand), len(treatment_hand)):
        control_card = control[sequence]
        interrupted_card = interrupted[sequence]
        card_code = treatment_hand[sequence]
        if control_card != interrupted_card:
            raise ValueError(
                "paired control/interrupted routes have different persistent card identity"
            )
        if control_card["card_code"] != card_code:
            raise ValueError("v2 card instance code does not match fixed_hands")
        instance_id = str(control_card["instance_id"])
        result.append(
            {
                "card_code": card_code,
                "instance_id": instance_id,
                "initial_observations": [
                    {
                        "control_route_id": control_route["route_id"],
                        "initial_location": "hand",
                        "initial_sequence": sequence,
                        "interrupted_route_id": interrupted_route["route_id"],
                    }
                ],
                "manifest_evidence": [
                    {
                        "control_route_id": control_route["route_id"],
                        "interrupted_route_id": interrupted_route["route_id"],
                        "source": "replay.initial_snapshot.persistent_instance_id",
                    }
                ],
                "matching_method": "ocgcore-card-id-authority-v2",
                "origin_kind": classify_card_origin(
                    owner=perspective,
                    perspective=perspective,
                    initial_fixed_hand=True,
                ).value,
                "owner": perspective,
                "schema_version": CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION,
                "usage_evidence": _usage_evidence_by_instance(
                    interrupted_route,
                    instance_id=instance_id,
                ),
            }
        )
    return result


def _build_additional_card_attribution(
    baseline_control_route: Mapping[str, Any],
    baseline_interrupted_route: Mapping[str, Any],
    treatment_trials: Sequence[Mapping[str, Any]],
    *,
    perspective: int = 0,
    target_board: RouteTargetBoard = RouteTargetBoard.PEAK,
    version: str,
) -> dict[str, Any]:
    """Build a fail-closed attribution report from exact paired real-core replays."""

    if version not in {"v1", "v2"}:
        raise ValueError("additional-card attribution version must be v1 or v2")
    if perspective not in {0, 1}:
        raise ValueError("perspective must be 0 or 1")
    if not treatment_trials:
        raise ValueError("at least one treatment trial is required")
    if not isinstance(target_board, RouteTargetBoard):
        target_board = RouteTargetBoard(target_board)
    routes = [baseline_control_route, baseline_interrupted_route]
    for index, raw_trial in enumerate(treatment_trials):
        trial = _mapping(raw_trial, f"treatment_trials[{index}]")
        routes.extend(
            [
                _mapping(
                    trial.get("control_route"),
                    f"treatment_trials[{index}].control_route",
                ),
                _mapping(
                    trial.get("interrupted_route"),
                    f"treatment_trials[{index}].interrupted_route",
                ),
            ]
        )
    for index, route in enumerate(routes):
        experiment = _mapping(route.get("experiment"), f"routes[{index}].experiment")
        if experiment.get("information_mode") != "complete_information":
            raise ValueError(
                "additional-card attribution currently requires complete_information"
            )
        assert_valid_route_document(route)
        if version == "v2":
            presentation = _mapping(
                route.get("presentation"), f"routes[{index}].presentation"
            )
            provenance = _mapping(
                presentation.get("card_instance_provenance"),
                f"routes[{index}].presentation.card_instance_provenance",
            )
            if (
                provenance.get("schema_version")
                != CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION
            ):
                raise ValueError("v2 attribution requires card-instance-provenance-v2")

    normalized = _normalized_experiment(baseline_control_route)
    if any(_normalized_experiment(route) != normalized for route in routes):
        raise ValueError(
            "counterfactual routes may differ only by interruption and recovery "
            "card presence"
        )

    baseline_comparison = build_interruption_comparison(
        baseline_control_route,
        baseline_interrupted_route,
        target_board=target_board,
    )
    baseline_hands = _fixed_hands(baseline_control_route, "baseline_control_route")
    if baseline_hands != _fixed_hands(
        baseline_interrupted_route, "baseline_interrupted_route"
    ):
        raise ValueError("baseline control/interrupted fixed hands must match")
    baseline_set = frozenset[str]()
    evaluated: dict[frozenset[str], dict[str, Any]] = {
        baseline_set: {
            "candidate_instance_ids": [],
            "control_success": _success(
                baseline_control_route, "baseline_control_route"
            ),
            "interrupted_success": _success(
                baseline_interrupted_route, "baseline_interrupted_route"
            ),
            "trial_id": "baseline_no_additional_card",
        }
    }
    provenance: dict[str, dict[str, Any]] = {}
    trial_reports: list[dict[str, Any]] = []
    player_key = str(perspective)
    opponent_key = str(1 - perspective)
    for index, raw_trial in enumerate(treatment_trials):
        trial = _mapping(raw_trial, f"treatment_trials[{index}]")
        trial_id = _string(trial.get("trial_id"), f"treatment_trials[{index}].trial_id")
        control = _mapping(
            trial.get("control_route"), f"treatment_trials[{index}].control_route"
        )
        interrupted = _mapping(
            trial.get("interrupted_route"),
            f"treatment_trials[{index}].interrupted_route",
        )
        comparison = build_interruption_comparison(
            control,
            interrupted,
            target_board=target_board,
        )
        control_hands = _fixed_hands(control, f"treatment_trials[{index}].control")
        if control_hands != _fixed_hands(
            interrupted, f"treatment_trials[{index}].interrupted"
        ):
            raise ValueError(f"treatment trial {trial_id!r} fixed hands must match")
        if control_hands[opponent_key] != baseline_hands[opponent_key]:
            raise ValueError("opponent fixed hand must be invariant across trials")
        candidate_builder = (
            _candidate_instances_v2 if version == "v2" else _candidate_instances
        )
        instances = candidate_builder(
            baseline_hands[player_key],
            control_hands[player_key],
            perspective=perspective,
            control_route=control,
            interrupted_route=interrupted,
        )
        candidate_set = frozenset(item["instance_id"] for item in instances)
        if not candidate_set:
            raise ValueError("treatment trial must add at least one candidate card")
        if candidate_set in evaluated:
            raise ValueError("candidate set is evaluated more than once")
        for item in instances:
            existing = provenance.get(item["instance_id"])
            if existing is None:
                provenance[item["instance_id"]] = item
                continue
            stable_fields = (
                "card_code",
                "instance_id",
                "matching_method",
                "origin_kind",
                "owner",
                "schema_version",
            )
            if any(existing[field] != item[field] for field in stable_fields):
                raise ValueError("card instance provenance differs across trials")
            for field in (
                "initial_observations",
                "manifest_evidence",
                "usage_evidence",
            ):
                merged = {
                    stable_digest(value, prefix="evidence_"): value
                    for value in [*existing[field], *item[field]]
                }
                existing[field] = [merged[key] for key in sorted(merged)]
        trial_result = {
            "candidate_instance_ids": sorted(candidate_set),
            "comparison_id": comparison["comparison_id"],
            "control_route_id": control["route_id"],
            "control_success": _success(control, f"treatment_trials[{index}].control"),
            "interrupted_route_id": interrupted["route_id"],
            "interrupted_success": _success(
                interrupted, f"treatment_trials[{index}].interrupted"
            ),
            "trial_id": trial_id,
        }
        evaluated[candidate_set] = trial_result
        trial_reports.append(trial_result)

    minimal_sets, incomplete_sets = _classify_minimal_sets(evaluated)
    baseline_outcome = evaluated[baseline_set]
    status = (
        "verified_minimal_required_sets"
        if minimal_sets
        else (
            "insufficient_subset_coverage"
            if incomplete_sets
            else "no_recovery_set_observed"
        )
    )
    counterfactual_trials = []
    for trial in trial_reports:
        counterfactual_trials.append(
            {
                **trial,
                "card_effect_under_interruption": (
                    int(trial["interrupted_success"])
                    - int(baseline_outcome["interrupted_success"])
                ),
                "control_effect": (
                    int(trial["control_success"])
                    - int(baseline_outcome["control_success"])
                ),
                "difference_in_differences": (
                    int(trial["interrupted_success"])
                    - int(trial["control_success"])
                    - int(baseline_outcome["interrupted_success"])
                    + int(baseline_outcome["control_success"])
                ),
            }
        )
    identity = to_canonical_data(
        {
            "baseline": {
                **baseline_outcome,
                "comparison_id": baseline_comparison["comparison_id"],
                "control_route_id": baseline_control_route["route_id"],
                "interrupted_route_id": baseline_interrupted_route["route_id"],
            },
            "counterfactual": {
                "method": COUNTERFACTUAL_METHOD,
                "trials": counterfactual_trials,
            },
            "information_scope": {
                "candidate_owner": perspective,
                "mode": "complete_information",
                "opponent_hidden_identifiers_embedded": False,
                "perspective": perspective,
                "publication_boundary": "candidate_provenance_only",
            },
            "instance_identity_scope": {
                "duplicate_same_code_policy": (
                    "compare_persistent_instance_id"
                    if version == "v2"
                    else "reject_ambiguous"
                ),
                "hand_sequence_may_compact": True,
                "matching_method": (
                    "ocgcore-card-id-authority-v2"
                    if version == "v2"
                    else "unique-card-code-within-candidate-scope-v1"
                ),
            },
            "minimal_required_sets": [sorted(item) for item in minimal_sets],
            "origin_taxonomy": [item.value for item in CardOriginKind],
            "provenance": [provenance[key] for key in sorted(provenance)],
            "schema_version": (
                ADDITIONAL_CARD_ATTRIBUTION_V2_SCHEMA_VERSION
                if version == "v2"
                else ADDITIONAL_CARD_ATTRIBUTION_SCHEMA_VERSION
            ),
            "status": status,
            "subset_coverage_missing": [sorted(item) for item in incomplete_sets],
            "target_board": target_board.value,
        }
    )
    return {
        **identity,
        "attribution_id": stable_digest(identity, prefix="cardattr_"),
    }


def build_additional_card_attribution(
    baseline_control_route: Mapping[str, Any],
    baseline_interrupted_route: Mapping[str, Any],
    treatment_trials: Sequence[Mapping[str, Any]],
    *,
    perspective: int = 0,
    target_board: RouteTargetBoard = RouteTargetBoard.PEAK,
) -> dict[str, Any]:
    """Build the immutable v1 unique-code attribution report."""

    return _build_additional_card_attribution(
        baseline_control_route,
        baseline_interrupted_route,
        treatment_trials,
        perspective=perspective,
        target_board=target_board,
        version="v1",
    )


def build_additional_card_attribution_v2(
    baseline_control_route: Mapping[str, Any],
    baseline_interrupted_route: Mapping[str, Any],
    treatment_trials: Sequence[Mapping[str, Any]],
    *,
    perspective: int = 0,
    target_board: RouteTargetBoard = RouteTargetBoard.PEAK,
) -> dict[str, Any]:
    """Build attribution from persistent ocgcore card-instance authority."""

    return _build_additional_card_attribution(
        baseline_control_route,
        baseline_interrupted_route,
        treatment_trials,
        perspective=perspective,
        target_board=target_board,
        version="v2",
    )
