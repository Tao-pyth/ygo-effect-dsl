from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from ygo_effect_dsl.experiment import (
    load_experiment_document,
    migrate_experiment_v03a_to_v03b,
    resolve_experiment_overrides,
    validate_experiment,
)
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.route_dsl import load_route_document
from ygo_effect_dsl.storage import RunCatalog, RunStatus, read_raw_log


ROOT = Path(__file__).parents[1]
SAMPLE = ROOT / "examples" / "experiments" / "real_core_effect_veiler.yaml"


def test_sample_experiment_and_distributed_json_schema_are_aligned() -> None:
    experiment = load_experiment_document(SAMPLE)
    experiment["schema_version"] = "0.4"
    experiment["deck"] = {
        "id": "schema_fixture",
        "source": "inline",
        "main": list(range(1, 41)),
        "extra": [],
        "side": [],
    }
    experiment["scenario"] = {
        "schema_version": "scenario-v1",
        "opening_hand": {"mode": "fixed", "cards": list(range(1, 6))},
    }
    schema = json.loads(
        (
            ROOT
            / "src"
            / "ygo_effect_dsl"
            / "resources"
            / "experiment.schema.json"
        ).read_text(encoding="utf-8")
    )

    assert validate_experiment(experiment) == ()
    assert schema["properties"]["schema_version"]["const"] == "0.4"
    assert set(schema["required"]).issubset(experiment)


def test_v03a_requires_explicit_policy_choices_to_migrate() -> None:
    legacy = load_experiment_document(SAMPLE)
    legacy["schema_version"] = "0.3a"
    legacy.pop("information_policy")

    assert validate_experiment(legacy) == ()
    migrated = migrate_experiment_v03a_to_v03b(
        legacy,
        deck_order="known",
        opening_hand="fixed",
    )

    assert migrated["schema_version"] == "0.3b"
    assert migrated["information_policy"]["policy_id"].startswith("infopol_")
    assert validate_experiment(migrated) == ()
    with pytest.raises(ValueError, match="explicitly migrate"):
        resolve_experiment_overrides(legacy)


def test_v03a_cannot_silently_carry_a_v03b_policy() -> None:
    legacy = load_experiment_document(SAMPLE)
    legacy["schema_version"] = "0.3a"

    issues = validate_experiment(legacy)

    assert ("$.information_policy", "field_not_allowed_in_legacy_schema") in {
        (issue.path, issue.code) for issue in issues
    }


def test_player_view_policy_derives_viewer_from_player_perspective() -> None:
    legacy = load_experiment_document(SAMPLE)
    legacy["schema_version"] = "0.3a"
    legacy["information_mode"] = "player_view"
    legacy["player"]["perspective"] = 1
    legacy.pop("information_policy")

    migrated = migrate_experiment_v03a_to_v03b(
        legacy,
        deck_order="unknown",
        opening_hand="natural",
    )

    assert "viewer" not in migrated["information_policy"]
    assert validate_experiment(migrated) == ()
    changed_perspective = deepcopy(migrated)
    changed_perspective["player"]["perspective"] = 0
    assert "invalid_information_policy" in {
        issue.code for issue in validate_experiment(changed_perspective)
    }


def test_migration_cli_requires_explicit_policy_dimensions(tmp_path: Path) -> None:
    legacy = load_experiment_document(SAMPLE)
    legacy["schema_version"] = "0.3a"
    legacy.pop("information_policy")
    source = tmp_path / "legacy.yaml"
    output = tmp_path / "current.yaml"
    source.write_text(yaml.safe_dump(legacy, sort_keys=False), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ygo_effect_dsl",
            "experiment-migrate",
            str(source),
            "--deck-order",
            "known",
            "--opening-hand",
            "fixed",
            "--out",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "experiment-migrate: ok" in completed.stdout
    assert validate_experiment(load_experiment_document(output)) == ()


def test_experiment_validation_reports_specific_paths_and_codes() -> None:
    experiment = load_experiment_document(SAMPLE)
    del experiment["deck"]
    experiment["turn_limit"] = 0
    experiment["search"]["budget"] = {}
    experiment["interruption"] = {
        "mode": "none",
        "definitions": [{"id": "invalid_for_none"}],
    }

    issues = validate_experiment(experiment)
    issue_keys = {(issue.path, issue.code) for issue in issues}

    assert ("$.deck", "required_field") in issue_keys
    assert ("$.turn_limit", "invalid_positive_integer") in issue_keys
    assert ("$.search.budget", "missing_budget_limit") in issue_keys
    assert (
        "$.interruption.definitions",
        "definitions_for_none_mode",
    ) in issue_keys


def test_evaluator_and_interruption_can_be_selected_from_config() -> None:
    experiment = load_experiment_document(SAMPLE)
    variant = deepcopy(experiment)
    variant["evaluator"] = {
        "id": "control_board",
        "version": "2",
        "config": {"interruption_weight": 20},
    }
    variant["interruption"] = {
        "mode": "scripted",
        "definitions": [{"id": "effect_veiler_at_first_monster_effect"}],
    }

    assert validate_experiment(variant) == ()

    variant["interruption"]["definitions"] = []
    assert "missing_interruption_definition" in {
        issue.code for issue in validate_experiment(variant)
    }


def test_validate_experiment_cli_accepts_sample() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ygo_effect_dsl", "validate-experiment", str(SAMPLE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "validate-experiment: ok experiment_id=" in completed.stdout


def test_cli_exit_codes_separate_validation_and_operational_failures(
    tmp_path: Path,
) -> None:
    invalid = load_experiment_document(SAMPLE)
    del invalid["deck"]
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text(
        yaml.safe_dump(invalid, sort_keys=False), encoding="utf-8"
    )
    validation = subprocess.run(
        [
            sys.executable,
            "-m",
            "ygo_effect_dsl",
            "validate-experiment",
            str(invalid_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    operational = subprocess.run(
        [
            sys.executable,
            "-m",
            "ygo_effect_dsl",
            "experiment-inspect",
            str(SAMPLE),
            str(tmp_path / "missing.route.yaml"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert validation.returncode == 1
    assert "validate-experiment: failed" in validation.stdout
    assert validation.stderr == ""
    assert operational.returncode == 2
    assert operational.stdout == ""
    assert operational.stderr.startswith("error:")


def test_explicit_cli_overrides_take_precedence_without_mutating_file_config() -> None:
    experiment = load_experiment_document(SAMPLE)

    resolved = resolve_experiment_overrides(
        experiment,
        max_nodes=64,
        max_seconds=12.5,
        evaluator_version="2",
    )

    assert experiment["search"]["budget"] == {"max_nodes": 32}
    assert experiment["evaluator"]["version"] == "1"
    assert resolved["search"]["budget"] == {
        "max_nodes": 64,
        "max_seconds": 12.5,
    }
    assert resolved["evaluator"]["version"] == "2"


def test_experiment_cli_runs_inspects_and_replays_sample(tmp_path: Path) -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    route_path = tmp_path / "experiment.route.yaml"
    report_path = tmp_path / "report.md"
    interrupted_path = tmp_path / "interrupted.yaml"
    catalog_path = tmp_path / "runs.sqlite3"
    raw_log_path = tmp_path / "run.jsonl"
    common = [sys.executable, "-m", "ygo_effect_dsl"]
    generated = subprocess.run(
        [
            *common,
            "experiment-run",
            str(SAMPLE),
            "--out",
            str(route_path),
            "--run-id",
            "run_cli_fixture",
            "--catalog",
            str(catalog_path),
            "--raw-log",
            str(raw_log_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    inspected = subprocess.run(
        [*common, "experiment-inspect", str(SAMPLE), str(route_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    replayed = subprocess.run(
        [
            *common,
            "experiment-replay",
            str(SAMPLE),
            str(route_path),
            "--run-id",
            "run_replay_fixture",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    reported = subprocess.run(
        [
            *common,
            "experiment-report",
            str(SAMPLE),
            str(route_path),
            "--out",
            str(report_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    interrupted = subprocess.run(
        [
            *common,
            "experiment-interrupt",
            str(SAMPLE),
            "--id",
            "effect_veiler_at_first_monster_effect",
            "--out",
            str(interrupted_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert generated.returncode == 0, generated.stdout + generated.stderr
    assert inspected.returncode == 0, inspected.stdout + inspected.stderr
    assert replayed.returncode == 0, replayed.stdout + replayed.stderr
    assert reported.returncode == 0, reported.stdout + reported.stderr
    assert interrupted.returncode == 0, interrupted.stdout + interrupted.stderr
    assert "experiment-run: ok" in generated.stdout
    assert "run_id=run_cli_fixture" in generated.stdout
    assert "experiment-inspect: ok" in inspected.stdout
    assert "experiment-replay: ok" in replayed.stdout
    assert "run_id=run_replay_fixture" in replayed.stdout
    assert "experiment-report: ok" in reported.stdout
    assert "experiment-interrupt: ok" in interrupted.stdout
    route = load_route_document(route_path)
    assert route["experiment"]["runner"]["adapter"] == "real_core_prototype"
    assert route["experiment"]["search"]["budget"]["max_nodes"] == 32
    catalog_record = RunCatalog(catalog_path).get_run("run_cli_fixture")
    assert catalog_record is not None
    assert catalog_record.status == RunStatus.COMPLETE
    assert [record.event_type for record in read_raw_log(raw_log_path)] == [
        "run_started",
        "run_completed",
    ]
    report = report_path.read_text(encoding="utf-8")
    assert "schema_version: report-v1" in report
    assert "## Peak Score Breakdown" in report
    interrupted_experiment = load_experiment_document(interrupted_path)
    assert interrupted_experiment["interruption"] == {
        "mode": "scripted",
        "definitions": [{"id": "effect_veiler_at_first_monster_effect"}],
    }
