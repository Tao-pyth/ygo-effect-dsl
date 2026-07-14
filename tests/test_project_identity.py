from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    tomllib = None


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from ygo_effect_dsl import PROJECT_IDENTITY
from ygo_effect_dsl.project_identity import PROJECT_IDENTITY_SCHEMA_VERSION


def test_project_identity_keeps_compatible_technical_names() -> None:
    assert PROJECT_IDENTITY.to_dict() == {
        "schema_version": PROJECT_IDENTITY_SCHEMA_VERSION,
        "technical_project_name": "ygo-effect-dsl",
        "python_package_name": "ygo_effect_dsl",
        "cli_name": "ygo-effect-dsl",
        "product_description": (
            "Reproducible Yu-Gi-Oh! route search and Route Information DSL"
        ),
        "current_dsl_name": "Route Information DSL",
        "legacy_pipeline_name": "legacy card-text artifact pipeline",
    }


def test_distribution_metadata_matches_project_identity() -> None:
    if tomllib is None:
        pytest.skip("tomllib is available in Python 3.11 and later")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["name"] == PROJECT_IDENTITY.technical_project_name
    assert project["description"] == PROJECT_IDENTITY.product_description
    assert project["scripts"][PROJECT_IDENTITY.cli_name] == (
        "ygo_effect_dsl.cli.main:main"
    )


def test_cli_help_uses_the_stable_name_and_product_description() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    completed = subprocess.run(
        [sys.executable, "-m", PROJECT_IDENTITY.python_package_name, "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert f"usage: {PROJECT_IDENTITY.cli_name}" in completed.stdout
    assert PROJECT_IDENTITY.product_description in completed.stdout


def test_engine_has_no_dependency_on_the_legacy_dsl_package() -> None:
    engine_root = SRC / "ygo_effect_dsl" / "engine"
    for module in engine_root.rglob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "ygo_effect_dsl.dsl" not in source, module
