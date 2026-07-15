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
    assert raw.index("Initialize sanitized smoke summary") < raw.index(
        "Check out exact commit"
    )
    assert "shell: pwsh" not in raw
    assert "actions/checkout@" not in raw
    assert "fetch --no-tags --depth=1 origin $env:GITHUB_SHA" in raw
    assert "if ($actual -ne $env:GITHUB_SHA)" in raw
    assert "actions/setup-python@v6" in raw
    assert "actions/upload-artifact@v7" in raw
    published = raw.split("Publish sanitized smoke summary", 1)[1]
    assert "best.route.yaml" not in published
    assert "lua.json" not in published
    assert "search.json" not in published


def test_all_actions_use_node24_compatible_majors() -> None:
    workflows = ROOT / ".github/workflows"
    for path in workflows.glob("*.yml"):
        raw = path.read_text(encoding="utf-8")
        assert "actions/checkout@v4" not in raw, path
        assert "actions/setup-python@v5" not in raw, path
        assert "actions/upload-artifact@v4" not in raw, path
