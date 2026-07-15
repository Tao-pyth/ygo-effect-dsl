from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


RELEASE_ARTIFACT_AUDIT_SCHEMA_VERSION = "release-artifact-audit-v1"
POLICY_SUFFIX = "ygo_effect_dsl/resources/distribution-policy-v1.json"
FORBIDDEN_SUFFIXES = {".cdb", ".dll", ".exe", ".lua"}
FORBIDDEN_PATH_PARTS = {"babelcdb", "cardscripts", "ygopro-core"}


class ReleaseArtifactAuditError(ValueError):
    """Raised when a package artifact crosses the distribution boundary."""


def _normalized_member(name: str) -> PurePosixPath:
    normalized = PurePosixPath(name.replace("\\", "/"))
    has_windows_drive = bool(normalized.parts and normalized.parts[0].endswith(":"))
    if normalized.is_absolute() or has_windows_drive or ".." in normalized.parts:
        raise ReleaseArtifactAuditError(f"unsafe archive member path: {name!r}")
    return normalized


def _validate_members(names: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(str(_normalized_member(name)) for name in names)
    forbidden: list[str] = []
    for name in normalized:
        path = PurePosixPath(name)
        lowered_parts = {part.lower() for part in path.parts}
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            forbidden.append(name)
        elif lowered_parts & FORBIDDEN_PATH_PARTS:
            forbidden.append(name)
    if forbidden:
        raise ReleaseArtifactAuditError(
            "third-party payload candidates found: " + ", ".join(sorted(forbidden))
        )
    return normalized


def _validate_policy(raw: bytes, *, artifact: Path) -> str:
    try:
        policy = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseArtifactAuditError(
            f"{artifact.name} has an invalid distribution policy"
        ) from exc
    if policy.get("project", {}).get("release_status") != "blocked":
        raise ReleaseArtifactAuditError(
            f"{artifact.name} does not preserve the fail-closed project policy"
        )
    artifacts = policy.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ReleaseArtifactAuditError(
            f"{artifact.name} has no third-party artifact policy"
        )
    if any(item.get("include_in_release") is not False for item in artifacts.values()):
        raise ReleaseArtifactAuditError(
            f"{artifact.name} enables a third-party release payload"
        )
    policy_id = policy.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id:
        raise ReleaseArtifactAuditError(f"{artifact.name} has no policy_id")
    return policy_id


def audit_release_artifact(path: str | Path) -> dict[str, Any]:
    artifact = Path(path)
    raw_artifact = artifact.read_bytes()
    if zipfile.is_zipfile(artifact):
        with zipfile.ZipFile(artifact) as archive:
            links = [
                item.filename
                for item in archive.infolist()
                if stat.S_ISLNK((item.external_attr >> 16) & 0xFFFF)
            ]
            if links:
                raise ReleaseArtifactAuditError(
                    f"{artifact.name} contains symbolic links: "
                    + ", ".join(sorted(links))
                )
            file_names = tuple(
                item.filename for item in archive.infolist() if not item.is_dir()
            )
            members = _validate_members(file_names)
            policy_members = [name for name in members if name.endswith(POLICY_SUFFIX)]
            if len(policy_members) != 1:
                raise ReleaseArtifactAuditError(
                    f"{artifact.name} must contain exactly one distribution policy"
                )
            policy_raw = archive.read(policy_members[0])
            kind = "wheel_or_zip"
    elif tarfile.is_tarfile(artifact):
        with tarfile.open(artifact, mode="r:*") as archive:
            archive_members = tuple(archive.getmembers())
            special = tuple(
                item.name
                for item in archive_members
                if not item.isfile() and not item.isdir()
            )
            if special:
                raise ReleaseArtifactAuditError(
                    f"{artifact.name} contains non-regular members: "
                    + ", ".join(sorted(special))
                )
            regular = tuple(item for item in archive_members if item.isfile())
            members = _validate_members(item.name for item in regular)
            policy_members = [name for name in members if name.endswith(POLICY_SUFFIX)]
            if len(policy_members) != 1:
                raise ReleaseArtifactAuditError(
                    f"{artifact.name} must contain exactly one distribution policy"
                )
            selected = archive.getmember(policy_members[0])
            extracted = archive.extractfile(selected)
            if extracted is None:
                raise ReleaseArtifactAuditError(
                    f"{artifact.name} distribution policy cannot be read"
                )
            policy_raw = extracted.read()
            kind = "sdist_or_tar"
    else:
        raise ReleaseArtifactAuditError(
            f"unsupported release artifact format: {artifact.name}"
        )
    policy_id = _validate_policy(policy_raw, artifact=artifact)
    return {
        "artifact_kind": kind,
        "filename": artifact.name,
        "member_count": len(members),
        "policy_id": policy_id,
        "sha256": hashlib.sha256(raw_artifact).hexdigest(),
        "third_party_payloads": "absent",
    }


def audit_release_artifacts(paths: Iterable[str | Path]) -> dict[str, Any]:
    reports = tuple(audit_release_artifact(path) for path in paths)
    if not reports:
        raise ReleaseArtifactAuditError("at least one release artifact is required")
    return {
        "artifacts": list(reports),
        "schema_version": RELEASE_ARTIFACT_AUDIT_SCHEMA_VERSION,
        "status": "passed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="fail-close audit of project wheel and sdist contents"
    )
    parser.add_argument("artifacts", nargs="+")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            audit_release_artifacts(args.artifacts),
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
