from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).parents[1]
WALKTHROUGH = ROOT / "docs" / "ocgcore" / "50_operator_walkthrough.md"


def test_operator_walkthrough_commands_match_the_current_cli() -> None:
    document = WALKTHROUGH.read_text(encoding="utf-8")
    commands = {
        command
        for command in re.findall(
            r"python -m ygo_effect_dsl ([a-z0-9-]+)",
            document,
        )
        if not command.startswith("-")
    }

    assert commands >= {
        "experiment-inspect",
        "experiment-replay",
        "experiment-search",
        "ocgcore-assets-bootstrap",
        "ocgcore-assets-verify",
        "ocgcore-bootstrap",
        "ocgcore-doctor",
        "ocgcore-lua-qualify",
        "ocgcore-verify",
        "real-deck-qualify",
        "validate-experiment",
    }
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    for command in sorted(commands):
        completed = subprocess.run(
            [sys.executable, "-m", "ygo_effect_dsl", command, "--help"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, command + "\n" + completed.stderr


def test_operator_walkthrough_preserves_fail_closed_and_owned_cache_boundaries() -> None:
    document = WALKTHROUGH.read_text(encoding="utf-8")

    assert (ROOT / "examples" / "experiments" / "general_search_inline.yaml").is_file()
    assert all(marker in document for marker in ("#main", "#extra", "!side"))
    assert "scenario-preflight-v1" in document
    assert "fresh-replay-verification-v1" in document
    assert "configuration_failure" in document
    assert "missing_card_database_row" in document
    assert "missing_card_script" in document
    assert "120 script" in document
    assert "別root" in document
    assert "Remove-Item" not in document
    assert "git clean" not in document
    assert "git reset" not in document
