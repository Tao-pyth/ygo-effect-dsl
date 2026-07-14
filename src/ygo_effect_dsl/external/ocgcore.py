from __future__ import annotations

import ctypes
import hashlib
import importlib.resources
import json
import os
import platform
import shutil
import stat
import subprocess
import urllib.request
import xml.etree.ElementTree as ElementTree
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


LOCK_RESOURCE = "ocgcore-v11.0-win-x64.lock.json"
ASSET_LOCK_RESOURCE = "ocgcore-assets-202504.lock.json"
EXTERNAL_ROOT_ENV = "YGO_EFFECT_DSL_EXTERNAL_ROOT"
VS_ROOT_ENV = "YGO_EFFECT_DSL_VS_ROOT"


class OcgcoreBootstrapError(ValueError):
    """Raised when a pinned ocgcore dependency cannot be provisioned safely."""


@dataclass(frozen=True)
class OcgcoreLock:
    data: Mapping[str, Any]
    sha256: str

    @property
    def lock_id(self) -> str:
        return str(self.data["lock_id"])

    @property
    def source(self) -> Mapping[str, Any]:
        return self.data["source"]

    @property
    def tool(self) -> Mapping[str, Any]:
        return self.data["tool"]

    @property
    def build(self) -> Mapping[str, Any]:
        return self.data["build"]

    @property
    def api(self) -> Mapping[str, Any]:
        return self.data["api"]


@dataclass(frozen=True)
class OcgcoreAssetLock:
    data: Mapping[str, Any]
    sha256: str

    @property
    def lock_id(self) -> str:
        return str(self.data["lock_id"])

    @property
    def repositories(self) -> Mapping[str, Mapping[str, Any]]:
        return self.data["repositories"]


@dataclass(frozen=True)
class OcgcoreAssets:
    scripts_root: Path
    database_path: Path
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class OcgcoreLayout:
    external_root: Path
    install_root: Path
    source: Path
    build: Path
    runtime: Path
    assets: Path
    tools: Path
    manifest: Path
    asset_manifest: Path

    @classmethod
    def create(cls, lock: OcgcoreLock, external_root: str | Path | None = None) -> "OcgcoreLayout":
        root = Path(external_root) if external_root is not None else default_external_root()
        root = root.expanduser().resolve()
        install_root = root / lock.lock_id
        return cls(
            external_root=root,
            install_root=install_root,
            source=install_root / "source",
            build=install_root / "build",
            runtime=install_root / "runtime",
            assets=install_root / "assets",
            tools=install_root / "tools",
            manifest=install_root / "install-manifest.json",
            asset_manifest=install_root / "asset-manifest.json",
        )


def _validate_lock(data: Mapping[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise OcgcoreBootstrapError("unsupported ocgcore lock schema")
    for field in ("lock_id", "source", "api", "tool", "build", "policy"):
        if field not in data:
            raise OcgcoreBootstrapError(f"ocgcore lock is missing {field!r}")
    for field in ("repository", "ref", "commit", "tree", "license", "submodules"):
        if field not in data["source"]:
            raise OcgcoreBootstrapError(f"ocgcore source lock is missing {field!r}")
    if data["policy"].get("runtime_network_access") is not False:
        raise OcgcoreBootstrapError("runtime network access must remain disabled")
    if data["policy"].get("redistribute_binary") is not False:
        raise OcgcoreBootstrapError("binary redistribution must remain disabled until license review")


def load_ocgcore_lock(path: str | Path | None = None) -> OcgcoreLock:
    if path is None:
        resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(LOCK_RESOURCE)
        raw = resource.read_bytes()
    else:
        raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise OcgcoreBootstrapError("ocgcore lock root must be an object")
    _validate_lock(data)
    return OcgcoreLock(data=data, sha256=hashlib.sha256(raw).hexdigest())


def _validate_asset_lock(data: Mapping[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise OcgcoreBootstrapError("unsupported ocgcore asset lock schema")
    for field in ("lock_id", "compatible_core_api", "repositories", "policy"):
        if field not in data:
            raise OcgcoreBootstrapError(f"ocgcore asset lock is missing {field!r}")
    repositories = data["repositories"]
    if set(repositories) != {"card_scripts", "card_database"}:
        raise OcgcoreBootstrapError("ocgcore asset lock repository set is invalid")
    for name, repository in repositories.items():
        for field in (
            "directory",
            "repository",
            "ref",
            "commit",
            "tree",
            "license",
            "required_files",
        ):
            if field not in repository:
                raise OcgcoreBootstrapError(
                    f"ocgcore asset repository {name!r} is missing {field!r}"
                )
        if not repository["required_files"]:
            raise OcgcoreBootstrapError(
                f"ocgcore asset repository {name!r} has no required files"
            )
    policy = data["policy"]
    if policy.get("runtime_network_access") is not False:
        raise OcgcoreBootstrapError("asset runtime network access must remain disabled")
    if policy.get("redistribute_assets") is not False:
        raise OcgcoreBootstrapError("asset redistribution must remain disabled")


def load_ocgcore_asset_lock(path: str | Path | None = None) -> OcgcoreAssetLock:
    if path is None:
        resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
            ASSET_LOCK_RESOURCE
        )
        raw = resource.read_bytes()
    else:
        raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise OcgcoreBootstrapError("ocgcore asset lock root must be an object")
    _validate_asset_lock(data)
    return OcgcoreAssetLock(data=data, sha256=hashlib.sha256(raw).hexdigest())


def default_external_root() -> Path:
    configured = os.environ.get(EXTERNAL_ROOT_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise OcgcoreBootstrapError("LOCALAPPDATA is required on Windows")
        return Path(local_app_data) / "ygo-effect-dsl" / "external"
    cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_home) if cache_home else Path.home() / ".cache"
    return base / "ygo-effect-dsl" / "external"


def _run(args: Sequence[str | Path], *, cwd: Path | None = None) -> str:
    command = [str(value) for value in args]
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
        raise OcgcoreBootstrapError(f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}")
    return completed.stdout.rstrip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_owned_tree(path: Path, install_root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = install_root.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise OcgcoreBootstrapError(f"refusing to remove path outside the lock directory: {path}")

    def make_writable_and_retry(function: Any, name: str, _error: Any) -> None:
        os.chmod(name, stat.S_IWRITE)
        function(name)

    shutil.rmtree(path, onerror=make_writable_and_retry)


def _publish_owned_tree(partial: Path, destination: Path, install_root: Path) -> None:
    if destination.exists():
        _remove_owned_tree(destination, install_root)
    try:
        shutil.copytree(partial, destination)
        _remove_owned_tree(partial, install_root)
    except Exception:
        if destination.exists():
            try:
                _remove_owned_tree(destination, install_root)
            except OSError:
                pass
        raise


def _normalise_repository(url: str) -> str:
    return url.rstrip("/").removesuffix(".git").lower()


def _parse_submodule_status(output: str) -> dict[str, str]:
    observed: dict[str, str] = {}
    for line in output.splitlines():
        if not line:
            continue
        if line[0] != " ":
            raise OcgcoreBootstrapError(f"submodule is not at its locked commit: {line}")
        columns = line[1:].split()
        if len(columns) < 2:
            raise OcgcoreBootstrapError(f"invalid submodule status: {line}")
        observed[columns[1].replace("\\", "/")] = columns[0]
    return observed


def verify_source(lock: OcgcoreLock, source: Path) -> dict[str, Any]:
    if not source.is_dir():
        raise OcgcoreBootstrapError(f"ocgcore source is missing: {source}")
    commit = _run(["git", "rev-parse", "HEAD"], cwd=source)
    tree = _run(["git", "rev-parse", "HEAD^{tree}"], cwd=source)
    origin = _run(["git", "remote", "get-url", "origin"], cwd=source)
    dirty = _run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=source)
    expected = lock.source
    if commit != expected["commit"]:
        raise OcgcoreBootstrapError(f"ocgcore commit mismatch: expected {expected['commit']}, got {commit}")
    if tree != expected["tree"]:
        raise OcgcoreBootstrapError(f"ocgcore tree mismatch: expected {expected['tree']}, got {tree}")
    if _normalise_repository(origin) != _normalise_repository(str(expected["repository"])):
        raise OcgcoreBootstrapError(f"ocgcore origin mismatch: {origin}")
    if dirty:
        raise OcgcoreBootstrapError(f"ocgcore source contains local changes:\n{dirty}")

    submodules = _parse_submodule_status(_run(["git", "submodule", "status", "--recursive"], cwd=source))
    expected_submodules = {item["path"]: item for item in expected["submodules"]}
    if set(submodules) != set(expected_submodules):
        raise OcgcoreBootstrapError("ocgcore submodule set does not match the lock")
    observed_submodules: list[dict[str, str]] = []
    for path, item in expected_submodules.items():
        actual_commit = submodules[path]
        if actual_commit != item["commit"]:
            raise OcgcoreBootstrapError(
                f"submodule {path} mismatch: expected {item['commit']}, got {actual_commit}"
            )
        submodule_origin = _run(["git", "remote", "get-url", "origin"], cwd=source / path)
        if _normalise_repository(submodule_origin) != _normalise_repository(str(item["repository"])):
            raise OcgcoreBootstrapError(f"submodule {path} origin mismatch: {submodule_origin}")
        observed_submodules.append(
            {"path": path, "repository": submodule_origin, "commit": actual_commit}
        )
    return {
        "repository": origin,
        "ref": expected["ref"],
        "commit": commit,
        "tree": tree,
        "commit_time": _run(["git", "show", "-s", "--format=%cI", "HEAD"], cwd=source),
        "license": expected["license"],
        "submodules": observed_submodules,
    }


def _verify_required_asset_files(
    root: Path, required_files: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    for relative_name, expected in sorted(required_files.items()):
        path = root / Path(relative_name)
        if not path.is_file():
            raise OcgcoreBootstrapError(f"locked asset file is missing: {path}")
        size = path.stat().st_size
        digest = _sha256(path)
        if size != int(expected["size"]) or digest != str(expected["sha256"]):
            raise OcgcoreBootstrapError(
                f"locked asset file does not match size/SHA-256: {path}"
            )
        observed.append(
            {
                "path": relative_name.replace("\\", "/"),
                "size": size,
                "sha256": digest,
            }
        )
    return observed


def verify_asset_repository(
    name: str, expected: Mapping[str, Any], root: Path
) -> dict[str, Any]:
    if not root.is_dir():
        raise OcgcoreBootstrapError(f"ocgcore asset repository is missing: {root}")
    commit = _run(["git", "rev-parse", "HEAD"], cwd=root)
    tree = _run(["git", "rev-parse", "HEAD^{tree}"], cwd=root)
    origin = _run(["git", "remote", "get-url", "origin"], cwd=root)
    dirty = _run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root)
    if commit != expected["commit"]:
        raise OcgcoreBootstrapError(
            f"{name} commit mismatch: expected {expected['commit']}, got {commit}"
        )
    if tree != expected["tree"]:
        raise OcgcoreBootstrapError(
            f"{name} tree mismatch: expected {expected['tree']}, got {tree}"
        )
    if _normalise_repository(origin) != _normalise_repository(str(expected["repository"])):
        raise OcgcoreBootstrapError(f"{name} origin mismatch: {origin}")
    if dirty:
        raise OcgcoreBootstrapError(f"{name} contains local changes:\n{dirty}")
    return {
        "name": name,
        "directory": expected["directory"],
        "repository": origin,
        "ref": expected["ref"],
        "commit": commit,
        "tree": tree,
        "commit_time": _run(["git", "show", "-s", "--format=%cI", "HEAD"], cwd=root),
        "license": expected["license"],
        "required_files": _verify_required_asset_files(root, expected["required_files"]),
    }


def _fetch_locked_commit(
    *, repository: str, commit: str, destination: Path
) -> None:
    """Acquire one immutable commit without depending on a movable ref."""

    _run(["git", "init", destination])
    _run(["git", "remote", "add", "origin", repository], cwd=destination)
    _run(
        [
            "git",
            "fetch",
            "--filter=blob:none",
            "--no-tags",
            "--depth=1",
            "origin",
            commit,
        ],
        cwd=destination,
    )
    fetched = _run(["git", "rev-parse", "FETCH_HEAD"], cwd=destination)
    if fetched != commit:
        raise OcgcoreBootstrapError(
            f"locked commit fetch mismatch: expected {commit}, got {fetched}"
        )
    _run(["git", "checkout", "--detach", commit], cwd=destination)


def _acquire_asset_repository(
    lock: OcgcoreAssetLock,
    layout: OcgcoreLayout,
    name: str,
    *,
    offline: bool,
) -> dict[str, Any]:
    expected = lock.repositories[name]
    destination = layout.assets / str(expected["directory"])
    if destination.exists():
        return verify_asset_repository(name, expected, destination)
    if offline:
        raise OcgcoreBootstrapError(
            f"offline mode: {name} is not cached at {destination}"
        )
    layout.assets.mkdir(parents=True, exist_ok=True)
    partial = layout.assets / f".{expected['directory']}.partial"
    if partial.exists():
        _remove_owned_tree(partial, layout.install_root)
    try:
        _fetch_locked_commit(
            repository=str(expected["repository"]),
            commit=str(expected["commit"]),
            destination=partial,
        )
        observed = verify_asset_repository(name, expected, partial)
        partial.replace(destination)
        return observed
    except Exception:
        if partial.exists():
            try:
                _remove_owned_tree(partial, layout.install_root)
            except OSError:
                pass
        raise


def bootstrap_ocgcore_assets(
    *,
    external_root: str | Path | None = None,
    core_lock_path: str | Path | None = None,
    asset_lock_path: str | Path | None = None,
    offline: bool = False,
) -> dict[str, Any]:
    core_lock = load_ocgcore_lock(core_lock_path)
    asset_lock = load_ocgcore_asset_lock(asset_lock_path)
    compatible = asset_lock.data["compatible_core_api"]
    if (int(compatible["major"]), int(compatible["minor"])) != (
        int(core_lock.api["major"]),
        int(core_lock.api["minor"]),
    ):
        raise OcgcoreBootstrapError("asset lock is incompatible with the core API lock")
    layout = OcgcoreLayout.create(core_lock, external_root)
    repositories = {
        name: _acquire_asset_repository(
            asset_lock, layout, name, offline=offline
        )
        for name in sorted(asset_lock.repositories)
    }
    manifest = {
        "schema_version": 1,
        "core_lock_id": core_lock.lock_id,
        "asset_lock_id": asset_lock.lock_id,
        "asset_lock_sha256": asset_lock.sha256,
        "provisioned_at": datetime.now(timezone.utc).isoformat(),
        "repositories": repositories,
        "policy": dict(asset_lock.data["policy"]),
    }
    partial = layout.asset_manifest.with_suffix(".json.partial")
    partial.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    partial.replace(layout.asset_manifest)
    return manifest


def verify_ocgcore_assets(
    *,
    external_root: str | Path | None = None,
    core_lock_path: str | Path | None = None,
    asset_lock_path: str | Path | None = None,
) -> dict[str, Any]:
    core_lock = load_ocgcore_lock(core_lock_path)
    asset_lock = load_ocgcore_asset_lock(asset_lock_path)
    layout = OcgcoreLayout.create(core_lock, external_root)
    if not layout.asset_manifest.is_file():
        raise OcgcoreBootstrapError(
            f"ocgcore asset manifest is missing: {layout.asset_manifest}"
        )
    manifest = json.loads(layout.asset_manifest.read_text(encoding="utf-8"))
    if (
        manifest.get("core_lock_id") != core_lock.lock_id
        or manifest.get("asset_lock_id") != asset_lock.lock_id
        or manifest.get("asset_lock_sha256") != asset_lock.sha256
    ):
        raise OcgcoreBootstrapError("asset manifest does not match the bundled locks")
    observed = {
        name: verify_asset_repository(
            name,
            expected,
            layout.assets / str(expected["directory"]),
        )
        for name, expected in sorted(asset_lock.repositories.items())
    }
    return {
        "ok": True,
        "core_lock_id": core_lock.lock_id,
        "asset_lock_id": asset_lock.lock_id,
        "repositories": observed,
        "policy": dict(asset_lock.data["policy"]),
    }


def resolve_ocgcore_assets(
    *,
    external_root: str | Path | None = None,
    core_lock_path: str | Path | None = None,
    asset_lock_path: str | Path | None = None,
) -> OcgcoreAssets:
    manifest = verify_ocgcore_assets(
        external_root=external_root,
        core_lock_path=core_lock_path,
        asset_lock_path=asset_lock_path,
    )
    core_lock = load_ocgcore_lock(core_lock_path)
    asset_lock = load_ocgcore_asset_lock(asset_lock_path)
    layout = OcgcoreLayout.create(core_lock, external_root)
    scripts = asset_lock.repositories["card_scripts"]
    database = asset_lock.repositories["card_database"]
    return OcgcoreAssets(
        scripts_root=layout.assets / str(scripts["directory"]),
        database_path=(
            layout.assets
            / str(database["directory"])
            / next(iter(database["required_files"]))
        ),
        manifest=manifest,
    )


def _finalize_source(lock: OcgcoreLock, layout: OcgcoreLayout, partial: Path) -> dict[str, Any]:
    if layout.source.exists():
        raise OcgcoreBootstrapError(f"refusing to replace existing source: {layout.source}")
    try:
        shutil.copytree(partial, layout.source)
        observed = verify_source(lock, layout.source)
        _remove_owned_tree(partial, layout.install_root)
        return observed
    except Exception:
        if layout.source.exists():
            try:
                _remove_owned_tree(layout.source, layout.install_root)
            except OSError:
                pass
        raise


def acquire_source(lock: OcgcoreLock, layout: OcgcoreLayout, *, offline: bool) -> dict[str, Any]:
    if layout.source.exists():
        return verify_source(lock, layout.source)
    if offline:
        raise OcgcoreBootstrapError(f"offline mode: source is not cached at {layout.source}")
    layout.install_root.mkdir(parents=True, exist_ok=True)
    partial = layout.install_root / ".source.partial"
    if partial.exists():
        try:
            verify_source(lock, partial)
        except OcgcoreBootstrapError:
            _remove_owned_tree(partial, layout.install_root)
        else:
            return _finalize_source(lock, layout, partial)
    try:
        _run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "--branch",
                str(lock.source["ref"]),
                str(lock.source["repository"]),
                partial,
            ]
        )
        _run(["git", "checkout", "--detach", str(lock.source["commit"])], cwd=partial)
        _run(["git", "submodule", "sync", "--recursive"], cwd=partial)
        _run(["git", "submodule", "update", "--init", "--recursive", "--checkout"], cwd=partial)
        verify_source(lock, partial)
        return _finalize_source(lock, layout, partial)
    except Exception:
        if partial.exists():
            try:
                _remove_owned_tree(partial, layout.install_root)
            except OSError:
                pass
        raise


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ygo-effect-dsl-bootstrap/1"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def ensure_premake(lock: OcgcoreLock, layout: OcgcoreLayout, *, offline: bool) -> Path:
    tool = lock.tool
    downloads = layout.tools / "downloads"
    archive = downloads / str(tool["archive"])
    executable_dir = layout.tools / f"premake-{tool['version']}"
    executable = executable_dir / str(tool["executable"])

    if archive.exists() and (
        archive.stat().st_size != int(tool["archive_size"])
        or _sha256(archive) != tool["archive_sha256"]
    ):
        if offline:
            raise OcgcoreBootstrapError(f"offline mode: cached Premake archive checksum mismatch: {archive}")
        archive.unlink()
    if not archive.exists():
        if offline:
            raise OcgcoreBootstrapError(f"offline mode: Premake archive is not cached at {archive}")
        downloads.mkdir(parents=True, exist_ok=True)
        partial = archive.with_suffix(archive.suffix + ".partial")
        partial.unlink(missing_ok=True)
        try:
            _download(str(tool["url"]), partial)
            if partial.stat().st_size != int(tool["archive_size"]) or _sha256(partial) != tool["archive_sha256"]:
                raise OcgcoreBootstrapError("downloaded Premake archive does not match the lock")
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)

    if executable.exists():
        if (
            executable.stat().st_size == int(tool["executable_size"])
            and _sha256(executable) == tool["executable_sha256"]
        ):
            return executable
        if offline:
            raise OcgcoreBootstrapError(f"offline mode: cached Premake executable checksum mismatch: {executable}")

    partial_dir = layout.tools / ".premake.partial"
    if partial_dir.exists():
        _remove_owned_tree(partial_dir, layout.install_root)
    if executable_dir.exists():
        _remove_owned_tree(executable_dir, layout.install_root)
    try:
        partial_dir.mkdir(parents=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(partial_dir)
        extracted = partial_dir / str(tool["executable"])
        if (
            not extracted.is_file()
            or extracted.stat().st_size != int(tool["executable_size"])
            or _sha256(extracted) != tool["executable_sha256"]
        ):
            raise OcgcoreBootstrapError("extracted Premake executable does not match the lock")
        partial_dir.replace(executable_dir)
        return executable
    except Exception:
        if partial_dir.exists():
            try:
                _remove_owned_tree(partial_dir, layout.install_root)
            except OSError:
                pass
        raise


def _candidate_vs_roots() -> list[Path]:
    roots: list[Path] = []
    for name in (VS_ROOT_ENV, "VSINSTALLDIR"):
        value = os.environ.get(name)
        if value:
            roots.append(Path(value))
    roots.append(Path("C:/BuildTools2022"))
    for base_name in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(base_name)
        if not base:
            continue
        root = Path(base) / "Microsoft Visual Studio" / "2022"
        roots.extend([root / "BuildTools", root / "Community", root / "Professional", root / "Enterprise"])
    return roots


def _find_visual_studio() -> dict[str, str] | None:
    for root in _candidate_vs_roots():
        msbuild = root / "MSBuild" / "Current" / "Bin" / "MSBuild.exe"
        vcvars = root / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
        msvc_root = root / "VC" / "Tools" / "MSVC"
        versions = sorted((path for path in msvc_root.glob("*") if path.is_dir()), reverse=True)
        if not msbuild.is_file() or not vcvars.is_file() or not versions:
            continue
        compiler = versions[0] / "bin" / "Hostx64" / "x64" / "cl.exe"
        if compiler.is_file():
            return {
                "root": str(root.resolve()),
                "msbuild": str(msbuild.resolve()),
                "vcvars64": str(vcvars.resolve()),
                "compiler": str(compiler.resolve()),
                "compiler_version": versions[0].name,
            }
    return None


def doctor_ocgcore(
    *, external_root: str | Path | None = None, lock_path: str | Path | None = None
) -> dict[str, Any]:
    lock = load_ocgcore_lock(lock_path)
    layout = OcgcoreLayout.create(lock, external_root)
    visual_studio = _find_visual_studio() if os.name == "nt" else None
    git = shutil.which("git")
    premake = layout.tools / f"premake-{lock.tool['version']}" / str(lock.tool["executable"])
    build_drive_available = not Path(f"{lock.build['virtual_build_drive']}/").exists()
    return {
        "ok": bool(git and visual_studio and build_drive_available),
        "lock_id": lock.lock_id,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "git": git,
        "visual_studio": visual_studio,
        "premake": str(premake) if premake.is_file() else None,
        "virtual_build_drive": lock.build["virtual_build_drive"],
        "virtual_build_drive_available": build_drive_available,
        "external_root": str(layout.external_root),
    }


def _prepare_build_workspace(layout: OcgcoreLayout) -> tuple[Path, Path]:
    partial = layout.install_root / ".build.partial"
    if partial.exists():
        _remove_owned_tree(partial, layout.install_root)
    work_source = partial / "worktree"
    shutil.copytree(layout.source, work_source, ignore=shutil.ignore_patterns(".git"))
    return partial, work_source


def _read_api_version(binary: Path) -> tuple[int, int]:
    library: ctypes.CDLL | None = None
    try:
        library = ctypes.CDLL(str(binary))
        get_version = library.OCG_GetVersion
        get_version.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        get_version.restype = None
        major = ctypes.c_int()
        minor = ctypes.c_int()
        get_version(ctypes.byref(major), ctypes.byref(minor))
        return major.value, minor.value
    except (OSError, AttributeError) as exc:
        raise OcgcoreBootstrapError(f"could not validate OCG_GetVersion in {binary}: {exc}") from exc
    finally:
        if library is not None and os.name == "nt":
            free_library = ctypes.WinDLL("kernel32", use_last_error=True).FreeLibrary
            free_library.argtypes = [ctypes.c_void_p]
            free_library.restype = ctypes.c_int
            handle = library._handle
            if free_library(handle) == 0:
                raise OcgcoreBootstrapError(
                    f"could not release ocgcore library handle for {binary}"
                )
            library._handle = 0


def _locked_definition_group(
    root: ElementTree.Element, namespace: str, lock: OcgcoreLock, project: Path
) -> ElementTree.Element:
    expected_condition = (
        f"'$(Configuration)|$(Platform)'=="
        f"'{lock.build['configuration']}|{lock.build['architecture']}'"
    )
    for definition_group in root.findall(f"{{{namespace}}}ItemDefinitionGroup"):
        if definition_group.get("Condition") == expected_condition:
            return definition_group
    raise OcgcoreBootstrapError(f"locked build configuration is missing in {project}")


def _configure_reproducible_link(project: Path, lock: OcgcoreLock) -> None:
    namespace = "http://schemas.microsoft.com/developer/msbuild/2003"
    ElementTree.register_namespace("", namespace)
    document = ElementTree.parse(project)
    root = document.getroot()
    definition_group = _locked_definition_group(root, namespace, lock, project)
    linker = definition_group.find(f"{{{namespace}}}Link")
    if linker is None:
        raise OcgcoreBootstrapError(f"Release linker settings are missing in {project}")
    additional = linker.find(f"{{{namespace}}}AdditionalOptions")
    if additional is None:
        additional = ElementTree.SubElement(linker, f"{{{namespace}}}AdditionalOptions")
    additional.text = " ".join([*lock.build["link_options"], "%(AdditionalOptions)"])
    debug_information = linker.find(f"{{{namespace}}}GenerateDebugInformation")
    if debug_information is None:
        debug_information = ElementTree.SubElement(
            linker, f"{{{namespace}}}GenerateDebugInformation"
        )
    debug_information.text = str(lock.build["generate_debug_information"]).lower()
    document.write(project, encoding="utf-8", xml_declaration=True)


@contextmanager
def _virtual_build_root(lock: OcgcoreLock, work_source: Path) -> Iterator[Path]:
    drive = str(lock.build["virtual_build_drive"])
    virtual_root = Path(f"{drive}/")
    if virtual_root.exists():
        raise OcgcoreBootstrapError(
            f"locked virtual build drive {drive} is already in use; it will not be replaced"
        )
    _run(["subst", drive, work_source])
    try:
        yield virtual_root
    except BaseException:
        subprocess.run(["subst", drive, "/D"], check=False, capture_output=True)
        raise
    else:
        completed = subprocess.run(["subst", drive, "/D"], check=False, capture_output=True)
        if completed.returncode != 0:
            raise OcgcoreBootstrapError(f"failed to release virtual build drive {drive}")


def build_ocgcore(lock: OcgcoreLock, layout: OcgcoreLayout, premake: Path) -> dict[str, Any]:
    if os.name != "nt":
        raise OcgcoreBootstrapError("this lock supports Windows x64 only")
    visual_studio = _find_visual_studio()
    if visual_studio is None:
        raise OcgcoreBootstrapError(
            f"Visual Studio 2022 C++ Build Tools were not found; set {VS_ROOT_ENV} to the install root"
        )
    build_partial, work_source = _prepare_build_workspace(layout)
    runtime_partial = layout.install_root / ".runtime.partial"
    if runtime_partial.exists():
        _remove_owned_tree(runtime_partial, layout.install_root)
    try:
        with _virtual_build_root(lock, work_source) as virtual_root:
            _run([premake, str(lock.build["generator"])], cwd=virtual_root)
            solution = work_source / "build" / "ocgcore.sln"
            if not solution.is_file():
                raise OcgcoreBootstrapError(f"Premake did not generate {solution}")
            shared_project = work_source / "build" / "ocgcoreshared.vcxproj"
            _configure_reproducible_link(shared_project, lock)
            properties = [
                f"/p:Configuration={lock.build['configuration']}",
                f"/p:Platform={lock.build['architecture']}",
            ]
            properties.extend(
                f"/p:{name}={value}"
                for name, value in sorted(lock.build["msbuild_properties"].items())
            )
            virtual_solution = virtual_root / "build" / "ocgcore.sln"
            _run(
                [
                    visual_studio["msbuild"],
                    virtual_solution,
                    "/m",
                    f"/t:{lock.build['target']}",
                    *properties,
                ],
                cwd=virtual_root,
            )
        built_binary = (
            work_source
            / "bin"
            / str(lock.build["architecture"])
            / str(lock.build["configuration"]).lower()
            / str(lock.build["binary"])
        )
        if not built_binary.is_file():
            raise OcgcoreBootstrapError(f"MSBuild did not produce {built_binary}")

        runtime_partial.mkdir(parents=True)
        runtime_binary = runtime_partial / str(lock.build["binary"])
        shutil.copy2(built_binary, runtime_binary)
        api_major, api_minor = _read_api_version(runtime_binary)
        if (api_major, api_minor) != (int(lock.api["major"]), int(lock.api["minor"])):
            raise OcgcoreBootstrapError(
                f"ocgcore API mismatch: expected {lock.api['major']}.{lock.api['minor']}, "
                f"got {api_major}.{api_minor}"
            )
    except Exception:
        if build_partial.exists():
            _remove_owned_tree(build_partial, layout.install_root)
        if runtime_partial.exists():
            _remove_owned_tree(runtime_partial, layout.install_root)
        raise

    _publish_owned_tree(build_partial, layout.build, layout.install_root)
    _publish_owned_tree(runtime_partial, layout.runtime, layout.install_root)
    runtime_binary = layout.runtime / str(lock.build["binary"])
    return {
        "generator": lock.build["generator"],
        "configuration": lock.build["configuration"],
        "architecture": lock.build["architecture"],
        "target": lock.build["target"],
        "cpp_standard": lock.build["cpp_standard"],
        "compiler_family": lock.build["compiler_family"],
        "compiler": visual_studio["compiler"],
        "compiler_version": visual_studio["compiler_version"],
        "msbuild": visual_studio["msbuild"],
        "msbuild_properties": dict(lock.build["msbuild_properties"]),
        "link_options": list(lock.build["link_options"]),
        "generate_debug_information": lock.build["generate_debug_information"],
        "virtual_build_drive": lock.build["virtual_build_drive"],
        "premake": {
            "path": str(premake),
            "version": lock.tool["version"],
            "sha256": _sha256(premake),
        },
        "api": {"major": api_major, "minor": api_minor},
        "binary": {
            "path": str(runtime_binary),
            "size": runtime_binary.stat().st_size,
            "sha256": _sha256(runtime_binary),
        },
    }


def _write_manifest(
    lock: OcgcoreLock,
    layout: OcgcoreLayout,
    source: Mapping[str, Any],
    build: Mapping[str, Any] | None,
) -> dict[str, Any]:
    manifest = {
        "schema_version": 1,
        "lock_id": lock.lock_id,
        "lock_sha256": lock.sha256,
        "provisioned_at": datetime.now(timezone.utc).isoformat(),
        "source": dict(source),
        "build": dict(build) if build is not None else None,
        "layout": {
            "source": str(layout.source),
            "build": str(layout.build),
            "runtime": str(layout.runtime),
            "assets": str(layout.assets),
            "tools": str(layout.tools),
        },
        "policy": dict(lock.data["policy"]),
    }
    layout.install_root.mkdir(parents=True, exist_ok=True)
    partial = layout.manifest.with_suffix(".json.partial")
    partial.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    partial.replace(layout.manifest)
    return manifest


def bootstrap_ocgcore(
    *,
    external_root: str | Path | None = None,
    lock_path: str | Path | None = None,
    offline: bool = False,
    source_only: bool = False,
) -> dict[str, Any]:
    lock = load_ocgcore_lock(lock_path)
    layout = OcgcoreLayout.create(lock, external_root)
    layout.assets.mkdir(parents=True, exist_ok=True)
    source = acquire_source(lock, layout, offline=offline)
    if source_only:
        return _write_manifest(lock, layout, source, None)
    premake = ensure_premake(lock, layout, offline=offline)
    build = build_ocgcore(lock, layout, premake)
    return _write_manifest(lock, layout, source, build)


def verify_ocgcore(
    *, external_root: str | Path | None = None, lock_path: str | Path | None = None
) -> dict[str, Any]:
    lock = load_ocgcore_lock(lock_path)
    layout = OcgcoreLayout.create(lock, external_root)
    source = verify_source(lock, layout.source)
    if not layout.manifest.is_file():
        raise OcgcoreBootstrapError(f"install manifest is missing: {layout.manifest}")
    manifest = json.loads(layout.manifest.read_text(encoding="utf-8"))
    if manifest.get("lock_id") != lock.lock_id or manifest.get("lock_sha256") != lock.sha256:
        raise OcgcoreBootstrapError("install manifest does not match the bundled lock")
    build = manifest.get("build")
    if build is not None:
        binary = layout.runtime / str(lock.build["binary"])
        if not binary.is_file():
            raise OcgcoreBootstrapError(f"ocgcore runtime binary is missing: {binary}")
        expected_binary = build.get("binary", {})
        if binary.stat().st_size != expected_binary.get("size") or _sha256(binary) != expected_binary.get("sha256"):
            raise OcgcoreBootstrapError("ocgcore runtime binary does not match the install manifest")
        api = _read_api_version(binary)
        if api != (int(lock.api["major"]), int(lock.api["minor"])):
            raise OcgcoreBootstrapError(f"ocgcore runtime API mismatch: {api[0]}.{api[1]}")
    return {"ok": True, "lock_id": lock.lock_id, "source": source, "build": build}


def resolve_ocgcore_runtime(
    *, external_root: str | Path | None = None, lock_path: str | Path | None = None
) -> Path:
    result = verify_ocgcore(external_root=external_root, lock_path=lock_path)
    if result["build"] is None:
        raise OcgcoreBootstrapError("ocgcore was provisioned as source-only; no runtime is available")
    lock = load_ocgcore_lock(lock_path)
    return OcgcoreLayout.create(lock, external_root).runtime / str(lock.build["binary"])
