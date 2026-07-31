from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ygo_effect_dsl.desktop.bridge import DESKTOP_BRIDGE_CONTRACT_VERSION, DesktopBridge
from ygo_effect_dsl.desktop import shell as shell_module
from ygo_effect_dsl.desktop.shell import (
    DEFAULT_WINDOW_SIZE,
    DESKTOP_EXECUTABLE_PREFLIGHT_VERSION,
    MINIMUM_WEBVIEW2_RUNTIME_VERSION,
    MINIMUM_WINDOW_SIZE,
    DesktopStartupError,
    SingleInstanceLock,
    WebView2Installation,
    build_desktop_preflight_diagnostic,
    find_webview2_installations,
    main,
    preflight_desktop_runtime,
    start_desktop,
    webview2_failure_guidance,
    webview2_runtime_policy_document,
)
from ygo_effect_dsl.version import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_dependency_and_entrypoint_are_optional() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_section = pyproject.split("[project.optional-dependencies]", 1)[0]
    desktop_section = pyproject.split("desktop = [", 1)[1].split("]", 1)[0]

    assert "pywebview" not in project_section
    assert '"pywebview==6.2.1"' in desktop_section
    assert 'ygo-effect-dsl = "ygo_effect_dsl.cli.main:main"' in pyproject
    assert 'ygo-effect-dsl-desktop = "ygo_effect_dsl.desktop.shell:main"' in pyproject


def test_desktop_entrypoint_reports_version_without_runtime_preflight(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


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
    assert missing.value.details["guidance"]["minimum_supported_version"] == (
        MINIMUM_WEBVIEW2_RUNTIME_VERSION
    )

    with pytest.raises(DesktopStartupError, match="older than") as outdated:
        preflight_desktop_runtime(
            platform_name="win32",
            environ=_runtime(tmp_path, "149.0.0.1"),
            installed_pywebview_version="6.2.1",
        )
    assert outdated.value.code == "webview2_runtime_outdated"
    assert outdated.value.details["observed_version"] == "149.0.0.1"
    assert outdated.value.details["required_version"] == MINIMUM_WEBVIEW2_RUNTIME_VERSION

    with pytest.raises(DesktopStartupError, match="does not match") as mismatch:
        preflight_desktop_runtime(
            platform_name="win32",
            environ=_runtime(tmp_path),
            installed_pywebview_version="6.2.0",
        )
    assert mismatch.value.code == "pywebview_version_mismatch"


def test_webview2_probe_uses_numeric_version_order(tmp_path: Path) -> None:
    environment = _runtime(tmp_path, "99.0.0.1")
    _runtime(tmp_path, MINIMUM_WEBVIEW2_RUNTIME_VERSION)
    installations = find_webview2_installations(environment)
    selected = preflight_desktop_runtime(
        platform_name="win32",
        environ=environment,
        installed_pywebview_version="6.2.1",
    )

    assert [item.version for item in installations] == [
        "99.0.0.1",
        MINIMUM_WEBVIEW2_RUNTIME_VERSION,
    ]
    assert selected.version == MINIMUM_WEBVIEW2_RUNTIME_VERSION


def test_desktop_preflight_only_writes_packaged_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = WebView2Installation(
        version="150.0.4078.65",
        executable=tmp_path / "msedgewebview2.exe",
    )
    output = tmp_path / "diagnostics.json"
    monkeypatch.setattr(shell_module, "preflight_desktop_runtime", lambda: runtime)

    assert main(["--preflight-only", "--diagnostics-out", str(output)]) == 0
    document = json.loads(output.read_text(encoding="utf-8"))

    assert document == build_desktop_preflight_diagnostic(runtime)
    assert document["schema_version"] == DESKTOP_EXECUTABLE_PREFLIGHT_VERSION
    assert document["package_version"] == __version__
    assert document["frontend"]["workflow_version"] == "desktop-workflow-v1"
    assert document["runtime_policy"] == webview2_runtime_policy_document()


def test_webview2_failure_guidance_is_user_facing() -> None:
    guidance = webview2_failure_guidance("outdated", observed_version="149.0.0.1")

    assert guidance["download_url"].startswith("https://developer.microsoft.com/")
    assert guidance["minimum_supported_version"] == MINIMUM_WEBVIEW2_RUNTIME_VERSION
    assert guidance["observed_version"] == "149.0.0.1"
    assert guidance["reason"] == "outdated"
    assert any("Install or repair" in action for action in guidance["actions"])
    assert any(
        "Do not download or run an installer" in action
        for action in guidance["actions"]
    )


def test_single_instance_lock_releases_for_next_launch(tmp_path: Path) -> None:
    path = tmp_path / "desktop.lock"
    with SingleInstanceLock(path):
        assert path.is_file()
    with SingleInstanceLock(path):
        assert path.is_file()
    assert path.read_bytes()


def test_start_desktop_uses_packaged_frontend_and_single_bridge_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class CardProvider:
        def close(self) -> None:
            captured["card_provider_closed"] = True

    monkeypatch.setattr(
        shell_module,
        "build_desktop_card_provider",
        lambda external_root=None: CardProvider(),
    )

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

    class ExportSupervisor:
        health = "stopped"

        def __init__(self, worker: Any) -> None:
            captured["export_worker"] = worker

        def start(self) -> None:
            self.health = "running"
            captured["export_supervisor_started"] = True

        def stop(self) -> None:
            self.health = "stopped"
            captured["export_supervisor_stopped"] = True

    start_desktop(
        data_root=tmp_path,
        webview_module=webview,
        supervisor_factory=Supervisor,  # type: ignore[arg-type]
        export_supervisor_factory=ExportSupervisor,  # type: ignore[arg-type]
    )

    assert captured["url"].startswith("file:")
    assert captured["width"] == DEFAULT_WINDOW_SIZE[0]
    assert captured["height"] == DEFAULT_WINDOW_SIZE[1]
    assert captured["min_size"] == MINIMUM_WINDOW_SIZE
    assert isinstance(captured["js_api"], DesktopBridge)
    description = captured["js_api"].invoke(
        {
            "method": "system.describe",
            "payload": {},
            "request_id": "describe",
            "version": DESKTOP_BRIDGE_CONTRACT_VERSION,
        }
    )
    assert description["result"]["capabilities"]["card_presentation"] is True
    assert description["result"]["capabilities"]["deck_card_options"] is True
    assert captured["start"] == {
        "debug": False,
        "gui": "edgechromium",
        "private_mode": True,
    }
    assert captured["supervisor_started"] is True
    assert captured["supervisor_stopped"] is True
    assert captured["export_supervisor_started"] is True
    assert captured["export_supervisor_stopped"] is True
    assert captured["card_provider_closed"] is True


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
