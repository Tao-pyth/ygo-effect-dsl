from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.cli.main import cmd_ingest, cmd_transform, cmd_validate
from ygo_effect_dsl.util.yaml_io import load_yaml


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "examples" / "synthetic_test_cards"


class _IngestArgs:
    def __init__(self) -> None:
        self.dataset = str(DATASET)
        self.manifest = None
        self.jsonl = None


class _TransformArgs:
    def __init__(self, out_dir: str) -> None:
        self.in_path = None
        self.glob = None
        self.dict_dir = str(ROOT / "resources" / "dict" / "v0_0")
        self.dataset = str(DATASET)
        self.manifest = None
        self.jsonl = None
        self.out_dir = out_dir
        self.limit = None
        self.fail_fast = False
        self.log_level = "INFO"
        self.report = True


class _ValidateArgs:
    def __init__(self, cards_dir: str) -> None:
        self.cards_dir = cards_dir


def test_distributable_synthetic_fixture_pipeline(tmp_path: Path) -> None:
    """Synthetic cards verify packaging and parser coverage, not benchmark quality."""
    out_dir = tmp_path / "synthetic_dsl"

    assert cmd_ingest(_IngestArgs()) == 0
    assert cmd_transform(_TransformArgs(str(out_dir))) == 0
    assert cmd_validate(_ValidateArgs(str(out_dir / "yaml"))) == 0

    files = sorted((out_dir / "yaml").glob("*.yaml"))
    assert len(files) == 10

    action_types = set()
    target_count = 0
    for file in files:
        payload = load_yaml(str(file))
        assert payload["card"]["cid"] >= 10001
        effect = payload["effects"][0]
        action_types.update(
            action.get("type")
            for action in effect.get("actions", [])
            if isinstance(action, dict)
        )
        target_count += len(effect.get("targets", []))

    assert {
        "add_to_hand",
        "banish",
        "destroy",
        "discard",
        "draw",
        "return_to_extra",
        "send_to_gy",
        "special_summon",
    }.issubset(action_types)
    assert target_count >= 2
