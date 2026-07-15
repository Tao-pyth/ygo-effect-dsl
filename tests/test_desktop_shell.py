from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ygo_effect_dsl.desktop.bridge import DesktopBridge
from ygo_effect_dsl.desktop.shell import (
    DEFAULT_WINDOW_SIZE,
    MINIMUM_WINDOW_SIZE,
    DesktopStartupError,
    SingleInstanceLock,
    find_webview2_installations,
    preflight_desktop_runtime,
    start_desktop,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_dependency_and_entrypoint_are_optional() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_section = pyproject.split("[project.optional-dependencies]", 1)[0]
    desktop_section = pyproject.split("desktop = [", 1)[1].split("]", 1)[0]

    assert "pywebview" not in project_section
    assert '"pywebview==6.2.1"' in desktop_section
    assert 'ygo-effect-dsl = "ygo_effect_dsl.cli.main:main"' in pyproject
    assert 'ygo-effect-dsl-desktop = "ygo_effect_dsl.desktop.shell:main"' in pyproject


def _runtime(tmp_path: Path, version: str = "150.0.4078.65") -> dict[str, str]:
    root = tmp_path / "Microsoft" / "EdgeWebView" / "Application" / version
    root.mkdir(parents=True)
    (root / "msedgewebview2.exe").write_bytes(b"fixture")
    return {"LOCALAPPDATA": str(tmp_path)}


def test_webview2_and_pywebview_preflight_fail_before_window_creation(
    tmp_path: Path,
) -> None:
    with pytest.raises(DesktopStartupError, match="requires Windows") as platform_error:
        preflight_desktop_runtime(
            platform_name="linux",
            environ={},
            installed_pywebview_version="6.2.1",
        )
    assert platform_error.value.code == "unsupported_platform"

    with pytest.raises(DesktopStartupError, match="was not found") as missing:
        preflight_desktop_runtime(
            platform_name="win32",
            environ={},
            installed_pywebview_version="6.2.1",
        )
    assert missing.value.code == "webview2_runtime_missing"

    with pytest.raises(DesktopStartupError, match="does not match") as mismatch:
        preflight_desktop_runtime(
            platform_name="win32",
            environ=_runtime(tmp_path),
            installed_pywebview_version="6.2.0",
        )
    assert mismatch.value.code == "pywebview_version_mismatch"


def test_webview2_probe_uses_numeric_version_order(tmp_path: Path) -> None:
    environment = _runtime(tmp_path, "99.0.0.1")
    _runtime(tmp_path, "150.0.0.1")
    installations = find_webview2_installations(environment)
    selected = preflight_desktop_runtime(
        platform_name="win32",
        environ=environment,
        installed_pywebview_version="6.2.1",
    )

    assert [item.version for item in installations] == ["99.0.0.1", "150.0.0.1"]
    assert selected.version == "150.0.0.1"


def test_single_instance_lock_releases_for_next_launch(tmp_path: Path) -> None:
    path = tmp_path / "desktop.lock"
    with SingleInstanceLock(path):
        assert path.is_file()
    with SingleInstanceLock(path):
        assert path.is_file()
    assert path.read_bytes()


def test_start_desktop_uses_packaged_frontend_and_single_bridge_method(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    class Supervisor:
        health = "stopped"

        def __init__(self, *_: Any, **__: Any) -> None:
            captured["supervisor"] = self

        def start(self) -> None:
            self.health = "running"
            captured["supervisor_started"] = True

        def stop(self) -> None:
            self.health = "stopped"
            captured["supervisor_stopped"] = True

    class Window:
        def create_file_dialog(self, *_: Any, **__: Any) -> None:
            return None

    def create_window(title: str, **kwargs: Any) -> Window:
        captured["title"] = title
        captured.update(kwargs)
        return Window()

    def start(**kwargs: Any) -> None:
        captured["start"] = kwargs

    webview = SimpleNamespace(
        OPEN_DIALOG=1,
        create_window=create_window,
        start=start,
    )
    start_desktop(
        data_root=tmp_path,
        webview_module=webview,
        supervisor_factory=Supervisor,  # type: ignore[arg-type]
    )

    assert captured["url"].startswith("file:")
    assert captured["width"] == DEFAULT_WINDOW_SIZE[0]
    assert captured["height"] == DEFAULT_WINDOW_SIZE[1]
    assert captured["min_size"] == MINIMUM_WINDOW_SIZE
    assert isinstance(captured["js_api"], DesktopBridge)
    assert captured["start"] == {
        "debug": False,
        "gui": "edgechromium",
        "private_mode": True,
    }
    assert captured["supervisor_started"] is True
    assert captured["supervisor_stopped"] is True


def test_start_desktop_wraps_edgechromium_startup_failure(tmp_path: Path) -> None:
    window = SimpleNamespace()
    webview = SimpleNamespace(
        OPEN_DIALOG=1,
        create_window=lambda *_args, **_kwargs: window,
        start=lambda **_kwargs: (_ for _ in ()).throw(OSError("fixture failure")),
    )

    with pytest.raises(DesktopStartupError) as failure:
        start_desktop(data_root=tmp_path, webview_module=webview)

    assert failure.value.code == "desktop_shell_start_failed"
    assert failure.value.details == {"error_type": "OSError"}
