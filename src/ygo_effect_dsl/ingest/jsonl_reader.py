from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

SUPPORTED_EXPORT_SCHEMA_VERSIONS = {"0.0"}


@dataclass(frozen=True)
class DatasetManifest:
    export_schema_version: str
    record_count: int
    fields: list[str]
    languages: list[str]
    has_images: bool
    exported_at: str


@dataclass(frozen=True)
class DatasetPaths:
    manifest_path: Path
    jsonl_path: Path


@dataclass(frozen=True)
class LoadedDataset:
    manifest: DatasetManifest
    cards: list[dict[str, Any]]


def resolve_dataset_paths(dataset: str | None, manifest: str | None, jsonl: str | None) -> DatasetPaths:
    if dataset:
        dataset_dir = Path(dataset)
        return DatasetPaths(manifest_path=dataset_dir / "manifest.json", jsonl_path=dataset_dir / "cards.jsonl")

    if manifest and jsonl:
        return DatasetPaths(manifest_path=Path(manifest), jsonl_path=Path(jsonl))

    raise ValueError("Specify either --dataset <dir> or both --manifest <path> and --jsonl <path>.")


def _load_manifest(path: Path) -> DatasetManifest:
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be object")

    schema_version = payload.get("export_schema_version")
    record_count = payload.get("record_count")
    fields = payload.get("fields")

    if not isinstance(schema_version, str):
        raise ValueError("manifest.export_schema_version must be string")
    if schema_version not in SUPPORTED_EXPORT_SCHEMA_VERSIONS:
        raise ValueError(
            f"unsupported export_schema_version={schema_version}; supported={sorted(SUPPORTED_EXPORT_SCHEMA_VERSIONS)}"
        )
    if not isinstance(record_count, int) or record_count < 0:
        raise ValueError("manifest.record_count must be non-negative int")
    if not isinstance(fields, list) or not all(isinstance(k, str) for k in fields):
        raise ValueError("manifest.fields must be list[str]")

    languages = payload.get("languages")
    if not isinstance(languages, list) or not all(isinstance(k, str) for k in languages):
        languages = []

    has_images = bool(payload.get("has_images", False))
    exported_at = payload.get("exported_at")
    if not isinstance(exported_at, str):
        exported_at = ""

    return DatasetManifest(
        export_schema_version=schema_version,
        record_count=record_count,
        fields=fields,
        languages=languages,
        has_images=has_images,
        exported_at=exported_at,
    )


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"cards jsonl not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                payload = json.loads(s)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in cards.jsonl line={lineno}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"cards.jsonl line={lineno} must be object")
            yield payload


def load_dataset(paths: DatasetPaths) -> LoadedDataset:
    manifest = _load_manifest(paths.manifest_path)

    cards: list[dict[str, Any]] = []
    for line_no, card in enumerate(iter_jsonl(paths.jsonl_path), start=1):
        missing = [key for key in manifest.fields if key not in card]
        if missing:
            raise ValueError(f"missing keys in cards.jsonl line={line_no}: {missing}")
        cards.append(card)

    if manifest.record_count != len(cards):
        raise ValueError(
            "manifest.record_count mismatch: "
            f"manifest={manifest.record_count}, cards.jsonl_lines={len(cards)}"
        )

    return LoadedDataset(manifest=manifest, cards=cards)
