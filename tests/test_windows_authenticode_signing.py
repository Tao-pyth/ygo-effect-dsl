from __future__ import annotations

import argparse
from pathlib import Path

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_authenticode_signing
from ygo_effect_dsl.spikes.windows_authenticode_signing import (
    V1_AUTHENTICODE_SIGNING_SCHEMA_VERSION,
    evaluate_v1_authenticode_signing,
    read_v1_authenticode_signing,
    write_v1_authenticode_signing,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_authenticode_signing.json"
)


def test_v1_authenticode_signing_evidence_fails_closed_without_signed_artifacts() -> None:
    evidence = evaluate_v1_authenticode_signing(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_AUTHENTICODE_SIGNING_SCHEMA_VERSION
    assert evidence["issue"] == 356
    assert evidence["passed"] is False
    assert evidence["release_state"] == "blocked_until_signed_artifact_evidence_exists"
    assert checks["signing_policy_documented"]["passed"] is True
    assert checks["unsigned_artifact_rejection_recorded_in_ci"]["passed"] is True
    assert checks["signed_artifacts_verified"]["reason"] == (
        "missing_signed_artifact_evidence"
    )
    assert evidence["rejection_reasons"] == [
        "signed_artifacts_verified:missing_signed_artifact_evidence"
    ]


def test_committed_v1_authenticode_signing_matches_current_checkout() -> None:
    assert read_v1_authenticode_signing(EVIDENCE_PATH) == evaluate_v1_authenticode_signing(
        REPO_ROOT
    )


def test_v1_authenticode_signing_cli_writes_failed_closed_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "authenticode-signing.json"

    status = cmd_v1_authenticode_signing(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 1
    assert "v1-authenticode-signing: failed" in captured.out
    assert read_v1_authenticode_signing(output)["passed"] is False


def test_v1_authenticode_signing_writer_round_trips(tmp_path: Path) -> None:
    output = tmp_path / "authenticode-signing.json"

    evidence = write_v1_authenticode_signing(REPO_ROOT, output_path=output)

    assert read_v1_authenticode_signing(output) == evidence
