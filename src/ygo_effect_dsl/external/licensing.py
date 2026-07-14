from __future__ import annotations

import hashlib
import importlib.resources
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


POLICY_RESOURCE = "distribution-policy-v1.json"
EXPECTED_ARTIFACTS = {
    "ocgcore",
    "card_scripts",
    "card_database",
    "lua",
    "premake",
}


class DistributionPolicyError(ValueError):
    """Raised when distribution is not authorized by the checked-in policy."""


@dataclass(frozen=True)
class DistributionPolicy:
    data: Mapping[str, Any]
    sha256: str

    @property
    def policy_id(self) -> str:
        return str(self.data["policy_id"])

    @property
    def artifacts(self) -> Mapping[str, Mapping[str, Any]]:
        return self.data["artifacts"]


def _validate_policy(data: Mapping[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise DistributionPolicyError("unsupported distribution policy schema")
    for field in (
        "policy_id",
        "legal_review_required",
        "project",
        "artifacts",
        "repository_material",
        "controls",
    ):
        if field not in data:
            raise DistributionPolicyError(f"distribution policy is missing {field!r}")
    if data["legal_review_required"] is not True:
        raise DistributionPolicyError("legal review must remain required")
    if data["project"].get("release_status") != "blocked":
        raise DistributionPolicyError("project releases must remain blocked until a license is chosen")
    artifacts = data["artifacts"]
    if set(artifacts) != EXPECTED_ARTIFACTS:
        raise DistributionPolicyError("distribution policy artifact set is invalid")
    for artifact_id, artifact in artifacts.items():
        for field in (
            "kind",
            "source",
            "license",
            "local_prototype_acquisition",
            "include_in_release",
            "commercial_bundle_status",
            "review_requirements",
        ):
            if field not in artifact:
                raise DistributionPolicyError(
                    f"distribution artifact {artifact_id!r} is missing {field!r}"
                )
        if artifact["include_in_release"] is not False:
            raise DistributionPolicyError(
                f"distribution artifact {artifact_id!r} cannot be release-enabled in policy v1"
            )
        if not artifact["review_requirements"]:
            raise DistributionPolicyError(
                f"distribution artifact {artifact_id!r} has no review requirements"
            )
    controls = data["controls"]
    if controls.get("external_files_location") != "user_cache_only":
        raise DistributionPolicyError("external files must remain in the user cache")
    for field in ("runtime_network_access", "implicit_download", "system_wide_install"):
        if controls.get(field) is not False:
            raise DistributionPolicyError(f"distribution control {field!r} must remain disabled")
    if controls.get("release_requires_explicit_artifact_allowlist") is not True:
        raise DistributionPolicyError("release artifact allowlisting must remain required")


def load_distribution_policy(path: str | Path | None = None) -> DistributionPolicy:
    if path is None:
        resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
            POLICY_RESOURCE
        )
        raw = resource.read_bytes()
    else:
        raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise DistributionPolicyError("distribution policy root must be an object")
    _validate_policy(data)
    return DistributionPolicy(data=data, sha256=hashlib.sha256(raw).hexdigest())


def assert_release_bundle_allowed(
    artifact_ids: Sequence[str],
    *,
    policy: DistributionPolicy | None = None,
) -> None:
    checked_policy = policy or load_distribution_policy()
    if checked_policy.data["project"]["release_status"] != "allowed":
        raise DistributionPolicyError(
            "release is blocked: the project has no approved distribution license"
        )
    unknown = sorted(set(artifact_ids) - set(checked_policy.artifacts))
    if unknown:
        raise DistributionPolicyError(f"unknown release artifacts: {', '.join(unknown)}")
    blocked = sorted(
        artifact_id
        for artifact_id in artifact_ids
        if checked_policy.artifacts[artifact_id]["include_in_release"] is not True
    )
    if blocked:
        raise DistributionPolicyError(
            f"release artifacts are not approved for bundling: {', '.join(blocked)}"
        )
