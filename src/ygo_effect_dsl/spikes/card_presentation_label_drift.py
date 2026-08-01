from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import (
    load_ocgcore_asset_lock,
    resolve_ocgcore_assets,
)
from ygo_effect_dsl.presentation.cards import (
    ATTRIBUTE_LABELS,
    RACE_LABELS,
    TYPE_LABELS,
)


CARD_PRESENTATION_LABEL_DRIFT_SCHEMA_VERSION = "card-presentation-label-drift-v1"

_CONSTANT_ASSIGNMENT = re.compile(
    r"^(?P<symbol>(?P<prefix>TYPE|RACE|ATTRIBUTE)_[A-Z0-9]+)\s*=\s*(?P<value>\S+)"
)

_TYPE_SYMBOLS_BY_BIT = {
    0x1: "TYPE_MONSTER",
    0x2: "TYPE_SPELL",
    0x4: "TYPE_TRAP",
    0x10: "TYPE_NORMAL",
    0x20: "TYPE_EFFECT",
    0x40: "TYPE_FUSION",
    0x80: "TYPE_RITUAL",
    0x100: "TYPE_TRAPMONSTER",
    0x200: "TYPE_SPIRIT",
    0x400: "TYPE_UNION",
    0x800: "TYPE_GEMINI",
    0x1000: "TYPE_TUNER",
    0x2000: "TYPE_SYNCHRO",
    0x4000: "TYPE_TOKEN",
    0x10000: "TYPE_QUICKPLAY",
    0x20000: "TYPE_CONTINUOUS",
    0x40000: "TYPE_EQUIP",
    0x80000: "TYPE_FIELD",
    0x100000: "TYPE_COUNTER",
    0x200000: "TYPE_FLIP",
    0x400000: "TYPE_TOON",
    0x800000: "TYPE_XYZ",
    0x1000000: "TYPE_PENDULUM",
    0x2000000: "TYPE_SPSUMMON",
    0x4000000: "TYPE_LINK",
}

_RACE_SYMBOLS_BY_BIT = {
    0x1: "RACE_WARRIOR",
    0x2: "RACE_SPELLCASTER",
    0x4: "RACE_FAIRY",
    0x8: "RACE_FIEND",
    0x10: "RACE_ZOMBIE",
    0x20: "RACE_MACHINE",
    0x40: "RACE_AQUA",
    0x80: "RACE_PYRO",
    0x100: "RACE_ROCK",
    0x200: "RACE_WINGEDBEAST",
    0x400: "RACE_PLANT",
    0x800: "RACE_INSECT",
    0x1000: "RACE_THUNDER",
    0x2000: "RACE_DRAGON",
    0x4000: "RACE_BEAST",
    0x8000: "RACE_BEASTWARRIOR",
    0x10000: "RACE_DINOSAUR",
    0x20000: "RACE_FISH",
    0x40000: "RACE_SEASERPENT",
    0x80000: "RACE_REPTILE",
    0x100000: "RACE_PSYCHIC",
    0x200000: "RACE_DIVINE",
    0x400000: "RACE_CREATORGOD",
    0x800000: "RACE_WYRM",
    0x1000000: "RACE_CYBERSE",
    0x2000000: "RACE_ILLUSION",
}

_ATTRIBUTE_SYMBOLS_BY_BIT = {
    0x1: "ATTRIBUTE_EARTH",
    0x2: "ATTRIBUTE_WATER",
    0x4: "ATTRIBUTE_FIRE",
    0x8: "ATTRIBUTE_WIND",
    0x10: "ATTRIBUTE_LIGHT",
    0x20: "ATTRIBUTE_DARK",
    0x40: "ATTRIBUTE_DIVINE",
}

_SUPPORTED_TABLES = {
    "attribute": (_ATTRIBUTE_SYMBOLS_BY_BIT, ATTRIBUTE_LABELS),
    "race": (_RACE_SYMBOLS_BY_BIT, RACE_LABELS),
    "type": (_TYPE_SYMBOLS_BY_BIT, TYPE_LABELS),
}


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_single_bit(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def parse_literal_constants(source: str) -> dict[str, dict[str, int]]:
    constants: dict[str, dict[str, int]] = {
        "attribute": {},
        "race": {},
        "type": {},
    }
    for raw_line in source.splitlines():
        line = raw_line.split("--", 1)[0].strip()
        if not line:
            continue
        match = _CONSTANT_ASSIGNMENT.match(line)
        if match is None:
            continue
        value_text = match.group("value")
        if not re.fullmatch(r"0x[0-9A-Fa-f]+|[0-9]+", value_text):
            continue
        value = int(value_text, 0)
        if not _is_single_bit(value):
            continue
        category = match.group("prefix").lower()
        constants[category][match.group("symbol")] = value
    return constants


def build_label_map_drift_evidence(
    constant_source: Path,
    *,
    source_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    path = constant_source.expanduser().resolve()
    source_text = path.read_text(encoding="utf-8")
    constants = parse_literal_constants(source_text)
    supported_rows: list[dict[str, Any]] = []
    unsupported_rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for category, (symbols_by_bit, labels_by_bit) in sorted(_SUPPORTED_TABLES.items()):
        supported_symbols = set(symbols_by_bit.values())
        upstream_by_symbol = constants[category]
        for bit, symbol in sorted(symbols_by_bit.items()):
            observed = upstream_by_symbol.get(symbol)
            status = "matched" if observed == bit else "missing"
            if observed is not None and observed != bit:
                status = "value_mismatch"
            row = {
                "bit": bit,
                "category": category,
                "label": labels_by_bit[bit],
                "status": status,
                "upstream_symbol": symbol,
                "upstream_value": observed,
            }
            supported_rows.append(row)
            if status != "matched":
                diagnostics.append(
                    {
                        "bit": bit,
                        "category": category,
                        "code": f"{category}_label_constant_{status}",
                        "expected_symbol": symbol,
                        "expected_value": bit,
                        "observed_value": observed,
                        "severity": "error",
                    }
                )
        for symbol, value in sorted(upstream_by_symbol.items(), key=lambda item: item[1]):
            if symbol in supported_symbols:
                continue
            unsupported_rows.append(
                {
                    "bit": value,
                    "category": category,
                    "status": "unsupported_presentation_label",
                    "upstream_symbol": symbol,
                }
            )

    identity = to_canonical_data(
        {
            "constant_source": {
                "filename": path.name,
                "sha256": _sha256(path),
                "size": path.stat().st_size,
            },
            "diagnostics": diagnostics,
            "passed": not diagnostics,
            "schema_version": CARD_PRESENTATION_LABEL_DRIFT_SCHEMA_VERSION,
            "source": dict(source_identity or {}),
            "supported_label_bits": supported_rows,
            "unsupported_upstream_bits": unsupported_rows,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="cardpresentationlabeldrift_"),
    }


def build_pinned_label_map_drift_evidence(
    *,
    external_root: str | Path | None = None,
) -> dict[str, Any]:
    lock = load_ocgcore_asset_lock()
    assets = resolve_ocgcore_assets(external_root=external_root)
    scripts = lock.repositories["card_scripts"]
    constant_path = assets.scripts_root / "constant.lua"
    required = scripts["required_files"]["constant.lua"]
    observed_hash = _sha256(constant_path)
    if observed_hash != required["sha256"]:
        raise ValueError("pinned CardScripts constant.lua SHA-256 does not match lock")
    return build_label_map_drift_evidence(
        constant_path,
        source_identity={
            "asset_lock_id": lock.lock_id,
            "license_status": scripts["license"],
            "repository": scripts["repository"],
            "source_commit": scripts["commit"],
            "source_tree": scripts["tree"],
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="compare card presentation label maps with pinned CardScripts constants"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--constant-source", type=Path)
    parser.add_argument("--external-root", type=Path)
    args = parser.parse_args()

    if args.constant_source is not None:
        evidence = build_label_map_drift_evidence(args.constant_source)
    else:
        evidence = build_pinned_label_map_drift_evidence(
            external_root=args.external_root,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    status = "passed" if evidence["passed"] else "failed"
    print(f"card-presentation-label-drift: {status} out={args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
