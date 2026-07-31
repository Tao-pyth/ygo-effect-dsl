from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

import pytest

from ygo_effect_dsl.cli.cmd_qualification import cmd_v1_security_threat_model
from ygo_effect_dsl.spikes.security_threat_model_release_gate import (
    REQUIRED_THREAT_ROWS,
    V1_SECURITY_THREAT_MODEL_SCHEMA_VERSION,
    evaluate_v1_security_threat_model,
    read_v1_security_threat_model,
    validate_v1_security_threat_model,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_security_threat_model.json"
)


def test_v1_security_threat_model_evidence_passes_current_contract() -> None:
    evidence = evaluate_v1_security_threat_model(REPO_ROOT)
    checks = {check["id"]: check for check in evidence["checks"]}

    assert evidence["schema_version"] == V1_SECURITY_THREAT_MODEL_SCHEMA_VERSION
    assert evidence["issue"] == 177
    assert evidence["passed"] is True
    assert evidence["evidence_id"].startswith("v1securitythreat_")
    assert tuple(row["id"] for row in evidence["threat_rows"]) == REQUIRED_THREAT_ROWS
    assert all(check["passed"] is True for check in checks.values())
    assert evidence["policy"]["critical_high_unmitigated_release_blocker"] is True
    assert evidence["policy"]["unsafe_lua_default"] is False


def test_committed_v1_security_threat_model_matches_current_checkout() -> None:
    assert read_v1_security_threat_model(
        EVIDENCE_PATH
    ) == evaluate_v1_security_threat_model(REPO_ROOT)


def test_v1_security_threat_model_cli_writes_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "v1-security-threat-model.json"

    status = cmd_v1_security_threat_model(
        argparse.Namespace(
            out=output,
            repo_root=REPO_ROOT,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "v1-security-threat-model: passed" in captured.out
    assert read_v1_security_threat_model(output) == evaluate_v1_security_threat_model(
        REPO_ROOT
    )


def test_v1_security_threat_model_blocks_unmitigated_critical_or_high_risk() -> None:
    evidence = evaluate_v1_security_threat_model(REPO_ROOT)
    tampered = deepcopy(evidence)
    for row in tampered["threat_rows"]:
        if row["id"] == "native_dll":
            row["status"] = "unmitigated"
    identity = {key: tampered[key] for key in tampered if key != "evidence_id"}
    tampered["evidence_id"] = evidence["evidence_id"]

    with pytest.raises(ValueError, match="evidence_id mismatch|rejections"):
        validate_v1_security_threat_model(tampered)
