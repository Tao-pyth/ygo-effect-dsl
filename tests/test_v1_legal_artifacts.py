from __future__ import annotations

import json
import tomllib
from pathlib import Path

from ygo_effect_dsl.external.licensing import load_distribution_policy
from ygo_effect_dsl.external.ocgcore import load_ocgcore_asset_lock, load_ocgcore_lock


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / "docs" / "release" / "evidence"


def _json(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def test_v1_sbom_matches_pyproject_dependency_surface() -> None:
    sbom = _json("v1_0_0_sbom.json")
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    requirements = {component.get("requirement") for component in sbom["components"]}
    assert sbom["schema_version"] == "v1-sbom-v1"
    assert sbom["artifact_scope"] == ["wheel", "sdist", "windows_executable", "installer"]
    assert project["name"] == "ygo-effect-dsl"
    assert set(project["dependencies"]) <= requirements
    for group in project["optional-dependencies"].values():
        assert set(group) <= requirements
    assert set(pyproject["build-system"]["requires"]) <= requirements
    assert sbom["external_local_only_components"] == [
        "ocgcore",
        "card_scripts",
        "card_database",
        "lua",
        "premake",
    ]
    assert all(component["license"] == "NOASSERTION" for component in sbom["components"])


def test_v1_asset_allowlist_matches_distribution_policy_and_locks() -> None:
    allowlist = _json("v1_0_0_asset_allowlist.json")
    policy = load_distribution_policy()
    core_lock = load_ocgcore_lock()
    asset_lock = load_ocgcore_asset_lock()
    rows = {row["artifact_id"]: row for row in allowlist["external_local_only_assets"]}

    assert allowlist["schema_version"] == "v1-asset-allowlist-v1"
    assert allowlist["default_action"] == "reject"
    assert allowlist["release_artifact_allowed_third_party_payloads"] == []
    assert set(rows) == set(policy.artifacts)
    assert all(row["include_in_release"] is False for row in rows.values())
    assert rows["ocgcore"]["commit"] == core_lock.source["commit"]
    assert rows["ocgcore"]["source_tree"] == core_lock.source["tree"]
    assert rows["ocgcore"]["license"] == policy.artifacts["ocgcore"]["license"]
    assert rows["card_scripts"]["commit"] == (
        asset_lock.repositories["card_scripts"]["commit"]
    )
    assert rows["card_scripts"]["source_tree"] == (
        asset_lock.repositories["card_scripts"]["tree"]
    )
    assert rows["card_scripts"]["required_files"] == (
        asset_lock.repositories["card_scripts"]["required_files"]
    )
    assert rows["card_database"]["commit"] == (
        asset_lock.repositories["card_database"]["commit"]
    )
    assert rows["card_database"]["license"] == "NOASSERTION"
    assert rows["card_database"]["required_files"] == (
        asset_lock.repositories["card_database"]["required_files"]
    )
    assert rows["premake"]["archive_sha256"] == core_lock.tool["archive_sha256"]
    assert rows["premake"]["executable_sha256"] == core_lock.tool["executable_sha256"]


def test_v1_release_artifacts_have_sbom_notice_and_allowlist_mapping() -> None:
    composition = _json("v1_0_0_release_artifact_composition.json")
    expected_artifacts = {"wheel", "sdist", "windows_executable", "installer"}

    assert composition["schema_version"] == "v1-release-artifact-composition-v1"
    assert {row["artifact_kind"] for row in composition["artifacts"]} == expected_artifacts
    for row in composition["artifacts"]:
        assert row["sbom"] == "docs/release/evidence/v1_0_0_sbom.json"
        assert row["notice"] == "docs/release/evidence/v1_0_0_third_party_notices.md"
        assert row["asset_allowlist"] == (
            "docs/release/evidence/v1_0_0_asset_allowlist.json"
        )
        assert row["release_audit_required"] is True
        assert row["third_party_payload_policy"] == "none_allowed"
        assert (REPO_ROOT / row["sbom"]).exists()
        assert (REPO_ROOT / row["notice"]).exists()
        assert (REPO_ROOT / row["asset_allowlist"]).exists()


def test_v1_third_party_notice_does_not_authorize_bundling() -> None:
    notice = (EVIDENCE / "v1_0_0_third_party_notices.md").read_text(encoding="utf-8")

    assert "approves no bundled third-party" in notice
    assert "not release payloads" in notice
    assert "not legal approval" in notice
    assert "NOASSERTION" in notice
