from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from ygo_effect_dsl.cli import cmd_experiment as command_module
from ygo_effect_dsl.engine.information import (
    InformationCanary,
    InformationCanaryRegistry,
    audit_information_artifact,
)
from ygo_effect_dsl.prototype import RealCorePlayerViewWorkerError


PRIVATE_CANARY = "private-cli-canary-9981"


def _registry() -> InformationCanaryRegistry:
    return InformationCanaryRegistry(
        artifact_kind="player_view_replay",
        viewer=0,
        canaries=(
            InformationCanary(
                canary_id="canary_cli_private",
                classification="persistent_card_identity",
                matcher_kind="substring",
                source_path="snapshots[0].zones[8].cards[0]",
                value=PRIVATE_CANARY,
            ),
        ),
    )


def _result(*, unsafe_verification: bool = False) -> SimpleNamespace:
    player_view = {
        "events": [{"action_category": "OPPONENT_ACTION", "actor": 1}],
        "player_view_id": "playerview_cli_public",
        "schema_version": "player-view-replay-v1",
        "viewer": 0,
    }
    registry = _registry()
    information_audit = audit_information_artifact(
        player_view,
        artifact_kind="player_view_replay",
        registry=registry,
    )
    return SimpleNamespace(
        player_view=player_view,
        information_audit=information_audit,
        verification={
            "event_count": 1,
            "information_access_audit_id": information_audit["audit_id"],
            "player_view_id": "playerview_cli_public",
            "schema_version": "player-view-verification-v1",
            "status": "verified",
            "verification_id": (
                PRIVATE_CANARY if unsafe_verification else "verification_public"
            ),
            "viewer": 0,
        },
        private_lineage={
            "source_route_id": "route_private",
            "source_replay_digest": PRIVATE_CANARY,
        },
        private_canary_registry=registry.to_private_dict(),
    )


def _args(tmp_path) -> argparse.Namespace:
    return argparse.Namespace(
        experiment_file="experiment.yaml",
        route_file="route.yaml",
        viewer=0,
        out=str(tmp_path / "player-view.json"),
        audit_report=str(tmp_path / "audit.json"),
        verification_report=str(tmp_path / "verification.json"),
        private_lineage=str(tmp_path / "private-lineage.json"),
        external_root=None,
        worker_timeout=30.0,
        max_retries=0,
        max_nodes=None,
        max_seconds=None,
        evaluator_id=None,
        evaluator_version=None,
        interruption_mode=None,
    )


def _patch_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        command_module,
        "_resolved_experiment",
        lambda _args: {"experiment_id": "experiment_cli"},
    )
    monkeypatch.setattr(
        command_module,
        "load_route_document",
        lambda _path: {"route_id": "route_private"},
    )
    monkeypatch.setattr(
        command_module,
        "assert_experiment_matches_route",
        lambda _experiment, _route: None,
    )


def test_player_view_cli_publishes_only_after_all_audits_pass(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_source(monkeypatch)
    fake_result = _result()
    monkeypatch.setattr(
        command_module,
        "RealCorePlayerViewAdapter",
        lambda **_kwargs: SimpleNamespace(
            project=lambda _route, viewer: fake_result
        ),
    )
    args = _args(tmp_path)

    assert command_module.cmd_experiment_player_view(args) == 0

    public = json.loads((tmp_path / "player-view.json").read_text(encoding="utf-8"))
    audit = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    verification = json.loads(
        (tmp_path / "verification.json").read_text(encoding="utf-8")
    )
    private_lineage = json.loads(
        (tmp_path / "private-lineage.json").read_text(encoding="utf-8")
    )
    assert public["player_view_id"] == "playerview_cli_public"
    assert audit["status"] == "passed"
    assert verification["status"] == "verified"
    assert private_lineage["source_route_id"] == "route_private"
    assert PRIVATE_CANARY not in json.dumps(public, sort_keys=True)
    assert PRIVATE_CANARY not in json.dumps(audit, sort_keys=True)
    assert PRIVATE_CANARY not in json.dumps(verification, sort_keys=True)
    console = capsys.readouterr()
    assert str(tmp_path) not in console.out
    assert PRIVATE_CANARY not in console.out


def test_player_view_cli_blocks_publication_when_support_artifact_leaks(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_source(monkeypatch)
    fake_result = _result(unsafe_verification=True)
    monkeypatch.setattr(
        command_module,
        "RealCorePlayerViewAdapter",
        lambda **_kwargs: SimpleNamespace(
            project=lambda _route, viewer: fake_result
        ),
    )
    args = _args(tmp_path)
    public_path = tmp_path / "player-view.json"
    public_path.write_text("existing-public-artifact\n", encoding="utf-8")

    with pytest.raises(ValueError, match="publication blocked"):
        command_module.cmd_experiment_player_view(args)

    assert public_path.read_text(encoding="utf-8") == "existing-public-artifact\n"
    failure = (tmp_path / "audit.json").read_text(encoding="utf-8")
    assert '"status":"audit_failure"' in failure
    assert PRIVATE_CANARY not in failure
    assert not (tmp_path / "verification.json").exists()
    assert not (tmp_path / "private-lineage.json").exists()


def test_player_view_cli_worker_failure_writes_only_safe_failure_report(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_source(monkeypatch)

    def fail(_route, *, viewer):
        raise RealCorePlayerViewWorkerError(
            "worker_timeout", retry_exhausted=True
        )

    monkeypatch.setattr(
        command_module,
        "RealCorePlayerViewAdapter",
        lambda **_kwargs: SimpleNamespace(project=fail),
    )
    args = _args(tmp_path)

    with pytest.raises(ValueError, match="safe code"):
        command_module.cmd_experiment_player_view(args)

    failure = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    assert failure == {
        "artifact_commit": {"status": "not_published"},
        "failure_code": "worker_timeout",
        "schema_version": "player-view-publication-failure-v1",
        "status": "worker_failure",
    }
    assert not (tmp_path / "player-view.json").exists()
    assert not (tmp_path / "verification.json").exists()
    assert not (tmp_path / "private-lineage.json").exists()


def test_player_view_cli_requires_distinct_output_paths(tmp_path) -> None:
    args = _args(tmp_path)
    args.audit_report = args.out

    with pytest.raises(ValueError, match="must be distinct"):
        command_module.cmd_experiment_player_view(args)
