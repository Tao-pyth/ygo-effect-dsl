from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from ygo_effect_dsl.engine.action import (
    ACTION_AGGREGATION_SCHEMA_VERSION,
    OCGCORE_ACTION_AGGREGATION_METHOD,
    derive_ocgcore_action_aggregation,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation import (
    EvaluationResult,
    assert_valid_temporary_modifier_observation,
    assert_valid_temporary_effect_report,
)
from ygo_effect_dsl.engine.peak import (
    DURABILITY_SCHEMA_VERSION,
    DURABLE_EVALUATION_TIMING,
    TEMPORARY_EVALUATION_TIMING,
    build_durability_report,
)
from ygo_effect_dsl.engine.information import (
    INFORMATION_AUDIT_SCHEMA_VERSION,
    InformationAccessPolicy,
    InformationField,
    build_opening_hand_sampling_evidence,
)
from ygo_effect_dsl.engine.interruption.target import InterruptionTarget
from ygo_effect_dsl.engine.interruption.adapter import (
    CoreInterruptionCandidatePolicy,
    InterruptionCandidatePolicyError,
)
from ygo_effect_dsl.engine.interruption.validation import (
    derive_ocgcore_interruption_validation,
)
from ygo_effect_dsl.engine.replay import (
    ReplayFormatError,
    assert_complete_io_trace,
    build_action_occurrence_id,
)
from ygo_effect_dsl.experiment import EXPERIMENT_SCHEMA_VERSION, validate_experiment


ROUTE_DSL_NAME = "ygo-route"
ROUTE_DSL_SCHEMA_VERSION = "0.1"
ROUTE_STATUSES = frozenset({"complete", "partial", "failed"})


@dataclass(frozen=True)
class RouteValidationIssue:
    path: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.code}: {self.message}"


def load_route_document(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid Route DSL serialization: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Route DSL root must be a mapping")
    return payload


def _mapping(
    value: Any,
    path: str,
    issues: list[RouteValidationIssue],
    *,
    required: bool = True,
) -> Mapping[str, Any] | None:
    if value is None and not required:
        return None
    if not isinstance(value, Mapping):
        issues.append(RouteValidationIssue(path, "expected_mapping", "must be a mapping"))
        return None
    return value


def _non_empty_string(value: Any, path: str, issues: list[RouteValidationIssue]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        issues.append(RouteValidationIssue(path, "expected_non_empty_string", "must be a non-empty string"))
        return None
    return value


def _validate_information_policy_links(
    root: Mapping[str, Any],
    experiment: Mapping[str, Any] | None,
    replay: Mapping[str, Any] | None,
    issues: list[RouteValidationIssue],
) -> None:
    if experiment is None or experiment.get("schema_version") != (
        EXPERIMENT_SCHEMA_VERSION
    ):
        return
    try:
        policy = InformationAccessPolicy.from_experiment(experiment)
    except (TypeError, ValueError):
        return
    policy_document = policy.to_dict()
    expected_policy_id = policy_document["policy_id"]
    if replay is not None:
        replay_policy_id = _non_empty_string(
            replay.get("information_policy_id"),
            "$.replay.information_policy_id",
            issues,
        )
        if replay_policy_id is not None and replay_policy_id != expected_policy_id:
            issues.append(
                RouteValidationIssue(
                    "$.replay.information_policy_id",
                    "information_policy_id_mismatch",
                    "must match experiment.information_policy.policy_id",
                )
            )
        manifest = replay.get("manifest")
        initial_conditions = (
            manifest.get("initial_conditions")
            if isinstance(manifest, Mapping)
            else None
        )
        if isinstance(initial_conditions, Mapping):
            manifest_policy_id = _non_empty_string(
                initial_conditions.get("information_policy_id"),
                "$.replay.manifest.initial_conditions.information_policy_id",
                issues,
            )
            if (
                manifest_policy_id is not None
                and manifest_policy_id != expected_policy_id
            ):
                issues.append(
                    RouteValidationIssue(
                        "$.replay.manifest.initial_conditions.information_policy_id",
                        "information_policy_id_mismatch",
                        "must match experiment.information_policy.policy_id",
                    )
                )
            expected_mode = policy.information_mode.value
            snapshot_kind = initial_conditions.get("snapshot_kind")
            if snapshot_kind != expected_mode:
                issues.append(
                    RouteValidationIssue(
                        "$.replay.manifest.initial_conditions.snapshot_kind",
                        "information_snapshot_kind_mismatch",
                        "must match experiment.information_mode",
                    )
                )
            initial_snapshot = replay.get("initial_snapshot")
            state_identity = (
                initial_snapshot.get("state_identity")
                if isinstance(initial_snapshot, Mapping)
                else None
            )
            if (
                not isinstance(state_identity, Mapping)
                or state_identity.get("information_mode") != expected_mode
            ):
                issues.append(
                    RouteValidationIssue(
                        "$.replay.initial_snapshot.state_identity.information_mode",
                        "information_state_mode_mismatch",
                        "must match experiment.information_mode",
                    )
                )
            if isinstance(state_identity, Mapping) and to_canonical_data(
                state_identity.get("sampling_reference")
            ) != to_canonical_data(policy.sampling_reference):
                issues.append(
                    RouteValidationIssue(
                        "$.replay.initial_snapshot.state_identity.sampling_reference",
                        "information_sampling_reference_mismatch",
                        "must match the canonical information policy",
                    )
                )
            randomness = (
                manifest.get("randomness")
                if isinstance(manifest, Mapping)
                else None
            )
            opening_sampling = (
                randomness.get("opening_hand_sampling")
                if isinstance(randomness, Mapping)
                else None
            )
            if expected_mode == "sampled_private_state":
                reference = policy.sampling_reference
                if not isinstance(opening_sampling, Mapping):
                    issues.append(
                        RouteValidationIssue(
                            "$.replay.manifest.randomness.opening_hand_sampling",
                            "missing_opening_hand_sampling_evidence",
                            "is required for sampled_private_state",
                        )
                    )
                elif not isinstance(reference, Mapping) or any(
                    opening_sampling.get(field) != reference.get(field)
                    for field in ("sampler_id", "sampling_policy_id", "seed")
                ):
                    issues.append(
                        RouteValidationIssue(
                            "$.replay.manifest.randomness.opening_hand_sampling",
                            "opening_hand_sampling_policy_mismatch",
                            "must match information_policy.sampling_reference",
                        )
                    )
                elif opening_sampling.get("information_policy_id") != (
                    expected_policy_id
                ):
                    issues.append(
                        RouteValidationIssue(
                            "$.replay.manifest.randomness.opening_hand_sampling.information_policy_id",
                            "information_policy_id_mismatch",
                            "must match the sampled information policy",
                        )
                    )
                if isinstance(reference, Mapping) and isinstance(
                    opening_sampling, Mapping
                ):
                    expected_opening_sampling = (
                        build_opening_hand_sampling_evidence(
                            reference,
                            information_policy_id=str(expected_policy_id),
                        )
                    )
                    if to_canonical_data(opening_sampling) != (
                        to_canonical_data(expected_opening_sampling)
                    ):
                        issues.append(
                            RouteValidationIssue(
                                "$.replay.manifest.randomness.opening_hand_sampling",
                                "opening_hand_sampling_evidence_mismatch",
                                "must match the deterministic sampling decision",
                            )
                        )
                sampling_result = (
                    opening_sampling.get("result")
                    if isinstance(opening_sampling, Mapping)
                    else None
                )
                sampled_result_hands = (
                    sampling_result.get("hands_by_player")
                    if isinstance(sampling_result, Mapping)
                    else None
                )
                initial_sampled_hands = initial_conditions.get("sampled_hands")
                if (
                    not isinstance(sampled_result_hands, Mapping)
                    or not isinstance(initial_sampled_hands, Mapping)
                    or any(
                        to_canonical_data(initial_sampled_hands.get(player))
                        != to_canonical_data(hand)
                        for player, hand in sampled_result_hands.items()
                    )
                ):
                    issues.append(
                        RouteValidationIssue(
                            "$.replay.manifest.initial_conditions.sampled_hands",
                            "sampled_opening_hand_result_mismatch",
                            "must match opening-hand sampling evidence",
                        )
                    )
            elif opening_sampling is not None:
                issues.append(
                    RouteValidationIssue(
                        "$.replay.manifest.randomness.opening_hand_sampling",
                        "unexpected_opening_hand_sampling_evidence",
                        "is only valid for sampled_private_state",
                    )
                )
            if expected_mode == "player_view" and any(
                key in initial_conditions for key in ("fixed_hands", "sampled_hands")
            ):
                issues.append(
                    RouteValidationIssue(
                        "$.replay.manifest.initial_conditions",
                        "player_view_private_hands_exposed",
                        "PlayerView Replay traces must not persist private hands",
                    )
                )

    audit = _mapping(root.get("information_audit"), "$.information_audit", issues)
    if audit is None:
        return
    if audit.get("schema_version") != INFORMATION_AUDIT_SCHEMA_VERSION:
        issues.append(
            RouteValidationIssue(
                "$.information_audit.schema_version",
                "unsupported_information_audit_schema",
                f"must be {INFORMATION_AUDIT_SCHEMA_VERSION!r}",
            )
        )
    if to_canonical_data(audit.get("policy")) != policy_document:
        issues.append(
            RouteValidationIssue(
                "$.information_audit.policy",
                "information_policy_mismatch",
                "must equal the canonical Experiment information policy",
            )
        )
    audit_identity = to_canonical_data(
        {
            "accesses": audit.get("accesses"),
            "leak_count": audit.get("leak_count"),
            "leaks": audit.get("leaks"),
            "policy": audit.get("policy"),
            "schema_version": audit.get("schema_version"),
        }
    )
    if audit.get("audit_id") != stable_digest(audit_identity, prefix="infoaudit_"):
        issues.append(
            RouteValidationIssue(
                "$.information_audit.audit_id",
                "information_audit_id_mismatch",
                "must match the canonical audit content",
            )
        )
    accesses = audit.get("accesses")
    expected_leaks: list[Mapping[str, Any]] = []
    if isinstance(accesses, list):
        for index, access in enumerate(accesses):
            access_path = f"$.information_audit.accesses[{index}]"
            if not isinstance(access, Mapping):
                issues.append(
                    RouteValidationIssue(
                        access_path, "expected_mapping", "must be a mapping"
                    )
                )
                continue
            try:
                field = InformationField(str(access.get("field")))
                expected_decision = policy.decide(field, access.get("owner")).value
            except (TypeError, ValueError) as exc:
                issues.append(
                    RouteValidationIssue(
                        access_path,
                        "invalid_information_access",
                        str(exc),
                    )
                )
                continue
            if access.get("sequence") != index:
                issues.append(
                    RouteValidationIssue(
                        f"{access_path}.sequence",
                        "information_access_sequence_mismatch",
                        "must equal its list index",
                    )
                )
            if access.get("decision") != expected_decision:
                issues.append(
                    RouteValidationIssue(
                        f"{access_path}.decision",
                        "information_access_decision_mismatch",
                        "must be recomputed from the information policy",
                    )
                )
            if expected_decision != "allowed":
                expected_leaks.append(access)
    if isinstance(accesses, list) and (
        audit.get("leak_count") != len(expected_leaks)
        or to_canonical_data(audit.get("leaks"))
        != to_canonical_data(expected_leaks)
    ):
        issues.append(
            RouteValidationIssue(
                "$.information_audit.leaks",
                "information_audit_leaks_mismatch",
                "must match recomputed access decisions",
            )
        )


def _board_result(
    value: Any,
    path: str,
    checkpoints: dict[int, Mapping[str, Any]],
    issues: list[RouteValidationIssue],
    *,
    required: bool,
) -> None:
    board = _mapping(value, path, issues, required=required)
    if board is None:
        return

    step = board.get("checkpoint_step")
    if not isinstance(step, int):
        issues.append(RouteValidationIssue(f"{path}.checkpoint_step", "expected_integer", "must be an integer"))
        return
    checkpoint = checkpoints.get(step)
    if checkpoint is None:
        issues.append(RouteValidationIssue(f"{path}.checkpoint_step", "unknown_checkpoint", "must reference checkpoints[].step"))
        return

    state_hash = _non_empty_string(board.get("state_hash"), f"{path}.state_hash", issues)
    if state_hash is not None and state_hash != checkpoint.get("state_hash"):
        issues.append(RouteValidationIssue(f"{path}.state_hash", "checkpoint_state_mismatch", "must match the referenced checkpoint"))
    score = board.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        issues.append(RouteValidationIssue(f"{path}.score", "expected_number", "must be a number"))
    _mapping(board.get("evaluation"), f"{path}.evaluation", issues)
    if "evaluation_result" in board and to_canonical_data(
        board.get("evaluation_result")
    ) != to_canonical_data(checkpoint.get("evaluation_result")):
        issues.append(
            RouteValidationIssue(
                f"{path}.evaluation_result",
                "checkpoint_evaluation_mismatch",
                "must match the referenced checkpoint",
            )
        )


def _durability_result(
    value: Any,
    checkpoints: dict[int, Mapping[str, Any]],
    issues: list[RouteValidationIssue],
) -> None:
    path = "$.result.durability"
    durability = _mapping(value, path, issues)
    if durability is None:
        return
    if durability.get("schema_version") != DURABILITY_SCHEMA_VERSION:
        issues.append(
            RouteValidationIssue(
                f"{path}.schema_version",
                "unsupported_durability_schema",
                f"must be {DURABILITY_SCHEMA_VERSION!r}",
            )
        )
    timing = _mapping(
        durability.get("evaluation_timing"),
        f"{path}.evaluation_timing",
        issues,
    )
    if timing is not None:
        expected_timings = {
            "before": TEMPORARY_EVALUATION_TIMING,
            "after": DURABLE_EVALUATION_TIMING,
        }
        for name, expected in expected_timings.items():
            if timing.get(name) != expected:
                issues.append(
                    RouteValidationIssue(
                        f"{path}.evaluation_timing.{name}",
                        "unexpected_evaluation_timing",
                        f"must be {expected!r}",
                    )
                )
    for name in ("before", "after"):
        side_path = f"{path}.{name}"
        side = _mapping(durability.get(name), side_path, issues)
        if side is None:
            continue
        _board_result(side, side_path, checkpoints, issues, required=True)
        step = side.get("checkpoint_step")
        checkpoint = checkpoints.get(step) if isinstance(step, int) else None
        if checkpoint is None:
            continue
        for field in ("turn", "phase", "success"):
            if side.get(field) != checkpoint.get(field):
                issues.append(
                    RouteValidationIssue(
                        f"{side_path}.{field}",
                        "checkpoint_value_mismatch",
                        f"must match the referenced checkpoint's {field}",
                    )
                )
    _mapping(durability.get("delta"), f"{path}.delta", issues)
    for field in ("state_changed", "success_retained"):
        if not isinstance(durability.get(field), bool):
            issues.append(
                RouteValidationIssue(
                    f"{path}.{field}", "expected_boolean", "must be a boolean"
                )
            )
    before = durability.get("before")
    after = durability.get("after")
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        before_step = before.get("checkpoint_step")
        after_step = after.get("checkpoint_step")
        before_checkpoint = (
            checkpoints.get(before_step) if isinstance(before_step, int) else None
        )
        after_checkpoint = (
            checkpoints.get(after_step) if isinstance(after_step, int) else None
        )
        if before_checkpoint is not None and after_checkpoint is not None:
            try:
                expected = build_durability_report(
                    before_checkpoint, after_checkpoint
                )
            except (TypeError, ValueError) as exc:
                issues.append(
                    RouteValidationIssue(
                        path,
                        "invalid_durability_source",
                        str(exc),
                    )
                )
            else:
                if to_canonical_data(durability) != expected:
                    issues.append(
                        RouteValidationIssue(
                            path,
                            "durability_recalculation_mismatch",
                            "must match the referenced checkpoints",
                        )
                    )


def _evaluation_explanation(
    value: Any,
    terminal_board: Any,
    issues: list[RouteValidationIssue],
) -> None:
    path = "$.result.evaluation_explanation"
    explanation = _mapping(value, path, issues)
    if explanation is None:
        return
    temporary = _mapping(
        explanation.get("temporary_effects"),
        f"{path}.temporary_effects",
        issues,
    )
    if temporary is None:
        return
    try:
        assert_valid_temporary_effect_report(temporary)
    except (TypeError, ValueError) as exc:
        issues.append(
            RouteValidationIssue(
                f"{path}.temporary_effects",
                "invalid_temporary_effect_report",
                str(exc),
            )
        )
        return
    terminal = terminal_board if isinstance(terminal_board, Mapping) else None
    boundary = temporary.get("evaluation_boundary")
    if terminal is not None and isinstance(boundary, Mapping):
        for field in ("turn", "phase"):
            if boundary.get(field) != terminal.get(field):
                issues.append(
                    RouteValidationIssue(
                        f"{path}.temporary_effects.evaluation_boundary.{field}",
                        "terminal_boundary_mismatch",
                        f"must match result.terminal_board.{field}",
                    )
                )


def _validate_action_aggregation(
    value: Any,
    events: list[Any],
    issues: list[RouteValidationIssue],
) -> None:
    path = "$.presentation.action_aggregation"
    aggregation = _mapping(value, path, issues)
    if aggregation is None:
        return
    if aggregation.get("schema_version") != ACTION_AGGREGATION_SCHEMA_VERSION:
        issues.append(
            RouteValidationIssue(
                f"{path}.schema_version",
                "unsupported_action_aggregation_schema",
                f"must be {ACTION_AGGREGATION_SCHEMA_VERSION!r}",
            )
        )
    groups = aggregation.get("groups")
    if not isinstance(groups, list):
        issues.append(RouteValidationIssue(f"{path}.groups", "expected_list", "must be a list"))
        return

    group_steps: dict[str, tuple[int, ...]] = {}
    covered_steps: list[int] = []
    for group_index, raw_group in enumerate(groups):
        group_path = f"{path}.groups[{group_index}]"
        group = _mapping(raw_group, group_path, issues)
        if group is None:
            continue
        composite_id = _non_empty_string(
            group.get("composite_id"), f"{group_path}.composite_id", issues
        )
        if composite_id is not None and composite_id in group_steps:
            issues.append(
                RouteValidationIssue(
                    f"{group_path}.composite_id",
                    "duplicate_composite_id",
                    "must be unique within action aggregation",
                )
            )
        raw_steps = group.get("atomic_steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            issues.append(
                RouteValidationIssue(
                    f"{group_path}.atomic_steps",
                    "expected_non_empty_list",
                    "must be a non-empty list",
                )
            )
            continue
        if any(
            not isinstance(step, int)
            or isinstance(step, bool)
            or step < 0
            or step >= len(events)
            for step in raw_steps
        ):
            issues.append(
                RouteValidationIssue(
                    f"{group_path}.atomic_steps",
                    "unknown_replay_step",
                    "all values must reference replay.events[].step",
                )
            )
            continue
        steps = tuple(raw_steps)
        if steps != tuple(range(steps[0], steps[-1] + 1)):
            issues.append(
                RouteValidationIssue(
                    f"{group_path}.atomic_steps",
                    "non_contiguous_action_group",
                    "must be a contiguous replay event span",
                )
            )
        covered_steps.extend(steps)
        if composite_id is not None:
            group_steps[composite_id] = steps

        for field in ("costs", "options", "parts", "selections", "targets"):
            if not isinstance(group.get(field), list):
                issues.append(
                    RouteValidationIssue(
                        f"{group_path}.{field}",
                        "expected_list",
                        "must be a list",
                    )
                )
        action_ids = group.get("action_ids")
        occurrence_ids = group.get("action_occurrence_ids")
        if not isinstance(action_ids, list) or len(action_ids) != len(steps):
            issues.append(
                RouteValidationIssue(
                    f"{group_path}.action_ids",
                    "action_group_length_mismatch",
                    "must have one entry per atomic step",
                )
            )
        if not isinstance(occurrence_ids, list) or len(occurrence_ids) != len(steps):
            issues.append(
                RouteValidationIssue(
                    f"{group_path}.action_occurrence_ids",
                    "action_group_length_mismatch",
                    "must have one entry per atomic step",
                )
            )
        if isinstance(action_ids, list) and len(action_ids) == len(steps):
            expected_action_ids = [
                event.get("action", {}).get("action_id")
                if isinstance(event, Mapping)
                and isinstance(event.get("action"), Mapping)
                else None
                for event in (events[step] for step in steps)
            ]
            if action_ids != expected_action_ids:
                issues.append(
                    RouteValidationIssue(
                        f"{group_path}.action_ids",
                        "action_group_reference_mismatch",
                        "must match the referenced replay actions",
                    )
                )
        if isinstance(occurrence_ids, list) and len(occurrence_ids) == len(steps):
            expected_occurrence_ids = [
                events[step].get("action_occurrence_id")
                if isinstance(events[step], Mapping)
                else None
                for step in steps
            ]
            if occurrence_ids != expected_occurrence_ids:
                issues.append(
                    RouteValidationIssue(
                        f"{group_path}.action_occurrence_ids",
                        "action_group_reference_mismatch",
                        "must match the referenced replay action occurrences",
                    )
                )

    if sorted(covered_steps) != list(range(len(events))) or len(covered_steps) != len(
        set(covered_steps)
    ):
        issues.append(
            RouteValidationIssue(
                f"{path}.groups",
                "action_group_coverage_mismatch",
                "every replay event must appear in exactly one group",
            )
        )

    links = aggregation.get("links")
    if not isinstance(links, list):
        issues.append(RouteValidationIssue(f"{path}.links", "expected_list", "must be a list"))
        return
    linked_steps: list[int] = []
    for link_index, raw_link in enumerate(links):
        link_path = f"{path}.links[{link_index}]"
        link = _mapping(raw_link, link_path, issues)
        if link is None:
            continue
        step = link.get("step")
        composite_id = link.get("composite_id")
        part_index = link.get("part_index")
        if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step < len(events):
            issues.append(
                RouteValidationIssue(
                    f"{link_path}.step",
                    "unknown_replay_step",
                    "must reference replay.events[].step",
                )
            )
            continue
        linked_steps.append(step)
        expected_steps = group_steps.get(composite_id)
        if expected_steps is None or step not in expected_steps:
            issues.append(
                RouteValidationIssue(
                    f"{link_path}.composite_id",
                    "action_group_link_mismatch",
                    "must reference the group containing this step",
                )
            )
        elif part_index != expected_steps.index(step):
            issues.append(
                RouteValidationIssue(
                    f"{link_path}.part_index",
                    "action_group_link_mismatch",
                    "must match the step position within the group",
                )
            )
        event_occurrence_id = (
            events[step].get("action_occurrence_id")
            if isinstance(events[step], Mapping)
            else None
        )
        if link.get("action_occurrence_id") != event_occurrence_id:
            issues.append(
                RouteValidationIssue(
                    f"{link_path}.action_occurrence_id",
                    "action_group_link_mismatch",
                    "must match the replay event occurrence",
                )
            )
    if sorted(linked_steps) != list(range(len(events))) or len(linked_steps) != len(
        set(linked_steps)
    ):
        issues.append(
            RouteValidationIssue(
                f"{path}.links",
                "action_group_link_coverage_mismatch",
                "every replay event must have exactly one link",
            )
        )


def validate_route_document(document: Any) -> tuple[RouteValidationIssue, ...]:
    issues: list[RouteValidationIssue] = []
    root = _mapping(document, "$", issues)
    if root is None:
        return tuple(issues)

    if root.get("dsl") != ROUTE_DSL_NAME:
        issues.append(RouteValidationIssue("$.dsl", "unsupported_dsl", f"must be {ROUTE_DSL_NAME!r}"))
    if root.get("schema_version") != ROUTE_DSL_SCHEMA_VERSION:
        issues.append(
            RouteValidationIssue(
                "$.schema_version",
                "unsupported_schema_version",
                f"must be {ROUTE_DSL_SCHEMA_VERSION!r}",
            )
        )
    _non_empty_string(root.get("route_id"), "$.route_id", issues)
    if root.get("status") not in ROUTE_STATUSES:
        issues.append(RouteValidationIssue("$.status", "unsupported_status", f"must be one of {sorted(ROUTE_STATUSES)}"))

    experiment = _mapping(root.get("experiment"), "$.experiment", issues)
    if experiment is not None:
        for experiment_issue in validate_experiment(experiment):
            suffix = experiment_issue.path[1:]
            issues.append(
                RouteValidationIssue(
                    f"$.experiment{suffix}",
                    f"experiment_{experiment_issue.code}",
                    experiment_issue.message,
                )
            )

    replay = _mapping(root.get("replay"), "$.replay", issues)
    events: list[Any] = []
    occurrence_ids: set[str] = set()
    if replay is not None:
        _non_empty_string(replay.get("schema_version"), "$.replay.schema_version", issues)
        _mapping(replay.get("initial_snapshot"), "$.replay.initial_snapshot", issues)
        _mapping(replay.get("version_metadata"), "$.replay.version_metadata", issues)
        if replay.get("manifest") is not None:
            _mapping(replay.get("manifest"), "$.replay.manifest", issues)
        raw_events = replay.get("events")
        if not isinstance(raw_events, list):
            issues.append(RouteValidationIssue("$.replay.events", "expected_list", "must be a list"))
        else:
            events = raw_events
            for index, raw_event in enumerate(events):
                event_path = f"$.replay.events[{index}]"
                event = _mapping(raw_event, event_path, issues)
                if event is None:
                    continue
                if event.get("step") != index:
                    issues.append(RouteValidationIssue(f"{event_path}.step", "non_contiguous_step", f"must be {index}"))
                request_signature = _non_empty_string(
                    event.get("request_signature"), f"{event_path}.request_signature", issues
                )
                action = _mapping(event.get("action"), f"{event_path}.action", issues)
                if action is not None:
                    action_id = _non_empty_string(
                        action.get("action_id"), f"{event_path}.action.action_id", issues
                    )
                    _non_empty_string(action.get("kind"), f"{event_path}.action.kind", issues)
                    action_signature = _non_empty_string(
                        action.get("request_signature"),
                        f"{event_path}.action.request_signature",
                        issues,
                    )
                    if request_signature is not None and action_signature is not None and action_signature != request_signature:
                        issues.append(
                            RouteValidationIssue(
                                f"{event_path}.action.request_signature",
                                "request_signature_mismatch",
                                "must match the containing replay event",
                            )
                        )
                    event_action_id = event.get("action_id")
                    if event_action_id is not None and event_action_id != action_id:
                        issues.append(
                            RouteValidationIssue(
                                f"{event_path}.action_id",
                                "action_id_mismatch",
                                "must match action.action_id",
                            )
                        )
                    occurrence_id = event.get("action_occurrence_id")
                    if occurrence_id is not None:
                        occurrence_id = _non_empty_string(
                            occurrence_id,
                            f"{event_path}.action_occurrence_id",
                            issues,
                        )
                        state_hash_before = _non_empty_string(
                            event.get("state_hash_before"),
                            f"{event_path}.state_hash_before",
                            issues,
                        )
                        coordinates: dict[str, int | None] = {}
                        coordinates_valid = True
                        for name in ("turn", "turn_action_index", "chain_index"):
                            value = event.get(name)
                            minimum = 1 if name == "turn" else 0
                            if value is not None and (
                                not isinstance(value, int)
                                or isinstance(value, bool)
                                or value < minimum
                            ):
                                issues.append(
                                    RouteValidationIssue(
                                        f"{event_path}.{name}",
                                        "invalid_action_coordinate",
                                        f"must be an integer >= {minimum} or null",
                                    )
                                )

                                coordinates_valid = False
                            coordinates[name] = value
                        if occurrence_id is not None:
                            if occurrence_id in occurrence_ids:
                                issues.append(
                                    RouteValidationIssue(
                                        f"{event_path}.action_occurrence_id",
                                        "duplicate_action_occurrence_id",
                                        "must be unique within replay.events",
                                    )
                                )
                            occurrence_ids.add(occurrence_id)
                        if (
                            occurrence_id is not None
                            and action_id is not None
                            and state_hash_before is not None
                            and coordinates_valid
                        ):
                            expected_occurrence_id = build_action_occurrence_id(
                                action_id=action_id,
                                step=index,
                                state_hash_before=state_hash_before,
                                turn=coordinates["turn"],
                                turn_action_index=coordinates["turn_action_index"],
                                chain_index=coordinates["chain_index"],
                            )
                            if occurrence_id != expected_occurrence_id:
                                issues.append(
                                    RouteValidationIssue(
                                        f"{event_path}.action_occurrence_id",
                                        "action_occurrence_id_mismatch",
                                        "must match the canonical action execution coordinates",
                                    )
                                )

    if replay is not None and replay.get("initial_core_output") is not None:
        try:
            assert_complete_io_trace(replay)
        except ReplayFormatError as exc:
            issues.append(
                RouteValidationIssue(
                    "$.replay",
                    "invalid_replay_io_trace",
                    str(exc),
                )
            )

    _validate_information_policy_links(root, experiment, replay, issues)

    presentation = _mapping(
        root.get("presentation"), "$.presentation", issues, required=False
    )
    if presentation is not None:
        _validate_action_aggregation(
            presentation.get("action_aggregation"), events, issues
        )
        validation = _mapping(
            presentation.get("validation"),
            "$.presentation.validation",
            issues,
        )
        if validation is not None:
            validation_status = validation.get("status")
            if validation_status not in {"validated", "provisional"}:
                issues.append(
                    RouteValidationIssue(
                        "$.presentation.validation.status",
                        "unsupported_validation_status",
                        "must be 'validated' or 'provisional'",
                    )
                )
            elif validation_status == "validated":
                if validation.get("method") != OCGCORE_ACTION_AGGREGATION_METHOD:
                    issues.append(
                        RouteValidationIssue(
                            "$.presentation.validation.method",
                            "unsupported_action_aggregation_validation_method",
                            f"must be {OCGCORE_ACTION_AGGREGATION_METHOD!r}",
                        )
                    )
                elif replay is not None:
                    try:
                        expected_aggregation, expected_evidence = (
                            derive_ocgcore_action_aggregation(replay)
                        )
                    except (TypeError, ValueError) as exc:
                        issues.append(
                            RouteValidationIssue(
                                "$.presentation.action_aggregation_evidence",
                                "invalid_ocgcore_action_aggregation_evidence",
                                str(exc),
                            )
                        )
                    else:
                        if to_canonical_data(
                            presentation.get("action_aggregation")
                        ) != expected_aggregation.to_dict():
                            issues.append(
                                RouteValidationIssue(
                                    "$.presentation.action_aggregation",
                                    "ocgcore_action_aggregation_mismatch",
                                    "must be derived from Replay raw core lifecycle frames",
                                )
                            )
                        if to_canonical_data(
                            presentation.get("action_aggregation_evidence")
                        ) != expected_evidence:
                            issues.append(
                                RouteValidationIssue(
                                    "$.presentation.action_aggregation_evidence",
                                    "ocgcore_action_aggregation_evidence_mismatch",
                                    "must match the canonical lifecycle derivation",
                                )
                            )
        if "interruption_validation_evidence" in presentation:
            if replay is None:
                issues.append(
                    RouteValidationIssue(
                        "$.presentation.interruption_validation_evidence",
                        "interruption_validation_requires_replay",
                        "cannot validate interruption evidence without Replay",
                    )
                )
            else:
                try:
                    expected_interruption_evidence = (
                        derive_ocgcore_interruption_validation(replay)
                    )
                except (TypeError, ValueError) as exc:
                    issues.append(
                        RouteValidationIssue(
                            "$.presentation.interruption_validation_evidence",
                            "invalid_ocgcore_interruption_validation_evidence",
                            str(exc),
                        )
                    )
                else:
                    if to_canonical_data(
                        presentation.get("interruption_validation_evidence")
                    ) != expected_interruption_evidence:
                        issues.append(
                            RouteValidationIssue(
                                "$.presentation.interruption_validation_evidence",
                                "ocgcore_interruption_validation_evidence_mismatch",
                                "must match Replay negation and timing frames",
                            )
                        )

    checkpoints: dict[int, Mapping[str, Any]] = {}
    raw_checkpoints = root.get("checkpoints")
    if not isinstance(raw_checkpoints, list):
        issues.append(RouteValidationIssue("$.checkpoints", "expected_list", "must be a list"))
    else:
        for index, raw_checkpoint in enumerate(raw_checkpoints):
            path = f"$.checkpoints[{index}]"
            checkpoint = _mapping(raw_checkpoint, path, issues)
            if checkpoint is None:
                continue
            step = checkpoint.get("step")
            if not isinstance(step, int):
                issues.append(RouteValidationIssue(f"{path}.step", "expected_integer", "must be an integer"))
                continue
            if step < 0 or step >= len(events):
                issues.append(RouteValidationIssue(f"{path}.step", "unknown_replay_step", "must reference replay.events[].step"))
            if step in checkpoints:
                issues.append(RouteValidationIssue(f"{path}.step", "duplicate_checkpoint", "must be unique"))
            checkpoints[step] = checkpoint
            state_hash = _non_empty_string(checkpoint.get("state_hash"), f"{path}.state_hash", issues)
            if 0 <= step < len(events) and isinstance(events[step], Mapping):
                event_state_hash = events[step].get("state_hash_after")
                if state_hash is not None and event_state_hash and state_hash != event_state_hash:
                    issues.append(
                        RouteValidationIssue(
                            f"{path}.state_hash",
                            "replay_state_mismatch",
                            "must match replay.events[step].state_hash_after",
                        )
                    )
            _mapping(checkpoint.get("board_summary"), f"{path}.board_summary", issues)
            _mapping(checkpoint.get("evaluation"), f"{path}.evaluation", issues)
            if "evaluation_result" in checkpoint:
                try:
                    evaluation_result = EvaluationResult.from_dict(
                        checkpoint.get("evaluation_result")
                    )
                except (TypeError, ValueError) as exc:
                    issues.append(
                        RouteValidationIssue(
                            f"{path}.evaluation_result",
                            "invalid_evaluation_result",
                            str(exc),
                        )
                    )
                else:
                    if to_canonical_data(evaluation_result.vector) != to_canonical_data(
                        checkpoint.get("evaluation")
                    ) or evaluation_result.total_score != checkpoint.get("score"):
                        issues.append(
                            RouteValidationIssue(
                                f"{path}.evaluation_result",
                                "checkpoint_score_mismatch",
                                "vector and total must match checkpoint evaluation and score",
                            )
                        )

    result = _mapping(root.get("result"), "$.result", issues)
    if result is not None:
        if not isinstance(result.get("success"), bool):
            issues.append(RouteValidationIssue("$.result.success", "expected_boolean", "must be a boolean"))
        complete = root.get("status") == "complete"
        _board_result(result.get("peak_board"), "$.result.peak_board", checkpoints, issues, required=complete)
        _board_result(result.get("terminal_board"), "$.result.terminal_board", checkpoints, issues, required=complete)
        if "durability" in result:
            _durability_result(result.get("durability"), checkpoints, issues)
        if "evaluation_explanation" in result:
            _evaluation_explanation(
                result.get("evaluation_explanation"),
                result.get("terminal_board"),
                issues,
            )
        if "temporary_modifier_observation" in result:
            try:
                assert_valid_temporary_modifier_observation(
                    result.get("temporary_modifier_observation")
                )
            except (TypeError, ValueError) as exc:
                issues.append(
                    RouteValidationIssue(
                        "$.result.temporary_modifier_observation",
                        "invalid_temporary_modifier_observation",
                        str(exc),
                    )
                )

    interruptions = root.get("interruptions", [])
    if not isinstance(interruptions, list):
        issues.append(RouteValidationIssue("$.interruptions", "expected_list", "must be a list"))
    else:
        interruption_config = (
            experiment.get("interruption")
            if isinstance(experiment, Mapping)
            else None
        )
        raw_definitions = (
            interruption_config.get("definitions")
            if isinstance(interruption_config, Mapping)
            else None
        )
        definitions = (
            [item for item in raw_definitions if isinstance(item, Mapping)]
            if isinstance(raw_definitions, list)
            else []
        )
        definitions_by_id = {
            str(item.get("id")): item
            for item in definitions
            if isinstance(item.get("id"), str)
        }
        interruption_sampling = None
        if replay is not None:
            replay_manifest = replay.get("manifest")
            randomness = (
                replay_manifest.get("randomness")
                if isinstance(replay_manifest, Mapping)
                else None
            )
            if isinstance(randomness, Mapping):
                interruption_sampling = randomness.get("interruption_sampling")
        applied_indexes = [
            index
            for index, item in enumerate(interruptions)
            if isinstance(item, Mapping) and item.get("status") == "applied_by_core"
        ]
        final_applied_index = applied_indexes[-1] if applied_indexes else None
        previous_applied_step = -1
        actual_definition_ids: list[str] = []
        for index, raw_interruption in enumerate(interruptions):
            path = f"$.interruptions[{index}]"
            interruption = _mapping(raw_interruption, path, issues)
            if interruption is None:
                continue
            _non_empty_string(interruption.get("interruption_id"), f"{path}.interruption_id", issues)
            at_step = interruption.get("at_step")
            if not isinstance(at_step, int) or at_step < 0 or at_step >= len(events):
                issues.append(RouteValidationIssue(f"{path}.at_step", "unknown_replay_step", "must reference replay.events[].step"))
                continue
            if interruption.get("status") == "applied_by_core":
                definition_id = interruption.get("definition_id")
                if isinstance(definition_id, str):
                    actual_definition_ids.append(definition_id)
                definition = definitions_by_id.get(str(definition_id))
                if definition is None:
                    issues.append(
                        RouteValidationIssue(
                            f"{path}.definition_id",
                            "unknown_interruption_definition",
                            "must reference Experiment interruption.definitions",
                        )
                    )
                else:
                    if interruption.get("interruption_id") != definition_id:
                        issues.append(
                            RouteValidationIssue(
                                f"{path}.interruption_id",
                                "interruption_definition_mismatch",
                                "must equal definition_id",
                            )
                        )
                    for field in ("source_card_code", "source_player"):
                        if interruption.get(field) != definition.get(field):
                            issues.append(
                                RouteValidationIssue(
                                    f"{path}.{field}",
                                    "interruption_definition_mismatch",
                                    f"must match definition.{field}",
                                )
                            )
                    if to_canonical_data(interruption.get("target")) != (
                        to_canonical_data(definition.get("target"))
                    ):
                        issues.append(
                            RouteValidationIssue(
                                f"{path}.target",
                                "interruption_definition_target_mismatch",
                                "must match the Experiment definition target",
                            )
                        )
                    raw_policy = definition.get("candidate_policy")
                    if raw_policy is not None:
                        try:
                            expected_policy = (
                                CoreInterruptionCandidatePolicy.from_dict(
                                    raw_policy,
                                    path=(
                                        "$.experiment.interruption.definitions"
                                        f"[{definitions.index(definition)}]"
                                        ".candidate_policy"
                                    ),
                                )
                            )
                        except InterruptionCandidatePolicyError:
                            expected_policy = None
                        if (
                            expected_policy is not None
                            and interruption.get("candidate_policy_id")
                            != expected_policy.policy_id
                        ):
                            issues.append(
                                RouteValidationIssue(
                                    f"{path}.candidate_policy_id",
                                    "interruption_candidate_policy_mismatch",
                                    "must match the Experiment candidate policy",
                                )
                            )
                    expected_sampling = (
                        interruption_sampling
                        if interruption_config.get("mode") == "sampled"
                        else None
                    )
                    if to_canonical_data(interruption.get("sampling")) != (
                        to_canonical_data(expected_sampling)
                    ):
                        issues.append(
                            RouteValidationIssue(
                                f"{path}.sampling",
                                "interruption_sampling_evidence_mismatch",
                                "must match Replay manifest interruption sampling",
                            )
                        )
                if at_step <= previous_applied_step:
                    issues.append(
                        RouteValidationIssue(
                            f"{path}.at_step",
                            "non_sequential_interruption_step",
                            "must be greater than the previous interruption step",
                        )
                    )
                previous_applied_step = at_step
                try:
                    target = InterruptionTarget.from_dict(interruption.get("target"))
                except (TypeError, ValueError) as exc:
                    issues.append(
                        RouteValidationIssue(
                            f"{path}.target",
                            "invalid_interruption_target",
                            str(exc),
                        )
                    )
                    continue
                raw_opportunity = events[at_step]
                opportunity = (
                    raw_opportunity if isinstance(raw_opportunity, Mapping) else {}
                )
                opportunity_action = opportunity.get("action")
                expected_opportunity = {
                    "chain_index": target.chain_index,
                    "player": target.player,
                    "request_signature": target.request_signature,
                    "state_hash_before": target.state_hash_before,
                    "step": target.step,
                    "turn": target.turn,
                    "turn_action_index": target.turn_action_index,
                }
                actual_opportunity = {
                    "chain_index": opportunity.get("chain_index"),
                    "player": (
                        opportunity_action.get("player")
                        if isinstance(opportunity_action, Mapping)
                        else None
                    ),
                    "request_signature": opportunity.get("request_signature"),
                    "state_hash_before": opportunity.get("state_hash_before"),
                    "step": at_step,
                    "turn": opportunity.get("turn"),
                    "turn_action_index": opportunity.get("turn_action_index"),
                }
                if expected_opportunity != actual_opportunity:
                    issues.append(
                        RouteValidationIssue(
                            f"{path}.target",
                            "interruption_opportunity_mismatch",
                            "must match the interrupted Replay request and State coordinates",
                        )
                    )
                activation_step = interruption.get("activation_step")
                if activation_step != at_step:
                    issues.append(
                        RouteValidationIssue(
                            f"{path}.activation_step",
                            "interruption_activation_step_mismatch",
                            "must equal at_step for a core-applied interruption",
                        )
                    )
                else:
                    activation_event = events[activation_step]
                    activation_action = (
                        activation_event.get("action")
                        if isinstance(activation_event, Mapping)
                        else None
                    )
                if (
                    activation_step == at_step
                    and (
                        not isinstance(activation_action, Mapping)
                        or activation_action.get("kind") != "ACTIVATE_EFFECT"
                    )
                ):
                    issues.append(
                        RouteValidationIssue(
                            f"{path}.activation_step",
                            "interruption_activation_action_mismatch",
                            "must reference an ACTIVATE_EFFECT Action",
                        )
                    )
                response_steps = interruption.get("response_steps")
                if response_steps is None:
                    target_selection_step = interruption.get("target_selection_step")
                    if (
                        not isinstance(target_selection_step, int)
                        or target_selection_step <= at_step
                        or target_selection_step >= len(events)
                    ):
                        issues.append(
                            RouteValidationIssue(
                                f"{path}.target_selection_step",
                                "unknown_interruption_target_selection_step",
                                "must reference a later Replay event",
                            )
                        )
                    elif (
                        not isinstance(events[target_selection_step], Mapping)
                        or not isinstance(
                            events[target_selection_step].get("action"), Mapping
                        )
                        or events[target_selection_step]["action"].get("kind")
                        != "SELECT_CARD"
                    ):
                        issues.append(
                            RouteValidationIssue(
                                f"{path}.target_selection_step",
                                "interruption_target_selection_action_mismatch",
                                "must reference a SELECT_CARD Action",
                            )
                        )
                elif not isinstance(response_steps, list):
                    issues.append(
                        RouteValidationIssue(
                            f"{path}.response_steps",
                            "expected_list",
                            "must be a list",
                        )
                    )
                else:
                    _non_empty_string(
                        interruption.get("candidate_policy_id"),
                        f"{path}.candidate_policy_id",
                        issues,
                    )
                    target_response_steps: list[int] = []
                    for response_index, raw_response_step in enumerate(
                        response_steps
                    ):
                        response_path = (
                            f"{path}.response_steps[{response_index}]"
                        )
                        response_step = _mapping(
                            raw_response_step, response_path, issues
                        )
                        if response_step is None:
                            continue
                        if response_step.get("response_index") != response_index:
                            issues.append(
                                RouteValidationIssue(
                                    f"{response_path}.response_index",
                                    "non_contiguous_interruption_response",
                                    "must equal its list index",
                                )
                            )
                        role = response_step.get("role")
                        if role not in {
                            "confirmation",
                            "cost",
                            "option",
                            "placement",
                            "target",
                        }:
                            issues.append(
                                RouteValidationIssue(
                                    f"{response_path}.role",
                                    "unsupported_interruption_response_role",
                                    "must be a supported candidate policy role",
                                )
                            )
                        action_step = response_step.get("action_step")
                        if (
                            not isinstance(action_step, int)
                            or isinstance(action_step, bool)
                            or action_step <= at_step
                            or action_step >= len(events)
                        ):
                            issues.append(
                                RouteValidationIssue(
                                    f"{response_path}.action_step",
                                    "unknown_interruption_response_step",
                                    "must reference a later Replay event",
                                )
                            )
                            continue
                        response_event = events[action_step]
                        response_action = (
                            response_event.get("action")
                            if isinstance(response_event, Mapping)
                            else None
                        )
                        raw_candidate_ids = response_step.get("candidate_ids")
                        selections = (
                            response_action.get("selections")
                            if isinstance(response_action, Mapping)
                            else None
                        )
                        replay_candidate_ids = (
                            [
                                selection.get("candidate_id")
                                for selection in selections
                                if isinstance(selection, Mapping)
                            ]
                            if isinstance(selections, list)
                            else None
                        )
                        if (
                            not isinstance(raw_candidate_ids, list)
                            or not raw_candidate_ids
                            or raw_candidate_ids != replay_candidate_ids
                        ):
                            issues.append(
                                RouteValidationIssue(
                                    f"{response_path}.candidate_ids",
                                    "interruption_response_candidates_mismatch",
                                    "must match Replay Action selections",
                                )
                            )
                        if role == "target":
                            target_response_steps.append(action_step)
                    target_selection_step = interruption.get(
                        "target_selection_step"
                    )
                    if target_response_steps:
                        if target_selection_step not in target_response_steps:
                            issues.append(
                                RouteValidationIssue(
                                    f"{path}.target_selection_step",
                                    "interruption_target_response_mismatch",
                                    "must reference a target response step",
                                )
                            )
                    elif "target_selection_step" in interruption:
                        issues.append(
                            RouteValidationIssue(
                                f"{path}.target_selection_step",
                                "unexpected_interruption_target_selection_step",
                                "must be absent without a target response",
                            )
                        )
                if index == final_applied_index:
                    lineage = root.get("lineage")
                    if (
                        not isinstance(lineage, Mapping)
                        or lineage.get("fork_step") != at_step
                    ):
                        issues.append(
                            RouteValidationIssue(
                                "$.lineage.fork_step",
                                "interruption_fork_step_mismatch",
                                "must equal the final core-applied interruption at_step",
                            )
                        )
                    if (
                        isinstance(lineage, Mapping)
                        and isinstance(definition, Mapping)
                        and lineage.get("parent_route_id")
                        != definition.get("base_route_id")
                    ):
                        issues.append(
                            RouteValidationIssue(
                                "$.lineage.parent_route_id",
                                "interruption_parent_route_mismatch",
                                "must match the final interruption base_route_id",
                            )
                        )
        if applied_indexes and isinstance(interruption_config, Mapping):
            mode = interruption_config.get("mode")
            if mode == "scripted":
                expected_definition_ids = [
                    str(definition.get("id")) for definition in definitions
                ]
            elif mode == "sampled" and isinstance(interruption_sampling, Mapping):
                expected_definition_ids = [
                    str(interruption_sampling.get("selected_definition_id"))
                ]
            else:
                expected_definition_ids = []
            if actual_definition_ids != expected_definition_ids:
                issues.append(
                    RouteValidationIssue(
                        "$.interruptions",
                        "interruption_definition_order_mismatch",
                        "must match the selected Experiment definition order",
                    )
                )

    _mapping(root.get("lineage", {}), "$.lineage", issues)
    return tuple(issues)


def assert_valid_route_document(document: Any) -> None:
    issues = validate_route_document(document)
    if issues:
        raise ValueError("invalid Route DSL:\n" + "\n".join(str(issue) for issue in issues))
