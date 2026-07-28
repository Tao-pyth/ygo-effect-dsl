from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from ygo_effect_dsl.cli.cmd_qualification import (
    cmd_research_dashboard_gate,
    cmd_research_dashboard_qualification,
    cmd_research_dashboard_qualification_bundle,
    cmd_research_dashboard_qualification_manifest_template,
)
from ygo_effect_dsl.desktop import DESKTOP_BRIDGE_CONTRACT_VERSION
from ygo_effect_dsl.desktop.service import DESKTOP_RESULT_VIEW_VERSION
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.research_dashboard_release_gate import (
    REQUIRED_MANUAL_GATE_CHECKS,
    REQUIRED_QUALIFICATION_CHECKS,
    REQUIRED_STATIC_GATE_CHECKS,
    RESEARCH_DASHBOARD_QUALIFICATION_SCHEMA_VERSION,
    RESEARCH_DASHBOARD_RELEASE_GATE_SCHEMA_VERSION,
    evaluate_research_dashboard_qualification,
    evaluate_research_dashboard_release_gate,
    read_research_dashboard_release_gate,
    validate_research_dashboard_qualification,
    validate_research_dashboard_release_gate,
    write_research_dashboard_release_gate,
)
from ygo_effect_dsl.storage.query import ANALYTICS_QUERY_CONTRACT_VERSION


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO_ROOT / "docs" / "release" / "evidence" / "research_dashboard_gate.json"
QUALIFICATION_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "research_dashboard_qualification.json"
)
_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64
_SHA_D = "d" * 64
_SHA_E = "e" * 64
_SHA_F = "f" * 64
_DASHBOARD_ROUTE_ID = stable_digest({"route": "fixture"}, prefix="route_")
_DASHBOARD_OTHER_ROUTE_ID = stable_digest({"route": "other"}, prefix="route_")


def _fresh_replay_report(route_id: str = _DASHBOARD_ROUTE_ID) -> dict[str, object]:
    identity = {
        "experiment": {
            "digest": stable_digest({"experiment": "fixture"}, prefix="experiment_"),
            "experiment_id": "experiment_fixture",
            "schema_version": "0.3a",
        },
        "lua_resolution": None,
        "replay": {
            "event_count": 1,
            "manifest_hash": stable_digest({"manifest": "fixture"}, prefix="manifest_"),
            "manifest_schema_version": "ygo-replay-manifest-v1",
            "terminal_state_hash": stable_digest({"state": "fixture"}, prefix="state_"),
        },
        "route": {
            "route_document_digest": stable_digest(
                {"route": route_id},
                prefix="routedoc_",
            ),
            "route_id": route_id,
        },
        "run_id": "run_fixture",
        "runtime": {
            "asset_lock_id": "asset_lock_fixture",
            "core_api": "0.0",
            "core_binary_sha256": _SHA_A,
            "core_lock_id": "core_lock_fixture",
            "core_source_commit": "1" * 40,
        },
        "scenario": None,
        "schema_version": "fresh-replay-verification-v1",
        "status": "verified",
        "verification_scope": "scripted_real_core",
    }
    return {
        **identity,
        "verification_id": stable_digest(identity, prefix="replayverify_"),
    }


def _png_header(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\r"
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def _write_dashboard_bundle_support_artifacts(artifacts: Path) -> None:
    for viewport in ("1440x900", "960x600", "360x800"):
        width, height = (int(part) for part in viewport.split("x"))
        (artifacts / f"desktop-{viewport}.png").write_bytes(
            _png_header(width, height)
        )
    (artifacts / "fresh-replay-report.json").write_text(
        json.dumps(_fresh_replay_report()),
        encoding="utf-8",
    )
    (artifacts / "security-redaction-review.json").write_text(
        json.dumps(
            {
                "absolute_paths_redacted": True,
                "csp_checked": True,
                "deck_contents_redacted": True,
                "renderer_path_input_rejected": True,
                "secret_scan_passed": True,
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "resource-budget.json").write_text(
        json.dumps(
            {
                "budget_wall_seconds": 30.0,
                "censor_state_recorded": True,
                "max_artifact_bytes": 32768,
                "max_peak_rss_bytes": 134217728,
                "max_wall_seconds": 12.5,
                "measured_runs": 3,
                "node_budget": 100000,
                "replay_budget": 100000,
                "within_budget": True,
            }
        ),
        encoding="utf-8",
    )


def _artifact(name: str, sha256: str, kind: str) -> dict[str, str]:
    return {"kind": kind, "name": name, "sha256": sha256}


def _passing_qualification_check(check_id: str) -> dict[str, object]:
    evidence_by_check: dict[str, dict[str, object]] = {
        "committed-artifact-e2e": {
            "artifact_id": "result_view_fixture",
            "artifact_kind": "committed-dashboard-result",
            "artifact_commit_status": "committed",
            "evidence_artifacts": [
                _artifact("result-view.json", _SHA_B, "result-view"),
                _artifact("route.yaml", _SHA_C, "route-dsl"),
                _artifact("search-report.json", _SHA_A, "search-run-report"),
            ],
            "path_redacted": True,
            "renderer_path_input": False,
            "report_sha256": _SHA_A,
            "report_sha256_verified": True,
            "result_view_schema_version": DESKTOP_RESULT_VIEW_VERSION,
            "result_view_sha256": _SHA_B,
            "route_artifact_schema_version": "route-dsl",
            "route_id": "route_fixture",
            "route_sha256": _SHA_C,
            "route_id_verified": True,
            "route_sha256_verified": True,
            "search_run_id": "search_run_fixture",
            "search_run_schema_version": "search-run-result-v5",
        },
        "fresh-replay-e2e": {
            "action_sequence_verified": True,
            "artifact_id": "fresh_replay_fixture",
            "artifact_kind": "fresh-replay-verification",
            "evidence_artifacts": [
                _artifact("fresh-replay-report.json", _SHA_D, "fresh-replay-report"),
            ],
            "fresh_worker": True,
            "path_redacted": True,
            "replay_report_sha256": _SHA_D,
            "route_id_verified": True,
            "schema_version": "fresh-replay-verification-v1",
            "search_worker_shared_state": False,
            "terminal_state_verified": True,
        },
        "desktop-screenshot-a11y": {
            "artifact_kind": "desktop-quality-evidence",
            "axe_violations": 0,
            "evidence_artifacts": [
                _artifact("desktop-1440x900.png", _SHA_A, "screenshot"),
                _artifact("desktop-360x800.png", _SHA_C, "screenshot"),
                _artifact("desktop-960x600.png", _SHA_B, "screenshot"),
            ],
            "high_contrast_passed": True,
            "keyboard_smoke_passed": True,
            "path_redacted": True,
            "reduced_motion_passed": True,
            "screenshot_sha256": {
                "1440x900": _SHA_A,
                "960x600": _SHA_B,
                "360x800": _SHA_C,
            },
            "viewports": ["1440x900", "960x600", "360x800"],
        },
        "security-redaction": {
            "absolute_paths_redacted": True,
            "artifact_kind": "security-redaction-review",
            "csp_checked": True,
            "deck_contents_redacted": True,
            "evidence_artifacts": [
                _artifact("security-redaction-review.json", _SHA_E, "security-review"),
            ],
            "path_redacted": True,
            "renderer_path_input_rejected": True,
            "review_sha256": _SHA_E,
            "secret_scan_passed": True,
        },
        "resource-budget": {
            "artifact_kind": "resource-budget",
            "budget_wall_seconds": 30.0,
            "censor_state_recorded": True,
            "evidence_artifacts": [
                _artifact("resource-budget.json", _SHA_F, "resource-budget"),
            ],
            "max_artifact_bytes": 32768,
            "max_peak_rss_bytes": 134217728,
            "max_wall_seconds": 12.5,
            "measured_runs": 3,
            "node_budget": 100000,
            "path_redacted": True,
            "replay_budget": 100000,
            "resource_report_sha256": _SHA_F,
            "within_budget": True,
        },
    }
    return {
        "check_id": check_id,
        "evidence": evidence_by_check[check_id],
        "passed": True,
    }


def _passing_qualification() -> dict[str, object]:
    return evaluate_research_dashboard_qualification(
        [_passing_qualification_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    )


def test_research_dashboard_gate_detects_static_contracts_and_committed_release() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == RESEARCH_DASHBOARD_RELEASE_GATE_SCHEMA_VERSION
    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="researchdashgate_",
    )
    assert [
        (check["gate"], check["check_id"]) for check in evidence["static_checks"]
    ] == list(REQUIRED_STATIC_GATE_CHECKS)
    assert [
        (check["gate"], check["check_id"]) for check in evidence["manual_checks"]
    ] == list(REQUIRED_MANUAL_GATE_CHECKS)
    assert all(check["passed"] for check in evidence["static_checks"])
    assert evidence["manual_checks"][0]["check_id"] == "real-core-dashboard-qualification"
    assert evidence["manual_checks"][0]["passed"] is True
    assert evidence["manual_checks"][0]["evidence"]["path_redacted"] is True
    assert evidence["manual_checks"][0]["evidence"]["source_path_name"] == (
        "research_dashboard_qualification.json"
    )
    assert evidence["manual_checks"][0]["evidence"]["check_count"] == len(
        REQUIRED_QUALIFICATION_CHECKS
    )
    committed_result = evidence["static_checks"][0]
    assert committed_result["evidence"]["bridge_schema_version"] == (
        DESKTOP_BRIDGE_CONTRACT_VERSION
    )
    assert committed_result["evidence"]["renderer_path_input"] is False
    assert committed_result["evidence"]["method_payload_fields_valid"] is True
    assert committed_result["evidence"]["requires_committed_artifacts"] == [
        "route-dsl",
        "search-run-report",
    ]
    assert committed_result["evidence"]["test_exists"] is True
    terminal_gate = [
        check
        for check in evidence["static_checks"]
        if check["check_id"] == "terminal-preference-contracts"
    ][0]
    assert terminal_gate["evidence"]["result_service_source_contains"] is True
    assert terminal_gate["evidence"]["desktop_test"] == "tests/test_desktop_bridge.py"
    assert terminal_gate["evidence"]["desktop_test_contains"] is True
    ranking_gate = [
        check
        for check in evidence["static_checks"]
        if check["check_id"] == "route-randomness-and-ranking-contracts"
    ][0]
    assert ranking_gate["evidence"]["result_service_source_contains"] is True
    assert ranking_gate["evidence"]["desktop_test"] == "tests/test_desktop_bridge.py"
    assert ranking_gate["evidence"]["desktop_test_contains"] is True
    coverage_gate = [
        check
        for check in evidence["static_checks"]
        if check["check_id"] == "candidate-coverage-and-drilldown-contracts"
    ][0]
    assert coverage_gate["evidence"]["result_service_source_contains"] is True
    assert coverage_gate["evidence"]["desktop_test"] == "tests/test_desktop_bridge.py"
    assert coverage_gate["evidence"]["desktop_test_contains"] is True
    cohort_ui = [
        check
        for check in evidence["static_checks"]
        if check["check_id"] == "typed-research-scenario-and-cohort-ui"
    ][0]
    assert cohort_ui["evidence"]["analytics_contract_version"] == (
        ANALYTICS_QUERY_CONTRACT_VERSION
    )
    assert cohort_ui["evidence"]["deck_register_inline_renderer_path_input"] is False
    assert cohort_ui["evidence"]["scenario_compose_renderer_path_input"] is False
    assert cohort_ui["evidence"]["scenario_compose_renderer_rule_inference"] is False
    assert cohort_ui["evidence"]["bridge_methods_valid"] is True
    assert cohort_ui["evidence"]["analytics_fields_present"] is True
    assert cohort_ui["evidence"]["source_contains"] is True
    assert evidence["passed"] is True
    assert evidence["rejection_reasons"] == []


def test_research_dashboard_gate_accepts_supplied_qualification(
    tmp_path: Path,
) -> None:
    qualification = tmp_path / "qualification.json"
    qualification.write_text(json.dumps(_passing_qualification()), encoding="utf-8")

    evidence = evaluate_research_dashboard_release_gate(
        REPO_ROOT,
        qualification_path=qualification,
    )

    assert evidence["passed"] is True
    assert evidence["rejection_reasons"] == []
    assert evidence["manual_checks"][0]["passed"] is True
    assert evidence["manual_checks"][0]["evidence"]["path_redacted"] is True
    assert evidence["manual_checks"][0]["evidence"]["source_path_name"] == (
        "qualification.json"
    )
    assert validate_research_dashboard_release_gate(evidence) == evidence


def test_research_dashboard_gate_rejects_unverified_minimal_qualification(
    tmp_path: Path,
) -> None:
    qualification = tmp_path / "qualification.json"
    qualification.write_text(
        json.dumps(
            {
                "evidence_id": "dashboardqual_fixture",
                "passed": True,
                "schema_version": "research-dashboard-qualification-v1",
            }
        ),
        encoding="utf-8",
    )

    evidence = evaluate_research_dashboard_release_gate(
        REPO_ROOT,
        qualification_path=qualification,
    )

    assert evidence["passed"] is False
    assert evidence["manual_checks"][0]["passed"] is False
    assert "invalid qualification evidence" in evidence["manual_checks"][0][
        "evidence"
    ]["reason"]


def test_research_dashboard_qualification_is_content_addressed() -> None:
    qualification = _passing_qualification()
    identity = {
        key: value for key, value in qualification.items() if key != "evidence_id"
    }

    assert (
        qualification["schema_version"]
        == RESEARCH_DASHBOARD_QUALIFICATION_SCHEMA_VERSION
    )
    assert qualification["passed"] is True
    assert qualification["evidence_id"] == stable_digest(
        identity,
        prefix="researchdashqual_",
    )
    assert validate_research_dashboard_qualification(qualification) == qualification


def test_research_dashboard_qualification_normalizes_required_check_order() -> None:
    reversed_checks = [
        _passing_qualification_check(check_id)
        for check_id in reversed(REQUIRED_QUALIFICATION_CHECKS)
    ]

    qualification = evaluate_research_dashboard_qualification(reversed_checks)

    assert [check["check_id"] for check in qualification["checks"]] == list(
        REQUIRED_QUALIFICATION_CHECKS
    )
    assert qualification == _passing_qualification()


def test_research_dashboard_qualification_rejects_tampering() -> None:
    qualification = _passing_qualification()
    qualification["checks"][0]["passed"] = False

    with pytest.raises(ValueError, match="evidence_id mismatch"):
        validate_research_dashboard_qualification(qualification)


def test_research_dashboard_qualification_rejects_inconsistent_pass_state() -> None:
    qualification = _passing_qualification()
    qualification["checks"][0]["passed"] = False
    identity = {
        key: value for key, value in qualification.items() if key != "evidence_id"
    }
    qualification["evidence_id"] = stable_digest(identity, prefix="researchdashqual_")

    with pytest.raises(ValueError, match="rejections are inconsistent"):
        validate_research_dashboard_qualification(qualification)


def test_research_dashboard_qualification_rejects_unexpected_or_duplicate_checks() -> None:
    extra = _passing_qualification()
    extra["checks"].append(
        {
            "check_id": "unreviewed-extra-check",
            "evidence": {"artifact": "extra.json"},
            "passed": True,
        }
    )
    identity = {key: value for key, value in extra.items() if key != "evidence_id"}
    extra["evidence_id"] = stable_digest(identity, prefix="researchdashqual_")

    with pytest.raises(ValueError, match="unexpected checks"):
        validate_research_dashboard_qualification(extra)

    duplicate = _passing_qualification()
    duplicate["checks"].append(dict(duplicate["checks"][0]))
    identity = {
        key: value for key, value in duplicate.items() if key != "evidence_id"
    }
    duplicate["evidence_id"] = stable_digest(identity, prefix="researchdashqual_")

    with pytest.raises(ValueError, match="duplicate checks"):
        validate_research_dashboard_qualification(duplicate)


def test_research_dashboard_qualification_rejects_non_canonical_check_order() -> None:
    qualification = _passing_qualification()
    qualification["checks"] = list(reversed(qualification["checks"]))
    identity = {
        key: value for key, value in qualification.items() if key != "evidence_id"
    }
    qualification["evidence_id"] = stable_digest(identity, prefix="researchdashqual_")

    with pytest.raises(ValueError, match="ordered as required"):
        validate_research_dashboard_qualification(qualification)


def test_research_dashboard_qualification_rejects_passing_minimal_evidence() -> None:
    checks = [_passing_qualification_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    checks[0] = {
        "check_id": "committed-artifact-e2e",
        "evidence": {"artifact": "committed-artifact-e2e.json"},
        "passed": True,
    }

    with pytest.raises(ValueError, match="passing evidence is insufficient"):
        evaluate_research_dashboard_qualification(checks)


def test_research_dashboard_qualification_rejects_passing_witness_tampering() -> None:
    checks = [_passing_qualification_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    checks[1]["evidence"]["fresh_worker"] = False

    with pytest.raises(ValueError, match="passing evidence is insufficient"):
        evaluate_research_dashboard_qualification(checks)


def test_research_dashboard_qualification_rejects_artifact_sha_mismatch() -> None:
    checks = [_passing_qualification_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    checks[0]["evidence"]["report_sha256"] = _SHA_D

    with pytest.raises(ValueError, match="passing evidence is insufficient"):
        evaluate_research_dashboard_qualification(checks)


def test_research_dashboard_qualification_rejects_passing_evidence_path_leak() -> None:
    checks = [_passing_qualification_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    checks[0]["evidence"]["evidence_artifacts"][0]["name"] = (
        "C:\\qualification\\result-view.json"
    )

    with pytest.raises(ValueError, match="passing evidence is insufficient"):
        evaluate_research_dashboard_qualification(checks)


def test_research_dashboard_qualification_rejects_passing_evidence_path_key() -> None:
    checks = [_passing_qualification_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    checks[0]["evidence"]["route_path"] = "route.yaml"

    with pytest.raises(ValueError, match="passing evidence is insufficient"):
        evaluate_research_dashboard_qualification(checks)


def test_research_dashboard_qualification_rejects_missing_artifact_manifest() -> None:
    checks = [_passing_qualification_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    del checks[-1]["evidence"]["evidence_artifacts"]

    with pytest.raises(ValueError, match="passing evidence is insufficient"):
        evaluate_research_dashboard_qualification(checks)


def test_research_dashboard_gate_writes_and_reads_content_addressed_json(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "research-dashboard-gate.json"
    evidence = write_research_dashboard_release_gate(
        REPO_ROOT,
        output_path=destination,
    )

    assert read_research_dashboard_release_gate(destination) == evidence


def test_research_dashboard_gate_rejects_tampering() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["static_checks"][0]["passed"] = False

    with pytest.raises(ValueError, match="evidence_id mismatch"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_inconsistent_rejections() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["manual_checks"][0]["passed"] = False
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="manual check evidence"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_duplicate_checks() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["static_checks"].append(dict(evidence["static_checks"][0]))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="duplicate checks"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_missing_static_check() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["static_checks"] = evidence["static_checks"][:-1]
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="static checks"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_unexpected_static_check() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["static_checks"][-1]["check_id"] = "untracked-static-contract"
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="static checks"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_static_evidence_tampering() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["static_checks"][0]["evidence"]["renderer_path_input"] = True
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="static check evidence"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_static_pass_tampering() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["static_checks"][0]["evidence"]["test_exists"] = False
    evidence["static_checks"][0]["passed"] = True
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="static check evidence"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_coverage_static_witness_tampering() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    coverage_gate = [
        check
        for check in evidence["static_checks"]
        if check["check_id"] == "candidate-coverage-and-drilldown-contracts"
    ][0]
    coverage_gate["evidence"]["result_service_source_contains"] = False
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="static check evidence"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_missing_manual_check() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["manual_checks"] = []
    evidence["rejection_reasons"] = []
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="manual checks"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_unexpected_manual_check() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["manual_checks"][0]["check_id"] = "paper-only-dashboard-review"
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="manual checks"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_manual_evidence_path_leak() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["manual_checks"][0]["evidence"]["path"] = (
        "C:\\qualification\\research_dashboard_qualification.json"
    )
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="leaks a path"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_manual_evidence_path_key_leak() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["manual_checks"][0]["evidence"]["qualification_path"] = (
        "research_dashboard_qualification.json"
    )
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="leaks a path"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_rejects_inconsistent_pass_state() -> None:
    evidence = evaluate_research_dashboard_release_gate(REPO_ROOT)
    evidence["passed"] = False
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}
    evidence["evidence_id"] = stable_digest(identity, prefix="researchdashgate_")

    with pytest.raises(ValueError, match="passed is inconsistent"):
        validate_research_dashboard_release_gate(evidence)


def test_research_dashboard_gate_cli_writes_committed_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "gate.json"

    status = cmd_research_dashboard_gate(
        argparse.Namespace(repo_root=REPO_ROOT, out=str(output), qualification=None)
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert evidence["passed"] is True
    assert "research-dashboard-gate: passed" in captured.out
    assert evidence["evidence_id"] in captured.out


def test_research_dashboard_qualification_cli_writes_failed_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    checks = tmp_path / "checks.json"
    output = tmp_path / "qualification.json"
    checks.write_text(
        json.dumps(
            {
                "checks": [
                    {
                        "check_id": check_id,
                        "evidence": {"reason": "pending self-hosted evidence"},
                        "passed": False,
                    }
                    for check_id in REQUIRED_QUALIFICATION_CHECKS
                ]
            }
        ),
        encoding="utf-8",
    )

    status = cmd_research_dashboard_qualification(
        argparse.Namespace(checks=checks, out=str(output))
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 1
    assert evidence["passed"] is False
    assert evidence["rejection_reasons"] == [
        f"failed:{check_id}" for check_id in REQUIRED_QUALIFICATION_CHECKS
    ]
    assert "research-dashboard-qualification: failed" in captured.out


def test_research_dashboard_qualification_cli_hashes_local_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for name in (
        "result-view.json",
        "route.yaml",
        "search-report.json",
        "fresh-replay-report.json",
        "desktop-1440x900.png",
        "desktop-960x600.png",
        "desktop-360x800.png",
        "security-redaction-review.json",
        "resource-budget.json",
    ):
        (artifacts / name).write_bytes(f"artifact:{name}".encode("utf-8"))
    checks = [_passing_qualification_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    for check in checks:
        evidence = check["evidence"]
        for artifact in evidence["evidence_artifacts"]:
            artifact.pop("sha256", None)
            artifact["path"] = str(Path("artifacts") / artifact["name"])
        for field in (
            "report_sha256",
            "result_view_sha256",
            "route_sha256",
            "replay_report_sha256",
            "review_sha256",
            "resource_report_sha256",
        ):
            evidence.pop(field, None)
        evidence.pop("screenshot_sha256", None)
    checks_path = tmp_path / "checks.json"
    output = tmp_path / "qualification.json"
    checks_path.write_text(json.dumps({"checks": checks}), encoding="utf-8")

    status = cmd_research_dashboard_qualification(
        argparse.Namespace(checks=checks_path, out=str(output))
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert evidence["passed"] is True
    assert "research-dashboard-qualification: passed" in captured.out
    for check in evidence["checks"]:
        assert check["evidence"]["path_redacted"] is True
        for artifact in check["evidence"]["evidence_artifacts"]:
            assert "path" not in artifact
            expected = (
                artifacts / artifact["name"]
            ).read_bytes()
            assert artifact["sha256"] == hashlib.sha256(expected).hexdigest()
    assert validate_research_dashboard_qualification(evidence) == evidence


def test_research_dashboard_qualification_bundle_builds_checks_from_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for name in (
        "fresh-replay-report.json",
        "desktop-1440x900.png",
        "desktop-960x600.png",
        "desktop-360x800.png",
        "security-redaction-review.json",
        "resource-budget.json",
    ):
        (artifacts / name).write_bytes(f"artifact:{name}".encode("utf-8"))
    _write_dashboard_bundle_support_artifacts(artifacts)
    search_report = {
        "artifact_commit": {"route_id": _DASHBOARD_ROUTE_ID, "status": "committed"},
        "best_route": {"route_id": _DASHBOARD_ROUTE_ID},
        "report_schema_version": "search-run-report-v1",
        "run_id": "searchrun_fixture",
        "schema_version": "search-run-result-v5",
    }
    (artifacts / "result-view.json").write_text(
        json.dumps({"schema_version": DESKTOP_RESULT_VIEW_VERSION}),
        encoding="utf-8",
    )
    (artifacts / "route.yaml").write_text(
        f"route_id: {_DASHBOARD_ROUTE_ID}\nlineage:\n  parent_route_id: null\n",
        encoding="utf-8",
    )
    (artifacts / "search-report.json").write_text(
        json.dumps(search_report),
        encoding="utf-8",
    )
    manifest = tmp_path / "artifact-manifest.json"
    checks_out = tmp_path / "checks.json"
    output = tmp_path / "qualification.json"
    manifest.write_text(
        json.dumps(
            {
                "committed_artifact": {
                    "renderer_path_input": False,
                    "report_sha256_verified": True,
                    "result_view": "artifacts/result-view.json",
                    "route": "artifacts/route.yaml",
                    "route_id_verified": True,
                    "route_sha256_verified": True,
                    "search_report": "artifacts/search-report.json",
                },
                "desktop": {
                    "axe_violations": 0,
                    "high_contrast_passed": True,
                    "keyboard_smoke_passed": True,
                    "reduced_motion_passed": True,
                    "screenshots": {
                        "1440x900": "artifacts/desktop-1440x900.png",
                        "960x600": "artifacts/desktop-960x600.png",
                        "360x800": "artifacts/desktop-360x800.png",
                    },
                },
                "fresh_replay": {
                    "action_sequence_verified": True,
                    "fresh_worker": True,
                    "report": "artifacts/fresh-replay-report.json",
                    "route_id_verified": True,
                    "search_worker_shared_state": False,
                    "terminal_state_verified": True,
                },
                "resource_budget": {
                    "budget_wall_seconds": 30.0,
                    "censor_state_recorded": True,
                    "max_artifact_bytes": 32768,
                    "max_peak_rss_bytes": 134217728,
                    "max_wall_seconds": 12.5,
                    "measured_runs": 3,
                    "node_budget": 100000,
                    "replay_budget": 100000,
                    "report": "artifacts/resource-budget.json",
                    "within_budget": True,
                },
                "schema_version": (
                    "research-dashboard-qualification-artifact-manifest-v1"
                ),
                "security_redaction": {
                    "absolute_paths_redacted": True,
                    "csp_checked": True,
                    "deck_contents_redacted": True,
                    "renderer_path_input_rejected": True,
                    "review": "artifacts/security-redaction-review.json",
                    "secret_scan_passed": True,
                },
            }
        ),
        encoding="utf-8",
    )

    status = cmd_research_dashboard_qualification_bundle(
        argparse.Namespace(manifest=manifest, checks_out=checks_out, out=str(output))
    )
    captured = capsys.readouterr()
    checks = json.loads(checks_out.read_text(encoding="utf-8"))
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert "research-dashboard-qualification-bundle: passed" in captured.out
    assert [check["check_id"] for check in checks["checks"]] == list(
        REQUIRED_QUALIFICATION_CHECKS
    )
    assert checks["checks"][0]["evidence"]["route_id"] == _DASHBOARD_ROUTE_ID
    assert checks["checks"][0]["evidence"]["search_run_id"] == "searchrun_fixture"
    assert validate_research_dashboard_qualification(evidence) == evidence
    for check in evidence["checks"]:
        assert check["passed"] is True
        assert check["evidence"]["path_redacted"] is True
        for artifact in check["evidence"]["evidence_artifacts"]:
            assert "path" not in artifact
            assert len(artifact["sha256"]) == 64


def test_research_dashboard_qualification_bundle_requires_measured_booleans(
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for name in (
        "fresh-replay-report.json",
        "desktop-1440x900.png",
        "desktop-960x600.png",
        "desktop-360x800.png",
        "security-redaction-review.json",
        "resource-budget.json",
    ):
        (artifacts / name).write_bytes(f"artifact:{name}".encode("utf-8"))
    _write_dashboard_bundle_support_artifacts(artifacts)
    (artifacts / "result-view.json").write_text(
        json.dumps({"schema_version": DESKTOP_RESULT_VIEW_VERSION}),
        encoding="utf-8",
    )
    (artifacts / "route.yaml").write_text(
        f"route_id: {_DASHBOARD_ROUTE_ID}\nlineage:\n  parent_route_id: null\n",
        encoding="utf-8",
    )
    (artifacts / "search-report.json").write_text(
        json.dumps(
            {
                "artifact_commit": {
                    "route_id": _DASHBOARD_ROUTE_ID,
                    "status": "committed",
                },
                "best_route": {"route_id": _DASHBOARD_ROUTE_ID},
                "report_schema_version": "search-run-report-v1",
                "run_id": "searchrun_fixture",
                "schema_version": "search-run-result-v5",
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "artifact-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "committed_artifact": {
                    "result_view": "artifacts/result-view.json",
                    "route": "artifacts/route.yaml",
                    "search_report": "artifacts/search-report.json",
                },
                "desktop": {
                    "axe_violations": 0,
                    "screenshots": {
                        "1440x900": "artifacts/desktop-1440x900.png",
                        "960x600": "artifacts/desktop-960x600.png",
                        "360x800": "artifacts/desktop-360x800.png",
                    },
                },
                "fresh_replay": {
                    "report": "artifacts/fresh-replay-report.json",
                },
                "resource_budget": {
                    "budget_wall_seconds": 30.0,
                    "max_artifact_bytes": 32768,
                    "max_peak_rss_bytes": 134217728,
                    "max_wall_seconds": 12.5,
                    "measured_runs": 3,
                    "node_budget": 100000,
                    "replay_budget": 100000,
                    "report": "artifacts/resource-budget.json",
                },
                "schema_version": (
                    "research-dashboard-qualification-artifact-manifest-v1"
                ),
                "security_redaction": {
                    "review": "artifacts/security-redaction-review.json",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="renderer_path_input must be a boolean"):
        cmd_research_dashboard_qualification_bundle(
            argparse.Namespace(
                manifest=manifest,
                checks_out=None,
                out=str(tmp_path / "qualification.json"),
            )
        )


def test_research_dashboard_qualification_bundle_rejects_invalid_committed_artifacts(
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for name in (
        "fresh-replay-report.json",
        "desktop-1440x900.png",
        "desktop-960x600.png",
        "desktop-360x800.png",
        "security-redaction-review.json",
        "resource-budget.json",
    ):
        (artifacts / name).write_bytes(f"artifact:{name}".encode("utf-8"))
    _write_dashboard_bundle_support_artifacts(artifacts)
    (artifacts / "result-view.json").write_text(
        json.dumps({"schema_version": DESKTOP_RESULT_VIEW_VERSION}),
        encoding="utf-8",
    )
    (artifacts / "route.yaml").write_text(
        f"route_id: {_DASHBOARD_OTHER_ROUTE_ID}\nlineage:\n  parent_route_id: null\n",
        encoding="utf-8",
    )
    (artifacts / "search-report.json").write_text(
        json.dumps(
            {
                "artifact_commit": {
                    "route_id": _DASHBOARD_ROUTE_ID,
                    "status": "committed",
                },
                "best_route": {"route_id": _DASHBOARD_ROUTE_ID},
                "report_schema_version": "search-run-report-v1",
                "run_id": "searchrun_fixture",
                "schema_version": "search-run-result-v5",
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "artifact-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "committed_artifact": {
                    "renderer_path_input": False,
                    "report_sha256_verified": True,
                    "result_view": "artifacts/result-view.json",
                    "route": "artifacts/route.yaml",
                    "route_id_verified": True,
                    "route_sha256_verified": True,
                    "search_report": "artifacts/search-report.json",
                },
                "desktop": {
                    "axe_violations": 0,
                    "high_contrast_passed": True,
                    "keyboard_smoke_passed": True,
                    "reduced_motion_passed": True,
                    "screenshots": {
                        "1440x900": "artifacts/desktop-1440x900.png",
                        "960x600": "artifacts/desktop-960x600.png",
                        "360x800": "artifacts/desktop-360x800.png",
                    },
                },
                "fresh_replay": {
                    "action_sequence_verified": True,
                    "fresh_worker": True,
                    "report": "artifacts/fresh-replay-report.json",
                    "route_id_verified": True,
                    "search_worker_shared_state": False,
                    "terminal_state_verified": True,
                },
                "resource_budget": {
                    "budget_wall_seconds": 30.0,
                    "censor_state_recorded": True,
                    "max_artifact_bytes": 32768,
                    "max_peak_rss_bytes": 134217728,
                    "max_wall_seconds": 12.5,
                    "measured_runs": 3,
                    "node_budget": 100000,
                    "replay_budget": 100000,
                    "report": "artifacts/resource-budget.json",
                    "within_budget": True,
                },
                "schema_version": (
                    "research-dashboard-qualification-artifact-manifest-v1"
                ),
                "security_redaction": {
                    "absolute_paths_redacted": True,
                    "csp_checked": True,
                    "deck_contents_redacted": True,
                    "renderer_path_input_rejected": True,
                    "review": "artifacts/security-redaction-review.json",
                    "secret_scan_passed": True,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="route_id mismatch"):
        cmd_research_dashboard_qualification_bundle(
            argparse.Namespace(
                manifest=manifest,
                checks_out=None,
                out=str(tmp_path / "qualification.json"),
            )
        )

    (artifacts / "route.yaml").write_text(
        f"route_id: {_DASHBOARD_ROUTE_ID}\nlineage:\n  parent_route_id: null\n",
        encoding="utf-8",
    )
    search_report = json.loads((artifacts / "search-report.json").read_text())
    search_report["report_schema_version"] = "wrong"
    (artifacts / "search-report.json").write_text(
        json.dumps(search_report),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="report_schema_version"):
        cmd_research_dashboard_qualification_bundle(
            argparse.Namespace(
                manifest=manifest,
                checks_out=None,
                out=str(tmp_path / "qualification.json"),
            )
        )

    search_report["report_schema_version"] = "search-run-report-v1"
    (artifacts / "search-report.json").write_text(
        json.dumps(search_report),
        encoding="utf-8",
    )
    (artifacts / "fresh-replay-report.json").write_text(
        json.dumps(_fresh_replay_report(route_id=_DASHBOARD_OTHER_ROUTE_ID)),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fresh_replay.report route_id"):
        cmd_research_dashboard_qualification_bundle(
            argparse.Namespace(
                manifest=manifest,
                checks_out=None,
                out=str(tmp_path / "qualification.json"),
            )
        )

    (artifacts / "fresh-replay-report.json").write_text(
        json.dumps(_fresh_replay_report()),
        encoding="utf-8",
    )
    resource_report = json.loads((artifacts / "resource-budget.json").read_text())
    resource_report["node_budget"] = 99999
    (artifacts / "resource-budget.json").write_text(
        json.dumps(resource_report),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="node_budget does not match"):
        cmd_research_dashboard_qualification_bundle(
            argparse.Namespace(
                manifest=manifest,
                checks_out=None,
                out=str(tmp_path / "qualification.json"),
            )
        )

    _write_dashboard_bundle_support_artifacts(artifacts)
    security_review = json.loads(
        (artifacts / "security-redaction-review.json").read_text()
    )
    security_review["secret_scan_passed"] = False
    (artifacts / "security-redaction-review.json").write_text(
        json.dumps(security_review),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="secret_scan_passed does not match"):
        cmd_research_dashboard_qualification_bundle(
            argparse.Namespace(
                manifest=manifest,
                checks_out=None,
                out=str(tmp_path / "qualification.json"),
            )
        )

    _write_dashboard_bundle_support_artifacts(artifacts)
    (artifacts / "desktop-360x800.png").write_bytes(_png_header(361, 800))
    with pytest.raises(ValueError, match="screenshot 360x800 dimensions"):
        cmd_research_dashboard_qualification_bundle(
            argparse.Namespace(
                manifest=manifest,
                checks_out=None,
                out=str(tmp_path / "qualification.json"),
            )
        )


def test_research_dashboard_qualification_manifest_template_requires_operator_fill(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = tmp_path / "artifact-manifest.json"

    status = cmd_research_dashboard_qualification_manifest_template(
        argparse.Namespace(
            artifact_root="runner-artifacts",
            out=str(manifest),
        )
    )
    captured = capsys.readouterr()
    template = json.loads(manifest.read_text(encoding="utf-8"))

    assert status == 0
    assert "research-dashboard-qualification-manifest-template:" in captured.out
    assert template["schema_version"] == (
        "research-dashboard-qualification-artifact-manifest-v1"
    )
    assert template["committed_artifact"]["result_view"] == (
        "runner-artifacts/result-view.json"
    )
    assert template["committed_artifact"]["renderer_path_input"] is None
    assert template["fresh_replay"]["fresh_worker"] is None
    assert template["desktop"]["high_contrast_passed"] is None
    assert template["security_redaction"]["secret_scan_passed"] is None
    assert template["resource_budget"]["within_budget"] is None

    with pytest.raises(ValueError, match="result_view must point to a readable"):
        cmd_research_dashboard_qualification_bundle(
            argparse.Namespace(
                manifest=manifest,
                checks_out=None,
                out=str(tmp_path / "qualification.json"),
            )
        )


def test_committed_research_dashboard_gate_is_content_addressed() -> None:
    evidence = read_research_dashboard_release_gate(EVIDENCE_PATH)

    assert evidence["schema_version"] == RESEARCH_DASHBOARD_RELEASE_GATE_SCHEMA_VERSION
    assert all(check["passed"] for check in evidence["static_checks"])
    assert evidence["passed"] is True
    assert evidence["rejection_reasons"] == []
    assert evidence["manual_checks"][0]["passed"] is True
    assert evidence["manual_checks"][0]["evidence"]["path_redacted"] is True
    assert evidence["manual_checks"][0]["evidence"]["source_path_name"] == (
        "research_dashboard_qualification.json"
    )
    assert evidence["manual_checks"][0]["evidence"]["evidence_id"].startswith(
        "researchdashqual_"
    )


def test_committed_research_dashboard_qualification_is_content_addressed() -> None:
    qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))

    assert validate_research_dashboard_qualification(qualification) == qualification
    assert qualification["passed"] is True
    assert qualification["rejection_reasons"] == []
    assert [check["check_id"] for check in qualification["checks"]] == list(
        REQUIRED_QUALIFICATION_CHECKS
    )
