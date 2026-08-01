from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.card_presentation_label_drift import (
    CARD_PRESENTATION_LABEL_DRIFT_SCHEMA_VERSION,
    _SUPPORTED_TABLES,
    build_label_map_drift_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _constant_source() -> str:
    lines: list[str] = []
    for _category, (symbols_by_bit, _labels_by_bit) in sorted(_SUPPORTED_TABLES.items()):
        for bit, symbol in sorted(symbols_by_bit.items()):
            lines.append(f"{symbol} = 0x{bit:x}")
    lines.extend(
        [
            "TYPE_SKILL = 0x8000000",
            "TYPE_EXTRA = TYPE_FUSION|TYPE_SYNCHRO|TYPE_XYZ|TYPE_LINK",
            "RACE_CYBORG = 0x4000000",
            "RACE_ALL = 0x3ffffff",
            "ATTRIBUTE_ALL = ATTRIBUTE_EARTH|ATTRIBUTE_WATER",
        ]
    )
    return "\n".join(lines) + "\n"


def test_label_map_drift_evidence_matches_supported_upstream_bits(
    tmp_path: Path,
) -> None:
    source = tmp_path / "constant.lua"
    source.write_text(_constant_source(), encoding="utf-8")

    evidence = build_label_map_drift_evidence(source)

    assert evidence["schema_version"] == CARD_PRESENTATION_LABEL_DRIFT_SCHEMA_VERSION
    assert evidence["passed"] is True
    assert evidence["diagnostics"] == []
    assert all(row["status"] == "matched" for row in evidence["supported_label_bits"])
    unsupported = {
        (row["category"], row["upstream_symbol"])
        for row in evidence["unsupported_upstream_bits"]
    }
    assert ("type", "TYPE_SKILL") in unsupported
    assert ("race", "RACE_CYBORG") in unsupported
    assert ("race", "RACE_ALL") not in unsupported
    assert ("attribute", "ATTRIBUTE_ALL") not in unsupported


def test_label_map_drift_evidence_reports_supported_bit_mismatch(
    tmp_path: Path,
) -> None:
    source = tmp_path / "constant.lua"
    source.write_text(
        _constant_source().replace("TYPE_MONSTER = 0x1", "TYPE_MONSTER = 0x8"),
        encoding="utf-8",
    )

    evidence = build_label_map_drift_evidence(source)

    assert evidence["passed"] is False
    assert {
        "bit": 1,
        "category": "type",
        "code": "type_label_constant_value_mismatch",
        "expected_symbol": "TYPE_MONSTER",
        "expected_value": 1,
        "observed_value": 8,
        "severity": "error",
    } in evidence["diagnostics"]


def test_committed_v1_label_drift_evidence_is_content_addressed() -> None:
    path = REPO_ROOT / "docs" / "release" / "evidence" / (
        "v1_0_0_card_presentation_label_drift.json"
    )
    evidence = json.loads(path.read_text(encoding="utf-8"))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="cardpresentationlabeldrift_",
    )
    assert evidence["schema_version"] == CARD_PRESENTATION_LABEL_DRIFT_SCHEMA_VERSION
    assert evidence["passed"] is True
    assert evidence["constant_source"] == {
        "filename": "constant.lua",
        "sha256": "9fbd72bcd67fc9b2f987598d876e6cbc335bf48c7d968a68d1de7b91221af9e4",
        "size": 40032,
    }
    assert all(row["status"] == "matched" for row in evidence["supported_label_bits"])
    assert any(
        row["status"] == "unsupported_presentation_label"
        for row in evidence["unsupported_upstream_bits"]
    )
