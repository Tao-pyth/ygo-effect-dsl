from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from ygo_effect_dsl.cli.main import cmd_transform
from ygo_effect_dsl.util.yaml_io import load_yaml
from ygo_effect_dsl.validate.validator import validate_card_yaml


class _Args:
    def __init__(self, in_path: str, out_dir: str):
        self.in_path = in_path
        self.out_dir = out_dir


def test_pipeline_smoke(tmp_path: Path) -> None:
    out_dir = tmp_path / "dsl_out"
    args = _Args(in_path="examples/sample_cards.jsonl", out_dir=str(out_dir))

    rc = cmd_transform(args)
    assert rc == 0

    files = sorted(out_dir.glob("*.yaml"))
    assert files, "transform must generate yaml files"

    for file in files:
        payload = load_yaml(str(file))
        assert "dsl_version" in payload
        assert "card" in payload
        assert "effects" in payload

        errs = validate_card_yaml(payload)
        assert not errs
