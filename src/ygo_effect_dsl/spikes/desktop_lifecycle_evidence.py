from __future__ import annotations

import argparse
from html.parser import HTMLParser
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
from typing import Any

from ygo_effect_dsl.desktop import (
    desktop_bridge_contract_document,
    desktop_frontend_entrypoint,
    desktop_workflow_contract_document,
    process_containment_contract,
)
from ygo_effect_dsl.desktop.bridge import DesktopBridge
from ygo_effect_dsl.desktop.lifecycle import launch_process_tree
from ygo_effect_dsl.desktop.lifecycle import DesktopSearchWorker
from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.desktop.shell import (
    DesktopStartupError,
    preflight_desktop_runtime,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.experiment.schema import load_experiment_document
from ygo_effect_dsl.spikes.windows_desktop_shell_evidence import (
    collect_pywebview_live_probe,
)
from ygo_effect_dsl.storage import JobCatalog, JobKind, JobRetryPolicy, JobSpec

DESKTOP_LIFECYCLE_EVIDENCE_VERSION = "desktop-lifecycle-evidence-v1"
DESKTOP_REAL_CORE_PROBE_VERSION = "desktop-real-core-search-probe-v1"
T0 = "2026-07-16T00:00:00Z"
T1 = "2026-07-16T00:00:01Z"
T2 = "2026-07-16T00:00:02Z"
T4 = "2026-07-16T00:00:04Z"


class _AccessibilityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.dialogs = 0
        self.focusable = 0
        self.icon_buttons = 0
        self.named_icon_buttons = 0
        self.labels = 0
        self.skip_link = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "dialog":
            self.dialogs += 1
        if tag in {"button", "input", "select"} or (
            tag == "a" and values.get("href") is not None
        ):
            self.focusable += 1
        if tag == "label":
            self.labels += 1
        if tag == "button" and "close-button" in (values.get("class") or ""):
            self.icon_buttons += 1
            if values.get("aria-label"):
                self.named_icon_buttons += 1
        if tag == "a" and values.get("href") == "#workspace":
            self.skip_link = True


def _spec(key: str, *, timeout: float = 300.0) -> JobSpec:
    experiment_digest = stable_digest(key, prefix="experiment_")
    return JobSpec(
        kind=JobKind.SEARCH,
        idempotency_key=key,
        input_digest=stable_digest(
            {"experiment_digest": experiment_digest}, prefix="jobinput_"
        ),
        payload={
            "experiment_digest": experiment_digest,
            "experiment_id": key,
        },
        retry_policy=JobRetryPolicy(attempt_timeout_seconds=timeout),
    )


def _create(catalog: JobCatalog, key: str, *, timeout: float = 300.0) -> str:
    return catalog.create_job(_spec(key, timeout=timeout), created_at=T0).job_id


def _wait_for_checkpoint(catalog: JobCatalog, job_id: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = catalog.get_job(job_id)
        if job is not None and job.state.value == "running":
            if catalog.latest_checkpoint(job_id) is not None:
                return
        time.sleep(0.05)
    raise RuntimeError("host-crash helper did not publish its checkpoint")


def _host_crash_probe(root: Path) -> dict[str, Any]:
    catalog = JobCatalog(root / "host-crash.sqlite3")
    job_id = _create(catalog, "host-crash")
    code = (
        "from ygo_effect_dsl.storage import JobCatalog; "
        "from pathlib import Path; import time; "
        f"c=JobCatalog(Path({str(catalog.path)!r})); "
        f"j=c.claim_next(worker_id='crashed-host',now={T0!r},lease_seconds=1); "
        "assert j is not None and j.lease_token is not None; "
        f"c.save_checkpoint(j.job_id,lease_token=j.lease_token,now={T0!r},"
        "recovery_position='search:frontier:17',completed_units=17,total_units=100,"
        "payload={'semantic_node_id':'node_17'}); time.sleep(60)"
    )
    tree = launch_process_tree([sys.executable, "-c", code], cwd=root)
    try:
        _wait_for_checkpoint(catalog, job_id)
        before = dict(tree.metrics())
        tree.terminate(grace_seconds=3)
        after = dict(tree.metrics())
    finally:
        tree.terminate(grace_seconds=3)
        tree.close()
    reclaimed = catalog.reclaim_orphans(now=T2, actor="desktop-restart")
    retry = catalog.claim_next(worker_id="restarted-host", now=T4, lease_seconds=10)
    if retry is None or retry.lease_token is None:
        raise RuntimeError("restarted desktop did not reclaim the host-crash job")
    checkpoint = catalog.resume_checkpoint(
        job_id, expected_input_digest=retry.spec.input_digest
    )
    if checkpoint is None:
        raise RuntimeError("host-crash checkpoint was lost")
    catalog.fail_job(
        job_id,
        actor="evidence-cleanup",
        now=T4,
        error_code="evidence_complete",
        error_message="evidence probe completed",
        lease_token=retry.lease_token,
    )
    return {
        "attempt_after_restart": retry.attempt,
        "checkpoint_completed_units": checkpoint.completed_units,
        "checkpoint_position": checkpoint.recovery_position,
        "job_id": job_id,
        "process_tree_after_termination": after,
        "process_tree_before_termination": before,
        "reclaimed_state": reclaimed[0].state.value,
        "resume_input_digest_matches": checkpoint.input_digest
        == retry.spec.input_digest,
    }


def _job_fault_matrix(root: Path) -> dict[str, Any]:
    catalog = JobCatalog(root / "fault-matrix.sqlite3")

    renderer_id = _create(catalog, "renderer-crash")
    renderer_job = catalog.claim_next(
        worker_id="renderer-independent-worker", now=T0, lease_seconds=10
    )
    assert renderer_job is not None and renderer_job.lease_token is not None
    before_renderer = catalog.status_snapshot(renderer_id).job.state.value
    heartbeat = catalog.heartbeat(
        renderer_id,
        lease_token=renderer_job.lease_token,
        now=T1,
        lease_seconds=10,
    )
    catalog.schedule_retry(
        renderer_id,
        actor="evidence-cleanup",
        now=T1,
        reason="renderer_recreated",
        error_code="worker_crash",
        lease_token=renderer_job.lease_token,
    )

    worker_id = _create(catalog, "worker-crash")
    worker_job = catalog.claim_next(
        worker_id="crashing-worker", now=T0, lease_seconds=10
    )
    assert worker_job is not None and worker_job.lease_token is not None
    crashed = catalog.schedule_retry(
        worker_id,
        actor="desktop-supervisor",
        now=T1,
        reason="worker_process_exit_86",
        error_code="worker_crash",
        lease_token=worker_job.lease_token,
    )

    timeout_id = _create(catalog, "worker-timeout", timeout=1)
    timeout_job = catalog.claim_next(
        worker_id="timeout-worker", now=T0, lease_seconds=10
    )
    assert timeout_job is not None and timeout_job.lease_token is not None
    timed_out = catalog.recover_timed_out_attempt(
        timeout_id,
        lease_token=timeout_job.lease_token,
        now=T2,
        actor="desktop-supervisor",
    )

    cancel_id = _create(catalog, "cancel")
    cancel_job = catalog.claim_next(worker_id="cancel-worker", now=T0, lease_seconds=10)
    assert cancel_job is not None and cancel_job.lease_token is not None
    catalog.request_cancel(cancel_id, actor="renderer", now=T1, reason="user_request")
    cancelled = catalog.finish_cancelled(
        cancel_id,
        actor="cancel-worker",
        now=T2,
        reason="cancel_ack",
        lease_token=cancel_job.lease_token,
    )
    return {
        "cancel": {"artifacts": 0, "state": cancelled.state.value},
        "renderer_crash": {
            "heartbeat_preserved": heartbeat.heartbeat_at == T1,
            "state_before_recovery": before_renderer,
            "worker_lease_survived_renderer_read": heartbeat.state.value == "running",
        },
        "worker_crash": {"artifacts": 0, "state": crashed.state.value},
        "worker_timeout": {
            "artifacts": 0,
            "error_code": timed_out.error_code,
            "state": timed_out.state.value,
        },
    }


def _descendant_cleanup_probe(root: Path) -> dict[str, Any]:
    code = (
        "import subprocess,sys,time; time.sleep(0.5); "
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "time.sleep(60)"
    )
    tree = launch_process_tree([sys.executable, "-c", code], cwd=root)
    try:
        deadline = time.monotonic() + 10
        before: dict[str, Any] = {}
        while time.monotonic() < deadline:
            before = dict(tree.metrics())
            expected = 2 if os.name == "nt" else 1
            active = before.get("active_processes")
            if isinstance(active, int) and active >= expected:
                break
            time.sleep(0.05)
        tree.terminate(grace_seconds=3)
        after = dict(tree.metrics())
    finally:
        tree.terminate(grace_seconds=3)
        tree.close()
    return {"after": after, "before": before}


def _startup_diagnostics(root: Path) -> dict[str, str]:
    try:
        preflight_desktop_runtime(
            platform_name="win32",
            environ={},
            installed_pywebview_version="6.2.1",
        )
    except DesktopStartupError as exc:
        missing = exc.code
    else:
        raise RuntimeError("missing WebView2 probe unexpectedly passed")
    runtime = root / "Microsoft" / "EdgeWebView" / "Application" / "150.0.0.1"
    runtime.mkdir(parents=True)
    (runtime / "msedgewebview2.exe").write_bytes(b"evidence fixture")
    try:
        preflight_desktop_runtime(
            platform_name="win32",
            environ={"LOCALAPPDATA": str(root)},
            installed_pywebview_version="6.2.0",
        )
    except DesktopStartupError as exc:
        outdated = exc.code
    else:
        raise RuntimeError("outdated pywebview probe unexpectedly passed")
    return {"missing_runtime": missing, "outdated_pywebview": outdated}


def _frontend_audit() -> dict[str, Any]:
    entrypoint = desktop_frontend_entrypoint()
    html = entrypoint.read_text(encoding="utf-8")
    css = entrypoint.with_name("app.css").read_text(encoding="utf-8")
    javascript = entrypoint.with_name("app.js").read_text(encoding="utf-8")
    parser = _AccessibilityParser()
    parser.feed(html)
    return {
        "accessibility": {
            "dialog_count": parser.dialogs,
            "focusable_control_count": parser.focusable,
            "forced_colors_rules": "forced-colors: active" in css,
            "icon_button_names_complete": parser.icon_buttons
            == parser.named_icon_buttons,
            "label_count": parser.labels,
            "minimum_window": [960, 700],
            "reduced_motion_rules": "prefers-reduced-motion: reduce" in css,
            "skip_link": parser.skip_link,
            "tab_arrow_navigation": "ArrowLeft" in javascript
            and "ArrowRight" in javascript,
        },
        "security": {
            "csp_default_deny": "default-src 'none'" in html,
            "local_rest_api": False,
            "network_api_absent": "fetch(" not in javascript
            and "XMLHttpRequest" not in javascript,
            "remote_urls_absent": "http://" not in html.lower()
            and "https://" not in html.lower(),
        },
    }


def _bridge_audit(root: Path) -> dict[str, Any]:
    service = DesktopApplicationService(root / "bridge")
    bridge = DesktopBridge(service.handlers())
    contract = desktop_bridge_contract_document()
    rejected = bridge.invoke(
        {
            "method": "system.describe",
            "payload": {"file_path": "C:/forbidden"},
            "request_id": "security-audit",
            "version": "desktop-bridge-v1",
        }
    )
    return {
        "method_count": len(bridge.methods),
        "method_drift": sorted(contract["methods"]) != list(bridge.methods),
        "path_input_diagnostic": rejected["diagnostics"][0]["code"],
        "public_python_methods": contract["security"]["public_python_methods"],
    }


def _real_core_search_probe(root: Path) -> dict[str, Any]:
    repository = Path(__file__).resolve().parents[3]
    source = load_experiment_document(
        repository / "examples" / "experiments" / "general_search_inline.yaml"
    )
    service = DesktopApplicationService(
        root / "real-search", worker_execution="desktop-supervisor-v1"
    )
    deck = service.deck_catalog.register(
        name="Real core desktop evidence",
        source="inline",
        sections={
            name: tuple(source["deck"][name]) for name in ("main", "extra", "side")
        },
    )
    experiment = service.scenario_compose_search(
        {
            "configuration": {
                "interruption_card_code": None,
                "max_depth": 8,
                "max_nodes": 10,
                "max_seconds": 30,
                "seed": 58,
                "strategy": "random_search_v1",
            },
            "deck_id": deck.deck_id,
        }
    )["experiment"]
    preflight = service.scenario_preflight(
        {"deck_id": deck.deck_id, "experiment": experiment}
    )["preflight"]
    if not preflight["ok"]:
        raise RuntimeError("real-core desktop evidence preflight failed")
    queued = service.job_enqueue_search(
        {
            "deck_id": deck.deck_id,
            "experiment": experiment,
            "idempotency_key": "desktop-real-core-evidence-v1",
            "priority": 0,
        }
    )
    started = time.perf_counter()
    outcome = DesktopSearchWorker(root / "real-search").run_once()
    elapsed = round(time.perf_counter() - started, 6)
    snapshot = service.job_catalog.status_snapshot(queued["job"]["job_id"])
    if outcome.status != "succeeded" or snapshot.job.state.value != "succeeded":
        raise RuntimeError("real-core desktop evidence search did not succeed")
    checkpoint = snapshot.latest_checkpoint
    if checkpoint is None:
        raise RuntimeError("real-core desktop evidence search lost its checkpoint")
    manifest = preflight["manifest"]
    identity = {
        "artifact_count": len(snapshot.artifacts),
        "artifacts": [
            {
                "kind": artifact.kind,
                "schema_version": artifact.schema_version,
                "sha256": artifact.sha256,
            }
            for artifact in snapshot.artifacts
        ],
        "asset_lock_id": manifest["asset_lock_id"],
        "card_database_commit": manifest["card_database_commit"],
        "card_scripts_commit": manifest["card_scripts_commit"],
        "checkpoint": {
            "completed_units": checkpoint.completed_units,
            "position": checkpoint.recovery_position,
            "semantic_result_digest": checkpoint.semantic_result_digest,
            "total_units": checkpoint.total_units,
        },
        "deck_sha256": manifest["deck_sha256"],
        "elapsed_seconds": elapsed,
        "job_id": snapshot.job.job_id,
        "process_count_before_cleanup": outcome.process_count_before_cleanup,
        "return_code": outcome.return_code,
        "schema_version": DESKTOP_REAL_CORE_PROBE_VERSION,
        "state": snapshot.job.state.value,
    }
    return {
        **identity,
        "probe_id": stable_digest(identity, prefix="desktoprealcoreprobe_"),
    }


def collect_desktop_lifecycle_evidence(
    *,
    live_webview: bool = True,
    real_core_search: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("desktop lifecycle evidence requires Windows")
    with tempfile.TemporaryDirectory(prefix="ygo-desktop-lifecycle-") as temporary:
        root = Path(temporary)
        startup: dict[str, Any] = {
            "diagnostics": _startup_diagnostics(root / "runtime-fixtures")
        }
        if live_webview:
            first = collect_pywebview_live_probe(sys.executable)
            second = collect_pywebview_live_probe(sys.executable)
            startup.update(
                {
                    "cold": first,
                    "warm": second,
                    "webview2_version": preflight_desktop_runtime().version,
                }
            )
        identity = to_canonical_data(
            {
                "bridge": _bridge_audit(root),
                "frontend": _frontend_audit(),
                "host": {
                    "machine": platform.machine(),
                    "operating_system": platform.platform(),
                    "python": platform.python_version(),
                    "pywebview": (
                        importlib.metadata.version("pywebview")
                        if live_webview
                        else None
                    ),
                },
                "job_fault_matrix": _job_fault_matrix(root),
                "process_containment": {
                    "contract": process_containment_contract(),
                    "descendant_cleanup": _descendant_cleanup_probe(root),
                    "host_crash_restart": _host_crash_probe(root),
                },
                "real_core_search": real_core_search,
                "schema_version": DESKTOP_LIFECYCLE_EVIDENCE_VERSION,
                "startup": startup,
                "workflow_contract": desktop_workflow_contract_document()[
                    "schema_version"
                ],
            }
        )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="desktoplifecycleevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="collect Windows desktop lifecycle and accessibility evidence"
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--skip-live-webview", action="store_true")
    parser.add_argument("--skip-real-core-search", action="store_true")
    parser.add_argument("--real-core-evidence", type=Path)
    parser.add_argument("--real-core-probe-out", type=Path)
    args = parser.parse_args()
    if args.real_core_probe_out is not None:
        with tempfile.TemporaryDirectory(
            prefix="ygo-desktop-real-core-evidence-"
        ) as temporary:
            probe = _real_core_search_probe(Path(temporary))
            args.real_core_probe_out.parent.mkdir(parents=True, exist_ok=True)
            args.real_core_probe_out.write_text(
                json.dumps(probe, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        print(f"desktop-real-core-probe: wrote {args.real_core_probe_out}")
        return 0
    if args.skip_real_core_search and args.real_core_evidence is not None:
        parser.error("--skip-real-core-search and --real-core-evidence conflict")
    if args.out is None:
        parser.error("--out is required unless --real-core-probe-out is used")
    if not args.skip_real_core_search and args.real_core_evidence is None:
        parser.error(
            "provide --real-core-evidence from --real-core-probe-out, "
            "or use --skip-real-core-search"
        )
    real_core = (
        json.loads(args.real_core_evidence.read_text(encoding="utf-8"))
        if args.real_core_evidence is not None
        else None
    )
    evidence = collect_desktop_lifecycle_evidence(
        live_webview=not args.skip_live_webview,
        real_core_search=real_core,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"desktop-lifecycle-evidence: wrote {args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
