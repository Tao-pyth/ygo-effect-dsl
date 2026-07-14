from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ygo_effect_dsl.runtime_imports import current_checkout_environment


def _run_cli(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ygo_effect_dsl", *args],
        cwd=repo_root,
        env=current_checkout_environment(),
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
    assert "analyze: action_type_coverage=" in analyze.stdout
    assert "analyze: target_resolution_rate=" in analyze.stdout
    assert "analyze: unmatched_fragments_top_count=" in analyze.stdout
    assert "analyze: validation_code_counts=" in analyze.stdout

    report_path = report_out / "analysis_report.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert isinstance(report["stats"]["action_type_coverage"], dict)
    assert isinstance(report["stats"]["targets_count"]["resolution_rate"], float)
    assert isinstance(report["stats"]["unmatched_fragments_top"], list)
    assert isinstance(report["quality"]["empty_block_ratio"], dict)
    assert isinstance(report["validation"]["severity_counts"], dict)
    assert isinstance(report["validation"]["code_counts"], dict)
