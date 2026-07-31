from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


BUILD_PROVENANCE_MANIFEST_SCHEMA_VERSION = "build-provenance-manifest-v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(repo_root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_provenance_manifest(
    *,
    repo_root: str | Path,
    artifacts: list[str | Path],
    build_kind: str,
    source_date_epoch: str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    rows: list[dict[str, Any]] = []
    for raw in artifacts:
        path = Path(raw)
        if not path.is_absolute():
            path = (root / path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"artifact does not exist: {path}")
        rows.append(
            {
                "artifact_name": path.name,
                "path": path.relative_to(root).as_posix()
                if path.is_relative_to(root)
                else str(path),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    identity = to_canonical_data(
        {
            "artifact_count": len(rows),
            "artifacts": sorted(rows, key=lambda item: item["path"]),
            "build_environment": {
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                "github_sha": os.environ.get("GITHUB_SHA"),
                "machine": platform.machine(),
                "os": platform.platform(),
                "python": platform.python_version(),
            },
            "build_kind": build_kind,
            "package_version": __version__,
            "schema_version": BUILD_PROVENANCE_MANIFEST_SCHEMA_VERSION,
            "source": {
                "commit": _git_value(root, "rev-parse", "HEAD"),
                "source_date_epoch": source_date_epoch
                or os.environ.get("SOURCE_DATE_EPOCH"),
                "tree": _git_value(root, "rev-parse", "HEAD^{tree}"),
            },
        }
    )
    return {
        **identity,
        "manifest_id": stable_digest(identity, prefix="buildprovenance_"),
    }


def write_build_provenance_manifest(
    *,
    repo_root: str | Path,
    artifacts: list[str | Path],
    build_kind: str,
    output_path: str | Path,
    checksum_output_path: str | Path | None = None,
    source_date_epoch: str | None = None,
) -> dict[str, Any]:
    manifest = build_provenance_manifest(
        repo_root=repo_root,
        artifacts=artifacts,
        build_kind=build_kind,
        source_date_epoch=source_date_epoch,
    )
    Path(output_path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if checksum_output_path is not None:
        checksums = {
            "artifacts": [
                {
                    "artifact_name": item["artifact_name"],
                    "path": item["path"],
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in manifest["artifacts"]
            ],
            "manifest_id": manifest["manifest_id"],
            "schema_version": "artifact-checksums-v1",
        }
        Path(checksum_output_path).write_text(
            json.dumps(checksums, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="write build artifact checksum and provenance manifests"
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--build-kind", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--checksum-out", type=Path)
    parser.add_argument("--source-date-epoch")
    parser.add_argument("artifacts", nargs="+")
    args = parser.parse_args(argv)
    manifest = write_build_provenance_manifest(
        repo_root=args.repo_root,
        artifacts=args.artifacts,
        build_kind=args.build_kind,
        output_path=args.out,
        checksum_output_path=args.checksum_out,
        source_date_epoch=args.source_date_epoch,
    )
    print(
        "build-provenance-manifest: "
        f"wrote {args.out} manifest_id={manifest['manifest_id']} "
        f"artifacts={manifest['artifact_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
