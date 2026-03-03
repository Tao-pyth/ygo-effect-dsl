from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.cli.main import cmd_ingest, cmd_transform, cmd_validate
from ygo_effect_dsl.util.yaml_io import load_yaml


class _IngestArgs:
    def __init__(self, dataset: str):
        self.dataset = dataset
        self.manifest = None
        self.jsonl = None


class _TransformArgs:
    def __init__(self, dataset: str, out_dir: str):
        self.in_path = None
        self.glob = None
        self.dict_dir = "resources/dict/v0_0"
        self.dataset = dataset
        self.manifest = None
        self.jsonl = None
        self.out_dir = out_dir
        self.limit = None
        self.fail_fast = False
        self.log_level = "INFO"
        self.report = True


class _ValidateArgs:
    def __init__(self, cards_dir: str):
        self.cards_dir = cards_dir


def test_pipeline_smoke(tmp_path: Path) -> None:
    dataset_dir = "examples/sample_dataset"
    out_dir = tmp_path / "dsl_out"

    ingest_rc = cmd_ingest(_IngestArgs(dataset=dataset_dir))
    assert ingest_rc == 0

    transform_rc = cmd_transform(_TransformArgs(dataset=dataset_dir, out_dir=str(out_dir)))
    assert transform_rc == 0

    validate_rc = cmd_validate(_ValidateArgs(cards_dir=str(out_dir / "yaml")))
    assert validate_rc == 0

    files = sorted((out_dir / "yaml").glob("*.yaml"))
    assert len(files) == 3

    for file in files:
        payload = load_yaml(str(file))

        assert payload.get("dsl_version") == "0.0"
        assert "card" in payload
        assert "effects" in payload

        card = payload["card"]
        assert "cid" in card
        assert "name" in card
        assert "en" in card["name"]
        assert "ja" in card["name"]
        assert "props" in card

        effects = payload["effects"]
        assert isinstance(effects, list)
        for effect in effects:
            for key in ["trigger", "restriction", "condition", "cost", "action"]:
                assert key in effect
