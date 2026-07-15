from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.desktop_lifecycle_evidence import (
    DESKTOP_LIFECYCLE_EVIDENCE_VERSION,
    DESKTOP_REAL_CORE_PROBE_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO_ROOT / "docs" / "ui" / "evidence" / "desktop_lifecycle.json"
REAL_CORE_EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "ui" / "evidence" / "desktop_real_core_search.json"
)


def test_committed_desktop_lifecycle_evidence_is_content_addressed() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == DESKTOP_LIFECYCLE_EVIDENCE_VERSION
    assert evidence["evidence_id"] == stable_digest(
        identity, prefix="desktoplifecycleevidence_"
    )
    assert evidence["bridge"] == {
        "method_count": 12,
        "method_drift": False,
        "path_input_diagnostic": "renderer_path_forbidden",
        "public_python_methods": ["invoke"],
    }


def test_committed_process_and_job_recovery_evidence_fails_closed() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    cleanup = evidence["process_containment"]["descendant_cleanup"]
    restart = evidence["process_containment"]["host_crash_restart"]
    faults = evidence["job_fault_matrix"]

    assert cleanup["before"]["active_processes"] >= 2
    assert cleanup["after"]["active_processes"] == 0
    assert cleanup["after"]["total_processes"] >= 2
    assert cleanup["after"]["peak_job_memory_bytes"] > 0
    assert restart["process_tree_after_termination"]["active_processes"] == 0
    assert restart["reclaimed_state"] == "retrying"
    assert restart["attempt_after_restart"] == 2
    assert restart["checkpoint_completed_units"] == 17
    assert restart["resume_input_digest_matches"] is True
    assert faults["renderer_crash"]["worker_lease_survived_renderer_read"] is True
    assert faults["worker_crash"] == {"artifacts": 0, "state": "retrying"}
    assert faults["cancel"] == {"artifacts": 0, "state": "cancelled"}
    assert faults["worker_timeout"] == {
        "artifacts": 0,
        "error_code": "hard_timeout",
        "state": "retrying",
    }


def test_committed_accessibility_security_and_runtime_evidence() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    accessibility = evidence["frontend"]["accessibility"]
    security = evidence["frontend"]["security"]

    assert accessibility["focusable_control_count"] >= 30
    assert accessibility["icon_button_names_complete"] is True
    assert accessibility["forced_colors_rules"] is True
    assert accessibility["reduced_motion_rules"] is True
    assert accessibility["skip_link"] is True
    assert accessibility["tab_arrow_navigation"] is True
    assert security == {
        "csp_default_deny": True,
        "local_rest_api": False,
        "network_api_absent": True,
        "remote_urls_absent": True,
    }
    assert evidence["startup"]["diagnostics"] == {
        "missing_runtime": "webview2_runtime_missing",
        "outdated_pywebview": "pywebview_version_mismatch",
    }
    assert evidence["startup"]["cold"]["loaded"] is True
    assert evidence["startup"]["warm"]["loaded"] is True
    assert evidence["startup"]["cold"]["pywebview_version"] == "6.2.1"
    assert evidence["startup"]["warm"]["pywebview_version"] == "6.2.1"
    assert evidence["startup"]["webview2_version"]


def test_committed_real_core_desktop_probe_is_reproducible_and_linked() -> None:
    probe = json.loads(REAL_CORE_EVIDENCE_PATH.read_text(encoding="utf-8"))
    identity = {key: value for key, value in probe.items() if key != "probe_id"}
    lifecycle = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert probe["schema_version"] == DESKTOP_REAL_CORE_PROBE_VERSION
    assert probe["probe_id"] == stable_digest(identity, prefix="desktoprealcoreprobe_")
    assert probe["state"] == "succeeded"
    assert probe["return_code"] == 0
    assert probe["artifact_count"] == 2
    assert {artifact["kind"] for artifact in probe["artifacts"]} == {
        "route-dsl",
        "search-run-report",
    }
    assert probe["checkpoint"]["position"] == "search:attempt:1:complete"
    assert probe["checkpoint"]["semantic_result_digest"].startswith("jobsemantic_")
    assert lifecycle["real_core_search"] == probe
