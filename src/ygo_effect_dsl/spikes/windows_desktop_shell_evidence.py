from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import _find_visual_studio


WINDOWS_DESKTOP_SHELL_EVIDENCE_SCHEMA_VERSION = (
    "windows-desktop-shell-selection-evidence-v1"
)

PYWEBVIEW_REQUIREMENT = "pywebview==6.2.1"
PYSIDE_REQUIREMENT = "PySide6==6.11.1"

_PYWEBVIEW_LIVE_PROBE = r"""
import importlib.metadata
import json
from pathlib import Path
import site
import time

import psutil
import webview

started = time.perf_counter()
result = {}
window = webview.create_window(
    "YGO desktop shell probe",
    html="<html><body><main id='ready'>ready</main></body></html>",
    width=800,
    height=600,
    hidden=True,
)


def loaded():
    process = psutil.Process()
    family = [process, *process.children(recursive=True)]
    site_bytes = 0
    for root in site.getsitepackages():
        path = Path(root)
        if path.is_dir():
            site_bytes += sum(
                item.stat().st_size for item in path.rglob("*") if item.is_file()
            )
    result.update(
        {
            "backend": "edgechromium",
            "cold_start_seconds": round(time.perf_counter() - started, 6),
            "family_process_count": len(family),
            "family_rss_bytes": sum(
                item.memory_info().rss for item in family if item.is_running()
            ),
            "loaded": True,
            "pywebview_version": importlib.metadata.version("pywebview"),
            "probe_site_packages_bytes": site_bytes,
        }
    )
    window.destroy()


window.events.loaded += loaded
webview.start(gui="edgechromium", debug=False, private_mode=True)
print(json.dumps(result, sort_keys=True))
"""


def desktop_shell_decision() -> dict[str, Any]:
    return {
        "automation": {
            "browser": "playwright_against_static_frontend",
            "desktop": "pywebview_bridge_and_webview2_smoke",
            "restriction": "browser_success_does_not_replace_desktop_smoke",
        },
        "desktop_integration": {
            "auto_update": "deferred_to_distribution_gate",
            "deep_links": "deferred",
            "file_picker": "native_select_then_python_path_validation",
            "single_instance": "required_for_single_writer_catalog",
            "ydk_file_association": "deferred",
        },
        "distribution": {
            "desktop_dependency_group": "optional_until_ui_release_gate",
            "installer": "deferred_to_distribution_gate",
            "third_party_card_assets": "never_bundle_before_license_review",
            "webview2": "evergreen_runtime_preflight",
        },
        "process_boundary": {
            "application_service": "typed_python_facade_in_desktop_host",
            "desktop_host": "python_pywebview_webview2",
            "renderer_api": "allowlisted_async_js_bridge",
            "rule_execution": "existing_ocgcore_worker_subprocesses",
            "worker_owner": "python_application_service",
        },
        "recovery": {
            "host_crash": "restart_and_recover_from_sqlite_job_checkpoints",
            "renderer_crash": "recreate_window_without_mutating_authority",
            "worker_crash": "retry_or_fail_through_job_state_machine",
        },
        "security": {
            "arbitrary_navigation": False,
            "bridge_payloads": "versioned_validate_before_dispatch",
            "csp": "default_deny_no_remote_content",
            "local_rest_api": False,
            "path_inputs": "canonicalize_and_scope_in_python",
            "remote_content": False,
        },
        "selected_shell": "pywebview_webview2",
        "selection_scope": "windows_developer_mvp_v0.5",
    }


def official_references() -> dict[str, str]:
    return {
        "electron_process_model": (
            "https://www.electronjs.org/docs/latest/tutorial/process-model"
        ),
        "electron_security": (
            "https://www.electronjs.org/docs/latest/tutorial/security"
        ),
        "pyside_deployment": (
            "https://doc.qt.io/qtforpython-6/deployment/index.html"
        ),
        "pywebview_architecture": (
            "https://pywebview.flowrl.com/guide/architecture.html"
        ),
        "pywebview_bridge": (
            "https://pywebview.flowrl.com/guide/interdomain"
        ),
        "pywebview_security": "https://pywebview.flowrl.com/guide/security",
        "tauri_prerequisites": "https://v2.tauri.app/start/prerequisites/",
        "tauri_sidecar": "https://v2.tauri.app/develop/sidecar/",
        "webview2_distribution": (
            "https://learn.microsoft.com/en-us/microsoft-edge/webview2/"
            "concepts/distribution"
        ),
    }


def _which(name: str) -> str | None:
    resolved = shutil.which(name)
    return str(Path(resolved).resolve()) if resolved else None


def _webview2_probe() -> dict[str, Any]:
    roots: list[Path] = []
    for environment_name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        value = os.environ.get(environment_name)
        if value:
            roots.append(Path(value) / "Microsoft" / "EdgeWebView" / "Application")
    installations: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in root.iterdir():
            executable = candidate / "msedgewebview2.exe"
            if candidate.is_dir() and executable.is_file():
                installations.append(
                    {
                        "executable": str(executable.resolve()),
                        "version": candidate.name,
                    }
                )
    installations.sort(key=lambda item: item["version"])
    return {
        "available": bool(installations),
        "installations": installations,
        "selected_version": installations[-1]["version"] if installations else None,
    }


def collect_host_probe() -> dict[str, Any]:
    visual_studio = _find_visual_studio() if os.name == "nt" else None
    return {
        "machine": platform.machine(),
        "operating_system": platform.platform(),
        "python": {
            "executable": str(Path(sys.executable).resolve()),
            "version": platform.python_version(),
        },
        "toolchains": {
            "cargo": _which("cargo"),
            "node": _which("node"),
            "npm": _which("npm"),
            "pyinstaller_module": importlib.util.find_spec("PyInstaller") is not None,
            "rustc": _which("rustc"),
            "visual_studio": visual_studio,
        },
        "webview2": _webview2_probe(),
    }


def collect_pywebview_live_probe(
    python_executable: str | Path,
) -> dict[str, Any]:
    completed = subprocess.run(
        [str(python_executable), "-c", _PYWEBVIEW_LIVE_PROBE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "pywebview live probe failed: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("pywebview live probe produced no JSON")
    result = json.loads(lines[-1])
    if result.get("backend") != "edgechromium" or result.get("loaded") is not True:
        raise RuntimeError("pywebview live probe did not load EdgeChromium")
    return result


def collect_package_download_probe(
    requirement: str,
    *,
    binary_only: bool,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ygo-desktop-package-") as temporary:
        command = [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--dest",
            temporary,
        ]
        if binary_only:
            command.append("--only-binary=:all:")
        command.append(requirement)
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        elapsed = round(time.perf_counter() - started, 6)
        if completed.returncode != 0:
            raise RuntimeError(
                f"package download probe failed for {requirement}: "
                + (completed.stderr.strip() or completed.stdout.strip())
            )
        files = sorted(Path(temporary).iterdir(), key=lambda item: item.name)
        entries = [
            {"bytes": item.stat().st_size, "name": item.name}
            for item in files
            if item.is_file()
        ]
    return {
        "download_bytes": sum(item["bytes"] for item in entries),
        "download_seconds": elapsed,
        "files": entries,
        "requirement": requirement,
    }


def _candidate_matrix(
    host: dict[str, Any],
    *,
    pywebview_live: dict[str, Any] | None,
    package_downloads: dict[str, Any] | None,
) -> dict[str, Any]:
    toolchains = host["toolchains"]
    downloads = package_downloads or {}
    return {
        "electron": {
            "automation": "playwright_electron_available",
            "decision": "not_selected",
            "host_gate": "passed" if toolchains["node"] else "missing_node_and_npm",
            "process_boundary": "chromium_node_shell_plus_python_child",
            "reason": "duplicates_runtime_and_adds_node_release_surface",
            "spike_level": "toolchain_preflight",
        },
        "pyside6": {
            "automation": "qt_native_harness_not_playwright",
            "decision": "not_selected",
            "host_gate": "python_compatible",
            "package_download": downloads.get("pyside6"),
            "process_boundary": "python_qt_host_plus_existing_workers",
            "reason": "large_dependency_and_separate_native_ui_test_stack",
            "spike_level": "package_acquisition",
        },
        "pywebview": {
            "automation": "browser_harness_plus_desktop_bridge_smoke",
            "decision": "selected",
            "host_gate": (
                "passed" if host["webview2"]["available"] else "missing_webview2"
            ),
            "live_probe": pywebview_live,
            "package_download": downloads.get("pywebview"),
            "process_boundary": "python_host_js_bridge_plus_existing_workers",
            "reason": "smallest_change_to_python_worker_and_pyinstaller_boundary",
            "spike_level": "live_edgechromium_launch",
        },
        "tauri": {
            "automation": "webdriver_supported_browser_harness_still_required",
            "decision": "rollback_candidate",
            "host_gate": (
                "passed"
                if toolchains["cargo"] and toolchains["rustc"]
                else "missing_rust_toolchain"
            ),
            "process_boundary": "rust_shell_plus_pyinstaller_sidecar",
            "reason": "stronger_native_boundary_but_adds_rust_sidecar_release_surface",
            "spike_level": "toolchain_preflight",
        },
    }


def build_windows_desktop_shell_evidence(
    *,
    host: dict[str, Any],
    pywebview_live: dict[str, Any] | None,
    package_downloads: dict[str, Any] | None,
) -> dict[str, Any]:
    candidates = _candidate_matrix(
        host,
        pywebview_live=pywebview_live,
        package_downloads=package_downloads,
    )
    if candidates["pywebview"]["host_gate"] != "passed":
        raise ValueError("selected pywebview shell requires WebView2 on the host")
    if pywebview_live is None or pywebview_live.get("loaded") is not True:
        raise ValueError("selected pywebview shell requires a successful live probe")
    identity = to_canonical_data(
        {
            "candidates": candidates,
            "decision": desktop_shell_decision(),
            "host": host,
            "limitations": [
                "single_windows_host_measurement",
                "hidden_minimal_window_not_dashboard_workload",
                "rss_includes_shared_webview2_processes",
                "package_download_bytes_are_not_final_installer_size",
                "pip_cache_may_reduce_package_download_time",
                "tauri_and_electron_live_builds_not_run_without_baseline_toolchains",
                "installer_update_and_signing_remain_release_gates",
            ],
            "references": official_references(),
            "schema_version": WINDOWS_DESKTOP_SHELL_EVIDENCE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="desktopshellevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="collect the v0.5 Windows desktop shell selection evidence"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pywebview-python", type=Path, required=True)
    parser.add_argument("--collect-package-downloads", action="store_true")
    args = parser.parse_args()
    downloads = None
    if args.collect_package_downloads:
        downloads = {
            "pyside6": collect_package_download_probe(
                PYSIDE_REQUIREMENT,
                binary_only=True,
            ),
            "pywebview": collect_package_download_probe(
                PYWEBVIEW_REQUIREMENT,
                binary_only=False,
            ),
        }
    evidence = build_windows_desktop_shell_evidence(
        host=collect_host_probe(),
        pywebview_live=collect_pywebview_live_probe(args.pywebview_python),
        package_downloads=downloads,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"windows-desktop-shell-evidence: wrote {args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
