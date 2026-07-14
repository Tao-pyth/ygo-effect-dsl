from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from ygo_effect_dsl.engine.action import (
    ACTIVATION_ROLLBACK_UNREACHABLE,
    action_aggregation_compatibility_report,
    assert_valid_activation_rollback_probe,
)
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import invoke_real_core_worker_process
from ygo_effect_dsl.spikes.activation_rollback_audit import (
    assert_valid_activation_rollback_audit,
)


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "examples/experiments/real_core_activation_rollback_probe.yaml"
AUDIT = ROOT / "docs/ocgcore/evidence/activation_rollback_audit.json"
EDGE_EVIDENCE = ROOT / "docs/ocgcore/evidence/action_aggregation_edges.json"


@pytest.fixture(scope="module")
def probe_runs() -> tuple[Any, Any]:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    experiment = load_experiment_document(EXPERIMENT)
    return (
        invoke_real_core_worker_process(
            experiment=experiment,
            document_kind="activation_rollback_probe",
        ),
        invoke_real_core_worker_process(
            experiment=experiment,
            document_kind="activation_rollback_probe",
        ),
    )


def test_native_cancel_probe_is_fresh_worker_deterministic(
    probe_runs: tuple[Any, Any],
) -> None:
    first, second = probe_runs
    assert first.succeeded is True
    assert second.succeeded is True
    assert first.document == second.document
    assert first.stdout_digest == second.stdout_digest
    assert first.process_id > 0
    assert second.process_id > 0
    assert first.terminated is True
    assert second.terminated is True


def test_native_cancel_probe_records_unreachable_rollback_contract(
    probe_runs: tuple[Any, Any],
) -> None:
    probe = probe_runs[0].document
    assert probe is not None
    assert_valid_activation_rollback_probe(probe)
    assert probe["evidence_id"] == (
        "rollbackprobe_"
        "274065e5270b5a216b2f228d743919fa4826e693bb416e236892d79d2cee5833"
    )
    assert probe["status"] == "unsupported"
    assert probe["classification"] == ACTIVATION_ROLLBACK_UNREACHABLE
    assert probe["rollback_supported"] is False
    assert probe["activation"]["kind"] == "ACTIVATE_EFFECT"
    assert probe["activation"]["action_occurrence_id"].startswith("aocc_")
    cancellation = probe["cancellation"]
    assert cancellation["request"]["request_type"] == "select_card"
    assert cancellation["request"]["context"]["extra"]["cancelable"] is True
    assert cancellation["action"]["kind"] == "DECLINE"
    assert cancellation["action"]["selections"] == []
    assert cancellation["response"]["response_hex"] == "ffffffff"
    assert cancellation["state_before"]["chain_count"] == 1
    assert cancellation["state_after"]["chain_count"] == 1
    assert cancellation["state_before"]["state_hash"] == (
        "state_54a27918389c7030e45b6f587d278ce91a7615ffbe2784a257677ed16e501b95"
    )
    assert cancellation["state_after"]["state_hash"] == (
        "state_c39de0e816903d451402757c6c4d722cc55f37214acf626da6e162384437da7f"
    )
    assert probe["followup"]["message_types"] == [71, 16]
    assert probe["followup"]["next_request"]["request_type"] == "select_chain"


def test_native_cancel_probe_manifest_pins_runtime_assets_and_fixture(
    probe_runs: tuple[Any, Any],
) -> None:
    probe = probe_runs[0].document
    assert probe is not None
    manifest = probe["manifest"]
    environment = manifest["environment"]
    assert manifest["reproducible"] is True
    assert manifest["randomness"]["core_seed"] == [1, 2, 3, 4]
    assert environment["core"] == {
        "api": "11.0",
        "binary_sha256": (
            "03e360cf694f5ac6ba686de1d3bec7ccde3f3233d01bfe3265884a18ce1b9028"
        ),
        "custom_patches": [],
        "lock_id": "ocgcore-v11.0-win-x64-msvc-v1",
        "source_commit": "158aebe758be3c46249c75d602e3f16d63d2ef31",
    }
    fixture = environment["fixture_script"]
    assert fixture["id"] == "action_activation_rollback_probe_v1"
    assert fixture["name"] == "c97268402.lua"
    assert fixture["sha256"] == (
        "4f9ebe609e760446b6b48318fad9379787acb70ab136f160b63a1c71bdc09986"
    )
    assert fixture["purpose"] == "native_activation_setup_cancellation_probe"
    assert fixture["card_database_rows"] == [
        {
            "alias": 0,
            "atk": 0,
            "attribute": 16,
            "def": 0,
            "id": 97268402,
            "level": 1,
            "race": 2,
            "setcode": 0,
            "type": 4129,
        }
    ]
    assert environment["assets"]["card_database_commit"] == (
        "f89c9a4be9a5f193e29b788e3cf880563f4f79b4"
    )
    assert environment["assets"]["database_sha256"] == (
        "c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225"
    )


def test_probe_validator_rejects_tampered_native_response(
    probe_runs: tuple[Any, Any],
) -> None:
    probe = probe_runs[0].document
    assert probe is not None
    tampered = deepcopy(probe)
    tampered["cancellation"]["response"]["response_hex"] = "00000000"
    identity = {
        key: value for key, value in tampered.items() if key != "evidence_id"
    }
    tampered["evidence_id"] = stable_digest(identity, prefix="rollbackprobe_")
    with pytest.raises(ValueError, match="response must be ffffffff"):
        assert_valid_activation_rollback_probe(tampered)


def test_probe_validator_rejects_tampered_followup_frame(
    probe_runs: tuple[Any, Any],
) -> None:
    probe = probe_runs[0].document
    assert probe is not None
    tampered = deepcopy(probe)
    tampered["followup"]["frames"][0]["payload_hex"] = "00"
    identity = {
        key: value for key, value in tampered.items() if key != "evidence_id"
    }
    tampered["evidence_id"] = stable_digest(identity, prefix="rollbackprobe_")
    with pytest.raises(ValueError, match="neither known-unreachable nor a candidate"):
        assert_valid_activation_rollback_probe(tampered)


def test_probe_validator_reuses_replay_manifest_validation(
    probe_runs: tuple[Any, Any],
) -> None:
    probe = probe_runs[0].document
    assert probe is not None
    tampered = deepcopy(probe)
    del tampered["manifest"]["environment"]
    identity = {
        key: value for key, value in tampered.items() if key != "evidence_id"
    }
    tampered["evidence_id"] = stable_digest(identity, prefix="rollbackprobe_")
    with pytest.raises(ValueError, match="manifest is missing 'environment'"):
        assert_valid_activation_rollback_probe(tampered)


def test_stored_upstream_audit_matches_fresh_probe(
    probe_runs: tuple[Any, Any],
) -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert_valid_activation_rollback_audit(audit)
    assert audit["evidence_id"] == (
        "rollbackaudit_"
        "2476441a3c8ed5acb8c7107acf7a2e3961f1be81bc9ad01a9cb634db44131c98"
    )
    assert audit["conclusion"] == "remains_unsupported"
    assert audit["probe"] == probe_runs[0].document
    assert audit["fresh_worker_reproducibility"]["documents_identical"] is True
    assert audit["source_audit"]["source_flow_unchanged"] is True
    assert all(
        item["relevant_contract_same"]
        for item in audit["source_audit"]["functions"]
    )
    upstream = audit["upstream"]
    assert upstream["latest_release"] == {
        "api": "11.0",
        "commit": "158aebe758be3c46249c75d602e3f16d63d2ef31",
        "runtime_tested": True,
        "tag": "v11.0",
    }
    assert upstream["head"]["api"] == "11.0"
    assert upstream["head"]["commit"] == (
        "0764db0c75b3d1d574880d365aa3695ab1f13b43"
    )
    assert upstream["head"]["runtime_tested"] is False
    assert upstream["commit_distance_from_release"] == 74


def test_raw_replay_cancel_contract_remains_preserved() -> None:
    compatibility = action_aggregation_compatibility_report()
    limitation = compatibility["limitations"]["activation_cancel"]
    assert limitation["status"] == "unreachable_in_ocgcore_api_11_0"
    assert limitation["native_cancel_response_hex"] == "ffffffff"
    assert limitation["tracking_issue"] == 115
    assert limitation["follow_up_issue"] == 117
    assert limitation["audit_evidence_id"] == (
        "rollbackaudit_"
        "2476441a3c8ed5acb8c7107acf7a2e3961f1be81bc9ad01a9cb634db44131c98"
    )
    evidence = json.loads(EDGE_EVIDENCE.read_text(encoding="utf-8"))
    cancel = evidence["edge_fixtures"]["cancel"]
    assert cancel["group_boundaries"][0]["boundary_kind"] == (
        "cancelled_selection"
    )
    assert cancel["atomic_replay_digest_before"] == (
        cancel["atomic_replay_digest_after"]
    )
