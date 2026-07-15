from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from ygo_effect_dsl.release_audit import (
    RELEASE_ARTIFACT_AUDIT_SCHEMA_VERSION,
    ReleaseArtifactAuditError,
    audit_release_artifact,
    audit_release_artifacts,
)


ROOT = Path(__file__).parents[1]
POLICY = (
    ROOT / "src/ygo_effect_dsl/resources/distribution-policy-v1.json"
).read_bytes()
POLICY_PATH = "fixture/ygo_effect_dsl/resources/distribution-policy-v1.json"


def _wheel(path: Path, *, extra_name: str = "fixture/module.py") -> None:
    with zipfile.ZipFile(path, mode="w") as archive:
        archive.writestr(POLICY_PATH, POLICY)
        archive.writestr(extra_name, b"pass\n")


def _sdist(path: Path) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for name, raw in ((POLICY_PATH, POLICY), ("fixture/module.py", b"pass\n")):
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))


def test_wheel_and_sdist_audit_preserve_fail_closed_policy(tmp_path: Path) -> None:
    wheel = tmp_path / "fixture.whl"
    sdist = tmp_path / "fixture.tar.gz"
    _wheel(wheel)
    _sdist(sdist)

    report = audit_release_artifacts((wheel, sdist))

    assert report["schema_version"] == RELEASE_ARTIFACT_AUDIT_SCHEMA_VERSION
    assert report["status"] == "passed"
    assert {item["artifact_kind"] for item in report["artifacts"]} == {
        "wheel_or_zip",
        "sdist_or_tar",
    }
    assert all(
        item["third_party_payloads"] == "absent"
        for item in report["artifacts"]
    )


@pytest.mark.parametrize(
    "name",
    [
        "fixture/ocgcore.dll",
        "fixture/cards.cdb",
        "fixture/CardScripts/c100.lua",
        "fixture/premake5.exe",
    ],
)
def test_release_audit_rejects_third_party_payload_candidates(
    tmp_path: Path, name: str
) -> None:
    wheel = tmp_path / "fixture.whl"
    _wheel(wheel, extra_name=name)

    with pytest.raises(ReleaseArtifactAuditError, match="payload candidates"):
        audit_release_artifact(wheel)


def test_release_audit_rejects_enabled_distribution_policy(tmp_path: Path) -> None:
    changed = json.loads(POLICY)
    changed["artifacts"]["ocgcore"]["include_in_release"] = True
    wheel = tmp_path / "fixture.whl"
    with zipfile.ZipFile(wheel, mode="w") as archive:
        archive.writestr(POLICY_PATH, json.dumps(changed))

    with pytest.raises(ReleaseArtifactAuditError, match="enables"):
        audit_release_artifact(wheel)


def test_release_audit_rejects_unsafe_and_link_members(tmp_path: Path) -> None:
    wheel = tmp_path / "unsafe.whl"
    _wheel(wheel, extra_name="C:/external/asset.json")
    with pytest.raises(ReleaseArtifactAuditError, match="unsafe archive"):
        audit_release_artifact(wheel)

    sdist = tmp_path / "linked.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        policy = tarfile.TarInfo(POLICY_PATH)
        policy.size = len(POLICY)
        archive.addfile(policy, io.BytesIO(POLICY))
        link = tarfile.TarInfo("fixture/cards")
        link.type = tarfile.SYMTYPE
        link.linkname = "C:/external/cards"
        archive.addfile(link)
    with pytest.raises(ReleaseArtifactAuditError, match="non-regular"):
        audit_release_artifact(sdist)


def test_windows_executable_build_has_no_external_asset_input() -> None:
    workflow = (ROOT / ".github/workflows/build-windows-exe.yml").read_text(
        encoding="utf-8"
    )
    assert '--add-data "resources;resources"' in workflow
    assert (
        '--add-data "src/ygo_effect_dsl/resources;ygo_effect_dsl/resources"'
        in workflow
    )
    assert "--add-binary" not in workflow
    assert "YGO_EFFECT_DSL_EXTERNAL_ROOT" not in workflow
