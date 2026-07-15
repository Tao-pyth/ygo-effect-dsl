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

from ygo_effect_dsl import PROJECT_IDENTITY, __version__
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
    assert project["dynamic"] == ["version"]
    assert "version" not in project
    assert project["scripts"][PROJECT_IDENTITY.cli_name] == (
        "ygo_effect_dsl.cli.main:main"
    )
    assert metadata["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "ygo_effect_dsl.version.__version__"
    }


def test_package_release_version_is_0_3_0_and_single_sourced() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert __version__ == "0.3.0"
    assert 'dynamic = ["version"]' in pyproject
    assert 'version = {attr = "ygo_effect_dsl.version.__version__"}' in pyproject


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


def test_cli_version_reports_the_package_release_version() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    completed = subprocess.run(
        [sys.executable, "-m", PROJECT_IDENTITY.python_package_name, "--version"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == f"{PROJECT_IDENTITY.cli_name} {__version__}"


def test_release_documents_match_the_current_version_baseline() -> None:
    documents = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in ("README.md", "docs/20_roadmap.md")
    }
    required_versions = (
        "0.3.0",
        "0.4",
        "0.3b",
        "0.3a",
        "0.1",
        "project-identity-v1",
        "scenario-v1",
        "ygo-replay-manifest-v1",
        "fresh-replay-verification-v1",
        "real-deck-qualification-index-v2",
        "ocgcore-lua-load-qualification-v1",
        "information-policy-v1",
        "ygo-state-id-v1",
        "evaluation-result-v1",
        "search-executor-v5",
        "search-frontier-v2",
        "search-run-result-v5",
        "search-strategy-evidence-v1",
        "search-run-report-v1",
        "search-run-failure-v2",
        "search-artifact-commit-v1",
        "random-search-strategy-v1",
        "beam-search-strategy-v1",
        "mcts-strategy-v1",
        "real-core-frontier-v2",
        "real-core-frontier-worker-attempt-v1",
        "real-core-frontier-worker-failure-v1",
        "interruption-support-taxonomy-v1",
        "aggregation-v1",
        "general-search-benchmark-v1",
        "real-core-benchmark-base-routes-v2",
        "cache-worker-policy-v2",
        "memory-preflight-v2",
        "real-core-replay-benchmark-v1",
        "real-core-worker-policy-v1",
        "real-core-memory-preflight-v1",
        "resolver-index-policy-v1",
        "ocgcore-platform-contract-v1",
        "ocgcore-doctor-v2",
    )

    for path, document in documents.items():
        for version in required_versions:
            assert f"`{version}`" in document, f"{path} is missing {version}"

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {__version__} - 2026-07-15" in changelog

    experiment_schema = (
        ROOT / "docs/experiment/10_schema.md"
    ).read_text(encoding="utf-8")
    assert "Status: V0.4 current contract" in experiment_schema
    assert "V0.3b current contract" not in experiment_schema


def test_engine_has_no_dependency_on_the_legacy_dsl_package() -> None:
    engine_root = SRC / "ygo_effect_dsl" / "engine"
    for module in engine_root.rglob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "ygo_effect_dsl.dsl" not in source, module
