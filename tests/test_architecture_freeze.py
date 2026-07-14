from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.engine.bridge.ocgcore import PROTOCOL_VERSION
from ygo_effect_dsl.engine.evaluation import (
    EVALUATION_RESULT_SCHEMA_VERSION,
    SCORE_BREAKDOWN_SCHEMA_VERSION,
)
from ygo_effect_dsl.engine.state import STATE_ID_SCHEMA_VERSION
from ygo_effect_dsl.experiment import LEGACY_EXPERIMENT_SCHEMA_VERSION
from ygo_effect_dsl.route_dsl import ROUTE_DSL_SCHEMA_VERSION


ROOT = Path(__file__).parents[1]


def test_architecture_freeze_manifest_matches_runtime_contract_versions() -> None:
    evidence = json.loads(
        (
            ROOT
            / "docs"
            / "adr"
            / "evidence"
            / "0007_pre_search_contracts.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["schema_version"] == "architecture-freeze-v1"
    assert evidence["contracts"] == {
        "bridge_protocol": PROTOCOL_VERSION,
        "evaluation_result": EVALUATION_RESULT_SCHEMA_VERSION,
        "experiment": LEGACY_EXPERIMENT_SCHEMA_VERSION,
        "replay": "0.3a",
        "route_dsl": ROUTE_DSL_SCHEMA_VERSION,
        "score_breakdown": SCORE_BREAKDOWN_SCHEMA_VERSION,
        "state_identity": STATE_ID_SCHEMA_VERSION,
    }
    assert evidence["post_freeze_extensions"] == {
        "experiment_current": "0.3b",
        "experiment_legacy_migration_source": LEGACY_EXPERIMENT_SCHEMA_VERSION,
        "information_policy": "information-policy-v1",
    }
    assert evidence["non_blocking_verification_issues"] == [91, 92, 93, 94, 95, 96]


def test_frozen_specifications_declare_adr_0007_status() -> None:
    evidence = json.loads(
        (
            ROOT
            / "docs"
            / "adr"
            / "evidence"
            / "0007_pre_search_contracts.json"
        ).read_text(encoding="utf-8")
    )

    for relative_path in evidence["frozen_specifications"]:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "Status: Frozen pre-search contract (ADR-0007)" in text
