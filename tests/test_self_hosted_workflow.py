from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def test_real_core_workflow_is_manual_self_hosted_and_sanitized() -> None:
    path = ROOT / ".github/workflows/real-core-self-hosted-smoke.yml"
    raw = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    trigger = workflow.get("on", workflow.get(True))

    assert set(trigger) == {"workflow_dispatch"}
    job = workflow["jobs"]["smoke"]
    assert job["runs-on"] == ["self-hosted", "Windows", "X64", "ygo-real-core"]
    assert "ocgcore-doctor" in raw
    assert "ocgcore-verify" in raw
    assert "ocgcore-assets-verify" in raw
    assert "experiment-search" in raw
    assert "experiment-replay" in raw
    assert "summary.json" in raw
    published = raw.split("Publish sanitized smoke summary", 1)[1]
    assert "best.route.yaml" not in published
    assert "lua.json" not in published
    assert "search.json" not in published
