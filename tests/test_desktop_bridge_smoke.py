from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ygo_effect_dsl.desktop import desktop_frontend_entrypoint
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.desktop_bridge_smoke import DESKTOP_BRIDGE_SMOKE_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO_ROOT / "docs" / "ui" / "evidence" / "desktop_bridge_smoke.json"


def test_committed_pywebview_bridge_smoke_is_content_addressed() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == DESKTOP_BRIDGE_SMOKE_VERSION
    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="desktopbridgesmoke_",
    )
    assert evidence["pywebview_version"] == "6.2.1"
    assert evidence["response"]["ok"] is True
    assert evidence["analytics_response"]["ok"] is True
    assert evidence["analytics_response"]["result"]["schema_version"] == (
        "analytics-query-response-v1"
    )
    assert evidence["analytics_response"]["result"]["rows"] == []
    assert evidence["response"]["method"] == "system.describe"
    assert evidence["response"]["result"]["schema_version"] == (
        "desktop-application-service-v1"
    )
    entrypoint = desktop_frontend_entrypoint()
    assert evidence["frontend"] == {
        "entrypoint": "index.html",
        "sha256": hashlib.sha256(
            entrypoint.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest(),
        "workflow_version": "desktop-workflow-v1",
    }
