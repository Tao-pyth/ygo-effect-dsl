from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import tempfile
import threading
import time
from typing import Any

from ygo_effect_dsl.desktop import desktop_frontend_entrypoint
from ygo_effect_dsl.desktop.bridge import DesktopBridge
from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.desktop.shell import preflight_desktop_runtime
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data

DESKTOP_BRIDGE_SMOKE_VERSION = "desktop-bridge-smoke-v1"


def collect_desktop_bridge_smoke() -> dict[str, Any]:
    import webview

    runtime = preflight_desktop_runtime()
    entrypoint = desktop_frontend_entrypoint()
    frontend_sha256 = hashlib.sha256(
        entrypoint.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()
    result: dict[str, Any] = {}
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="ygo-desktop-bridge-smoke-") as temporary:
        service = DesktopApplicationService(temporary)
        bridge = DesktopBridge(service.handlers())
        window = webview.create_window(
            "RouteLab bridge smoke",
            url=entrypoint.as_uri(),
            js_api=bridge,
            width=960,
            height=700,
            min_size=(960, 700),
            hidden=True,
        )

        def finish(response: Any) -> None:
            if isinstance(response, dict):
                result.update(response)
            window.destroy()

        def loaded() -> None:
            window.evaluate_js(
                "Promise.all(["
                "window.routeLabBridge.invoke('system.describe', {}),"
                "window.routeLabBridge.invoke('analytics.query', {request: {"
                "cursor: null, fields: ['run', 'success'], filters: [], limit: 20, "
                "schema_version: 'analytics-query-request-v1', snapshot_id: null, "
                "sort: []}}),"
                "window.routeLabBridge.invoke('analytics.export.enqueue', {"
                "format: 'json', idempotency_key: null, priority: 0, source_kind: 'query', "
                "source: {cursor: null, fields: ['run', 'success'], filters: [], limit: 20, "
                "schema_version: 'analytics-query-request-v1', snapshot_id: null, sort: []}})"
                "]).then(([response, analytics_response, export_response]) => ({"
                "response, analytics_response, export_response, workflow_version: "
                "document.documentElement.dataset.workflowVersion}))",
                callback=finish,
            )

        window.events.loaded += loaded
        watchdog = threading.Timer(20.0, window.destroy)
        watchdog.start()
        try:
            webview.start(gui="edgechromium", debug=False, private_mode=True)
        finally:
            watchdog.cancel()
        export_response = result.get("export_response")
        if (
            not isinstance(export_response, dict)
            or export_response.get("ok") is not True
        ):
            raise RuntimeError("desktop bridge smoke did not enqueue analytics export")
        export_outcome = service.analytics_export_worker.run_once()
        export_job_id = export_response["result"]["job"]["job_id"]
        export_status = service.job_catalog.status_snapshot(export_job_id)
        result["export_worker"] = {
            "artifact_kinds": sorted(
                artifact.kind for artifact in export_status.artifacts
            ),
            "state": export_status.job.state.value,
            "status": export_outcome.status,
        }
    response = result.get("response")
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise RuntimeError("desktop bridge smoke did not return a successful response")
    analytics_response = result.get("analytics_response")
    if (
        not isinstance(analytics_response, dict)
        or analytics_response.get("ok") is not True
        or analytics_response.get("result", {}).get("schema_version")
        != "analytics-query-response-v1"
    ):
        raise RuntimeError("desktop bridge smoke did not complete analytics.query")
    if result.get("workflow_version") != "desktop-workflow-v1":
        raise RuntimeError("desktop bridge smoke loaded the wrong frontend contract")
    if result.get("export_worker") != {
        "artifact_kinds": [
            "analytics_export_data",
            "analytics_export_manifest",
        ],
        "state": "succeeded",
        "status": "succeeded",
    }:
        raise RuntimeError("desktop bridge smoke did not publish analytics export")
    identity = to_canonical_data(
        {
            "analytics_response": analytics_response,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "frontend": {
                "entrypoint": entrypoint.name,
                "sha256": frontend_sha256,
                "workflow_version": result["workflow_version"],
            },
            "limitations": [
                "hidden_same_host_window",
                "empty_snapshot_query_and_export_smoke_only",
                "worker_lifecycle_and_accessibility_verified_by_desktop_lifecycle_evidence",
            ],
            "pywebview_version": importlib.metadata.version("pywebview"),
            "response": response,
            "export_response": result["export_response"],
            "export_worker": result["export_worker"],
            "schema_version": DESKTOP_BRIDGE_SMOKE_VERSION,
            "webview2_version": runtime.version,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="desktopbridgesmoke_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="run the packaged frontend through the pywebview bridge"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    evidence = collect_desktop_bridge_smoke()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"desktop-bridge-smoke: wrote {args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
