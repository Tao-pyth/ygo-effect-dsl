from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.cli.cmd_analyze import cmd_analyze
from ygo_effect_dsl.cli.cmd_transform import cmd_transform
from ygo_effect_dsl.cli.cmd_validate import cmd_validate
from ygo_effect_dsl.dict_loader import load_dictionary, validate_dictionary
from ygo_effect_dsl.io_input import load_inputs
from ygo_effect_dsl.normalize import normalize_card_texts
from ygo_effect_dsl.pipeline.transform import load_dataset_from_args


def _add_dataset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", help="dataset directory that contains manifest.json and cards.jsonl")
    parser.add_argument("--manifest", help="path to manifest.json")
    parser.add_argument("--jsonl", help="path to cards.jsonl")


def cmd_ingest(args: argparse.Namespace) -> int:
    rc, loaded = load_dataset_from_args(args)
    if rc != 0 or loaded is None:
        return rc

    print(f"ingest: schema_version={loaded.manifest.export_schema_version}")
    print(f"ingest: record_count={loaded.manifest.record_count}")
    print(f"ingest: loaded={len(loaded.cards)}")
    print(f"ingest: fields={','.join(loaded.manifest.fields)}")
    return 0


def cmd_validate_dict(args: argparse.Namespace) -> int:
    errors = validate_dictionary(args.dict_dir)
    if errors:
        print("validate-dict: failed")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("validate-dict: ok")
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    dict_errors = validate_dictionary(args.dict_dir)
    if dict_errors:
        print("validate-dict failed:")
        for err in dict_errors:
            print(f"  - {err}")
        return 2

    dictionary = load_dictionary(args.dict_dir)
    cards = load_inputs(args.in_path, glob_pattern=getattr(args, "glob", None), limit=getattr(args, "limit", None))
    out_rows: list[dict[str, Any]] = []
    from ygo_effect_dsl.io_input import extract_card_fields

    for row in cards:
        fields = extract_card_fields(row)
        norm = normalize_card_texts(fields, dictionary.vocab)
        out_rows.append({"cid": fields.get("cid", ""), "norm": norm.as_dict()})

    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"normalize: wrote={len(out_rows)} to {out_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="ygo-effect-dsl")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p0 = sub.add_parser("ingest", help="validate dataset manifest + read cards.jsonl")
    _add_dataset_arguments(p0)
    p0.set_defaults(func=cmd_ingest)

    p1 = sub.add_parser("transform", help="ETL JSON/JSONL -> v0.0 DSL YAML")
    p1.add_argument("--in", dest="in_path", help="input file or directory")
    p1.add_argument("--glob", help="glob pattern when --in is directory")
    p1.add_argument("--dict", dest="dict_dir", default="resources/dict/v0_0", help="dictionary directory")
    p1.add_argument("--out", dest="out_dir", default="data/export", help="output root directory")
    p1.add_argument("--limit", type=int, help="limit number of cards")
    p1.add_argument("--fail-fast", action="store_true", help="stop at first card failure")
    p1.add_argument("--log-level", default="INFO", choices=["INFO", "DEBUG"], help="log verbosity")
    p1.add_argument("--report", action=argparse.BooleanOptionalAction, default=True, help="write summary and unmatched reports")
    _add_dataset_arguments(p1)
    p1.set_defaults(func=cmd_transform)

    pvd = sub.add_parser("validate-dict", help="validate dictionary files and regex patterns")
    pvd.add_argument("--dict", dest="dict_dir", default="resources/dict/v0_0", help="dictionary directory")
    pvd.set_defaults(func=cmd_validate_dict)

    pn = sub.add_parser("normalize", help="debug: normalize ETL text and dump JSON")
    pn.add_argument("--in", dest="in_path", required=True, help="input file or directory")
    pn.add_argument("--glob", help="glob pattern when --in is directory")
    pn.add_argument("--dict", dest="dict_dir", default="resources/dict/v0_0", help="dictionary directory")
    pn.add_argument("--out", dest="out_path", required=True, help="output JSON path")
    pn.add_argument("--limit", type=int, help="limit number of cards")
    pn.set_defaults(func=cmd_normalize)

    p2 = sub.add_parser("validate", help="validate DSL YAML files for spec v0.0 minimum")
    p2.add_argument("cards_dir", help="directory that contains YAML cards")
    p2.set_defaults(func=cmd_validate)

    p3 = sub.add_parser("analyze", help="analyze DSL YAML cards and output report")
    p3.add_argument("cards_dir", help="directory that contains YAML cards")
    p3.add_argument("--out", dest="out_dir", required=True, help="report output directory")
    p3.set_defaults(func=cmd_analyze)

    args = ap.parse_args()
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
