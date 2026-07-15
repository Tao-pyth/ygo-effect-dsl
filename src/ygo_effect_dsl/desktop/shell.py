from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, BinaryIO, Mapping

from ygo_effect_dsl.desktop import desktop_frontend_entrypoint
from ygo_effect_dsl.desktop.bridge import DesktopBridge
from ygo_effect_dsl.desktop.service import DesktopApplicationService

PYWEBVIEW_REQUIREMENT = "6.2.1"
DESKTOP_STARTUP_DIAGNOSTIC_VERSION = "desktop-startup-diagnostic-v1"
MINIMUM_WINDOW_SIZE = (960, 700)
DEFAULT_WINDOW_SIZE = (1440, 900)


@dataclass(frozen=True)
class WebView2Installation:
    version: str
    executable: Path

    def to_dict(self) -> dict[str, str]:
        return {"executable": str(self.executable), "version": self.version}


class DesktopStartupError(RuntimeError):
    def __init__(
        self, code: str, message: str, *, details: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "details": self.details,
            "message": str(self),
            "schema_version": DESKTOP_STARTUP_DIAGNOSTIC_VERSION,
            "severity": "error",
        }


def _version_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        return ()


def find_webview2_installations(
    environ: Mapping[str, str] | None = None,
) -> tuple[WebView2Installation, ...]:
    environment = os.environ if environ is None else environ
    roots: set[Path] = set()
    for name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        if value := environment.get(name):
            roots.add(Path(value) / "Microsoft" / "EdgeWebView" / "Application")
    installations: list[WebView2Installation] = []
    for root in sorted(roots):
        if not root.is_dir():
            continue
        for candidate in root.iterdir():
            executable = candidate / "msedgewebview2.exe"
            if (
                candidate.is_dir()
                and executable.is_file()
                and _version_key(candidate.name)
            ):
                installations.append(
                    WebView2Installation(
                        version=candidate.name,
                        executable=executable.resolve(),
                    )
                )
    return tuple(
        sorted(
            installations,
            key=lambda item: (_version_key(item.version), str(item.executable)),
        )
    )


def preflight_desktop_runtime(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    installed_pywebview_version: str | None = None,
) -> WebView2Installation:
    observed_platform = sys.platform if platform_name is None else platform_name
    if observed_platform != "win32":
        raise DesktopStartupError(
            "unsupported_platform",
            "the v0.5 desktop shell requires Windows",
            details={"platform": observed_platform},
        )
    installations = find_webview2_installations(environ)
    if not installations:
        raise DesktopStartupError(
            "webview2_runtime_missing",
            "Microsoft Evergreen WebView2 Runtime was not found",
        )
    if installed_pywebview_version is None:
        try:
            installed_pywebview_version = importlib.metadata.version("pywebview")
        except importlib.metadata.PackageNotFoundError as exc:
            raise DesktopStartupError(
                "pywebview_missing",
                "install the optional desktop dependency group before launch",
                details={"required_version": PYWEBVIEW_REQUIREMENT},
            ) from exc
    if installed_pywebview_version != PYWEBVIEW_REQUIREMENT:
        raise DesktopStartupError(
            "pywebview_version_mismatch",
            "installed pywebview version does not match the qualified desktop contract",
            details={
                "observed_version": installed_pywebview_version,
                "required_version": PYWEBVIEW_REQUIREMENT,
            },
        )
    return installations[-1]


class SingleInstanceLock:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self._stream: BinaryIO | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            raise DesktopStartupError(
                "desktop_already_running",
                "another desktop process owns the single-writer catalog",
            ) from exc
        self._stream = stream

    def release(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        finally:
            self._stream.close()
            self._stream = None

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


class NativeYdkPicker:
    def __init__(self, webview_module: ModuleType) -> None:
        self.webview = webview_module
        self.window: Any | None = None

    def __call__(self) -> str | Path | None:
        if self.window is None:
            raise DesktopStartupError(
                "desktop_window_unavailable",
                "native file selection requires an active desktop window",
            )
        dialog_kind = getattr(self.webview, "OPEN_DIALOG", None)
        if dialog_kind is None:
            dialog_kind = self.webview.FileDialog.OPEN
        selected = self.window.create_file_dialog(
            dialog_kind,
            allow_multiple=False,
            file_types=("YDK deck (*.ydk)",),
        )
        if not selected:
            return None
        return selected[0] if isinstance(selected, (list, tuple)) else selected


def default_desktop_data_root(environ: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environ is None else environ
    local = environment.get("LOCALAPPDATA")
    if not local:
        raise DesktopStartupError(
            "local_app_data_missing",
            "LOCALAPPDATA is required for the desktop operational catalog",
        )
    return (Path(local) / "ygo-effect-dsl" / "desktop-v1").resolve()


def start_desktop(
    *,
    data_root: str | Path,
    external_root: str | Path | None = None,
    webview_module: ModuleType | None = None,
) -> None:
    if webview_module is None:
        try:
            webview = importlib.import_module("webview")
        except (ImportError, OSError) as exc:
            raise DesktopStartupError(
                "pywebview_import_failed",
                "the qualified pywebview runtime could not be imported",
            ) from exc
    else:
        webview = webview_module
    picker = NativeYdkPicker(webview)
    service = DesktopApplicationService(
        data_root,
        external_root=external_root,
        ydk_picker=picker,
    )
    bridge = DesktopBridge(service.handlers())
    window = webview.create_window(
        "RouteLab Deck Research",
        url=desktop_frontend_entrypoint().as_uri(),
        js_api=bridge,
        width=DEFAULT_WINDOW_SIZE[0],
        height=DEFAULT_WINDOW_SIZE[1],
        min_size=MINIMUM_WINDOW_SIZE,
    )
    if window is None:
        raise DesktopStartupError(
            "desktop_window_creation_failed",
            "pywebview did not create the desktop window",
        )
    picker.window = window
    try:
        webview.start(gui="edgechromium", debug=False, private_mode=True)
    except Exception as exc:
        raise DesktopStartupError(
            "desktop_shell_start_failed",
            "pywebview could not start the EdgeChromium desktop shell",
            details={"error_type": type(exc).__name__},
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="launch the RouteLab Windows desktop MVP"
    )
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--external-root", type=Path)
    args = parser.parse_args(argv)
    try:
        preflight_desktop_runtime()
        data_root = args.data_root or default_desktop_data_root()
        with SingleInstanceLock(data_root / "desktop.lock"):
            start_desktop(data_root=data_root, external_root=args.external_root)
    except DesktopStartupError as exc:
        print(json.dumps(exc.to_dict(), sort_keys=True), file=sys.stderr)
        return 2
    return 0


__all__ = [
    "DEFAULT_WINDOW_SIZE",
    "DESKTOP_STARTUP_DIAGNOSTIC_VERSION",
    "MINIMUM_WINDOW_SIZE",
    "PYWEBVIEW_REQUIREMENT",
    "DesktopStartupError",
    "NativeYdkPicker",
    "SingleInstanceLock",
    "WebView2Installation",
    "default_desktop_data_root",
    "find_webview2_installations",
    "main",
    "preflight_desktop_runtime",
    "start_desktop",
]


if __name__ == "__main__":
    raise SystemExit(main())
