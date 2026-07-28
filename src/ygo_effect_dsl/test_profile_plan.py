from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections import Counter
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from statistics import median
from typing import Any

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text


TEST_PROFILE_PLAN_SCHEMA_VERSION = "pytest-profile-plan-v1"
PYTEST_PROFILE_MEASUREMENT_SCHEMA_VERSION = "pytest-profile-measurement-v1"
PYTEST_PROFILE_SUITE_SCHEMA_VERSION = "pytest-profile-suite-v1"
PYTEST_PROFILE_SUMMARY_SCHEMA_VERSION = "pytest-profile-summary-v1"
PYTEST_PROFILE_RELEASE_GATE_SCHEMA_VERSION = "pytest-profile-release-gate-v1"
TEST_PROFILE_ORDER = (
    "unit",
    "integration",
    "real_core",
    "evidence",
    "packaging",
    "release",
)
TEST_PROFILE_PHASE_ORDER = ("baseline", "current")
TEST_PROFILE_TEMPERATURE_ORDER = ("cold", "warm")

_RELEASE_TESTS = {
    "test_architecture_freeze.py",
    "test_distribution_policy.py",
    "test_parallel_search_release_gate.py",
    "test_project_identity.py",
    "test_release_audit.py",
    "test_release_governance.py",
}
_PACKAGING_TESTS = {
    "test_cli_module_smoke.py",
    "test_platform_contract.py",
    "test_runtime_imports.py",
    "test_self_hosted_smoke.py",
    "test_self_hosted_workflow.py",
}
_REAL_CORE_MARKERS = (
    "clean_bootstrap",
    "cross_channel",
    "direct_random",
    "lua_qualification",
    "ocgcore",
    "real_core",
    "real_deck",
    "strategy_interruption",
)
_EVIDENCE_MARKERS = (
    "benchmark",
    "calibration",
    "evidence",
    "qualification",
)
_INTEGRATION_MARKERS = (
    "analytics",
    "desktop",
    "experiment",
    "job",
    "parquet",
    "player_view",
    "replay",
    "route",
    "search",
    "storage",
)
_PYTEST_COUNT = re.compile(
    r"(?P<count>\d+)\s+"
    r"(?P<kind>passed|failed|skipped|xfailed|xpassed|error|errors)"
)
_WALL_TIME_REDUCTION_TARGET_RATIO = 0.75
_OUTPUT_REDUCTION_TARGET_RATIO = 0.30


def discover_pytest_files(repo_root: str | Path) -> tuple[str, ...]:
    root = Path(repo_root)
    tests_root = root / "tests"
    return tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in tests_root.glob("test_*.py")
        )
    )


def classify_pytest_file(path: str) -> str:
    name = Path(path).name
    lowered = name.lower()
    if name in _RELEASE_TESTS:
        return "release"
    if name in _PACKAGING_TESTS:
        return "packaging"
    if any(marker in lowered for marker in _REAL_CORE_MARKERS):
        return "real_core"
    if any(marker in lowered for marker in _EVIDENCE_MARKERS):
        return "evidence"
    if any(marker in lowered for marker in _INTEGRATION_MARKERS):
        return "integration"
    return "unit"


def build_pytest_profile_plan(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    files = discover_pytest_files(root)
    by_profile = {profile: [] for profile in TEST_PROFILE_ORDER}
    for path in files:
        by_profile[classify_pytest_file(path)].append(path)
    assigned = sorted(path for paths in by_profile.values() for path in paths)
    duplicate_count = len(assigned) - len(set(assigned))
    missing = sorted(set(files) - set(assigned))
    profiles = {
        profile: {
            "file_count": len(by_profile[profile]),
            "files": by_profile[profile],
            "pytest_args": ["-q", *by_profile[profile]],
        }
        for profile in TEST_PROFILE_ORDER
    }
    identity = to_canonical_data(
        {
            "package_version": __version__,
            "profiles": profiles,
            "quiet_output_policy": {
                "default_pytest_args": ["-q"],
                "failure_must_keep_first_divergence": True,
                "success_summary_only": True,
            },
            "release_boundaries": {
                "manual_evidence_regeneration_is_separate": True,
                "release_profile_is_not_a_substitute_for_full_regression": True,
                "skipped_real_core_counts_as_release_success": False,
            },
            "schema_version": TEST_PROFILE_PLAN_SCHEMA_VERSION,
            "source": {
                "discovered_file_count": len(files),
                "repo_root_name": root.resolve().name,
            },
            "validation": {
                "duplicate_assignment_count": duplicate_count,
                "missing_assignment_count": len(missing),
                "missing_assignments": missing,
            },
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="pytestprofile_"),
    }


def validate_pytest_profile_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("pytest profile plan must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("pytest profile plan must be an object")
    if document.get("schema_version") != TEST_PROFILE_PLAN_SCHEMA_VERSION:
        raise ValueError("unsupported pytest profile plan schema_version")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith("pytestprofile_"):
        raise ValueError("pytest profile plan evidence_id is invalid")
    identity = {key: item for key, item in document.items() if key != "evidence_id"}
    if evidence_id != stable_digest(identity, prefix="pytestprofile_"):
        raise ValueError("pytest profile plan evidence_id mismatch")
    profiles = document.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ValueError("pytest profile plan profiles must be an object")
    if set(profiles) != set(TEST_PROFILE_ORDER):
        raise ValueError("pytest profile plan profiles are incomplete")
    seen: set[str] = set()
    for profile, record in profiles.items():
        if not isinstance(record, Mapping):
            raise ValueError(f"pytest profile {profile} must be an object")
        files = record.get("files")
        if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
            raise ValueError(f"pytest profile {profile} files must be a list")
        if any(not isinstance(item, str) for item in files):
            raise ValueError(f"pytest profile {profile} files must contain strings")
        if len(set(files)) != len(files):
            raise ValueError(f"pytest profile {profile} has duplicate files")
        seen.update(files)
        if record.get("file_count") != len(files):
            raise ValueError(f"pytest profile {profile} file_count mismatch")
    validation = document.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError("pytest profile plan validation must be an object")
    if validation.get("duplicate_assignment_count") != 0:
        raise ValueError("pytest profile plan contains duplicate assignments")
    if validation.get("missing_assignment_count") != 0:
        raise ValueError("pytest profile plan contains missing assignments")
    if not seen:
        raise ValueError("pytest profile plan must assign at least one test file")
    return document


def read_pytest_profile_plan(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("pytest profile plan is invalid JSON") from exc
    return validate_pytest_profile_plan(value)


def write_pytest_profile_plan(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = build_pytest_profile_plan(repo_root)
    validate_pytest_profile_plan(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


def _parse_pytest_counts(output: str) -> dict[str, int]:
    counts = {
        "errors": 0,
        "failed": 0,
        "passed": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
    }
    for match in _PYTEST_COUNT.finditer(output):
        kind = match.group("kind")
        if kind == "error":
            kind = "errors"
        counts[kind] += int(match.group("count"))
    return counts


def _parse_junit_counts(path: Path) -> dict[str, int] | None:
    if not path.exists():
        return None
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except ET.ParseError:
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return None
    total = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
    passed = max(0, total - failures - errors - skipped)
    return {
        "errors": errors,
        "failed": failures,
        "passed": passed,
        "skipped": skipped,
        "xfailed": 0,
        "xpassed": 0,
    }


def _process_peak_rss_bytes(process: subprocess.Popen[str]) -> int | None:
    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError:  # pragma: no cover - ctypes is part of CPython
            return None

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(ProcessMemoryCounters)
        handle = int(getattr(process, "_handle", 0))
        if not handle:
            return None
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(  # type: ignore[attr-defined]
            handle,
            ctypes.byref(counters),
            counters.cb,
        )
        if not ok:
            return None
        return int(counters.PeakWorkingSetSize)
    status = Path(f"/proc/{process.pid}/status")
    if not status.exists():
        return None
    for line in status.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("VmHWM:") or line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024
    return None


def _run_pytest_subprocess(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str, str, int | None]:
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    peak_rss = _process_peak_rss_bytes(process)
    while True:
        try:
            stdout, stderr = process.communicate(timeout=0.05)
            break
        except subprocess.TimeoutExpired:
            pass
        current = _process_peak_rss_bytes(process)
        if current is not None:
            peak_rss = max(peak_rss or 0, current)
    current = _process_peak_rss_bytes(process)
    if current is not None:
        peak_rss = max(peak_rss or 0, current)
    return process.returncode, stdout or "", stderr or "", peak_rss


def run_pytest_profile_measurement(
    repo_root: str | Path,
    *,
    profile: str,
    extra_pytest_args: Sequence[str] = (),
    suppress_success_output: bool = False,
    runner: Any | None = None,
) -> dict[str, Any]:
    plan = build_pytest_profile_plan(repo_root)
    profiles = plan["profiles"]
    if profile not in profiles:
        raise ValueError(f"unknown pytest profile {profile!r}")
    root = Path(repo_root)
    default_pytest_args = list(profiles[profile]["pytest_args"])
    junit_path = root / ".pytest-profile-work" / f"{profile}-junit.xml"
    command = [
        sys.executable,
        "-m",
        "pytest",
        *default_pytest_args,
        *extra_pytest_args,
    ]
    failure_rerun_command: list[str] | None = None
    if suppress_success_output:
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            junit_path.unlink()
        except FileNotFoundError:
            pass
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:terminal",
            f"--junitxml={junit_path.relative_to(root).as_posix()}",
            *default_pytest_args[1:],
            *extra_pytest_args,
        ]
        failure_rerun_command = [
            sys.executable,
            "-m",
            "pytest",
            *default_pytest_args,
            *extra_pytest_args,
        ]
    started = time.perf_counter()
    if runner is None:
        subprocess_env = {
            **os.environ,
            "YGO_EFFECT_DSL_PYTEST_PROFILE_MEASUREMENT": "1",
        }
        return_code, stdout, stderr, peak_rss_bytes = _run_pytest_subprocess(
            command,
            cwd=root,
            env=subprocess_env,
        )
        if return_code != 0 and failure_rerun_command is not None:
            return_code, stdout, stderr, rerun_peak_rss_bytes = _run_pytest_subprocess(
                failure_rerun_command,
                cwd=root,
                env=subprocess_env,
            )
            if rerun_peak_rss_bytes is not None:
                peak_rss_bytes = max(peak_rss_bytes or 0, rerun_peak_rss_bytes)
    else:
        completed = runner(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        return_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        peak_rss_bytes = getattr(completed, "peak_rss_bytes", None)
        if return_code != 0 and failure_rerun_command is not None:
            completed = runner(
                failure_rerun_command,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            return_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            rerun_peak_rss_bytes = getattr(completed, "peak_rss_bytes", None)
            if rerun_peak_rss_bytes is not None:
                peak_rss_bytes = max(peak_rss_bytes or 0, rerun_peak_rss_bytes)
    wall_seconds = time.perf_counter() - started
    combined = f"{stdout}\n{stderr}"
    counts = _parse_pytest_counts(combined)
    counts_source = "terminal-output"
    if suppress_success_output and return_code == 0:
        junit_counts = _parse_junit_counts(junit_path)
        if junit_counts is not None:
            counts = junit_counts
            counts_source = "junitxml"
    if suppress_success_output:
        try:
            junit_path.unlink()
        except FileNotFoundError:
            pass
    identity = to_canonical_data(
        {
            "command": command,
            "environment": {
                "package_version": __version__,
                "platform": platform.platform(),
                "python_version": platform.python_version(),
            },
            "extra_pytest_args": list(extra_pytest_args),
            "failure_rerun_command": failure_rerun_command,
            "measurement_environment": {
                "YGO_EFFECT_DSL_PYTEST_PROFILE_MEASUREMENT": "1",
            },
            "passed": return_code == 0,
            "peak_rss_bytes": peak_rss_bytes,
            "profile": profile,
            "profile_plan_id": plan["evidence_id"],
            "pytest_counts": counts,
            "pytest_counts_source": counts_source,
            "return_code": return_code,
            "rss_measurement": (
                "process_peak_working_set"
                if peak_rss_bytes is not None
                else "unavailable"
            ),
            "schema_version": PYTEST_PROFILE_MEASUREMENT_SCHEMA_VERSION,
            "stderr_bytes": len(stderr.encode("utf-8")),
            "stdout_bytes": len(stdout.encode("utf-8")),
            "success_output_policy": (
                "terminal-reporter-disabled"
                if suppress_success_output
                else "pytest-quiet"
            ),
            "summary_tail": "\n".join(combined.strip().splitlines()[-12:]),
            "wall_seconds": round(wall_seconds, 6),
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="pytestprofilemeasure_"),
    }


def validate_pytest_profile_measurement(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("pytest profile measurement must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("pytest profile measurement must be an object")
    if document.get("schema_version") != PYTEST_PROFILE_MEASUREMENT_SCHEMA_VERSION:
        raise ValueError("unsupported pytest profile measurement schema_version")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "pytestprofilemeasure_"
    ):
        raise ValueError("pytest profile measurement evidence_id is invalid")
    identity = {key: item for key, item in document.items() if key != "evidence_id"}
    if evidence_id != stable_digest(identity, prefix="pytestprofilemeasure_"):
        raise ValueError("pytest profile measurement evidence_id mismatch")
    if document.get("profile") not in TEST_PROFILE_ORDER:
        raise ValueError("pytest profile measurement profile is invalid")
    if not isinstance(document.get("passed"), bool):
        raise ValueError("pytest profile measurement passed must be a boolean")
    if not isinstance(document.get("return_code"), int):
        raise ValueError("pytest profile measurement return_code must be an integer")
    for key in ("stdout_bytes", "stderr_bytes"):
        value = document.get(key)
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"pytest profile measurement {key} must be non-negative")
    peak_rss = document.get("peak_rss_bytes")
    if peak_rss is not None and (
        not isinstance(peak_rss, int) or isinstance(peak_rss, bool) or peak_rss < 0
    ):
        raise ValueError("pytest profile measurement peak_rss_bytes is invalid")
    return document


def read_pytest_profile_measurement(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("pytest profile measurement is invalid JSON") from exc
    return validate_pytest_profile_measurement(value)


def write_pytest_profile_measurement(
    repo_root: str | Path,
    *,
    output_path: str | Path,
    profile: str,
    extra_pytest_args: Sequence[str] = (),
    suppress_success_output: bool = False,
) -> dict[str, Any]:
    document = run_pytest_profile_measurement(
        repo_root,
        profile=profile,
        extra_pytest_args=extra_pytest_args,
        suppress_success_output=suppress_success_output,
    )
    validate_pytest_profile_measurement(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


def _validated_profile_list(values: Sequence[str], *, field: str) -> list[str]:
    if not values or any(value not in TEST_PROFILE_ORDER for value in values):
        raise ValueError(f"pytest profile suite {field} is invalid")
    return list(dict.fromkeys(values))


def _validated_phase_list(values: Sequence[str], *, field: str) -> list[str]:
    if not values or any(value not in TEST_PROFILE_PHASE_ORDER for value in values):
        raise ValueError(f"pytest profile suite {field} is invalid")
    return list(dict.fromkeys(values))


def _validated_temperature_list(values: Sequence[str], *, field: str) -> list[str]:
    if not values or any(value not in TEST_PROFILE_TEMPERATURE_ORDER for value in values):
        raise ValueError(f"pytest profile suite {field} is invalid")
    return list(dict.fromkeys(values))


def build_pytest_profile_suite(
    cells: Sequence[Mapping[str, Any]],
    *,
    required_profiles: Sequence[str] = TEST_PROFILE_ORDER,
    required_phases: Sequence[str] = TEST_PROFILE_PHASE_ORDER,
    required_temperatures: Sequence[str] = TEST_PROFILE_TEMPERATURE_ORDER,
) -> dict[str, Any]:
    if not cells:
        raise ValueError("pytest profile suite requires at least one cell")
    required_profile_list = _validated_profile_list(
        required_profiles,
        field="required_profiles",
    )
    required_phase_list = _validated_phase_list(
        required_phases,
        field="required_phases",
    )
    required_temperature_list = _validated_temperature_list(
        required_temperatures,
        field="required_temperatures",
    )

    normalized_cells: list[dict[str, Any]] = []
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise ValueError("pytest profile suite cell must be an object")
        phase = cell.get("phase")
        temperature = cell.get("temperature")
        profile = cell.get("profile")
        repeat_index = cell.get("repeat_index")
        if phase not in TEST_PROFILE_PHASE_ORDER:
            raise ValueError("pytest profile suite cell phase is invalid")
        if temperature not in TEST_PROFILE_TEMPERATURE_ORDER:
            raise ValueError("pytest profile suite cell temperature is invalid")
        if profile not in TEST_PROFILE_ORDER:
            raise ValueError("pytest profile suite cell profile is invalid")
        if (
            not isinstance(repeat_index, int)
            or isinstance(repeat_index, bool)
            or repeat_index < 1
        ):
            raise ValueError("pytest profile suite repeat_index is invalid")
        measurement = validate_pytest_profile_measurement(cell.get("measurement"))
        if measurement["profile"] != profile:
            raise ValueError("pytest profile suite cell profile mismatch")
        normalized_cells.append(
            {
                "measurement": measurement,
                "measurement_id": measurement["evidence_id"],
                "phase": phase,
                "profile": profile,
                "repeat_index": repeat_index,
                "temperature": temperature,
            }
        )
    normalized_cells.sort(
        key=lambda item: (
            TEST_PROFILE_PHASE_ORDER.index(item["phase"]),
            TEST_PROFILE_TEMPERATURE_ORDER.index(item["temperature"]),
            TEST_PROFILE_ORDER.index(item["profile"]),
            item["repeat_index"],
            item["measurement_id"],
        )
    )

    present_profiles = sorted(
        {cell["profile"] for cell in normalized_cells},
        key=TEST_PROFILE_ORDER.index,
    )
    present_phases = sorted(
        {cell["phase"] for cell in normalized_cells},
        key=TEST_PROFILE_PHASE_ORDER.index,
    )
    present_temperatures = sorted(
        {cell["temperature"] for cell in normalized_cells},
        key=TEST_PROFILE_TEMPERATURE_ORDER.index,
    )
    present_cells = {
        (cell["phase"], cell["temperature"], cell["profile"])
        for cell in normalized_cells
    }
    missing_cells = [
        {
            "phase": phase,
            "profile": profile,
            "temperature": temperature,
        }
        for phase in required_phase_list
        for temperature in required_temperature_list
        for profile in required_profile_list
        if (phase, temperature, profile) not in present_cells
    ]
    duplicate_keys = [
        key
        for key, count in Counter(
            (
                cell["phase"],
                cell["temperature"],
                cell["profile"],
                cell["repeat_index"],
            )
            for cell in normalized_cells
        ).items()
        if count > 1
    ]
    all_measurements_passed = all(
        cell["measurement"]["passed"] for cell in normalized_cells
    )
    coverage_passed = not missing_cells and not duplicate_keys
    identity = to_canonical_data(
        {
            "all_measurements_passed": all_measurements_passed,
            "cells": normalized_cells,
            "coverage": {
                "duplicate_cell_count": len(duplicate_keys),
                "missing_cell_count": len(missing_cells),
                "missing_cells": missing_cells,
                "present_phases": present_phases,
                "present_profiles": present_profiles,
                "present_temperatures": present_temperatures,
            },
            "included_measurement_count": len(normalized_cells),
            "measurement_ids": [cell["measurement_id"] for cell in normalized_cells],
            "package_version": __version__,
            "passed": all_measurements_passed and coverage_passed,
            "profile_plan_ids": sorted(
                {cell["measurement"]["profile_plan_id"] for cell in normalized_cells}
            ),
            "required_phases": required_phase_list,
            "required_profiles": required_profile_list,
            "required_temperatures": required_temperature_list,
            "schema_version": PYTEST_PROFILE_SUITE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="pytestprofilesuite_"),
    }


def run_pytest_profile_suite(
    repo_root: str | Path,
    *,
    profiles: Sequence[str] = TEST_PROFILE_ORDER,
    phases: Sequence[str] = ("current",),
    temperatures: Sequence[str] = ("warm",),
    repeats: int = 1,
    required_profiles: Sequence[str] = TEST_PROFILE_ORDER,
    required_phases: Sequence[str] = TEST_PROFILE_PHASE_ORDER,
    required_temperatures: Sequence[str] = TEST_PROFILE_TEMPERATURE_ORDER,
    extra_pytest_args: Sequence[str] = (),
    suppress_success_output: bool = False,
    runner: Any | None = None,
) -> dict[str, Any]:
    profile_list = _validated_profile_list(profiles, field="profiles")
    phase_list = _validated_phase_list(phases, field="phases")
    temperature_list = _validated_temperature_list(
        temperatures,
        field="temperatures",
    )
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
        raise ValueError("pytest profile suite repeats is invalid")

    cells: list[dict[str, Any]] = []
    for phase in phase_list:
        for temperature in temperature_list:
            for profile in profile_list:
                for repeat_index in range(1, repeats + 1):
                    measurement = run_pytest_profile_measurement(
                        repo_root,
                        profile=profile,
                        extra_pytest_args=extra_pytest_args,
                        suppress_success_output=suppress_success_output,
                        runner=runner,
                    )
                    cells.append(
                        {
                            "measurement": measurement,
                            "phase": phase,
                            "profile": profile,
                            "repeat_index": repeat_index,
                            "temperature": temperature,
                        }
                    )
    return build_pytest_profile_suite(
        cells,
        required_profiles=required_profiles,
        required_phases=required_phases,
        required_temperatures=required_temperatures,
    )


def merge_pytest_profile_suite_cells(
    existing_suite: Mapping[str, Any],
    new_suite: Mapping[str, Any],
) -> dict[str, Any]:
    existing = validate_pytest_profile_suite(existing_suite)
    new = validate_pytest_profile_suite(new_suite)
    required_profiles = list(
        dict.fromkeys([*existing["required_profiles"], *new["required_profiles"]])
    )
    required_phases = list(
        dict.fromkeys([*existing["required_phases"], *new["required_phases"]])
    )
    required_temperatures = list(
        dict.fromkeys(
            [*existing["required_temperatures"], *new["required_temperatures"]]
        )
    )
    by_key: dict[tuple[str, str, str, int], Mapping[str, Any]] = {}
    for cell in [*existing["cells"], *new["cells"]]:
        by_key[
            (
                cell["phase"],
                cell["temperature"],
                cell["profile"],
                cell["repeat_index"],
            )
        ] = cell
    return build_pytest_profile_suite(
        list(by_key.values()),
        required_profiles=required_profiles,
        required_phases=required_phases,
        required_temperatures=required_temperatures,
    )


def validate_pytest_profile_suite(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("pytest profile suite must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("pytest profile suite must be an object")
    if document.get("schema_version") != PYTEST_PROFILE_SUITE_SCHEMA_VERSION:
        raise ValueError("unsupported pytest profile suite schema_version")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "pytestprofilesuite_"
    ):
        raise ValueError("pytest profile suite evidence_id is invalid")
    identity = {key: item for key, item in document.items() if key != "evidence_id"}
    if evidence_id != stable_digest(identity, prefix="pytestprofilesuite_"):
        raise ValueError("pytest profile suite evidence_id mismatch")
    if not isinstance(document.get("passed"), bool):
        raise ValueError("pytest profile suite passed must be a boolean")
    if not isinstance(document.get("all_measurements_passed"), bool):
        raise ValueError("pytest profile suite all_measurements_passed is invalid")
    count = document.get("included_measurement_count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("pytest profile suite included_measurement_count is invalid")
    cells = document.get("cells")
    if not isinstance(cells, Sequence) or isinstance(cells, (str, bytes)):
        raise ValueError("pytest profile suite cells must be a list")
    if len(cells) != count:
        raise ValueError("pytest profile suite cell count mismatch")
    rebuilt = build_pytest_profile_suite(
        cells,
        required_profiles=document.get("required_profiles", ()),
        required_phases=document.get("required_phases", ()),
        required_temperatures=document.get("required_temperatures", ()),
    )
    if rebuilt != document:
        raise ValueError("pytest profile suite derived fields mismatch")
    return document


def read_pytest_profile_suite(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("pytest profile suite is invalid JSON") from exc
    return validate_pytest_profile_suite(value)


def measurements_from_pytest_profile_suite(
    suite: Mapping[str, Any],
    *,
    phase: str = "current",
    temperature: str = "warm",
) -> list[dict[str, Any]]:
    if phase not in TEST_PROFILE_PHASE_ORDER:
        raise ValueError("pytest profile suite summary phase is invalid")
    if temperature not in TEST_PROFILE_TEMPERATURE_ORDER:
        raise ValueError("pytest profile suite summary temperature is invalid")
    document = validate_pytest_profile_suite(suite)
    measurements = [
        validate_pytest_profile_measurement(cell["measurement"])
        for cell in document["cells"]
        if cell["phase"] == phase and cell["temperature"] == temperature
    ]
    if not measurements:
        raise ValueError("pytest profile suite contains no matching measurements")
    return measurements


def write_pytest_profile_suite(
    repo_root: str | Path,
    *,
    output_path: str | Path,
    profiles: Sequence[str] = TEST_PROFILE_ORDER,
    phases: Sequence[str] = ("current",),
    temperatures: Sequence[str] = ("warm",),
    repeats: int = 1,
    required_profiles: Sequence[str] = TEST_PROFILE_ORDER,
    required_phases: Sequence[str] = TEST_PROFILE_PHASE_ORDER,
    required_temperatures: Sequence[str] = TEST_PROFILE_TEMPERATURE_ORDER,
    extra_pytest_args: Sequence[str] = (),
    suppress_success_output: bool = False,
    existing_suite_path: str | Path | None = None,
) -> dict[str, Any]:
    document = run_pytest_profile_suite(
        repo_root,
        profiles=profiles,
        phases=phases,
        temperatures=temperatures,
        repeats=repeats,
        required_profiles=required_profiles,
        required_phases=required_phases,
        required_temperatures=required_temperatures,
        extra_pytest_args=extra_pytest_args,
        suppress_success_output=suppress_success_output,
    )
    if existing_suite_path is not None:
        document = merge_pytest_profile_suite_cells(
            read_pytest_profile_suite(existing_suite_path),
            document,
        )
    validate_pytest_profile_suite(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


def _series_stats(values: Sequence[float | int]) -> dict[str, float | int]:
    if not values:
        raise ValueError("pytest profile summary cannot summarize an empty series")
    sorted_values = sorted(values)
    middle = median(sorted_values)
    if all(isinstance(item, int) and not isinstance(item, bool) for item in values):
        return {
            "max": max(sorted_values),
            "median": middle,
            "min": min(sorted_values),
        }
    return {
        "max": round(float(max(sorted_values)), 6),
        "median": round(float(middle), 6),
        "min": round(float(min(sorted_values)), 6),
    }


def _ratio(current: float | int, baseline: float | int) -> float | None:
    if baseline == 0:
        return 0.0 if current == 0 else None
    return round(float(current) / float(baseline), 6)


def _ratio_passed(ratio: float | None, target: float) -> bool:
    return ratio is not None and ratio <= target


def summarize_pytest_profile_measurements(
    measurements: Sequence[Mapping[str, Any]],
    *,
    baseline: Mapping[str, Any] | None = None,
    required_profiles: Sequence[str] = TEST_PROFILE_ORDER,
) -> dict[str, Any]:
    if not measurements:
        raise ValueError("pytest profile summary requires at least one measurement")
    required = list(required_profiles)
    if not required or any(profile not in TEST_PROFILE_ORDER for profile in required):
        raise ValueError("pytest profile summary required_profiles are invalid")

    normalized = [validate_pytest_profile_measurement(item) for item in measurements]
    normalized.sort(key=lambda item: item["evidence_id"])
    baseline_summary = validate_pytest_profile_summary(baseline) if baseline else None
    grouped: dict[str, list[dict[str, Any]]] = {
        profile: [] for profile in TEST_PROFILE_ORDER
    }
    for item in normalized:
        grouped[item["profile"]].append(item)

    profiles: dict[str, Any] = {}
    profiles_present: list[str] = []
    for profile in TEST_PROFILE_ORDER:
        records = grouped[profile]
        if not records:
            continue
        profiles_present.append(profile)
        peak_values = [
            item["peak_rss_bytes"]
            for item in records
            if item.get("peak_rss_bytes") is not None
        ]
        profiles[profile] = {
            "failed_count": sum(1 for item in records if not item["passed"]),
            "max_peak_rss_bytes": max(peak_values) if peak_values else None,
            "measurement_count": len(records),
            "measurement_ids": [item["evidence_id"] for item in records],
            "passed_count": sum(1 for item in records if item["passed"]),
            "pytest_passed_tests": _series_stats(
                [item["pytest_counts"]["passed"] for item in records]
            ),
            "rss_measurements": dict(
                sorted(Counter(item["rss_measurement"] for item in records).items())
            ),
            "stderr_bytes": _series_stats([item["stderr_bytes"] for item in records]),
            "stdout_bytes": _series_stats([item["stdout_bytes"] for item in records]),
            "wall_seconds": _series_stats([item["wall_seconds"] for item in records]),
        }

    missing_profiles = [profile for profile in required if profile not in profiles]
    all_measurements_passed = all(item["passed"] for item in normalized)
    profile_coverage_passed = not missing_profiles
    comparison: dict[str, Any] = {
        "baseline_evidence_id": (
            baseline_summary["evidence_id"] if baseline_summary is not None else None
        ),
        "missing_baseline_profiles": [],
        "profile_reduction_passed": False,
        "profile_selection_comparison": None,
        "profile_selection_passed": False,
        "profiles": {},
        "stdout_stderr_reduction_target_ratio": _OUTPUT_REDUCTION_TARGET_RATIO,
        "wall_time_reduction_target_ratio": _WALL_TIME_REDUCTION_TARGET_RATIO,
    }
    baseline_comparison_passed = baseline_summary is not None
    if baseline_summary is None:
        baseline_comparison_passed = False
    else:
        baseline_profiles = baseline_summary["profiles"]
        profile_reduction_passed = True
        for profile in required:
            current = profiles.get(profile)
            base = baseline_profiles.get(profile)
            if current is None:
                continue
            if base is None:
                comparison["missing_baseline_profiles"].append(profile)
                baseline_comparison_passed = False
                continue
            wall_ratio = _ratio(
                current["wall_seconds"]["median"],
                base["wall_seconds"]["median"],
            )
            stdout_ratio = _ratio(
                current["stdout_bytes"]["median"],
                base["stdout_bytes"]["median"],
            )
            stderr_ratio = _ratio(
                current["stderr_bytes"]["median"],
                base["stderr_bytes"]["median"],
            )
            profile_passed = (
                _ratio_passed(wall_ratio, _WALL_TIME_REDUCTION_TARGET_RATIO)
                and _ratio_passed(stdout_ratio, _OUTPUT_REDUCTION_TARGET_RATIO)
                and _ratio_passed(stderr_ratio, _OUTPUT_REDUCTION_TARGET_RATIO)
            )
            current_pytest_passed = current["pytest_passed_tests"]["median"]
            baseline_pytest_passed = base["pytest_passed_tests"]["median"]
            passed_count_delta = current_pytest_passed - baseline_pytest_passed
            workload_count_changed = passed_count_delta != 0
            comparison["profiles"][profile] = {
                "baseline_pytest_passed_count": baseline_pytest_passed,
                "passed": profile_passed,
                "current_pytest_passed_count": current_pytest_passed,
                "pytest_passed_count_delta": passed_count_delta,
                "stderr_bytes_median_ratio": stderr_ratio,
                "stdout_bytes_median_ratio": stdout_ratio,
                "wall_seconds_median_ratio": wall_ratio,
                "workload_count_changed": workload_count_changed,
            }
            if not profile_passed:
                profile_reduction_passed = False
        comparison["profile_reduction_passed"] = profile_reduction_passed
        selection_profile = "release"
        selection_current = profiles.get(selection_profile)
        selection_baseline_profiles = [
            baseline_profiles.get(profile) for profile in required
        ]
        if (
            selection_current is not None
            and selection_baseline_profiles
            and all(item is not None for item in selection_baseline_profiles)
        ):
            baseline_wall = round(
                sum(
                    float(item["wall_seconds"]["median"])  # type: ignore[index]
                    for item in selection_baseline_profiles
                ),
                6,
            )
            baseline_stdout = sum(
                int(item["stdout_bytes"]["median"])  # type: ignore[index]
                for item in selection_baseline_profiles
            )
            baseline_stderr = sum(
                int(item["stderr_bytes"]["median"])  # type: ignore[index]
                for item in selection_baseline_profiles
            )
            wall_ratio = _ratio(
                selection_current["wall_seconds"]["median"],
                baseline_wall,
            )
            stdout_ratio = _ratio(
                selection_current["stdout_bytes"]["median"],
                baseline_stdout,
            )
            stderr_ratio = _ratio(
                selection_current["stderr_bytes"]["median"],
                baseline_stderr,
            )
            selection_passed = (
                _ratio_passed(wall_ratio, _WALL_TIME_REDUCTION_TARGET_RATIO)
                and _ratio_passed(stdout_ratio, _OUTPUT_REDUCTION_TARGET_RATIO)
                and _ratio_passed(stderr_ratio, _OUTPUT_REDUCTION_TARGET_RATIO)
            )
            comparison["profile_selection_comparison"] = {
                "baseline_profile_count": len(required),
                "baseline_stdout_bytes_median_sum": baseline_stdout,
                "baseline_stderr_bytes_median_sum": baseline_stderr,
                "baseline_wall_seconds_median_sum": baseline_wall,
                "current_profile": selection_profile,
                "current_stdout_bytes_median": selection_current["stdout_bytes"][
                    "median"
                ],
                "current_stderr_bytes_median": selection_current["stderr_bytes"][
                    "median"
                ],
                "current_wall_seconds_median": selection_current["wall_seconds"][
                    "median"
                ],
                "full_regression_substitute": False,
                "passed": selection_passed,
                "stderr_bytes_median_ratio": stderr_ratio,
                "stdout_bytes_median_ratio": stdout_ratio,
                "wall_seconds_median_ratio": wall_ratio,
            }
            comparison["profile_selection_passed"] = selection_passed
        baseline_comparison_passed = (
            profile_reduction_passed or comparison["profile_selection_passed"]
        )

    rejection_reasons: list[str] = []
    if not all_measurements_passed:
        rejection_reasons.append("measurement-failed")
    if missing_profiles:
        rejection_reasons.append("missing-required-profiles")
    if baseline_summary is None:
        rejection_reasons.append("missing-baseline-summary")
    if comparison["missing_baseline_profiles"]:
        rejection_reasons.append("missing-baseline-profiles")
    if baseline_summary is not None and not baseline_comparison_passed:
        rejection_reasons.append("reduction-target-not-met")
    workload_count_changed = any(
        profile.get("workload_count_changed")
        for profile in comparison["profiles"].values()
    )
    if workload_count_changed and not comparison["profile_selection_passed"]:
        rejection_reasons.append("workload-count-changed")

    release_gate_passed = (
        all_measurements_passed
        and profile_coverage_passed
        and baseline_comparison_passed
    )
    identity = to_canonical_data(
        {
            "all_measurements_passed": all_measurements_passed,
            "baseline_comparison_passed": baseline_comparison_passed,
            "included_measurement_count": len(normalized),
            "measurement_ids": [item["evidence_id"] for item in normalized],
            "missing_profiles": missing_profiles,
            "passed": release_gate_passed,
            "profile_coverage_passed": profile_coverage_passed,
            "profiles": profiles,
            "profiles_present": profiles_present,
            "reduction_comparison": comparison,
            "rejection_reasons": rejection_reasons,
            "release_gate_passed": release_gate_passed,
            "required_profiles": required,
            "schema_version": PYTEST_PROFILE_SUMMARY_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="pytestprofilesummary_"),
    }


def validate_pytest_profile_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("pytest profile summary must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("pytest profile summary must be an object")
    if document.get("schema_version") != PYTEST_PROFILE_SUMMARY_SCHEMA_VERSION:
        raise ValueError("unsupported pytest profile summary schema_version")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "pytestprofilesummary_"
    ):
        raise ValueError("pytest profile summary evidence_id is invalid")
    identity = {key: item for key, item in document.items() if key != "evidence_id"}
    if evidence_id != stable_digest(identity, prefix="pytestprofilesummary_"):
        raise ValueError("pytest profile summary evidence_id mismatch")
    for key in (
        "all_measurements_passed",
        "baseline_comparison_passed",
        "passed",
        "profile_coverage_passed",
        "release_gate_passed",
    ):
        if not isinstance(document.get(key), bool):
            raise ValueError(f"pytest profile summary {key} must be a boolean")
    if document["passed"] != document["release_gate_passed"]:
        raise ValueError("pytest profile summary passed must mirror release_gate_passed")
    required_profiles = document.get("required_profiles")
    if (
        not isinstance(required_profiles, Sequence)
        or isinstance(required_profiles, (str, bytes))
        or not required_profiles
    ):
        raise ValueError("pytest profile summary required_profiles must be a list")
    if any(profile not in TEST_PROFILE_ORDER for profile in required_profiles):
        raise ValueError("pytest profile summary required_profiles are invalid")
    for key in ("measurement_ids", "missing_profiles", "profiles_present"):
        values = document.get(key)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ValueError(f"pytest profile summary {key} must be a list")
        if any(not isinstance(item, str) for item in values):
            raise ValueError(f"pytest profile summary {key} must contain strings")
    count = document.get("included_measurement_count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("pytest profile summary included_measurement_count is invalid")
    if count != len(document["measurement_ids"]):
        raise ValueError("pytest profile summary measurement count mismatch")
    profiles = document.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ValueError("pytest profile summary profiles must be an object")
    for profile, record in profiles.items():
        if profile not in TEST_PROFILE_ORDER:
            raise ValueError("pytest profile summary profile is invalid")
        if not isinstance(record, Mapping):
            raise ValueError(f"pytest profile summary profile {profile} is invalid")
        measurement_count = record.get("measurement_count")
        if (
            not isinstance(measurement_count, int)
            or isinstance(measurement_count, bool)
            or measurement_count <= 0
        ):
            raise ValueError("pytest profile summary measurement_count is invalid")
        if record.get("passed_count", 0) + record.get("failed_count", 0) != measurement_count:
            raise ValueError("pytest profile summary pass/fail count mismatch")
        ids = record.get("measurement_ids")
        if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
            raise ValueError("pytest profile summary profile measurement_ids invalid")
        if len(ids) != measurement_count:
            raise ValueError("pytest profile summary profile measurement count mismatch")
        for stats_key in ("wall_seconds", "stdout_bytes", "stderr_bytes"):
            stats = record.get(stats_key)
            if not isinstance(stats, Mapping):
                raise ValueError(f"pytest profile summary {stats_key} is invalid")
            for item in ("min", "median", "max"):
                number = stats.get(item)
                if not isinstance(number, (int, float)) or isinstance(number, bool):
                    raise ValueError(
                        f"pytest profile summary {stats_key}.{item} is invalid"
                    )
                if number < 0:
                    raise ValueError(
                        f"pytest profile summary {stats_key}.{item} is negative"
                    )
            if stats["min"] > stats["median"] or stats["median"] > stats["max"]:
                raise ValueError(f"pytest profile summary {stats_key} is inconsistent")
    return document


def read_pytest_profile_summary(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("pytest profile summary is invalid JSON") from exc
    return validate_pytest_profile_summary(value)


def write_pytest_profile_summary(
    measurement_paths: Sequence[str | Path],
    *,
    output_path: str | Path,
    baseline_path: str | Path | None = None,
    suite_path: str | Path | None = None,
    suite_phase: str = "current",
    suite_temperature: str = "warm",
    baseline_suite_path: str | Path | None = None,
    baseline_suite_phase: str = "baseline",
    baseline_suite_temperature: str = "warm",
    required_profiles: Sequence[str] = TEST_PROFILE_ORDER,
) -> dict[str, Any]:
    measurements = [read_pytest_profile_measurement(path) for path in measurement_paths]
    if suite_path is not None:
        measurements.extend(
            measurements_from_pytest_profile_suite(
                read_pytest_profile_suite(suite_path),
                phase=suite_phase,
                temperature=suite_temperature,
            )
        )
    if not measurements:
        raise ValueError("pytest profile summary requires measurements or a suite")
    baseline = read_pytest_profile_summary(baseline_path) if baseline_path else None
    if baseline_suite_path is not None:
        baseline_measurements = measurements_from_pytest_profile_suite(
            read_pytest_profile_suite(baseline_suite_path),
            phase=baseline_suite_phase,
            temperature=baseline_suite_temperature,
        )
        baseline = summarize_pytest_profile_measurements(
            baseline_measurements,
            required_profiles=required_profiles,
        )
    document = summarize_pytest_profile_measurements(
        measurements,
        baseline=baseline,
        required_profiles=required_profiles,
    )
    validate_pytest_profile_summary(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


def evaluate_pytest_profile_release_gate(
    *,
    plan: Mapping[str, Any],
    suite: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    plan_document = validate_pytest_profile_plan(plan)
    suite_document = validate_pytest_profile_suite(suite)
    summary_document = validate_pytest_profile_summary(summary)
    rejection_reasons: list[str] = []
    cell_rejections: list[dict[str, Any]] = []
    suite_plan_ids = set(suite_document["profile_plan_ids"])
    if plan_document["evidence_id"] not in suite_plan_ids:
        rejection_reasons.append("suite-plan-mismatch")
    if not suite_document["passed"]:
        rejection_reasons.append("suite-gate-failed")
    if not summary_document["release_gate_passed"]:
        rejection_reasons.append("summary-gate-failed")
    summary_measurement_ids = set(summary_document["measurement_ids"])
    suite_measurement_ids = set(suite_document["measurement_ids"])
    if not summary_measurement_ids.issubset(suite_measurement_ids):
        rejection_reasons.append("summary-measurement-not-in-suite")
    for cell in suite_document["cells"]:
        measurement = cell["measurement"]
        reasons: list[str] = []
        if any(arg == "--collect-only" for arg in measurement["extra_pytest_args"]):
            reasons.append("collect-only-measurement")
        if (
            measurement["profile"] == "real_core"
            and measurement["pytest_counts"].get("skipped", 0) > 0
        ):
            reasons.append("real-core-skipped")
        if not measurement["passed"]:
            reasons.append("measurement-failed")
        if reasons:
            cell_rejections.append(
                {
                    "measurement_id": measurement["evidence_id"],
                    "phase": cell["phase"],
                    "profile": cell["profile"],
                    "reasons": reasons,
                    "repeat_index": cell["repeat_index"],
                    "temperature": cell["temperature"],
                }
            )
    if cell_rejections:
        rejection_reasons.append("cell-rejections")
    rejection_reasons = sorted(set(rejection_reasons))
    passed = not rejection_reasons
    identity = to_canonical_data(
        {
            "cell_rejections": cell_rejections,
            "checks": {
                "plan_evidence_id": plan_document["evidence_id"],
                "summary_evidence_id": summary_document["evidence_id"],
                "summary_measurement_ids": summary_document["measurement_ids"],
                "suite_evidence_id": suite_document["evidence_id"],
                "suite_measurement_ids": suite_document["measurement_ids"],
                "suite_missing_cell_count": suite_document["coverage"][
                    "missing_cell_count"
                ],
                "suite_passed": suite_document["passed"],
                "suite_profile_plan_ids": suite_document["profile_plan_ids"],
                "summary_release_gate_passed": summary_document[
                    "release_gate_passed"
                ],
            },
            "package_version": __version__,
            "passed": passed,
            "rejection_reasons": rejection_reasons,
            "schema_version": PYTEST_PROFILE_RELEASE_GATE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="pytestprofilegate_"),
    }


def _pytest_profile_release_gate_rejections(
    checks: Mapping[str, Any],
    cell_rejections: Sequence[Mapping[str, Any]],
) -> list[str]:
    rejection_reasons: list[str] = []
    plan_id = checks.get("plan_evidence_id")
    suite_plan_ids = checks.get("suite_profile_plan_ids")
    if isinstance(suite_plan_ids, Sequence) and not isinstance(
        suite_plan_ids,
        (str, bytes),
    ) and isinstance(plan_id, str) and plan_id not in suite_plan_ids:
        rejection_reasons.append("suite-plan-mismatch")
    if checks.get("suite_passed") is not True:
        rejection_reasons.append("suite-gate-failed")
    if checks.get("summary_release_gate_passed") is not True:
        rejection_reasons.append("summary-gate-failed")
    summary_measurement_ids = checks.get("summary_measurement_ids")
    suite_measurement_ids = checks.get("suite_measurement_ids")
    if (
        isinstance(summary_measurement_ids, Sequence)
        and not isinstance(summary_measurement_ids, (str, bytes))
        and isinstance(suite_measurement_ids, Sequence)
        and not isinstance(suite_measurement_ids, (str, bytes))
        and not set(summary_measurement_ids).issubset(set(suite_measurement_ids))
    ):
        rejection_reasons.append("summary-measurement-not-in-suite")
    if cell_rejections:
        rejection_reasons.append("cell-rejections")
    return sorted(set(rejection_reasons))


def validate_pytest_profile_release_gate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("pytest profile release gate must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("pytest profile release gate must be an object")
    if document.get("schema_version") != PYTEST_PROFILE_RELEASE_GATE_SCHEMA_VERSION:
        raise ValueError("unsupported pytest profile release gate schema_version")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "pytestprofilegate_"
    ):
        raise ValueError("pytest profile release gate evidence_id is invalid")
    identity = {key: item for key, item in document.items() if key != "evidence_id"}
    if evidence_id != stable_digest(identity, prefix="pytestprofilegate_"):
        raise ValueError("pytest profile release gate evidence_id mismatch")
    if not isinstance(document.get("passed"), bool):
        raise ValueError("pytest profile release gate passed must be a boolean")
    rejections = document.get("rejection_reasons")
    if not isinstance(rejections, Sequence) or isinstance(rejections, (str, bytes)):
        raise ValueError("pytest profile release gate rejection_reasons must be a list")
    if any(not isinstance(reason, str) for reason in rejections):
        raise ValueError("pytest profile release gate rejection_reasons are invalid")
    if document["passed"] == bool(rejections):
        raise ValueError("pytest profile release gate passed/rejections mismatch")
    checks = document.get("checks")
    if not isinstance(checks, Mapping):
        raise ValueError("pytest profile release gate checks must be an object")
    for key in ("plan_evidence_id", "summary_evidence_id", "suite_evidence_id"):
        if not isinstance(checks.get(key), str):
            raise ValueError(f"pytest profile release gate {key} is invalid")
    for key in (
        "summary_measurement_ids",
        "suite_measurement_ids",
        "suite_missing_cell_count",
        "suite_passed",
        "suite_profile_plan_ids",
        "summary_release_gate_passed",
    ):
        if key not in checks:
            raise ValueError(f"pytest profile release gate {key} is missing")
    for key in (
        "summary_measurement_ids",
        "suite_measurement_ids",
        "suite_profile_plan_ids",
    ):
        values = checks[key]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ValueError(f"pytest profile release gate {key} must be a list")
        if any(not isinstance(item, str) for item in values):
            raise ValueError(f"pytest profile release gate {key} is invalid")
    if (
        not isinstance(checks["suite_missing_cell_count"], int)
        or isinstance(checks["suite_missing_cell_count"], bool)
        or checks["suite_missing_cell_count"] < 0
    ):
        raise ValueError("pytest profile release gate suite_missing_cell_count is invalid")
    for key in ("suite_passed", "summary_release_gate_passed"):
        if not isinstance(checks[key], bool):
            raise ValueError(f"pytest profile release gate {key} must be a boolean")
    cell_rejections = document.get("cell_rejections")
    if not isinstance(cell_rejections, Sequence) or isinstance(
        cell_rejections,
        (str, bytes),
    ):
        raise ValueError("pytest profile release gate cell_rejections must be a list")
    for item in cell_rejections:
        if not isinstance(item, Mapping):
            raise ValueError("pytest profile release gate cell_rejections are invalid")
        reasons = item.get("reasons")
        if not isinstance(reasons, Sequence) or isinstance(reasons, (str, bytes)):
            raise ValueError("pytest profile release gate cell rejection reasons invalid")
        if any(not isinstance(reason, str) for reason in reasons):
            raise ValueError("pytest profile release gate cell rejection reasons invalid")
    derived_rejections = _pytest_profile_release_gate_rejections(
        checks,
        cell_rejections,
    )
    if list(rejections) != derived_rejections:
        raise ValueError("pytest profile release gate rejections are inconsistent")
    if document["passed"] != (not derived_rejections):
        raise ValueError("pytest profile release gate passed is inconsistent")
    return document


def read_pytest_profile_release_gate(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("pytest profile release gate is invalid JSON") from exc
    return validate_pytest_profile_release_gate(value)


def write_pytest_profile_release_gate(
    *,
    plan_path: str | Path,
    suite_path: str | Path,
    summary_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_pytest_profile_release_gate(
        plan=read_pytest_profile_plan(plan_path),
        suite=read_pytest_profile_suite(suite_path),
        summary=read_pytest_profile_summary(summary_path),
    )
    validate_pytest_profile_release_gate(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document
