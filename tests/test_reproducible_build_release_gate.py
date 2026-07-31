from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_build_provenance
from ygo_effect_dsl.spikes.build_provenance_manifest import (
    BUILD_PROVENANCE_MANIFEST_SCHEMA_VERSION,
    write_build_provenance_manifest,
)
from ygo_effect_dsl.spikes.reproducible_build_release_gate import (
    V1_BUILD_PROVENANCE_SCHEMA_VERSION,
    evaluate_v1_build_provenance,
    read_v1_build_provenance,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_build_provenance.json"
)


def test_build_provenance_manifest_writes_hashes_and_checksums(tmp_path: Path) -> None:
    artifact = tmp_path / "dist" / "artifact.whl"
    artifact.parent.mkdir()
    artifact.write_bytes(b"example-artifact")
    manifest_path = tmp_path / "build-provenance.json"
    checksum_path = tmp_path / "checksums.json"

    manifest = write_build_provenance_manifest(
        repo_root=tmp_path,
        artifacts=[artifact],
        build_kind="unit-test",
        output_path=manifest_path,
        checksum_output_path=checksum_path,
        source_date_epoch="12345",
    )

    expected_sha = hashlib.sha256(b"example-artifact").hexdigest()
    checksums = json.loads(checksum_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == BUILD_PROVENANCE_MANIFEST_SCHEMA_VERSION
    assert manifest["artifact_count"] == 1
    assert manifest["artifacts"][0]["sha256"] == expected_sha
    assert manifest["artifacts"][0]["size_bytes"] == len(b"example-artifact")
    assert manifest["source"]["source_date_epoch"] == "12345"
    assert manifest["manifest_id"].startswith("buildprovenance_")
    assert checksums["schema_version"] == "artifact-checksums-v1"
    assert checksums["artifacts"][0]["sha256"] == expected_sha
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest


def test_v1_build_provenance_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_build_provenance(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_BUILD_PROVENANCE_SCHEMA_VERSION
    assert evidence["issue"] == 171
    assert evidence["passed"] is True
    assert set(checks) == {
        "artifact_composition_covers_release_artifacts",
        "ci_generates_checksums_and_provenance",
        "fixed_build_environment_documented",
        "manifest_writer_records_artifact_hashes_and_source",
        "tests_cover_reproducible_build_gate",
    }
    assert all(check["passed"] is True for check in checks.values())


def test_committed_v1_build_provenance_matches_current_checkout() -> None:
    assert read_v1_build_provenance(EVIDENCE_PATH) == evaluate_v1_build_provenance(
        REPO_ROOT
    )


def test_v1_build_provenance_cli_writes_evidence(tmp_path: Path, capsys) -> None:
    output = tmp_path / "v1-build-provenance.json"

    status = cmd_v1_build_provenance(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-build-provenance: passed" in captured.out
    assert read_v1_build_provenance(output) == evaluate_v1_build_provenance(REPO_ROOT)
