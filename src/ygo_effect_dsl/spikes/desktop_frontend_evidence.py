from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from typing import Any, Iterable

from ygo_effect_dsl.desktop import (
    DESKTOP_WORKFLOW_CONTRACT_VERSION,
    desktop_frontend_entrypoint,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data

DESKTOP_FRONTEND_EVIDENCE_SCHEMA_VERSION = "desktop-frontend-evidence-v1"

DEFAULT_VIEWPORTS = (
    ("deck_dashboard_1440x900.png", 1440, 900, ""),
    ("deck_search_960x700.png", 960, 700, "#view=search&deck=short-route"),
)


def find_edge_executable() -> Path:
    candidates = (
        Path(os.environ.get("PROGRAMFILES(X86)", ""))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES", ""))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("Microsoft Edge executable was not found")


def _run_edge(edge: Path, arguments: Iterable[str]) -> subprocess.CompletedProcess[str]:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    completed = subprocess.run(
        [str(edge), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=creationflags,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Edge frontend probe failed: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    return completed


def _png_identity(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or len(payload) < 24:
        raise ValueError(f"frontend screenshot is not a PNG: {path}")
    width, height = struct.unpack(">II", payload[16:24])
    return {
        "bytes": len(payload),
        "filename": path.name,
        "height": height,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "width": width,
    }


def collect_desktop_frontend_evidence(
    *,
    edge: Path,
    screenshot_dir: Path,
    entrypoint: Path | None = None,
) -> dict[str, Any]:
    html = (entrypoint or desktop_frontend_entrypoint()).resolve()
    uri = html.as_uri()
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ygo-desktop-edge-") as profile:
        common = [
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-features=msEdgeFirstRunExperience",
            f"--user-data-dir={profile}",
            "--allow-file-access-from-files",
            "--force-device-scale-factor=1",
        ]
        dom = _run_edge(
            edge,
            [*common, "--virtual-time-budget=1500", "--dump-dom", uri],
        ).stdout
        screenshots: list[dict[str, Any]] = []
        for filename, width, height, fragment in DEFAULT_VIEWPORTS:
            output = (screenshot_dir / filename).resolve()
            _run_edge(
                edge,
                [
                    *common,
                    f"--window-size={width},{height}",
                    "--virtual-time-budget=1800",
                    f"--screenshot={output}",
                    f"{uri}{fragment}",
                ],
            )
            screenshot = _png_identity(output)
            if screenshot["width"] != width or screenshot["height"] != height:
                raise ValueError("Edge screenshot dimensions do not match the viewport")
            screenshots.append(screenshot)
    identity = to_canonical_data(
        {
            "dom": {
                "deck_row_count": dom.count("data-deck-id="),
                "search_dialog_present": 'id="search-dialog"' in dom,
                "workflow_version_present": (
                    'data-workflow-version="desktop-workflow-v1"' in dom
                ),
            },
            "limitations": [
                "synthetic_search_browser_adapter_only",
                "desktop_bridge_is_verified_separately_from_browser_capture",
                "continuous_search_worker_execution_not_exercised_by_browser_capture",
                "desktop_lifecycle_and_accessibility_verified_separately",
                "catalog_virtualization_deferred_to_issue_165",
                "single_windows_host_headless_edge_capture",
            ],
            "schema_version": DESKTOP_FRONTEND_EVIDENCE_SCHEMA_VERSION,
            "screenshots": screenshots,
            "security": {
                "remote_content": False,
                "runtime_network_access": False,
                "third_party_card_assets": False,
            },
            "workflow_version": DESKTOP_WORKFLOW_CONTRACT_VERSION,
        }
    )
    if identity["dom"] != {
        "deck_row_count": 4,
        "search_dialog_present": True,
        "workflow_version_present": True,
    }:
        raise ValueError("packaged frontend did not initialize its deterministic DOM")
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="desktopfrontendevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="capture the packaged v0.5 desktop frontend in headless Edge"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--screenshot-dir", type=Path, required=True)
    parser.add_argument("--edge", type=Path)
    args = parser.parse_args()
    evidence = collect_desktop_frontend_evidence(
        edge=(args.edge or find_edge_executable()),
        screenshot_dir=args.screenshot_dir,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"desktop-frontend-evidence: wrote {args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
