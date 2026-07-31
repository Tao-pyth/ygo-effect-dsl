from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from ygo_effect_dsl.cli.cmd_ocgcore import cmd_external_asset_setup_status
from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_external_asset_setup
from ygo_effect_dsl.desktop.bridge import DESKTOP_BRIDGE_CONTRACT_VERSION, DesktopBridge
from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.external import asset_setup
from ygo_effect_dsl.external.asset_setup import (
    EXTERNAL_ASSET_SETUP_STATUS_SCHEMA_VERSION,
    describe_external_asset_setup,
)
from ygo_effect_dsl.external.ocgcore import OcgcoreBootstrapError
from ygo_effect_dsl.spikes.external_asset_setup_release_gate import (
    V1_EXTERNAL_ASSET_SETUP_SCHEMA_VERSION,
    evaluate_v1_external_asset_setup,
    read_v1_external_asset_setup,
    write_v1_external_asset_setup,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_external_asset_setup.json"
)


def _request(method: str, payload: dict) -> dict:
    return {
        "method": method,
        "payload": payload,
        "request_id": "external-assets-test",
        "version": DESKTOP_BRIDGE_CONTRACT_VERSION,
    }


def test_external_asset_status_blocks_features_when_cache_is_missing(
    tmp_path: Path,
) -> None:
    status = describe_external_asset_setup(external_root=tmp_path / "external")
    checks = {check["id"]: check for check in status["checks"]}

    assert status["schema_version"] == EXTERNAL_ASSET_SETUP_STATUS_SCHEMA_VERSION
    assert status["ready"] is False
    assert status["dependent_features"] == {
        "card_names": "blocked",
        "deck_card_options": "blocked",
        "search_jobs": "blocked",
    }
    assert checks["ocgcore_runtime_verified"]["passed"] is False
    assert checks["card_scripts_and_database_verified"]["passed"] is False
    assert "ocgcore-bootstrap" in " ".join(status["guidance"]["commands"])
    assert status["guidance"]["policy"]["silent_download_at_runtime"] is False


def test_external_asset_status_reports_ready_after_verified_runtime_and_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        asset_setup,
        "verify_ocgcore",
        lambda *, external_root=None: {"build": {}, "lock_id": "core-lock", "ok": True},
    )
    monkeypatch.setattr(
        asset_setup,
        "verify_ocgcore_assets",
        lambda *, external_root=None: {
            "asset_lock_id": "asset-lock",
            "ok": True,
            "repositories": {},
        },
    )

    status = describe_external_asset_setup(external_root=tmp_path / "external")

    assert status["ready"] is True
    assert status["dependent_features"] == {
        "card_names": "enabled",
        "deck_card_options": "enabled",
        "search_jobs": "enabled",
    }
    assert all(check["passed"] is True for check in status["checks"])


def test_external_asset_status_reports_invalid_runtime_without_enabling_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_runtime(*, external_root=None):
        del external_root
        raise OcgcoreBootstrapError(
            "ocgcore runtime binary does not match the install manifest",
            code="runtime_integrity_mismatch",
        )

    monkeypatch.setattr(asset_setup, "verify_ocgcore", invalid_runtime)
    monkeypatch.setattr(
        asset_setup,
        "verify_ocgcore_assets",
        lambda *, external_root=None: {
            "asset_lock_id": "asset-lock",
            "ok": True,
            "repositories": {},
        },
    )

    status = describe_external_asset_setup(external_root=tmp_path / "external")
    checks = {check["id"]: check for check in status["checks"]}

    assert status["ready"] is False
    assert status["dependent_features"]["card_names"] == "enabled"
    assert status["dependent_features"]["search_jobs"] == "blocked"
    assert checks["ocgcore_runtime_verified"]["reason"] == "runtime_integrity_mismatch"


def test_desktop_describe_exposes_external_asset_setup_status(tmp_path: Path) -> None:
    blocked_status = {
        "asset_lock_id": "asset-lock",
        "checks": [],
        "core_lock_id": "core-lock",
        "dependent_features": {
            "card_names": "blocked",
            "deck_card_options": "blocked",
            "search_jobs": "blocked",
        },
        "external_root": str(tmp_path / "external"),
        "guidance": {"commands": ["python -m ygo_effect_dsl ocgcore-assets-verify"]},
        "ready": False,
        "schema_version": EXTERNAL_ASSET_SETUP_STATUS_SCHEMA_VERSION,
    }
    service = DesktopApplicationService(
        tmp_path,
        card_provider=SimpleNamespace(get_card=lambda _query: None),
        external_asset_status=lambda *, external_root=None: blocked_status,
    )
    bridge = DesktopBridge(service.handlers())

    description = bridge.invoke(_request("system.describe", {}))
    status = bridge.invoke(_request("system.external_asset_status", {}))
    service_without_provider = DesktopApplicationService(
        tmp_path,
        external_asset_status=lambda *, external_root=None: blocked_status,
    )
    blocked_bridge = DesktopBridge(service_without_provider.handlers())
    card = blocked_bridge.invoke(
        _request(
            "card.get",
            {
                "query": {
                    "card_code": 10000,
                    "expected_asset_lock_id": None,
                    "expected_provider_version": None,
                    "fallback_locales": [],
                    "redacted": False,
                    "requested_locale": "ja",
                    "schema_version": "card-presentation-query-v1",
                }
            },
        )
    )

    assert description["result"]["external_assets"] == blocked_status
    assert description["result"]["capabilities"]["card_presentation"] is False
    assert description["result"]["capabilities"]["deck_card_options"] is False
    assert description["result"]["capabilities"]["search_job_queue"] is False
    assert status["result"] == blocked_status
    assert card["ok"] is False
    assert card["diagnostics"][0]["code"] == "card_presentation_source_unavailable"
    assert card["details"]["external_assets"] == blocked_status


def test_external_asset_setup_status_cli_returns_nonzero_when_blocked(
    tmp_path: Path,
    capsys,
) -> None:
    status = cmd_external_asset_setup_status(
        argparse.Namespace(external_root=tmp_path / "external")
    )

    captured = capsys.readouterr()
    assert status == 1
    assert "external-asset-setup-status-v1" in captured.out
    assert "ocgcore-assets-bootstrap" in captured.out


def test_v1_external_asset_setup_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_external_asset_setup(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_EXTERNAL_ASSET_SETUP_SCHEMA_VERSION
    assert evidence["issue"] == 358
    assert evidence["passed"] is True
    assert evidence["dependent_features"]["search_jobs"] == (
        "blocked_until_core_and_card_assets_verified"
    )
    assert set(checks) == {
        "cli_status_reports_setup_guidance",
        "desktop_diagnostics_block_dependent_features",
        "first_run_policy_documented",
        "release_artifacts_do_not_bundle_external_assets",
        "tests_cover_missing_and_invalid_assets",
    }
    assert all(check["passed"] is True for check in checks.values())


def test_committed_v1_external_asset_setup_matches_current_checkout() -> None:
    assert read_v1_external_asset_setup(EVIDENCE_PATH) == evaluate_v1_external_asset_setup(
        REPO_ROOT
    )


def test_v1_external_asset_setup_cli_writes_content_addressed_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "external-asset-setup.json"

    status = cmd_v1_external_asset_setup(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-external-asset-setup: passed" in captured.out
    assert read_v1_external_asset_setup(output)["passed"] is True


def test_v1_external_asset_setup_writer_round_trips(tmp_path: Path) -> None:
    output = tmp_path / "external-asset-setup.json"

    evidence = write_v1_external_asset_setup(REPO_ROOT, output_path=output)

    assert read_v1_external_asset_setup(output) == evidence
