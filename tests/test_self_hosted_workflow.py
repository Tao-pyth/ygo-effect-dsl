from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from ygo_effect_dsl.cli.cmd_qualification import (
    cmd_release_self_hosted_evidence_adopt,
    cmd_release_self_hosted_evidence_audit,
    cmd_release_self_hosted_evidence_verify_adopted,
    cmd_release_readiness_verify,
)
from ygo_effect_dsl.desktop.service import DESKTOP_RESULT_VIEW_VERSION
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.parallel_search_release_gate import (
    PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION,
    _record_bundle_witness,
    write_parallel_search_release_gate,
)
from ygo_effect_dsl.spikes.research_dashboard_release_gate import (
    REQUIRED_QUALIFICATION_CHECKS,
    evaluate_research_dashboard_qualification,
    write_research_dashboard_release_gate,
)
from ygo_effect_dsl.spikes.release_self_hosted_evidence import (
    adopt_release_self_hosted_evidence,
    read_adopted_release_self_hosted_evidence_verification,
)
from ygo_effect_dsl.spikes.release_readiness_status import (
    read_release_readiness_status,
    validate_release_readiness_status,
    write_release_readiness_status,
)


ROOT = Path(__file__).parents[1]
RELEASE_EVIDENCE = ROOT / "docs" / "release" / "evidence"
_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64
_SHA_D = "d" * 64
_SHA_E = "e" * 64
_SHA_F = "f" * 64


def _artifact(name: str, sha256: str, kind: str) -> dict[str, str]:
    return {"kind": kind, "name": name, "sha256": sha256}


def _passing_parallel_record(
    profile_id: str,
    pool_size: int,
    repeat_index: int,
    wall_seconds: float,
) -> dict[str, object]:
    return {
        "best_route_id": f"route_{profile_id}",
        "committed_nodes": 100_000,
        "lineage_digest": f"lineage_{profile_id}",
        "node_budget": 100_000,
        "pool_size": pool_size,
        "profile_id": profile_id,
        "repeat_index": repeat_index,
        "replay_budget": 100_000,
        "rss_peak_bytes": 256_000_000 + pool_size,
        "semantic_digest": f"semantic_{profile_id}",
        "timing_censored": False,
        "wall_seconds": wall_seconds,
        "worker_kind": "real_core",
    }


def _passing_parallel_records() -> list[dict[str, object]]:
    profile_walls = {
        "grave_banish_or_chain": {1: 100.0, 2: 80.0, 4: 70.0},
        "long_line": {1: 120.0, 2: 95.0, 4: 89.0},
        "short_line": {1: 80.0, 2: 70.0, 4: 74.0},
    }
    records = []
    for profile_id, pool_walls in profile_walls.items():
        for pool_size, wall_seconds in pool_walls.items():
            for repeat_index in range(5):
                records.append(
                    _passing_parallel_record(
                        profile_id,
                        pool_size,
                        repeat_index,
                        wall_seconds + repeat_index * 0.1,
                    )
                )
    return records


def _parallel_manifest_for_records(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    manifest = []
    for record in records:
        report_name = (
            f"{record['profile_id']}-{record['pool_size']}-"
            f"{record['repeat_index']}.json"
        )
        manifest.append(
            {
                "node_budget": record["node_budget"],
                "path_redacted": True,
                "pool_size": record["pool_size"],
                "profile_id": record["profile_id"],
                "repeat_index": record["repeat_index"],
                "replay_budget": record["replay_budget"],
                "report_path_name": report_name,
                "report_sha256": hashlib.sha256(
                    report_name.encode("utf-8")
                ).hexdigest(),
                "rss_peak_bytes": record["rss_peak_bytes"],
                "timing_censored": record["timing_censored"],
                "worker_kind": record["worker_kind"],
            }
        )
    return sorted(
        manifest,
        key=lambda entry: (
            entry["profile_id"],
            entry["pool_size"],
            entry["repeat_index"],
            entry["report_sha256"],
            entry.get("route_sha256") or "",
        ),
    )


def _write_passing_parallel_artifacts(artifact_dir: Path) -> None:
    records = _passing_parallel_records()
    records_document = {
        "input_manifest": _parallel_manifest_for_records(records),
        "records": records,
        "schema_version": PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION,
    }
    records_document["evidence_id"] = stable_digest(
        records_document,
        prefix="parsearchrecords_",
    )
    records_path = artifact_dir / "parallel_search_records.json"
    records_path.write_text(
        json.dumps(records_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_parallel_search_release_gate(
        records,
        output_path=artifact_dir / "parallel_search_gate.json",
        record_bundle=_record_bundle_witness(records_document, source_path=records_path),
    )


def _passing_dashboard_check(check_id: str) -> dict[str, object]:
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
            "route_id_verified": True,
            "route_sha256": _SHA_C,
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
                "360x800": _SHA_C,
                "960x600": _SHA_B,
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
    return {"check_id": check_id, "evidence": evidence_by_check[check_id], "passed": True}


def _write_passing_dashboard_artifacts(artifact_dir: Path) -> None:
    qualification = evaluate_research_dashboard_qualification(
        [_passing_dashboard_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    )
    qualification_path = artifact_dir / "research_dashboard_qualification.json"
    qualification_path.write_text(
        json.dumps(qualification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_research_dashboard_release_gate(
        ROOT,
        output_path=artifact_dir / "research_dashboard_gate.json",
        qualification_path=qualification_path,
    )


def _write_failing_dashboard_artifacts(artifact_dir: Path) -> None:
    checks = [_passing_dashboard_check(check_id) for check_id in REQUIRED_QUALIFICATION_CHECKS]
    checks[-1]["passed"] = False
    qualification = evaluate_research_dashboard_qualification(checks)
    qualification_path = artifact_dir / "research_dashboard_qualification.json"
    qualification_path.write_text(
        json.dumps(qualification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_research_dashboard_release_gate(
        ROOT,
        output_path=artifact_dir / "research_dashboard_gate.json",
        qualification_path=qualification_path,
    )


def test_real_core_workflow_is_manual_self_hosted_and_sanitized() -> None:
    path = ROOT / ".github/workflows/real-core-self-hosted-smoke.yml"
    raw = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    trigger = workflow.get("on", workflow.get(True))

    assert set(trigger) == {"workflow_dispatch"}
    job = workflow["jobs"]["smoke"]
    assert job["runs-on"] == ["self-hosted", "Windows", "X64", "ygo-real-core"]
    assert "ocgcore-doctor" in raw
    assert "ocgcore-verify" in raw
    assert "ocgcore-assets-verify" in raw
    assert "experiment-search" in raw
    assert "experiment-replay" in raw
    assert "summary.json" in raw
    assert raw.index("Initialize sanitized smoke summary") < raw.index(
        "Check out exact commit"
    )
    assert "shell: pwsh" not in raw
    assert "actions/checkout@" not in raw
    assert "fetch --no-tags --depth=1 origin $env:GITHUB_SHA" in raw
    assert "if ($actual -ne $env:GITHUB_SHA)" in raw
    assert "sys.version_info >= (3, 10)" in raw
    assert "actions/upload-artifact@v7" in raw
    published = raw.split("Publish sanitized smoke summary", 1)[1]
    assert "best.route.yaml" not in published
    assert "lua.json" not in published
    assert "search.json" not in published


def test_release_evidence_workflow_runs_only_self_hosted_and_publishes_redacted_outputs() -> None:
    path = ROOT / ".github/workflows/release-self-hosted-evidence.yml"
    raw = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    trigger = workflow.get("on", workflow.get(True))

    assert set(trigger) == {"workflow_dispatch"}
    job = workflow["jobs"]["evidence"]
    assert job["runs-on"] == ["self-hosted", "Windows", "X64", "ygo-real-core"]
    assert "parallel-search-collect" in raw
    assert "parallel-search-gate" in raw
    assert "docs/search/evidence/real_core_parallel_stress.json" in raw
    assert "docs/adr/evidence/0105_general_search_100k.json" in raw
    assert "docs/adr/evidence/0128_real_core_replay_pool.json" in raw
    assert "cross_validation_short.yaml" in raw
    assert "cross_validation_long.yaml" in raw
    assert "cross_validation_grave_banish.yaml" in raw
    assert "real_core_recovery_interrupted_with_card.yaml" not in raw
    assert "real_core_interruption_sequence_stage2.yaml" not in raw
    assert "research-dashboard-qualification-bundle" in raw
    assert "research-dashboard-gate" in raw
    assert "Finalize and audit sanitized release evidence" in raw
    assert "release-self-hosted-evidence-audit" in raw
    assert "ocgcore-verify --external-root $env:YGO_EFFECT_DSL_EXTERNAL_ROOT" in raw
    assert "ocgcore-assets-verify --external-root $env:YGO_EFFECT_DSL_EXTERNAL_ROOT" in raw
    assert "--external-root $env:YGO_EFFECT_DSL_EXTERNAL_ROOT" in raw
    assert "--require-release-grid" in raw
    assert "--max-depth 2" in raw
    assert "RESEARCH_DASHBOARD_MANIFEST" in raw
    assert "--expected-commit', $env:GITHUB_SHA" in raw
    assert "--expected-run-id', $env:GITHUB_RUN_ID" in raw
    assert raw.index("Initialize sanitized release summary") < raw.index(
        "Check out exact commit"
    )
    assert "actions/checkout@" not in raw
    assert "fetch --no-tags --depth=1 origin $env:GITHUB_SHA" in raw
    assert "if ($actual -ne $env:GITHUB_SHA)" in raw
    assert "actions/upload-artifact@v7" in raw
    assert "New-Object System.Text.UTF8Encoding $false" in raw
    assert "[System.IO.File]::WriteAllText" in raw
    assert "Set-Content -Encoding utf8" not in raw
    published = raw.split("Publish sanitized release evidence", 1)[1]
    assert "raw-parallel-search" not in published
    assert "parallel_search_record_inputs.json" not in published
    assert "research_dashboard_qualification_checks.json" not in published
    assert "release-self-hosted-evidence-audit.json" not in published
    assert "best.route.yaml" not in published
    assert "search-report.json" not in published
    assert "parallel_search_records.json" in published
    assert "parallel_search_gate.json" in published
    assert "research_dashboard_qualification.json" in published
    assert "research_dashboard_gate.json" in published
    summary_step = next(
        step
        for step in job["steps"]
        if step["name"] == "Initialize sanitized release summary"
    )
    assert summary_step["env"]["RUN_PARALLEL_SEARCH"] == (
        "${{ inputs.run_parallel_search }}"
    )
    assert summary_step["env"]["RUN_RESEARCH_DASHBOARD"] == (
        "${{ inputs.run_research_dashboard }}"
    )
    assert "${{ inputs.run_parallel_search }}" not in summary_step["run"]
    assert "${{ inputs.run_research_dashboard }}" not in summary_step["run"]
    research_step = next(
        step
        for step in job["steps"]
        if step["name"] == "Run 0.7 research-dashboard qualification bundle"
    )
    assert research_step["env"]["RESEARCH_DASHBOARD_MANIFEST"] == (
        "${{ inputs.research_dashboard_manifest }}"
    )
    assert "${{ inputs.research_dashboard_manifest }}" not in research_step["run"]
    assert "--manifest $env:RESEARCH_DASHBOARD_MANIFEST" in research_step["run"]
    finalize_step = next(
        step
        for step in job["steps"]
        if step["name"] == "Finalize and audit sanitized release evidence"
    )
    assert finalize_step["env"]["RUN_PARALLEL_SEARCH"] == (
        "${{ inputs.run_parallel_search }}"
    )
    assert finalize_step["env"]["RUN_RESEARCH_DASHBOARD"] == (
        "${{ inputs.run_research_dashboard }}"
    )
    assert "${{ inputs.run_parallel_search }}" not in finalize_step["run"]
    assert "${{ inputs.run_research_dashboard }}" not in finalize_step["run"]
    assert "release_evidence_audit_failed" in finalize_step["run"]


def test_default_ci_verifies_release_readiness_status_freshness() -> None:
    path = ROOT / ".github/workflows/test.yml"
    raw = path.read_text(encoding="utf-8")

    assert "release-readiness-verify" in raw
    assert "--evidence-dir docs/release/evidence" in raw
    assert "--status docs/release/evidence/release_readiness_status.json" in raw
    assert "--require-passed" not in raw
    assert raw.index("Run pytest") < raw.index(
        "Verify release readiness evidence is current"
    )


def test_readme_regenerates_readiness_after_stage_gates() -> None:
    raw = (ROOT / "README.md").read_text(encoding="utf-8")

    readiness = raw.index("release-readiness-status")
    assert raw.index("test-profile-gate") < readiness
    assert raw.index(
        "parallel-search-gate --records docs/release/evidence/"
        "parallel_search_records_pending.json"
    ) < readiness
    assert raw.index("research-dashboard-gate --repo-root .") < readiness
    assert readiness < raw.index("release-self-hosted-evidence-audit")
    assert readiness < raw.index("release-self-hosted-evidence-adopt")


def test_release_readiness_status_reports_current_pending_release_evidence(
    tmp_path: Path,
) -> None:
    output = tmp_path / "release-readiness.json"

    evidence = write_release_readiness_status(RELEASE_EVIDENCE, output_path=output)
    validated = read_release_readiness_status(output, evidence_dir=RELEASE_EVIDENCE)
    stages = {stage["stage"]: stage for stage in validated["stages"]}

    assert evidence["evidence_id"] == validated["evidence_id"]
    assert validated["passed"] is True
    assert validated["ready_versions"] == ["0.5.1", "0.6.0", "0.7.0"]
    assert validated["incomplete_versions"] == []
    assert stages["0.5.1"]["ready"] is True
    assert stages["0.5.1"]["gate"]["passed"] is True
    assert stages["0.6.0"]["ready"] is True
    assert stages["0.6.0"]["gate"]["passed"] is True
    assert stages["0.6.0"]["adopted_self_hosted_evidence"]["passed"] is True
    assert stages["0.7.0"]["ready"] is True
    assert stages["0.7.0"]["gate"]["passed"] is True
    assert stages["0.7.0"]["adopted_self_hosted_evidence"]["passed"] is True
    assert validated["evidence_id"].startswith("releasereadiness_")


def test_release_readiness_status_rejects_tampered_status(
    tmp_path: Path,
) -> None:
    output = tmp_path / "release-readiness.json"
    write_release_readiness_status(RELEASE_EVIDENCE, output_path=output)
    evidence = json.loads(output.read_text(encoding="utf-8"))
    evidence["ready_versions"] = ["0.5.1"]
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="evidence_id mismatch"):
        read_release_readiness_status(output)

    identity = dict(evidence)
    identity.pop("evidence_id")
    evidence["evidence_id"] = stable_digest(identity, prefix="releasereadiness_")

    with pytest.raises(ValueError, match="ready_versions are inconsistent"):
        validate_release_readiness_status(evidence)


def test_release_readiness_status_rejects_stage_ready_witness_mismatch(
    tmp_path: Path,
) -> None:
    output = tmp_path / "release-readiness.json"
    write_release_readiness_status(RELEASE_EVIDENCE, output_path=output)
    evidence = json.loads(output.read_text(encoding="utf-8"))
    evidence["stages"][1]["ready"] = False
    evidence["ready_versions"] = ["0.5.1", "0.6.0", "0.7.0"]
    evidence["incomplete_versions"] = []
    identity = dict(evidence)
    identity.pop("evidence_id")
    evidence["evidence_id"] = stable_digest(identity, prefix="releasereadiness_")

    with pytest.raises(ValueError, match="stage ready is inconsistent"):
        validate_release_readiness_status(evidence)


def test_release_readiness_status_rejects_stale_evidence_directory(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "release-evidence"
    shutil.copytree(RELEASE_EVIDENCE, evidence_dir)
    output = evidence_dir / "release_readiness_status.json"
    write_release_readiness_status(evidence_dir, output_path=output)
    gate_path = evidence_dir / "parallel_search_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["rejection_reasons"] = ["tampered-after-status"]
    identity = dict(gate)
    identity.pop("evidence_id")
    gate["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")
    gate_path.write_text(
        json.dumps(gate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match current evidence directory"):
        read_release_readiness_status(output, evidence_dir=evidence_dir)


def test_release_readiness_verify_cli_accepts_current_incomplete_status(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "release-readiness.json"
    write_release_readiness_status(RELEASE_EVIDENCE, output_path=output)

    status = cmd_release_readiness_verify(
        argparse.Namespace(
            evidence_dir=RELEASE_EVIDENCE,
            require_passed=False,
            status=output,
        )
    )
    captured = capsys.readouterr()

    assert status == 0
    assert "release-readiness-verify: passed" in captured.out
    assert "ready=0.5.1,0.6.0,0.7.0" in captured.out
    assert "incomplete=-" in captured.out


def test_release_readiness_verify_cli_checks_current_partial_adoption_identity(
    tmp_path: Path,
) -> None:
    output = tmp_path / "release-readiness.json"
    write_release_readiness_status(RELEASE_EVIDENCE, output_path=output)
    audit = json.loads(
        (RELEASE_EVIDENCE / "release_self_hosted_evidence_audit.json").read_text(
            encoding="utf-8"
        )
    )

    status = cmd_release_readiness_verify(
        argparse.Namespace(
            evidence_dir=RELEASE_EVIDENCE,
            expected_commit=audit["summary"]["commit"],
            expected_run_id=audit["summary"]["run_id"],
            require_passed=False,
            status=output,
        )
    )

    assert status == 0


def test_release_readiness_verify_cli_can_require_passed_status(
    tmp_path: Path,
) -> None:
    output = tmp_path / "release-readiness.json"
    write_release_readiness_status(RELEASE_EVIDENCE, output_path=output)

    status = cmd_release_readiness_verify(
        argparse.Namespace(
            evidence_dir=RELEASE_EVIDENCE,
            require_passed=True,
            status=output,
        )
    )

    assert status == 0


def test_release_readiness_verify_cli_checks_expected_workflow_identity_when_passed(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "artifact"
    evidence_dir = tmp_path / "release-evidence"
    shutil.copytree(RELEASE_EVIDENCE, evidence_dir)
    for name in (
        "release_self_hosted_evidence_audit.json",
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
    ):
        (evidence_dir / name).unlink()
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    _write_passing_dashboard_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=True,
            artifact_dir=artifact_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture",
            output_dir=evidence_dir,
        )
    )
    output = evidence_dir / "release_readiness_status.json"

    status = cmd_release_readiness_verify(
        argparse.Namespace(
            evidence_dir=evidence_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture",
            require_passed=True,
            status=output,
        )
    )
    assert status == 0
    capsys.readouterr()

    with pytest.raises(ValueError, match="commit does not match expected"):
        cmd_release_readiness_verify(
            argparse.Namespace(
                evidence_dir=evidence_dir,
                expected_commit="other_commit",
                expected_run_id="run_fixture",
                require_passed=True,
                status=output,
            )
        )
    captured = capsys.readouterr()
    assert "release-readiness-verify: passed" not in captured.out


def test_release_readiness_verify_cli_checks_expected_identity_for_partial_adoption(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "artifact"
    evidence_dir = tmp_path / "release-evidence"
    shutil.copytree(RELEASE_EVIDENCE, evidence_dir)
    for name in (
        "release_self_hosted_evidence_audit.json",
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
    ):
        (evidence_dir / name).unlink()
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture",
            output_dir=evidence_dir,
        )
    )
    output = evidence_dir / "release_readiness_status.json"

    status = cmd_release_readiness_verify(
        argparse.Namespace(
            evidence_dir=evidence_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture",
            require_passed=False,
            status=output,
        )
    )
    assert status == 0

    with pytest.raises(ValueError, match="run_id does not match expected"):
        cmd_release_readiness_verify(
            argparse.Namespace(
                evidence_dir=evidence_dir,
                expected_commit="commit_fixture",
                expected_run_id="other_run",
                require_passed=False,
                status=output,
            )
        )
    captured = capsys.readouterr()
    assert "other_run" not in captured.out


def test_release_readiness_verify_cli_rejects_stale_status(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "release-evidence"
    shutil.copytree(RELEASE_EVIDENCE, evidence_dir)
    output = evidence_dir / "release_readiness_status.json"
    write_release_readiness_status(evidence_dir, output_path=output)
    gate_path = evidence_dir / "parallel_search_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["rejection_reasons"] = ["tampered-after-status"]
    identity = dict(gate)
    identity.pop("evidence_id")
    gate["evidence_id"] = stable_digest(identity, prefix="parsearchgate_")
    gate_path.write_text(
        json.dumps(gate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match current evidence directory"):
        cmd_release_readiness_verify(
            argparse.Namespace(
                evidence_dir=evidence_dir,
                require_passed=False,
                status=output,
            )
        )


def test_release_self_hosted_evidence_audit_validates_downloaded_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    summary = {
        "commit": "commit_fixture",
        "parallel_search": "false",
        "research_dashboard": "true",
        "run_id": "run_fixture",
        "schema_version": "release-self-hosted-evidence-v1",
        "status": "success",
    }
    (artifact_dir / "summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )
    for name in (
        "research_dashboard_qualification.json",
        "research_dashboard_gate.json",
    ):
        shutil.copyfile(RELEASE_EVIDENCE / name, artifact_dir / name)
    output = tmp_path / "audit.json"

    status = cmd_release_self_hosted_evidence_audit(
        argparse.Namespace(
            artifact_dir=artifact_dir,
            out=str(output),
            require_parallel_search=False,
            require_research_dashboard=False,
        )
    )
    captured = capsys.readouterr()
    audit = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert "release-self-hosted-evidence-audit:" in captured.out
    assert audit["schema_version"] == "release-self-hosted-evidence-audit-v1"
    assert audit["parallel_search"] is None
    assert audit["research_dashboard"]["passed"] is True
    assert audit["artifact_files"] == [
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
    ]
    assert audit["source_artifact_files"] == [
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
        "summary.json",
    ]
    assert audit["evidence_id"].startswith("releaseevidenceaudit_")


def test_release_self_hosted_evidence_audit_rejects_unexpected_identity(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "false",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )

    status = cmd_release_self_hosted_evidence_audit(
        argparse.Namespace(
            artifact_dir=artifact_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture",
            out=str(tmp_path / "audit.json"),
            require_parallel_search=False,
            require_research_dashboard=False,
        )
    )
    assert status == 0

    with pytest.raises(ValueError, match="commit does not match expected"):
        cmd_release_self_hosted_evidence_audit(
            argparse.Namespace(
                artifact_dir=artifact_dir,
                expected_commit="other_commit",
                expected_run_id=None,
                out=str(tmp_path / "audit.json"),
                require_parallel_search=False,
                require_research_dashboard=False,
            )
        )
    with pytest.raises(ValueError, match="run_id does not match expected"):
        cmd_release_self_hosted_evidence_audit(
            argparse.Namespace(
                artifact_dir=artifact_dir,
                expected_commit=None,
                expected_run_id="other_run",
                out=str(tmp_path / "audit.json"),
                require_parallel_search=False,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_audit_rejects_raw_or_failed_required_artifacts(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "best.route.yaml").write_text("raw route\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected files"):
        cmd_release_self_hosted_evidence_audit(
            argparse.Namespace(
                artifact_dir=artifact_dir,
                out=str(tmp_path / "audit.json"),
                require_parallel_search=False,
                require_research_dashboard=False,
            )
        )

    (artifact_dir / "best.route.yaml").unlink()
    with pytest.raises(ValueError, match="requires records and gate"):
        cmd_release_self_hosted_evidence_audit(
            argparse.Namespace(
                artifact_dir=artifact_dir,
                out=str(tmp_path / "audit.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_audit_rejects_unexpected_directories(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "false",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "raw-parallel-search").mkdir()

    with pytest.raises(ValueError, match="unexpected directories"):
        cmd_release_self_hosted_evidence_audit(
            argparse.Namespace(
                artifact_dir=artifact_dir,
                out=str(tmp_path / "audit.json"),
                require_parallel_search=False,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_adopt_requires_selected_passing_branch(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "false",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_failing_dashboard_artifacts(artifact_dir)

    with pytest.raises(ValueError, match="at least one"):
        cmd_release_self_hosted_evidence_adopt(
            argparse.Namespace(
                adopt_parallel_search=False,
                adopt_research_dashboard=False,
                artifact_dir=artifact_dir,
                output_dir=output_dir,
            )
        )

    with pytest.raises(ValueError, match="did not pass"):
        cmd_release_self_hosted_evidence_adopt(
            argparse.Namespace(
                adopt_parallel_search=False,
                adopt_research_dashboard=True,
                artifact_dir=artifact_dir,
                output_dir=output_dir,
            )
        )
    assert not output_dir.exists()


def test_release_self_hosted_evidence_adopt_copies_passing_dashboard_branch(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "false",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_dashboard_artifacts(artifact_dir)

    status = cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=False,
            adopt_research_dashboard=True,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    captured = capsys.readouterr()
    audit = json.loads(
        (output_dir / "release_self_hosted_evidence_audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert status == 0
    assert "release-self-hosted-evidence-adopt:" in captured.out
    assert (output_dir / "research_dashboard_qualification.json").is_file()
    assert (output_dir / "research_dashboard_gate.json").is_file()
    assert audit["research_dashboard"]["passed"] is True
    assert audit["parallel_search"] is None


def test_release_self_hosted_evidence_adopt_records_only_selected_branch(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    _write_passing_dashboard_artifacts(artifact_dir)

    result = cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=False,
            adopt_research_dashboard=True,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    assert result == 0

    audit = json.loads(
        (output_dir / "release_self_hosted_evidence_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["parallel_search"] is None
    assert audit["research_dashboard"]["passed"] is True
    assert "parallel_search_gate.json" not in audit["artifact_files"]
    assert "summary.json" not in audit["artifact_files"]
    assert "summary.json" in audit["source_artifact_files"]
    assert not (output_dir / "parallel_search_gate.json").exists()

    verify_status = cmd_release_self_hosted_evidence_verify_adopted(
        argparse.Namespace(
            evidence_dir=output_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture",
            out=str(tmp_path / "verification.json"),
            require_parallel_search=False,
            require_research_dashboard=True,
        )
    )
    assert verify_status == 0


def test_release_self_hosted_evidence_adopt_merges_same_workflow_branches(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    _write_passing_dashboard_artifacts(artifact_dir)

    adopt_release_self_hosted_evidence(
        artifact_dir,
        expected_commit="commit_fixture",
        expected_run_id="run_fixture",
        output_dir=output_dir,
        adopt_parallel_search=True,
        adopt_research_dashboard=False,
    )
    adopted = adopt_release_self_hosted_evidence(
        artifact_dir,
        expected_commit="commit_fixture",
        expected_run_id="run_fixture",
        output_dir=output_dir,
        adopt_parallel_search=False,
        adopt_research_dashboard=True,
    )
    audit = json.loads(
        (output_dir / "release_self_hosted_evidence_audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert audit["parallel_search"]["passed"] is True
    assert audit["research_dashboard"]["passed"] is True
    assert audit["artifact_files"] == [
        "parallel_search_gate.json",
        "parallel_search_records.json",
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
    ]
    assert adopted["adoption_verification"]["verified_files"] == [
        "parallel_search_gate.json",
        "parallel_search_records.json",
        "release_self_hosted_evidence_audit.json",
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
    ]


def test_release_self_hosted_evidence_adopt_rejects_mixed_workflow_branch_merge(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    other_artifact_dir = tmp_path / "other-artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    other_artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture_a",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    (other_artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "false",
                "research_dashboard": "true",
                "run_id": "run_fixture_b",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    _write_passing_dashboard_artifacts(other_artifact_dir)
    adopt_release_self_hosted_evidence(
        artifact_dir,
        expected_commit="commit_fixture",
        expected_run_id="run_fixture_a",
        output_dir=output_dir,
        adopt_parallel_search=True,
        adopt_research_dashboard=False,
    )

    with pytest.raises(ValueError, match="different workflow identity"):
        adopt_release_self_hosted_evidence(
            other_artifact_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture_b",
            output_dir=output_dir,
            adopt_parallel_search=False,
            adopt_research_dashboard=True,
        )
    assert not (output_dir / "research_dashboard_gate.json").exists()


def test_release_self_hosted_evidence_verify_adopted_rejects_unadopted_passing_branch(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    _write_passing_dashboard_artifacts(artifact_dir)
    adopt_release_self_hosted_evidence(
        artifact_dir,
        expected_commit="commit_fixture",
        expected_run_id="run_fixture",
        output_dir=output_dir,
        adopt_parallel_search=True,
        adopt_research_dashboard=False,
    )
    for name in (
        "research_dashboard_qualification.json",
        "research_dashboard_gate.json",
    ):
        shutil.copyfile(artifact_dir / name, output_dir / name)

    with pytest.raises(ValueError, match="unadopted passing research-dashboard"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit="commit_fixture",
                expected_run_id="run_fixture",
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_adopt_rejects_existing_unadopted_passing_branch(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    output_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    dashboard_artifact_dir = tmp_path / "dashboard-artifact"
    dashboard_artifact_dir.mkdir()
    _write_passing_dashboard_artifacts(dashboard_artifact_dir)
    for name in (
        "research_dashboard_qualification.json",
        "research_dashboard_gate.json",
    ):
        shutil.copyfile(dashboard_artifact_dir / name, output_dir / name)

    with pytest.raises(ValueError, match="unadopted passing research-dashboard"):
        adopt_release_self_hosted_evidence(
            artifact_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture",
            output_dir=output_dir,
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
        )
    assert not (output_dir / "parallel_search_gate.json").exists()


def test_release_self_hosted_evidence_adopt_rejects_unexpected_identity(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "false",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_dashboard_artifacts(artifact_dir)

    with pytest.raises(ValueError, match="commit does not match expected"):
        cmd_release_self_hosted_evidence_adopt(
            argparse.Namespace(
                adopt_parallel_search=False,
                adopt_research_dashboard=True,
                artifact_dir=artifact_dir,
                expected_commit="other_commit",
                expected_run_id="run_fixture",
                output_dir=output_dir,
            )
        )
    assert not output_dir.exists()


def test_release_self_hosted_evidence_adopt_copies_both_passing_branches(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    _write_passing_dashboard_artifacts(artifact_dir)

    status = cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=True,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    captured = capsys.readouterr()
    audit = json.loads(
        (output_dir / "release_self_hosted_evidence_audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert status == 0
    assert "release-self-hosted-evidence-adopt:" in captured.out
    assert "verification_id=releaseevidenceverify_" in captured.out
    assert (output_dir / "parallel_search_records.json").is_file()
    assert (output_dir / "parallel_search_gate.json").is_file()
    assert (output_dir / "research_dashboard_qualification.json").is_file()
    assert (output_dir / "research_dashboard_gate.json").is_file()
    assert audit["parallel_search"]["passed"] is True
    assert audit["research_dashboard"]["passed"] is True
    assert audit["artifact_files"] == [
        "parallel_search_gate.json",
        "parallel_search_records.json",
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
    ]
    assert "summary.json" in audit["source_artifact_files"]


def test_release_self_hosted_evidence_adopt_updates_readiness_status(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    shutil.copytree(RELEASE_EVIDENCE, output_dir)
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    _write_passing_dashboard_artifacts(artifact_dir)

    status = cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=True,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
            readiness_out=None,
        )
    )
    captured = capsys.readouterr()
    readiness = read_release_readiness_status(
        output_dir / "release_readiness_status.json",
        evidence_dir=output_dir,
    )

    assert status == 0
    assert "readiness_id=releasereadiness_" in captured.out
    assert readiness["ready_versions"] == ["0.5.1", "0.6.0", "0.7.0"]
    assert readiness["incomplete_versions"] == []


def test_release_self_hosted_evidence_adopt_returns_post_copy_verification(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)

    adopted = adopt_release_self_hosted_evidence(
        artifact_dir,
        expected_commit="commit_fixture",
        expected_run_id="run_fixture",
        output_dir=output_dir,
        adopt_parallel_search=True,
        adopt_research_dashboard=False,
    )

    assert adopted["adoption_verification"]["evidence_id"].startswith(
        "releaseevidenceverify_"
    )
    assert adopted["adoption_verification"]["requirements"] == {
        "expected_commit": "commit_fixture",
        "expected_run_id": "run_fixture",
        "require_parallel_search": True,
        "require_research_dashboard": False,
    }
    assert adopted["adoption_verification"]["verified_file_sha256"] == {
        name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
        for name in (
            "parallel_search_gate.json",
            "parallel_search_records.json",
            "release_self_hosted_evidence_audit.json",
        )
    }
    assert adopted["adoption_verification"]["verified_files"] == [
        "parallel_search_gate.json",
        "parallel_search_records.json",
        "release_self_hosted_evidence_audit.json",
    ]
    assert adopted["adopted_files"] == [
        "parallel_search_records.json",
        "parallel_search_gate.json",
        "release_self_hosted_evidence_audit.json",
    ]


def test_release_self_hosted_evidence_verify_adopted_matches_saved_audit(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    _write_passing_dashboard_artifacts(artifact_dir)

    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=True,
            artifact_dir=artifact_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture",
            output_dir=output_dir,
        )
    )
    verification_path = tmp_path / "verification.json"

    status = cmd_release_self_hosted_evidence_verify_adopted(
        argparse.Namespace(
            evidence_dir=output_dir,
            expected_commit="commit_fixture",
            expected_run_id="run_fixture",
            out=str(verification_path),
            require_parallel_search=True,
            require_research_dashboard=True,
        )
    )
    captured = capsys.readouterr()
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    audit = json.loads(
        (output_dir / "release_self_hosted_evidence_audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert status == 0
    assert "release-self-hosted-evidence-verify-adopted:" in captured.out
    assert verification["schema_version"] == (
        "release-self-hosted-evidence-verification-v1"
    )
    assert verification["audit_evidence_id"] == audit["evidence_id"]
    assert verification["parallel_search"] == audit["parallel_search"]
    assert verification["requirements"] == {
        "expected_commit": "commit_fixture",
        "expected_run_id": "run_fixture",
        "require_parallel_search": True,
        "require_research_dashboard": True,
    }
    assert verification["research_dashboard"] == audit["research_dashboard"]
    assert set(verification["verified_files"]) == {
        "parallel_search_gate.json",
        "parallel_search_records.json",
        "release_self_hosted_evidence_audit.json",
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
    }
    assert verification["verified_file_sha256"] == {
        name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
        for name in verification["verified_files"]
    }
    assert verification["evidence_id"].startswith("releaseevidenceverify_")
    validated = read_adopted_release_self_hosted_evidence_verification(
        verification_path,
        evidence_dir=output_dir,
    )
    assert validated["evidence_id"] == verification["evidence_id"]

    with pytest.raises(ValueError, match="commit does not match expected"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit="other_commit",
                expected_run_id=None,
                out=str(tmp_path / "verification-other.json"),
                require_parallel_search=True,
                require_research_dashboard=True,
            )
        )


def test_release_self_hosted_evidence_read_verification_rejects_content_drift(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    verification_path = tmp_path / "verification.json"
    cmd_release_self_hosted_evidence_verify_adopted(
        argparse.Namespace(
            evidence_dir=output_dir,
            expected_commit=None,
            expected_run_id=None,
            out=str(verification_path),
            require_parallel_search=True,
            require_research_dashboard=False,
        )
    )
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    verification["requirements"]["require_parallel_search"] = False
    verification_path.write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="evidence_id mismatch"):
        read_adopted_release_self_hosted_evidence_verification(verification_path)


def test_release_self_hosted_evidence_read_verification_rejects_sha_drift(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    verification_path = tmp_path / "verification.json"
    cmd_release_self_hosted_evidence_verify_adopted(
        argparse.Namespace(
            evidence_dir=output_dir,
            expected_commit=None,
            expected_run_id=None,
            out=str(verification_path),
            require_parallel_search=True,
            require_research_dashboard=False,
        )
    )
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    verification["verified_file_sha256"]["parallel_search_gate.json"] = "0" * 64
    identity = dict(verification)
    identity.pop("evidence_id")
    verification["evidence_id"] = stable_digest(
        identity,
        prefix="releaseevidenceverify_",
    )
    verification_path.write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="file sha256 mismatch"):
        read_adopted_release_self_hosted_evidence_verification(
            verification_path,
            evidence_dir=output_dir,
        )


def test_release_self_hosted_evidence_verify_adopted_rejects_tampering(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    gate_path = output_dir / "parallel_search_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["passed"] = False
    gate_path.write_text(
        json.dumps(gate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="evidence_id mismatch"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit=None,
                expected_run_id=None,
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_verify_adopted_rejects_audit_file_drift(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    audit_path = output_dir / "release_self_hosted_evidence_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["artifact_files"] = ["parallel_search_gate.json"]
    identity = dict(audit)
    identity.pop("evidence_id")
    audit["evidence_id"] = stable_digest(identity, prefix="releaseevidenceaudit_")
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="files do not match audit"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit=None,
                expected_run_id=None,
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_verify_adopted_rejects_invalid_audit_file_list(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    audit_path = output_dir / "release_self_hosted_evidence_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["artifact_files"] = [
        "parallel_search_gate.json",
        "parallel_search_gate.json",
        "summary.json",
    ]
    identity = dict(audit)
    identity.pop("evidence_id")
    audit["evidence_id"] = stable_digest(identity, prefix="releaseevidenceaudit_")
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="artifact_files is invalid"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit=None,
                expected_run_id=None,
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_verify_adopted_requires_source_artifact_files(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    audit_path = output_dir / "release_self_hosted_evidence_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.pop("source_artifact_files")
    identity = dict(audit)
    identity.pop("evidence_id")
    audit["evidence_id"] = stable_digest(identity, prefix="releaseevidenceaudit_")
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source_artifact_files is invalid"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit=None,
                expected_run_id=None,
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_verify_adopted_rejects_source_file_drift(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    audit_path = output_dir / "release_self_hosted_evidence_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["source_artifact_files"] = ["parallel_search_gate.json", "summary.json"]
    identity = dict(audit)
    identity.pop("evidence_id")
    audit["evidence_id"] = stable_digest(identity, prefix="releaseevidenceaudit_")
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not cover artifact_files"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit=None,
                expected_run_id=None,
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_verify_adopted_requires_source_summary_file(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    audit_path = output_dir / "release_self_hosted_evidence_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["source_artifact_files"] = [
        "parallel_search_gate.json",
        "parallel_search_records.json",
    ]
    identity = dict(audit)
    identity.pop("evidence_id")
    audit["evidence_id"] = stable_digest(identity, prefix="releaseevidenceaudit_")
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must include summary.json"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit=None,
                expected_run_id=None,
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_verify_adopted_rejects_invalid_branch_witness(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    audit_path = output_dir / "release_self_hosted_evidence_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["parallel_search"].pop("records_evidence_id")
    audit["parallel_search"]["extra"] = "unexpected"
    identity = dict(audit)
    identity.pop("evidence_id")
    audit["evidence_id"] = stable_digest(identity, prefix="releaseevidenceaudit_")
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="parallel-search branch keys are invalid"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit=None,
                expected_run_id=None,
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_verify_adopted_rejects_branch_summary_mismatch(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    audit_path = output_dir / "release_self_hosted_evidence_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["summary"]["parallel_search"] = "false"
    identity = dict(audit)
    identity.pop("evidence_id")
    audit["evidence_id"] = stable_digest(identity, prefix="releaseevidenceaudit_")
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="parallel-search branch contradicts summary"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit=None,
                expected_run_id=None,
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_verify_adopted_rejects_passed_zero_count_branch(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    output_dir = tmp_path / "release-evidence"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "true",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_parallel_artifacts(artifact_dir)
    cmd_release_self_hosted_evidence_adopt(
        argparse.Namespace(
            adopt_parallel_search=True,
            adopt_research_dashboard=False,
            artifact_dir=artifact_dir,
            output_dir=output_dir,
        )
    )
    audit_path = output_dir / "release_self_hosted_evidence_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["parallel_search"]["record_count"] = 0
    identity = dict(audit)
    identity.pop("evidence_id")
    audit["evidence_id"] = stable_digest(identity, prefix="releaseevidenceaudit_")
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="passed branch count is invalid"):
        cmd_release_self_hosted_evidence_verify_adopted(
            argparse.Namespace(
                evidence_dir=output_dir,
                expected_commit=None,
                expected_run_id=None,
                out=str(tmp_path / "verification.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_require_rejects_failed_workflow_summary(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "false",
                "research_dashboard": "true",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "failure",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_dashboard_artifacts(artifact_dir)

    with pytest.raises(ValueError, match="summary did not succeed"):
        cmd_release_self_hosted_evidence_adopt(
            argparse.Namespace(
                adopt_parallel_search=False,
                adopt_research_dashboard=True,
                artifact_dir=artifact_dir,
                output_dir=tmp_path / "release-evidence",
            )
        )


def test_release_self_hosted_evidence_require_rejects_unrun_branch(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "false",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="did not run parallel-search"):
        cmd_release_self_hosted_evidence_audit(
            argparse.Namespace(
                artifact_dir=artifact_dir,
                out=str(tmp_path / "audit.json"),
                require_parallel_search=True,
                require_research_dashboard=False,
            )
        )


def test_release_self_hosted_evidence_adopt_rejects_unrun_dashboard_branch(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "commit": "commit_fixture",
                "parallel_search": "false",
                "research_dashboard": "false",
                "run_id": "run_fixture",
                "schema_version": "release-self-hosted-evidence-v1",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    _write_passing_dashboard_artifacts(artifact_dir)

    with pytest.raises(ValueError, match="did not run research-dashboard"):
        cmd_release_self_hosted_evidence_adopt(
            argparse.Namespace(
                adopt_parallel_search=False,
                adopt_research_dashboard=True,
                artifact_dir=artifact_dir,
                output_dir=tmp_path / "release-evidence",
            )
        )


def test_all_actions_use_node24_compatible_majors() -> None:
    workflows = ROOT / ".github/workflows"
    for path in workflows.glob("*.yml"):
        raw = path.read_text(encoding="utf-8")
        assert "actions/checkout@v4" not in raw, path
        assert "actions/setup-python@v5" not in raw, path
        assert "actions/upload-artifact@v4" not in raw, path
