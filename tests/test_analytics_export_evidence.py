from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.analytics_export_evidence import (
    ANALYTICS_EXPORT_EVIDENCE_VERSION,
)
from ygo_effect_dsl.storage import AnalyticsExportFormat, decode_export_dataset
from ygo_effect_dsl.version import __version__

EVIDENCE_ROOT = Path(__file__).resolve().parents[1] / "docs" / "storage" / "evidence"


def test_committed_export_evidence_is_content_addressed_and_decodable() -> None:
    evidence = json.loads(
        (EVIDENCE_ROOT / "analytics_export.json").read_text(encoding="utf-8")
    )
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == ANALYTICS_EXPORT_EVIDENCE_VERSION
    assert evidence["package_version"] == __version__
    assert evidence["evidence_id"] == stable_digest(
        identity, prefix="analyticsexportevidence_"
    )
    assert evidence["surfaces"] == [
        "service",
        "cli_subprocess",
        "desktop_bridge_worker",
    ]
    assert evidence["safety"] == {
        "csv_formula_leading_character_exposed": False,
        "desktop_renderer_authors_bytes": False,
        "desktop_renderer_path_input": False,
    }
    semantic_digests = set()
    for name, record in evidence["formats"].items():
        data_path = EVIDENCE_ROOT / "analytics_export_v1" / record["data"]["filename"]
        manifest_path = (
            EVIDENCE_ROOT / "analytics_export_v1" / record["manifest"]["filename"]
        )
        data = data_path.read_bytes()
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        assert record["surface_byte_parity"] is True
        assert record["data"]["bytes"] == len(data)
        assert record["data"]["sha256"] == hashlib.sha256(data).hexdigest()
        assert record["manifest"]["bytes"] == len(manifest_bytes)
        assert record["manifest"]["sha256"] == hashlib.sha256(
            manifest_bytes
        ).hexdigest()
        assert decode_export_dataset(AnalyticsExportFormat(name), data, manifest)
        semantic_digests.add(record["semantic_digest"])
    assert len(semantic_digests) == 1
