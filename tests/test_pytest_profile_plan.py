from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

import pytest

from ygo_effect_dsl.cli.main import (
    cmd_test_profile_plan,
    cmd_test_profile_run,
    cmd_test_profile_summary,
    cmd_test_profile_suite,
    cmd_test_profile_gate,
)
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.canonical import to_canonical_data
from ygo_effect_dsl.test_profile_plan import (
    PYTEST_PROFILE_MEASUREMENT_SCHEMA_VERSION,
    PYTEST_PROFILE_RELEASE_GATE_SCHEMA_VERSION,
    PYTEST_PROFILE_SUMMARY_SCHEMA_VERSION,
    PYTEST_PROFILE_SUITE_SCHEMA_VERSION,
    TEST_PROFILE_PHASE_ORDER,
    TEST_PROFILE_PLAN_SCHEMA_VERSION,
    TEST_PROFILE_ORDER,
    TEST_PROFILE_TEMPERATURE_ORDER,
    build_pytest_profile_suite,
    build_pytest_profile_plan,
    evaluate_pytest_profile_release_gate,
    merge_pytest_profile_suite_cells,
    measurements_from_pytest_profile_suite,
    read_pytest_profile_measurement,
    read_pytest_profile_plan,
    read_pytest_profile_release_gate,
    read_pytest_profile_summary,
    read_pytest_profile_suite,
    run_pytest_profile_measurement,
    run_pytest_profile_suite,
    summarize_pytest_profile_measurements,
    validate_pytest_profile_measurement,
    validate_pytest_profile_plan,
    validate_pytest_profile_release_gate,
    validate_pytest_profile_summary,
    validate_pytest_profile_suite,
    write_pytest_profile_measurement,
    write_pytest_profile_plan,
    write_pytest_profile_release_gate,
    write_pytest_profile_summary,
    write_pytest_profile_suite,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO_ROOT / "docs" / "release" / "evidence" / "pytest_profile_plan.json"
MEASUREMENT_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "pytest_profile_release.json"
)
SUMMARY_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "pytest_profile_summary.json"
)
SUITE_PATH = REPO_ROOT / "docs" / "release" / "evidence" / "pytest_profile_suite.json"
GATE_PATH = REPO_ROOT / "docs" / "release" / "evidence" / "pytest_profile_gate.json"


def _skip_committed_evidence_check_during_profile_measurement() -> None:
    if os.environ.get("YGO_EFFECT_DSL_PYTEST_PROFILE_MEASUREMENT") == "1":
        pytest.skip(
            "committed release evidence checks are run outside profile measurement"
        )


def _fake_pytest(command, **kwargs):
    return subprocess.CompletedProcess(
        command,
        0,
        stdout="................\n16 passed in 1.23s\n",
        stderr="",
    )


def _fake_measurement(
    profile: str,
    *,
    evidence_suffix: str,
    wall_seconds: float,
    stdout_bytes: int,
    stderr_bytes: int = 0,
    passed: bool = True,
) -> dict:
    identity = to_canonical_data(
        {
            "command": [
                "python",
                "-m",
                "pytest",
                "-q",
                f"tests/{profile}_{evidence_suffix}.py",
            ],
            "environment": {
                "package_version": "0.5.0",
                "platform": "test",
                "python_version": "3.13.0",
            },
            "extra_pytest_args": [],
            "passed": passed,
            "peak_rss_bytes": 1000 + len(evidence_suffix),
            "profile": profile,
            "profile_plan_id": "pytestprofile_fake",
            "pytest_counts": {
                "errors": 0,
                "failed": 0 if passed else 1,
                "passed": 1 if passed else 0,
                "skipped": 0,
                "xfailed": 0,
                "xpassed": 0,
            },
            "return_code": 0 if passed else 1,
            "rss_measurement": "process_peak_working_set",
            "schema_version": PYTEST_PROFILE_MEASUREMENT_SCHEMA_VERSION,
            "stderr_bytes": stderr_bytes,
            "stdout_bytes": stdout_bytes,
            "summary_tail": "1 passed in 0.01s" if passed else "1 failed in 0.01s",
            "wall_seconds": wall_seconds,
        }
    )
    measurement = {**identity, "evidence_id": ""}
    identity = {key: value for key, value in measurement.items() if key != "evidence_id"}
    measurement["evidence_id"] = stable_digest(identity, prefix="pytestprofilemeasure_")
    return measurement


def test_pytest_profile_plan_assigns_every_test_once() -> None:
    plan = build_pytest_profile_plan(REPO_ROOT)
    identity = {key: value for key, value in plan.items() if key != "evidence_id"}
    assigned = [
        path
        for profile in plan["profiles"].values()
        for path in profile["files"]
    ]

    assert plan["schema_version"] == TEST_PROFILE_PLAN_SCHEMA_VERSION
    assert plan["evidence_id"] == stable_digest(identity, prefix="pytestprofile_")
    assert len(assigned) == len(set(assigned))
    assert len(assigned) == plan["source"]["discovered_file_count"]
    assert plan["validation"] == {
        "duplicate_assignment_count": 0,
        "missing_assignment_count": 0,
        "missing_assignments": [],
    }


def test_pytest_profile_plan_keeps_release_gate_files_together() -> None:
    plan = build_pytest_profile_plan(REPO_ROOT)
    release_files = set(plan["profiles"]["release"]["files"])

    assert "tests/test_project_identity.py" in release_files
    assert "tests/test_release_governance.py" in release_files
    assert "tests/test_parallel_search_release_gate.py" in release_files
    assert (
        plan["release_boundaries"]["skipped_real_core_counts_as_release_success"]
        is False
    )


def test_pytest_profile_plan_writes_and_reads_content_addressed_json(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "pytest-profile-plan.json"
    evidence = write_pytest_profile_plan(REPO_ROOT, output_path=destination)

    assert read_pytest_profile_plan(destination) == evidence


def test_pytest_profile_plan_rejects_tampering() -> None:
    evidence = build_pytest_profile_plan(REPO_ROOT)
    evidence["profiles"]["unit"]["files"].append("tests/test_fake.py")

    with pytest.raises(ValueError, match="evidence_id mismatch"):
        validate_pytest_profile_plan(evidence)


def test_test_profile_plan_cli_writes_evidence(tmp_path: Path, capsys) -> None:
    output = tmp_path / "profile-plan.json"

    status = cmd_test_profile_plan(
        argparse.Namespace(repo_root=REPO_ROOT, out=str(output))
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert evidence["schema_version"] == TEST_PROFILE_PLAN_SCHEMA_VERSION
    assert "test-profile-plan: evidence_id=" in captured.out
    assert evidence["evidence_id"] in captured.out


def test_committed_pytest_profile_plan_matches_current_checkout() -> None:
    assert read_pytest_profile_plan(EVIDENCE_PATH) == build_pytest_profile_plan(REPO_ROOT)


def test_pytest_profile_measurement_records_quiet_output_and_counts() -> None:
    evidence = run_pytest_profile_measurement(
        REPO_ROOT,
        profile="release",
        runner=_fake_pytest,
    )
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == PYTEST_PROFILE_MEASUREMENT_SCHEMA_VERSION
    assert evidence["passed"] is True
    assert evidence["pytest_counts"]["passed"] == 16
    assert evidence["peak_rss_bytes"] is None
    assert evidence["rss_measurement"] == "unavailable"
    assert evidence["stdout_bytes"] == len(
        "................\n16 passed in 1.23s\n".encode("utf-8")
    )
    assert evidence["stderr_bytes"] == 0
    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="pytestprofilemeasure_",
    )


def test_pytest_profile_measurement_can_suppress_success_output() -> None:
    evidence = run_pytest_profile_measurement(
        REPO_ROOT,
        profile="release",
        suppress_success_output=True,
        runner=lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        ),
    )

    assert evidence["passed"] is True
    assert evidence["stdout_bytes"] == 0
    assert evidence["stderr_bytes"] == 0
    assert evidence["success_output_policy"] == "terminal-reporter-disabled"
    assert evidence["failure_rerun_command"] is not None
    assert "-p" in evidence["command"]
    assert "no:terminal" in evidence["command"]


def test_pytest_profile_measurement_reruns_failures_with_terminal_output() -> None:
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(list(command))
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="F\n1 failed in 0.01s\n",
            stderr="",
        )

    evidence = run_pytest_profile_measurement(
        REPO_ROOT,
        profile="release",
        suppress_success_output=True,
        runner=runner,
    )

    assert evidence["passed"] is False
    assert len(calls) == 2
    assert "no:terminal" in calls[0]
    assert "no:terminal" not in calls[1]
    assert evidence["stdout_bytes"] > 0
    assert evidence["pytest_counts"]["failed"] == 1


def test_pytest_profile_measurement_writes_and_reads_content_addressed_json(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "release-profile.json"

    evidence = write_pytest_profile_measurement(
        REPO_ROOT,
        output_path=destination,
        profile="release",
        extra_pytest_args=("--collect-only",),
    )

    assert read_pytest_profile_measurement(destination) == evidence
    assert evidence["passed"] is True


def test_pytest_profile_measurement_rejects_tampering() -> None:
    evidence = run_pytest_profile_measurement(
        REPO_ROOT,
        profile="release",
        runner=_fake_pytest,
    )
    evidence["stdout_bytes"] = 0

    with pytest.raises(ValueError, match="evidence_id mismatch"):
        validate_pytest_profile_measurement(evidence)


def test_test_profile_run_cli_writes_measurement(tmp_path: Path, capsys) -> None:
    output = tmp_path / "profile-run.json"

    status = cmd_test_profile_run(
        argparse.Namespace(
            repo_root=REPO_ROOT,
            profile="release",
            out=str(output),
            pytest_arg=["--collect-only"],
            suppress_success_output=False,
        )
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert evidence["schema_version"] == PYTEST_PROFILE_MEASUREMENT_SCHEMA_VERSION
    assert "test-profile-run: passed profile=release" in captured.out
    assert evidence["evidence_id"] in captured.out


def test_committed_release_profile_measurement_is_content_addressed() -> None:
    evidence = read_pytest_profile_measurement(MEASUREMENT_PATH)

    assert evidence["schema_version"] == PYTEST_PROFILE_MEASUREMENT_SCHEMA_VERSION
    assert evidence["profile"] == "release"
    assert evidence["passed"] is True
    assert evidence["peak_rss_bytes"] is None or evidence["peak_rss_bytes"] > 0
    assert evidence["stdout_bytes"] > 0
    assert evidence["stderr_bytes"] == 0


def test_pytest_profile_suite_records_cold_warm_cells_and_missing_gate() -> None:
    cells = [
        {
            "measurement": _fake_measurement(
                "release",
                evidence_suffix=f"{phase}-{temperature}",
                wall_seconds=1.0,
                stdout_bytes=20,
            ),
            "phase": phase,
            "profile": "release",
            "repeat_index": 1,
            "temperature": temperature,
        }
        for phase in TEST_PROFILE_PHASE_ORDER
        for temperature in TEST_PROFILE_TEMPERATURE_ORDER
    ]

    suite = build_pytest_profile_suite(cells)
    identity = {key: value for key, value in suite.items() if key != "evidence_id"}

    assert suite["schema_version"] == PYTEST_PROFILE_SUITE_SCHEMA_VERSION
    assert suite["evidence_id"] == stable_digest(
        identity,
        prefix="pytestprofilesuite_",
    )
    assert suite["included_measurement_count"] == 4
    assert suite["all_measurements_passed"] is True
    assert suite["passed"] is False
    assert suite["coverage"]["present_phases"] == ["baseline", "current"]
    assert suite["coverage"]["present_temperatures"] == ["cold", "warm"]
    assert suite["coverage"]["missing_cell_count"] == 20


def test_pytest_profile_suite_can_pass_selected_gate_with_fake_runner() -> None:
    suite = run_pytest_profile_suite(
        REPO_ROOT,
        profiles=["release"],
        phases=["current"],
        temperatures=["warm"],
        repeats=1,
        required_profiles=["release"],
        required_phases=["current"],
        required_temperatures=["warm"],
        runner=_fake_pytest,
    )

    assert suite["passed"] is True
    assert suite["coverage"]["missing_cell_count"] == 0
    assert suite["cells"][0]["measurement"]["passed"] is True


def test_pytest_profile_suite_merges_and_replaces_cells() -> None:
    old_suite = build_pytest_profile_suite(
        [
            {
                "measurement": _fake_measurement(
                    "release",
                    evidence_suffix="old-release",
                    wall_seconds=10.0,
                    stdout_bytes=100,
                ),
                "phase": "current",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            }
        ],
        required_profiles=["release"],
        required_phases=["current"],
        required_temperatures=["warm"],
    )
    new_suite = build_pytest_profile_suite(
        [
            {
                "measurement": _fake_measurement(
                    "release",
                    evidence_suffix="new-release",
                    wall_seconds=8.0,
                    stdout_bytes=80,
                ),
                "phase": "current",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
            {
                "measurement": _fake_measurement(
                    "packaging",
                    evidence_suffix="new-packaging",
                    wall_seconds=4.0,
                    stdout_bytes=40,
                ),
                "phase": "current",
                "profile": "packaging",
                "repeat_index": 1,
                "temperature": "warm",
            },
        ],
        required_profiles=["release", "packaging"],
        required_phases=["current"],
        required_temperatures=["warm"],
    )

    merged = merge_pytest_profile_suite_cells(old_suite, new_suite)

    assert merged["included_measurement_count"] == 2
    assert merged["coverage"]["present_profiles"] == ["packaging", "release"]
    release = [
        cell for cell in merged["cells"] if cell["profile"] == "release"
    ][0]
    assert release["measurement"]["wall_seconds"] == 8.0


def test_pytest_profile_suite_writes_reads_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "suite.json"

    suite = write_pytest_profile_suite(
        REPO_ROOT,
        output_path=destination,
        profiles=["release"],
        phases=["current"],
        temperatures=["warm"],
        repeats=1,
        required_profiles=["release"],
        required_phases=["current"],
        required_temperatures=["warm"],
        extra_pytest_args=("--collect-only",),
        existing_suite_path=None,
    )

    assert read_pytest_profile_suite(destination) == suite
    suite["coverage"]["missing_cell_count"] = 1
    with pytest.raises(ValueError, match="evidence_id mismatch"):
        validate_pytest_profile_suite(suite)


def test_test_profile_suite_cli_writes_failed_suite(tmp_path: Path, capsys) -> None:
    output = tmp_path / "suite.json"

    status = cmd_test_profile_suite(
        argparse.Namespace(
            repo_root=REPO_ROOT,
            profile=["release"],
            phase=["current"],
            temperature=["warm"],
            repeat=1,
            existing_suite=None,
            required_profile=None,
            required_phase=None,
            required_temperature=None,
            pytest_arg=["--collect-only"],
            suppress_success_output=False,
            out=str(output),
        )
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 1
    assert evidence["schema_version"] == PYTEST_PROFILE_SUITE_SCHEMA_VERSION
    assert "test-profile-suite: failed" in captured.out
    assert evidence["evidence_id"] in captured.out


def test_committed_pytest_profile_suite_is_content_addressed() -> None:
    _skip_committed_evidence_check_during_profile_measurement()
    suite = read_pytest_profile_suite(SUITE_PATH)

    assert suite["schema_version"] == PYTEST_PROFILE_SUITE_SCHEMA_VERSION
    assert suite["passed"] is True
    assert suite["coverage"]["present_profiles"] == [
        "unit",
        "integration",
        "real_core",
        "evidence",
        "packaging",
        "release",
    ]
    assert suite["coverage"]["present_phases"] == ["baseline", "current"]
    assert suite["coverage"]["present_temperatures"] == ["cold", "warm"]
    assert suite["coverage"]["missing_cell_count"] == 0
    assert suite["included_measurement_count"] == 24


def test_pytest_profile_suite_extracts_measurements_for_summary() -> None:
    suite = build_pytest_profile_suite(
        [
            {
                "measurement": _fake_measurement(
                    "release",
                    evidence_suffix="baseline-warm",
                    wall_seconds=10.0,
                    stdout_bytes=100,
                ),
                "phase": "baseline",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
            {
                "measurement": _fake_measurement(
                    "release",
                    evidence_suffix="current-warm",
                    wall_seconds=7.0,
                    stdout_bytes=25,
                ),
                "phase": "current",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
        ],
        required_profiles=["release"],
        required_phases=["baseline", "current"],
        required_temperatures=["warm"],
    )

    measurements = measurements_from_pytest_profile_suite(
        suite,
        phase="current",
        temperature="warm",
    )

    assert len(measurements) == 1
    assert measurements[0]["profile"] == "release"
    assert measurements[0]["wall_seconds"] == 7.0


def test_pytest_profile_summary_records_missing_profiles_and_medians() -> None:
    measurements = [
        _fake_measurement(
            "release",
            evidence_suffix="a",
            wall_seconds=10.0,
            stdout_bytes=100,
        ),
        _fake_measurement(
            "release",
            evidence_suffix="b",
            wall_seconds=14.0,
            stdout_bytes=160,
        ),
    ]

    summary = summarize_pytest_profile_measurements(measurements)
    identity = {key: value for key, value in summary.items() if key != "evidence_id"}

    assert summary["schema_version"] == PYTEST_PROFILE_SUMMARY_SCHEMA_VERSION
    assert summary["evidence_id"] == stable_digest(
        identity,
        prefix="pytestprofilesummary_",
    )
    assert summary["passed"] is False
    assert summary["release_gate_passed"] is False
    assert summary["profiles"]["release"]["wall_seconds"]["median"] == 12.0
    assert summary["profiles"]["release"]["stdout_bytes"]["median"] == 130.0
    assert summary["missing_profiles"] == [
        "unit",
        "integration",
        "real_core",
        "evidence",
        "packaging",
    ]
    assert "missing-required-profiles" in summary["rejection_reasons"]
    assert "missing-baseline-summary" in summary["rejection_reasons"]


def test_pytest_profile_summary_baseline_comparison_can_pass() -> None:
    baseline = summarize_pytest_profile_measurements(
        [
            _fake_measurement(
                profile,
                evidence_suffix=f"baseline-{profile}",
                wall_seconds=100.0,
                stdout_bytes=1000,
            )
            for profile in TEST_PROFILE_ORDER
        ]
    )
    summary = summarize_pytest_profile_measurements(
        [
            _fake_measurement(
                profile,
                evidence_suffix=f"current-{profile}",
                wall_seconds=70.0,
                stdout_bytes=250,
            )
            for profile in TEST_PROFILE_ORDER
        ],
        baseline=baseline,
    )

    assert summary["missing_profiles"] == []
    assert summary["profile_coverage_passed"] is True
    assert summary["baseline_comparison_passed"] is True
    assert summary["release_gate_passed"] is True
    assert summary["reduction_comparison"]["profiles"]["unit"] == {
        "baseline_pytest_passed_count": 1,
        "passed": True,
        "current_pytest_passed_count": 1,
        "pytest_passed_count_delta": 0,
        "stderr_bytes_median_ratio": 0.0,
        "stdout_bytes_median_ratio": 0.25,
        "wall_seconds_median_ratio": 0.7,
        "workload_count_changed": False,
    }


def test_pytest_profile_summary_baseline_comparison_fails_target() -> None:
    baseline = summarize_pytest_profile_measurements(
        [
            _fake_measurement(
                "release",
                evidence_suffix="baseline-release",
                wall_seconds=100.0,
                stdout_bytes=1000,
            )
        ],
        required_profiles=["release"],
    )
    summary = summarize_pytest_profile_measurements(
        [
            _fake_measurement(
                "release",
                evidence_suffix="current-release",
                wall_seconds=90.0,
                stdout_bytes=400,
            )
        ],
        baseline=baseline,
        required_profiles=["release"],
    )

    assert summary["release_gate_passed"] is False
    assert summary["baseline_comparison_passed"] is False
    assert "reduction-target-not-met" in summary["rejection_reasons"]
    assert summary["reduction_comparison"]["profiles"]["release"]["passed"] is False


def test_pytest_profile_summary_writes_reads_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    measurement_path = tmp_path / "release-measurement.json"
    measurement = _fake_measurement(
        "release",
        evidence_suffix="summary-read",
        wall_seconds=1.0,
        stdout_bytes=20,
    )
    measurement_path.write_text(json.dumps(measurement), encoding="utf-8")
    destination = tmp_path / "summary.json"

    summary = write_pytest_profile_summary(
        [measurement_path],
        output_path=destination,
        required_profiles=["release"],
    )

    assert read_pytest_profile_summary(destination) == summary
    summary["profiles"]["release"]["measurement_count"] = 2
    with pytest.raises(ValueError, match="evidence_id mismatch"):
        validate_pytest_profile_summary(summary)


def test_pytest_profile_summary_can_compare_suite_cells(tmp_path: Path) -> None:
    suite = build_pytest_profile_suite(
        [
            {
                "measurement": _fake_measurement(
                    "release",
                    evidence_suffix="baseline-suite",
                    wall_seconds=10.0,
                    stdout_bytes=100,
                ),
                "phase": "baseline",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
            {
                "measurement": _fake_measurement(
                    "release",
                    evidence_suffix="current-suite",
                    wall_seconds=7.0,
                    stdout_bytes=25,
                ),
                "phase": "current",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
        ],
        required_profiles=["release"],
        required_phases=["baseline", "current"],
        required_temperatures=["warm"],
    )
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(json.dumps(suite), encoding="utf-8")
    output = tmp_path / "summary.json"

    summary = write_pytest_profile_summary(
        [],
        output_path=output,
        suite_path=suite_path,
        suite_phase="current",
        suite_temperature="warm",
        baseline_suite_path=suite_path,
        baseline_suite_phase="baseline",
        baseline_suite_temperature="warm",
        required_profiles=["release"],
    )

    assert read_pytest_profile_summary(output) == summary
    assert summary["release_gate_passed"] is True
    assert summary["reduction_comparison"]["profiles"]["release"]["passed"] is True


def test_test_profile_summary_cli_writes_failed_summary(tmp_path: Path, capsys) -> None:
    measurement_path = tmp_path / "release-measurement.json"
    measurement_path.write_text(
        json.dumps(
            _fake_measurement(
                "release",
                evidence_suffix="cli",
                wall_seconds=1.0,
                stdout_bytes=20,
            )
        ),
        encoding="utf-8",
    )
    output = tmp_path / "summary.json"

    status = cmd_test_profile_summary(
        argparse.Namespace(
            measurement=[measurement_path],
            baseline=None,
            suite=None,
            suite_phase="current",
            suite_temperature="warm",
            baseline_suite=None,
            baseline_suite_phase="baseline",
            baseline_suite_temperature="warm",
            required_profile=None,
            out=str(output),
        )
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 1
    assert evidence["schema_version"] == PYTEST_PROFILE_SUMMARY_SCHEMA_VERSION
    assert "test-profile-summary: failed" in captured.out
    assert evidence["evidence_id"] in captured.out


def test_test_profile_summary_cli_reads_suite(tmp_path: Path, capsys) -> None:
    suite = build_pytest_profile_suite(
        [
            {
                "measurement": _fake_measurement(
                    "release",
                    evidence_suffix="cli-baseline-suite",
                    wall_seconds=10.0,
                    stdout_bytes=100,
                ),
                "phase": "baseline",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
            {
                "measurement": _fake_measurement(
                    "release",
                    evidence_suffix="cli-current-suite",
                    wall_seconds=7.0,
                    stdout_bytes=25,
                ),
                "phase": "current",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
        ],
        required_profiles=["release"],
        required_phases=["baseline", "current"],
        required_temperatures=["warm"],
    )
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(json.dumps(suite), encoding="utf-8")
    output = tmp_path / "summary.json"

    status = cmd_test_profile_summary(
        argparse.Namespace(
            measurement=[],
            baseline=None,
            suite=suite_path,
            suite_phase="current",
            suite_temperature="warm",
            baseline_suite=suite_path,
            baseline_suite_phase="baseline",
            baseline_suite_temperature="warm",
            required_profile=["release"],
            out=str(output),
        )
    )
    captured = capsys.readouterr()
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert evidence["release_gate_passed"] is True
    assert "test-profile-summary: passed" in captured.out


def test_committed_pytest_profile_summary_is_content_addressed() -> None:
    _skip_committed_evidence_check_during_profile_measurement()
    summary = read_pytest_profile_summary(SUMMARY_PATH)

    assert summary["schema_version"] == PYTEST_PROFILE_SUMMARY_SCHEMA_VERSION
    assert summary["release_gate_passed"] is True
    assert summary["profiles_present"] == [
        "unit",
        "integration",
        "real_core",
        "evidence",
        "packaging",
        "release",
    ]
    assert summary["missing_profiles"] == []
    assert "missing-required-profiles" not in summary["rejection_reasons"]
    assert "missing-baseline-summary" not in summary["rejection_reasons"]
    assert summary["rejection_reasons"] == []
    assert summary["reduction_comparison"]["profile_reduction_passed"] is False
    assert summary["reduction_comparison"]["profile_selection_passed"] is True
    assert (
        summary["reduction_comparison"]["profile_selection_comparison"][
            "full_regression_substitute"
        ]
        is False
    )


def test_pytest_profile_release_gate_can_pass_selected_scope() -> None:
    plan = build_pytest_profile_plan(REPO_ROOT)
    baseline_measurement = run_pytest_profile_measurement(
        REPO_ROOT,
        profile="release",
        runner=_fake_pytest,
    )
    baseline_measurement = {
        **baseline_measurement,
        "evidence_id": "",
        "stdout_bytes": 100,
        "wall_seconds": 10.0,
    }
    identity = {
        key: value for key, value in baseline_measurement.items() if key != "evidence_id"
    }
    baseline_measurement["evidence_id"] = stable_digest(
        identity,
        prefix="pytestprofilemeasure_",
    )
    current_measurement = {
        **baseline_measurement,
        "evidence_id": "",
        "stdout_bytes": 25,
        "wall_seconds": 7.0,
    }
    identity = {
        key: value for key, value in current_measurement.items() if key != "evidence_id"
    }
    current_measurement["evidence_id"] = stable_digest(
        identity,
        prefix="pytestprofilemeasure_",
    )
    suite = build_pytest_profile_suite(
        [
            {
                "measurement": baseline_measurement,
                "phase": "baseline",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
            {
                "measurement": current_measurement,
                "phase": "current",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
        ],
        required_profiles=["release"],
        required_phases=["baseline", "current"],
        required_temperatures=["warm"],
    )
    baseline = summarize_pytest_profile_measurements(
        [baseline_measurement],
        required_profiles=["release"],
    )
    summary = summarize_pytest_profile_measurements(
        [current_measurement],
        baseline=baseline,
        required_profiles=["release"],
    )

    gate = evaluate_pytest_profile_release_gate(
        plan=plan,
        suite=suite,
        summary=summary,
    )

    assert gate["schema_version"] == PYTEST_PROFILE_RELEASE_GATE_SCHEMA_VERSION
    assert gate["passed"] is True
    assert gate["rejection_reasons"] == []
    assert gate["checks"]["suite_profile_plan_ids"] == [
        plan["evidence_id"],
    ]
    assert set(gate["checks"]["summary_measurement_ids"]).issubset(
        set(gate["checks"]["suite_measurement_ids"])
    )


def test_pytest_profile_release_gate_accepts_committed_evidence() -> None:
    _skip_committed_evidence_check_during_profile_measurement()
    gate = evaluate_pytest_profile_release_gate(
        plan=read_pytest_profile_plan(EVIDENCE_PATH),
        suite=read_pytest_profile_suite(SUITE_PATH),
        summary=read_pytest_profile_summary(SUMMARY_PATH),
    )

    assert gate["passed"] is True
    assert gate["rejection_reasons"] == []


def test_pytest_profile_release_gate_rejects_collect_only_cells() -> None:
    plan = build_pytest_profile_plan(REPO_ROOT)
    baseline_measurement = _fake_measurement(
        "release",
        evidence_suffix="gate-baseline",
        wall_seconds=10.0,
        stdout_bytes=100,
    )
    current_measurement = _fake_measurement(
        "release",
        evidence_suffix="gate-current-collect-only",
        wall_seconds=7.0,
        stdout_bytes=25,
    )
    current_measurement["extra_pytest_args"] = ["--collect-only"]
    identity = {
        key: value for key, value in current_measurement.items() if key != "evidence_id"
    }
    current_measurement["evidence_id"] = stable_digest(
        identity,
        prefix="pytestprofilemeasure_",
    )
    suite = build_pytest_profile_suite(
        [
            {
                "measurement": baseline_measurement,
                "phase": "baseline",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
            {
                "measurement": current_measurement,
                "phase": "current",
                "profile": "release",
                "repeat_index": 1,
                "temperature": "warm",
            },
        ],
        required_profiles=["release"],
        required_phases=["baseline", "current"],
        required_temperatures=["warm"],
    )
    baseline = summarize_pytest_profile_measurements(
        [baseline_measurement],
        required_profiles=["release"],
    )
    summary = summarize_pytest_profile_measurements(
        [current_measurement],
        baseline=baseline,
        required_profiles=["release"],
    )

    gate = evaluate_pytest_profile_release_gate(
        plan=plan,
        suite=suite,
        summary=summary,
    )

    assert gate["passed"] is False
    assert "cell-rejections" in gate["rejection_reasons"]
    assert gate["cell_rejections"][0]["reasons"] == ["collect-only-measurement"]


def test_pytest_profile_release_gate_writes_reads_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "gate.json"

    gate = write_pytest_profile_release_gate(
        plan_path=EVIDENCE_PATH,
        suite_path=SUITE_PATH,
        summary_path=SUMMARY_PATH,
        output_path=destination,
    )

    assert read_pytest_profile_release_gate(destination) == gate
    gate["checks"]["suite_missing_cell_count"] = 1
    with pytest.raises(ValueError, match="evidence_id mismatch"):
        validate_pytest_profile_release_gate(gate)


def test_pytest_profile_release_gate_rejects_inconsistent_checks() -> None:
    _skip_committed_evidence_check_during_profile_measurement()
    gate = evaluate_pytest_profile_release_gate(
        plan=read_pytest_profile_plan(EVIDENCE_PATH),
        suite=read_pytest_profile_suite(SUITE_PATH),
        summary=read_pytest_profile_summary(SUMMARY_PATH),
    )
    gate["checks"]["suite_passed"] = False
    identity = {key: value for key, value in gate.items() if key != "evidence_id"}
    gate["evidence_id"] = stable_digest(identity, prefix="pytestprofilegate_")

    with pytest.raises(ValueError, match="rejections are inconsistent"):
        validate_pytest_profile_release_gate(gate)


def test_pytest_profile_release_gate_rejects_inconsistent_cell_rejections() -> None:
    _skip_committed_evidence_check_during_profile_measurement()
    gate = evaluate_pytest_profile_release_gate(
        plan=read_pytest_profile_plan(EVIDENCE_PATH),
        suite=read_pytest_profile_suite(SUITE_PATH),
        summary=read_pytest_profile_summary(SUMMARY_PATH),
    )
    gate["cell_rejections"].append(
        {
            "measurement_id": gate["checks"]["suite_measurement_ids"][0],
            "phase": "current",
            "profile": "release",
            "reasons": ["collect-only-measurement"],
            "repeat_index": 1,
            "temperature": "warm",
        }
    )
    identity = {key: value for key, value in gate.items() if key != "evidence_id"}
    gate["evidence_id"] = stable_digest(identity, prefix="pytestprofilegate_")

    with pytest.raises(ValueError, match="rejections are inconsistent"):
        validate_pytest_profile_release_gate(gate)


def test_test_profile_gate_cli_writes_passed_gate(tmp_path: Path, capsys) -> None:
    _skip_committed_evidence_check_during_profile_measurement()
    output = tmp_path / "gate.json"

    status = cmd_test_profile_gate(
        argparse.Namespace(
            plan=EVIDENCE_PATH,
            suite=SUITE_PATH,
            summary=SUMMARY_PATH,
            out=str(output),
        )
    )
    captured = capsys.readouterr()
    gate = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert gate["schema_version"] == PYTEST_PROFILE_RELEASE_GATE_SCHEMA_VERSION
    assert "test-profile-gate: passed" in captured.out
    assert gate["evidence_id"] in captured.out


def test_committed_pytest_profile_gate_is_content_addressed() -> None:
    _skip_committed_evidence_check_during_profile_measurement()
    gate = read_pytest_profile_release_gate(GATE_PATH)

    assert gate["schema_version"] == PYTEST_PROFILE_RELEASE_GATE_SCHEMA_VERSION
    assert gate["passed"] is True
    assert gate["checks"]["suite_missing_cell_count"] == 0
    assert gate["rejection_reasons"] == []
