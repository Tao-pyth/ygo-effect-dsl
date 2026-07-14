from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ygo_effect_dsl.engine.information import (
    DeckOrderKnowledge,
    INFORMATION_POLICY_SCHEMA_VERSION,
    InformationAccessPolicy,
    OpeningHandPolicy,
)


LEGACY_EXPERIMENT_SCHEMA_VERSION = "0.3a"
EXPERIMENT_SCHEMA_VERSION = "0.3b"
SUPPORTED_EXPERIMENT_SCHEMA_VERSIONS = {
    LEGACY_EXPERIMENT_SCHEMA_VERSION,
    EXPERIMENT_SCHEMA_VERSION,
}
INFORMATION_MODES = {
    "complete_information",
    "player_view",
    "sampled_private_state",
}
INTERRUPTION_MODES = {"none", "scripted", "sampled"}
INTERRUPTION_SAMPLING_SCHEMA_VERSION = "interruption-sampling-v1"
INTERRUPTION_SAMPLER_IDS = {"stable-digest-mod-v1"}


@dataclass(frozen=True)
class ExperimentValidationIssue:
    path: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.code}: {self.message}"


def load_experiment_document(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid experiment YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("experiment root must be a mapping")
    return value


def dump_experiment_document(value: Mapping[str, Any], path: str | Path) -> None:
    assert_valid_experiment(value)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(dict(value), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _required_mapping(
    root: Mapping[str, Any],
    name: str,
    issues: list[ExperimentValidationIssue],
) -> Mapping[str, Any] | None:
    path = f"$.{name}"
    if name not in root:
        issues.append(ExperimentValidationIssue(path, "required_field", "is required"))
        return None
    value = root[name]
    if not isinstance(value, Mapping):
        issues.append(ExperimentValidationIssue(path, "expected_mapping", "must be a mapping"))
        return None
    return value


def _non_empty_string(
    value: Any,
    path: str,
    issues: list[ExperimentValidationIssue],
) -> str | None:
    if not isinstance(value, str) or not value:
        issues.append(
            ExperimentValidationIssue(
                path, "expected_non_empty_string", "must be a non-empty string"
            )
        )
        return None
    return value


def _plugin(
    value: Mapping[str, Any] | None,
    path: str,
    issues: list[ExperimentValidationIssue],
) -> None:
    if value is None:
        return
    _non_empty_string(value.get("id"), f"{path}.id", issues)
    _non_empty_string(value.get("version"), f"{path}.version", issues)
    if not isinstance(value.get("config"), Mapping):
        issues.append(
            ExperimentValidationIssue(
                f"{path}.config", "expected_mapping", "must be a mapping"
            )
        )


def _information_policy(
    root: Mapping[str, Any],
    issues: list[ExperimentValidationIssue],
) -> None:
    raw_policy = _required_mapping(root, "information_policy", issues)
    if raw_policy is None:
        return
    allowed_fields = {
        "deck_order",
        "opening_hand",
        "policy_id",
        "sampling_reference",
        "schema_version",
    }
    for field in sorted(set(raw_policy) - allowed_fields):
        issues.append(
            ExperimentValidationIssue(
                f"$.information_policy.{field}",
                "unknown_information_policy_field",
                "is not allowed in information-policy-v1",
            )
        )
    if "viewer" in raw_policy:
        issues.append(
            ExperimentValidationIssue(
                "$.information_policy.viewer",
                "derived_field_not_allowed",
                "must be derived from player.perspective",
            )
        )
    if "sampling_reference" not in raw_policy:
        issues.append(
            ExperimentValidationIssue(
                "$.information_policy.sampling_reference",
                "required_field",
                "is required and must be a mapping or null",
            )
        )
    if raw_policy.get("schema_version") != INFORMATION_POLICY_SCHEMA_VERSION:
        issues.append(
            ExperimentValidationIssue(
                "$.information_policy.schema_version",
                "unsupported_information_policy_schema",
                f"must be {INFORMATION_POLICY_SCHEMA_VERSION!r}",
            )
        )
    _non_empty_string(
        raw_policy.get("policy_id"), "$.information_policy.policy_id", issues
    )
    if raw_policy.get("deck_order") not in {
        item.value for item in DeckOrderKnowledge
    }:
        issues.append(
            ExperimentValidationIssue(
                "$.information_policy.deck_order",
                "unsupported_deck_order_policy",
                "must be 'known' or 'unknown'",
            )
        )
    if raw_policy.get("opening_hand") not in {
        item.value for item in OpeningHandPolicy
    }:
        issues.append(
            ExperimentValidationIssue(
                "$.information_policy.opening_hand",
                "unsupported_opening_hand_policy",
                "must be 'natural', 'fixed', or 'probability_distribution'",
            )
        )
    sampling_reference = raw_policy.get("sampling_reference")
    if sampling_reference is not None and not isinstance(sampling_reference, Mapping):
        issues.append(
            ExperimentValidationIssue(
                "$.information_policy.sampling_reference",
                "expected_mapping_or_null",
                "must be a mapping or null",
            )
        )
    policy_fields_valid = not any(
        issue.path.startswith("$.information_policy") for issue in issues
    )
    if policy_fields_valid:
        try:
            InformationAccessPolicy.from_experiment(root)
        except (TypeError, ValueError) as exc:
            issues.append(
                ExperimentValidationIssue(
                    "$.information_policy",
                    "invalid_information_policy",
                    str(exc),
                )
            )


def validate_experiment(value: Any) -> tuple[ExperimentValidationIssue, ...]:
    issues: list[ExperimentValidationIssue] = []
    if not isinstance(value, Mapping):
        return (
            ExperimentValidationIssue("$", "expected_mapping", "must be a mapping"),
        )
    schema_version = value.get("schema_version")
    if schema_version not in SUPPORTED_EXPERIMENT_SCHEMA_VERSIONS:
        issues.append(
            ExperimentValidationIssue(
                "$.schema_version",
                "unsupported_schema_version",
                f"must be one of {sorted(SUPPORTED_EXPERIMENT_SCHEMA_VERSIONS)}",
            )
        )
    for field in ("experiment_id", "objective", "evaluate_at"):
        _non_empty_string(value.get(field), f"$.{field}", issues)

    deck = _required_mapping(value, "deck", issues)
    if deck is not None:
        _non_empty_string(deck.get("id"), "$.deck.id", issues)
        source = _non_empty_string(deck.get("source"), "$.deck.source", issues)
        if source is not None and source not in {"fixed", "inline", "ydk"}:
            issues.append(
                ExperimentValidationIssue(
                    "$.deck.source",
                    "unsupported_deck_source",
                    "must be 'fixed', 'inline', or 'ydk'",
                )
            )

    player = _required_mapping(value, "player", issues)
    if player is not None:
        for field in ("starting_player", "perspective"):
            if player.get(field) not in (0, 1):
                issues.append(
                    ExperimentValidationIssue(
                        f"$.player.{field}",
                        "invalid_player",
                        "must be 0 or 1",
                    )
                )

    turn_limit = value.get("turn_limit")
    if (
        not isinstance(turn_limit, int)
        or isinstance(turn_limit, bool)
        or turn_limit < 1
    ):
        issues.append(
            ExperimentValidationIssue(
                "$.turn_limit", "invalid_positive_integer", "must be an integer >= 1"
            )
        )
    if value.get("information_mode") not in INFORMATION_MODES:
        issues.append(
            ExperimentValidationIssue(
                "$.information_mode",
                "unsupported_information_mode",
                f"must be one of {sorted(INFORMATION_MODES)}",
            )
        )
    if schema_version == EXPERIMENT_SCHEMA_VERSION:
        _information_policy(value, issues)
    elif schema_version == LEGACY_EXPERIMENT_SCHEMA_VERSION and (
        "information_policy" in value
    ):
        issues.append(
            ExperimentValidationIssue(
                "$.information_policy",
                "field_not_allowed_in_legacy_schema",
                "Experiment 0.3a cannot carry a 0.3b information policy",
            )
        )

    success_predicate = _required_mapping(value, "success_predicate", issues)
    evaluator = _required_mapping(value, "evaluator", issues)
    _plugin(success_predicate, "$.success_predicate", issues)
    _plugin(evaluator, "$.evaluator", issues)

    search = _required_mapping(value, "search", issues)
    if search is not None:
        _non_empty_string(search.get("strategy"), "$.search.strategy", issues)
        budget = search.get("budget")
        if not isinstance(budget, Mapping):
            issues.append(
                ExperimentValidationIssue(
                    "$.search.budget", "expected_mapping", "must be a mapping"
                )
            )
        else:
            present_limits = [
                name for name in ("max_nodes", "max_seconds") if name in budget
            ]
            if not present_limits:
                issues.append(
                    ExperimentValidationIssue(
                        "$.search.budget",
                        "missing_budget_limit",
                        "must define max_nodes or max_seconds",
                    )
                )
            for name in present_limits:
                limit = budget[name]
                invalid = (
                    not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0
                    if name == "max_nodes"
                    else not isinstance(limit, (int, float))
                    or isinstance(limit, bool)
                    or limit <= 0
                )
                if invalid:
                    issues.append(
                        ExperimentValidationIssue(
                            f"$.search.budget.{name}",
                            (
                                "invalid_positive_integer"
                                if name == "max_nodes"
                                else "invalid_positive_number"
                            ),
                            (
                                "must be an integer >= 1"
                                if name == "max_nodes"
                                else "must be greater than 0"
                            ),
                        )
                    )
        parameters = search.get("parameters", {})
        if not isinstance(parameters, Mapping):
            issues.append(
                ExperimentValidationIssue(
                    "$.search.parameters", "expected_mapping", "must be a mapping"
                )
            )

    interruption = _required_mapping(value, "interruption", issues)
    if interruption is not None:
        mode = interruption.get("mode")
        if mode not in INTERRUPTION_MODES:
            issues.append(
                ExperimentValidationIssue(
                    "$.interruption.mode",
                    "unsupported_interruption_mode",
                    f"must be one of {sorted(INTERRUPTION_MODES)}",
                )
            )
        sampling = interruption.get("sampling")
        if mode == "sampled":
            if not isinstance(sampling, Mapping):
                issues.append(
                    ExperimentValidationIssue(
                        "$.interruption.sampling",
                        "expected_mapping",
                        "must be a mapping for sampled mode",
                    )
                )
            else:
                if sampling.get("schema_version") != (
                    INTERRUPTION_SAMPLING_SCHEMA_VERSION
                ):
                    issues.append(
                        ExperimentValidationIssue(
                            "$.interruption.sampling.schema_version",
                            "unsupported_interruption_sampling_schema",
                            f"must be {INTERRUPTION_SAMPLING_SCHEMA_VERSION!r}",
                        )
                    )
                if sampling.get("sampler_id") not in INTERRUPTION_SAMPLER_IDS:
                    issues.append(
                        ExperimentValidationIssue(
                            "$.interruption.sampling.sampler_id",
                            "unsupported_interruption_sampler",
                            f"must be one of {sorted(INTERRUPTION_SAMPLER_IDS)}",
                        )
                    )
                seed = sampling.get("seed")
                if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
                    issues.append(
                        ExperimentValidationIssue(
                            "$.interruption.sampling.seed",
                            "invalid_non_negative_integer",
                            "must be an integer >= 0",
                        )
                    )
        elif sampling is not None:
            issues.append(
                ExperimentValidationIssue(
                    "$.interruption.sampling",
                    "sampling_for_non_sampled_mode",
                    "is only valid when interruption.mode is 'sampled'",
                )
            )
        definitions = interruption.get("definitions")
        if not isinstance(definitions, list):
            issues.append(
                ExperimentValidationIssue(
                    "$.interruption.definitions", "expected_list", "must be a list"
                )
            )
        elif mode == "none" and definitions:
            issues.append(
                ExperimentValidationIssue(
                    "$.interruption.definitions",
                    "definitions_for_none_mode",
                    "must be empty when interruption.mode is 'none'",
                )
            )
        elif mode in {"scripted", "sampled"} and not definitions:
            issues.append(
                ExperimentValidationIssue(
                    "$.interruption.definitions",
                    "missing_interruption_definition",
                    f"must contain at least one definition for {mode} mode",
                )
            )
        else:
            for index, definition in enumerate(definitions):
                path = f"$.interruption.definitions[{index}]"
                if not isinstance(definition, Mapping):
                    issues.append(
                        ExperimentValidationIssue(
                            path, "expected_mapping", "must be a mapping"
                        )
                    )
                    continue
                _non_empty_string(definition.get("id"), f"{path}.id", issues)

    replay = _required_mapping(value, "replay", issues)
    if replay is not None and not isinstance(replay.get("strict_versions"), bool):
        issues.append(
            ExperimentValidationIssue(
                "$.replay.strict_versions",
                "expected_boolean",
                "must be a boolean",
            )
        )
    runner = value.get("runner")
    if runner is not None:
        if not isinstance(runner, Mapping):
            issues.append(
                ExperimentValidationIssue(
                    "$.runner", "expected_mapping", "must be a mapping"
                )
            )
        else:
            _non_empty_string(runner.get("adapter"), "$.runner.adapter", issues)
            _non_empty_string(
                runner.get("scenario_id"), "$.runner.scenario_id", issues
            )
    return tuple(issues)


def assert_valid_experiment(value: Any) -> None:
    issues = validate_experiment(value)
    if issues:
        raise ValueError("invalid Experiment:\n" + "\n".join(str(issue) for issue in issues))


def assert_current_experiment(value: Any) -> None:
    assert_valid_experiment(value)
    if value.get("schema_version") != EXPERIMENT_SCHEMA_VERSION:
        raise ValueError(
            f"Experiment {value.get('schema_version')!r} is a valid legacy artifact; "
            f"explicitly migrate it to {EXPERIMENT_SCHEMA_VERSION!r} before execution"
        )
