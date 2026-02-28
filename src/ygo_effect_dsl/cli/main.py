from __future__ import annotations
import argparse
import json
import os
from typing import Any

from ygo_effect_dsl.ingest.jsonl_reader import iter_jsonl
from ygo_effect_dsl.transform.etl_to_dsl import to_dsl_yaml_dict
from ygo_effect_dsl.transform.dsl_writer import write_card_yaml
from ygo_effect_dsl.util.yaml_io import load_yaml
from ygo_effect_dsl.dsl.normalize import normalize_card_dsl
from ygo_effect_dsl.analyze.report import build_report
from ygo_effect_dsl.ir.compiler import compile_card_yaml_to_ir

def _dump_json(obj: Any, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def cmd_transform(args: argparse.Namespace) -> int:
    count = 0
    for card in iter_jsonl(args.in_path):
        dsl = to_dsl_yaml_dict(card, mode=args.mode)
        write_card_yaml(dsl, args.out_dir)
        count += 1
    print(f"transform: wrote {count} cards into {args.out_dir}")
    return 0

def _load_cards_from_dir(cards_dir: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for name in os.listdir(cards_dir):
        if not (name.endswith(".yml") or name.endswith(".yaml")):
            continue
        p = os.path.join(cards_dir, name)
        d = load_yaml(p)
        d = normalize_card_dsl(d)
        cards.append(d)
    return cards

def cmd_analyze(args: argparse.Namespace) -> int:
    cards = _load_cards_from_dir(args.cards_dir)
    report = build_report(cards)
    _dump_json(report, args.out)
    print(f"analyze: wrote report to {args.out}")
    return 0

def cmd_compile_ir(args: argparse.Namespace) -> int:
    cards = _load_cards_from_dir(args.cards_dir)
    os.makedirs(args.out_dir, exist_ok=True)
    n = 0
    for c in cards:
        ir = compile_card_yaml_to_ir(c)
        out_path = os.path.join(args.out_dir, f"{c.get('cid', 0)}.ir.json")
        _dump_json(ir.__dict__ | {"effects":[e.__dict__ for e in ir.effects]}, out_path)
        n += 1
    print(f"compile-ir: wrote {n} IR files into {args.out_dir}")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(prog="ygo-effect-dsl")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("transform", help="JSONL(ETL) -> DSL YAML(cards/*.yml)")
    p1.add_argument("--in", dest="in_path", required=True, help="input JSONL path")
    p1.add_argument("--out-dir", required=True, help="output directory for YAML cards")
    p1.add_argument("--mode", default="skeleton", choices=["skeleton"], help="transform mode")
    p1.set_defaults(func=cmd_transform)

    p2 = sub.add_parser("analyze", help="Analyze DSL YAML cards -> report.json")
    p2.add_argument("--cards-dir", required=True, help="directory that contains YAML cards")
    p2.add_argument("--out", required=True, help="output report json path")
    p2.set_defaults(func=cmd_analyze)

    p3 = sub.add_parser("compile-ir", help="Compile DSL YAML cards -> IR json files")
    p3.add_argument("--cards-dir", required=True, help="directory that contains YAML cards")
    p3.add_argument("--out-dir", required=True, help="output directory for IR files")
    p3.set_defaults(func=cmd_compile_ir)

    args = ap.parse_args()
    return int(args.func(args))

if __name__ == "__main__":
    raise SystemExit(main())
