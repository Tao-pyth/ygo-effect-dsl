from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ygo_effect_dsl.external.ocgcore import (
    EXTERNAL_ROOT_ENV,
    OcgcoreBootstrapError,
    OcgcoreLayout,
    _verify_required_asset_files,
    _configure_reproducible_link,
    acquire_source,
    default_external_root,
    ensure_premake,
    load_ocgcore_asset_lock,
    load_ocgcore_lock,
    _parse_submodule_status,
    verify_source,
)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def test_bundled_ocgcore_lock_pins_source_toolchain_and_policy() -> None:
    lock = load_ocgcore_lock()

    assert lock.lock_id == "ocgcore-v11.0-win-x64-msvc-v1"
    assert lock.source["commit"] == "158aebe758be3c46249c75d602e3f16d63d2ef31"
    assert lock.source["tree"] == "23915a17e8e0d6b0b64ffc868bf0067a55e00aa0"
    assert lock.source["submodules"][0]["commit"] == "1ab3208a1fceb12fca8f24ba57d6e13c5bff15e3"
    assert lock.tool["archive_sha256"] == "87cfa10ed52fd1f4e835f738ac1033ff302035758671400fec078b700c622c54"
    assert lock.data["policy"] == {
        "runtime_network_access": False,
        "system_wide_install": False,
        "redistribute_binary": False,
        "assets_included": False,
    }


def test_bundled_asset_lock_pins_compatible_repositories_and_files() -> None:
    lock = load_ocgcore_asset_lock()

    assert lock.lock_id == "ocgcore-assets-202504-v1"
    assert lock.data["compatible_core_api"] == {"major": 11, "minor": 0}
    assert lock.repositories["card_scripts"]["commit"] == (
        "c8e9c0bcd026a5ccc303bbc73881b8f86f818657"
    )
    assert lock.repositories["card_database"]["commit"] == (
        "f89c9a4be9a5f193e29b788e3cf880563f4f79b4"
    )
    assert lock.data["policy"]["redistribute_assets"] is False
    assert lock.data["policy"]["license_review_required"] is True


def test_required_asset_file_verification_fails_closed(tmp_path: Path) -> None:
    asset = tmp_path / "cards.cdb"
    asset.write_bytes(b"fixture")
    required = {
        "cards.cdb": {
            "size": len(b"fixture"),
            "sha256": "f16d05ec6b29248d2c61adb1e9263f78e4f7bace1b955014a2d17872cfe4064d",
        }
    }
    assert _verify_required_asset_files(tmp_path, required)[0]["path"] == "cards.cdb"

    asset.write_bytes(b"tampered")
    with pytest.raises(OcgcoreBootstrapError, match="size/SHA-256"):
        _verify_required_asset_files(tmp_path, required)


def test_external_root_can_be_shared_by_dev_ci_and_packaged_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "external"
    monkeypatch.setenv(EXTERNAL_ROOT_ENV, str(configured))

    assert default_external_root() == configured.resolve()


def test_offline_source_acquisition_never_falls_back_to_network(tmp_path: Path) -> None:
    lock = load_ocgcore_lock()
    layout = OcgcoreLayout.create(lock, tmp_path)

    with pytest.raises(OcgcoreBootstrapError, match="offline mode: source is not cached"):
        acquire_source(lock, layout, offline=True)


def test_offline_premake_rejects_checksum_mismatch(tmp_path: Path) -> None:
    lock = load_ocgcore_lock()
    layout = OcgcoreLayout.create(lock, tmp_path)
    archive = layout.tools / "downloads" / str(lock.tool["archive"])
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"not the pinned archive")

    with pytest.raises(OcgcoreBootstrapError, match="checksum mismatch"):
        ensure_premake(lock, layout, offline=True)


def test_submodule_status_preserves_git_state_prefix() -> None:
    commit = "1ab3208a1fceb12fca8f24ba57d6e13c5bff15e3"

    assert _parse_submodule_status(f" {commit} lua/src (heads/master)") == {"lua/src": commit}
    with pytest.raises(OcgcoreBootstrapError, match="not at its locked commit"):
        _parse_submodule_status(f"+{commit} lua/src (heads/master)")


def test_reproducible_link_options_are_applied_to_locked_configuration(tmp_path: Path) -> None:
    project = tmp_path / "ocgcoreshared.vcxproj"
    project.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Release|x64'">
    <Link><GenerateDebugInformation>true</GenerateDebugInformation></Link>
  </ItemDefinitionGroup>
</Project>
""",
        encoding="utf-8",
    )

    lock = load_ocgcore_lock()
    _configure_reproducible_link(project, lock)
    updated = project.read_text(encoding="utf-8")

    assert lock.build["virtual_build_drive"] == "Y:"
    assert "/Brepro /PDBALTPATH:%_PDB% %(AdditionalOptions)" in updated
    assert "<GenerateDebugInformation>false</GenerateDebugInformation>" in updated


def test_source_verification_detects_local_changes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init")
    _git(source, "config", "user.email", "test@example.invalid")
    _git(source, "config", "user.name", "Test")
    (source / "core.cpp").write_text("int core = 1;\n", encoding="utf-8")
    _git(source, "add", "core.cpp")
    _git(source, "commit", "-m", "fixture")
    _git(source, "remote", "add", "origin", str(source))
    commit = _git(source, "rev-parse", "HEAD")
    tree = _git(source, "rev-parse", "HEAD^{tree}")

    bundled = load_ocgcore_lock()
    custom_data = json.loads(json.dumps(bundled.data))
    custom_data["source"].update(
        {
            "repository": str(source),
            "ref": "HEAD",
            "commit": commit,
            "tree": tree,
            "submodules": [],
        }
    )
    lock_path = tmp_path / "fixture.lock.json"
    lock_path.write_text(json.dumps(custom_data), encoding="utf-8")
    fixture_lock = load_ocgcore_lock(lock_path)

    assert verify_source(fixture_lock, source)["commit"] == commit
    (source / "core.cpp").write_text("int core = 2;\n", encoding="utf-8")

    with pytest.raises(OcgcoreBootstrapError, match="local changes"):
        verify_source(fixture_lock, source)
