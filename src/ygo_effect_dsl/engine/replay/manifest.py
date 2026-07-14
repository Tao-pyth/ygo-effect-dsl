from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.replay.errors import (
    ReplayEnvironmentMismatchError,
    ReplayFormatError,
    ReplayManifestIncompleteError,
)


REPLAY_MANIFEST_SCHEMA_VERSION = "ygo-replay-manifest-v1"
RANDOM_TRACE_POLICY = "raw-core-frames-and-script-log-random-events-v3"
REQUIRED_PATHS = (
    "environment.project.replay_schema",
    "environment.project.bridge_protocol",
    "environment.project.snapshot_schema",
    "environment.core.api",
    "environment.core.lock_id",
    "environment.core.source_commit",
    "environment.core.binary_sha256",
    "environment.core.custom_patches",
    "environment.assets.lock_id",
    "environment.assets.card_scripts_commit",
    "environment.assets.card_database_commit",
    "environment.assets.constant_sha256",
    "environment.assets.utility_sha256",
    "environment.assets.database_sha256",
    "environment.instrumentation.direct_random_trace.enabled",
    "environment.instrumentation.direct_random_trace.script_sha256",
    "environment.instrumentation.direct_random_trace.schema_version",
    "randomness.core_seed",
    "randomness.python_random_used",
    "randomness.trace_policy",
    "rules.duel_flags",
    "rules.master_rule",
    "rules.forbidden_limited_list",
    "rules.unsafe_lua_libraries",
    "initial_conditions.snapshot_hash",
    "initial_conditions.snapshot_kind",
    "initial_conditions.starting_player",
    "initial_conditions.deck_order_in_snapshot",
)
SAMPLED_PRIVATE_STATE_REQUIRED_PATHS = (
    "randomness.opening_hand_sampling.schema_version",
    "randomness.opening_hand_sampling.sampler_id",
    "randomness.opening_hand_sampling.seed",
    "randomness.opening_hand_sampling.sampling_policy_id",
    "randomness.opening_hand_sampling.information_policy_id",
    "randomness.opening_hand_sampling.selected_index",
    "randomness.opening_hand_sampling.result.hands_by_player",
    "randomness.opening_hand_sampling.sample_id",
    "initial_conditions.opening_hand_kind",
)
_MISSING = object()


def _at_path(root: Mapping[str, Any], path: str) -> Any:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


@dataclass(frozen=True)
class ReplayManifestV03a:
    environment: Mapping[str, Any]
    randomness: Mapping[str, Any]
    rules: Mapping[str, Any]
    initial_conditions: Mapping[str, Any]
    schema_version: str = REPLAY_MANIFEST_SCHEMA_VERSION

    def to_identity_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "environment": self.environment,
                "initial_conditions": self.initial_conditions,
                "randomness": self.randomness,
                "rules": self.rules,
                "schema_version": self.schema_version,
            }
        )

    @property
    def missing_requirements(self) -> tuple[str, ...]:
        identity = self.to_identity_dict()
        missing: list[str] = []
        required_paths = REQUIRED_PATHS
        if self.initial_conditions.get("snapshot_kind") == "sampled_private_state":
            required_paths += SAMPLED_PRIVATE_STATE_REQUIRED_PATHS
        for path in required_paths:
            value = _at_path(identity, path)
            if value is _MISSING or value is None or value == "":
                missing.append(path)
        if self.randomness.get("python_random_used") is True and self.randomness.get(
            "python_seed"
        ) is None:
            missing.append("randomness.python_seed")
        if self.randomness.get("trace_policy") != RANDOM_TRACE_POLICY:
            if "randomness.trace_policy" not in missing:
                missing.append("randomness.trace_policy")
        return tuple(missing)

    @property
    def reproducible(self) -> bool:
        return self.schema_version == REPLAY_MANIFEST_SCHEMA_VERSION and not (
            self.missing_requirements
        )

    @property
    def manifest_hash(self) -> str:
        return stable_digest(self.to_identity_dict(), prefix="manifest_")

    def assert_reproducible(self) -> None:
        if self.schema_version != REPLAY_MANIFEST_SCHEMA_VERSION:
            raise ReplayManifestIncompleteError(
                f"unsupported replay manifest schema {self.schema_version!r}"
            )
        if self.missing_requirements:
            raise ReplayManifestIncompleteError(
                "replay manifest is not reproducible; missing: "
                + ", ".join(self.missing_requirements)
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_identity_dict(),
            "manifest_hash": self.manifest_hash,
            "missing_requirements": list(self.missing_requirements),
            "reproducible": self.reproducible,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReplayManifestV03a":
        for field in (
            "environment",
            "initial_conditions",
            "randomness",
            "rules",
            "schema_version",
        ):
            if field not in data:
                raise ReplayManifestIncompleteError(
                    f"replay manifest is missing {field!r}"
                )
        for field in ("environment", "initial_conditions", "randomness", "rules"):
            if not isinstance(data[field], Mapping):
                raise ReplayFormatError(f"replay manifest {field} must be a mapping")
        manifest = cls(
            environment=dict(data["environment"]),
            initial_conditions=dict(data["initial_conditions"]),
            randomness=dict(data["randomness"]),
            rules=dict(data["rules"]),
            schema_version=str(data["schema_version"]),
        )
        supplied_hash = data.get("manifest_hash")
        if supplied_hash is not None and supplied_hash != manifest.manifest_hash:
            raise ReplayFormatError("replay manifest hash does not match its identity fields")
        return manifest


@dataclass(frozen=True)
class ReplayManifestDifference:
    path: str
    recorded: Any
    current: Any


def first_manifest_difference(
    recorded: ReplayManifestV03a, current: ReplayManifestV03a
) -> ReplayManifestDifference | None:
    def compare(left: Any, right: Any, path: str) -> ReplayManifestDifference | None:
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            for key in sorted(set(left) | set(right)):
                next_path = f"{path}.{key}" if path else str(key)
                if key not in left:
                    return ReplayManifestDifference(next_path, _MISSING, right[key])
                if key not in right:
                    return ReplayManifestDifference(next_path, left[key], _MISSING)
                difference = compare(left[key], right[key], next_path)
                if difference is not None:
                    return difference
            return None
        if isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                return ReplayManifestDifference(f"{path}.length", len(left), len(right))
            for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
                difference = compare(left_item, right_item, f"{path}[{index}]")
                if difference is not None:
                    return difference
            return None
        if left != right:
            return ReplayManifestDifference(path, left, right)
        return None

    return compare(recorded.to_identity_dict(), current.to_identity_dict(), "")


def assert_manifest_matches(
    recorded: ReplayManifestV03a, current: ReplayManifestV03a
) -> None:
    recorded.assert_reproducible()
    current.assert_reproducible()
    difference = first_manifest_difference(recorded, current)
    if difference is not None:
        raise ReplayEnvironmentMismatchError(
            difference.path,
            "<missing>" if difference.recorded is _MISSING else difference.recorded,
            "<missing>" if difference.current is _MISSING else difference.current,
        )
