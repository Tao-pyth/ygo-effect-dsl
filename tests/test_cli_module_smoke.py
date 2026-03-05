from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "ygo_effect_dsl", *args],
        cwd=repo_root,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def test_python_m_pipeline_smoke(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    dataset = repo_root / "tests/datasets/smoke_dataset"
    dsl_out = tmp_path / "dsl_out"
    yaml_out = dsl_out / "yaml"
    report_out = tmp_path / "reports"

    transform = _run_cli(["transform", "--dataset", str(dataset), "--out", str(dsl_out)], repo_root)
    assert transform.returncode == 0, transform.stdout + transform.stderr

    validate = _run_cli(["validate", str(yaml_out)], repo_root)
    assert validate.returncode == 0, validate.stdout + validate.stderr

    analyze = _run_cli(["analyze", str(yaml_out), "--out", str(report_out)], repo_root)
    assert analyze.returncode == 0, analyze.stdout + analyze.stderr

    assert (report_out / "analysis_report.json").exists()
