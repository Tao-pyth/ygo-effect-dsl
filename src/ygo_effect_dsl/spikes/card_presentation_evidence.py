from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import (
    load_ocgcore_asset_lock,
    resolve_ocgcore_assets,
)
from ygo_effect_dsl.presentation import (
    CARD_PRESENTATION_PROVIDER_VERSION,
    CardPresentationQuery,
    CardPresentationSource,
    LocalizedCardPresentationProvider,
)


CARD_PRESENTATION_EVIDENCE_SCHEMA_VERSION = "card-presentation-evidence-v1"


def pinned_card_presentation_source(
    *,
    locale: str,
    external_root: str | Path | None = None,
) -> CardPresentationSource:
    lock = load_ocgcore_asset_lock()
    assets = resolve_ocgcore_assets(external_root=external_root)
    database = lock.repositories["card_database"]
    required_file = database["required_files"].get(assets.database_path.name)
    if not isinstance(required_file, dict):
        raise ValueError(
            "resolved presentation database is not pinned by the asset lock"
        )
    return CardPresentationSource(
        locale=locale,
        database_path=assets.database_path,
        database_sha256=str(required_file["sha256"]),
        asset_lock_id=lock.lock_id,
        source_commit=str(database["commit"]),
        source_tree=str(database["tree"]),
        license_status=str(database["license"]),
        repository=str(database["repository"]),
    )


def build_card_presentation_evidence(
    source: CardPresentationSource,
    card_codes: Iterable[int],
) -> dict[str, Any]:
    codes = tuple(card_codes)
    if not codes or len(set(codes)) != len(codes):
        raise ValueError("card_codes must be non-empty and unique")
    card_summaries: list[dict[str, Any]] = []
    with LocalizedCardPresentationProvider((source,)) as provider:
        for code in codes:
            presentation = provider.get_card(
                CardPresentationQuery(
                    card_code=code,
                    requested_locale=source.locale,
                    fallback_locales=(),
                    expected_asset_lock_id=source.asset_lock_id,
                )
            )
            metadata = presentation.metadata
            card_summaries.append(
                {
                    "auxiliary_region_count": len(presentation.auxiliary_texts),
                    "availability": presentation.availability,
                    "card_code": code,
                    "effect_text_chars": len(presentation.effect_text or ""),
                    "effect_text_present": presentation.effect_text is not None,
                    "locale_status": presentation.locale_status,
                    "metadata_fields_present": sorted(
                        key
                        for key, value in (
                            metadata.to_dict() if metadata else {}
                        ).items()
                        if key != "schema_version" and value is not None
                    ),
                    "name_chars": len(presentation.name or ""),
                    "name_present": presentation.name is not None,
                    "presentation_id": presentation.presentation_id,
                    "resolved_locale": presentation.resolved_locale,
                }
            )
    identity = to_canonical_data(
        {
            "authority": {
                "effect_interpretation": "forbidden",
                "legality_or_timing": "ocgcore_only",
                "search_input": False,
            },
            "cards": card_summaries,
            "provider_version": CARD_PRESENTATION_PROVIDER_VERSION,
            "schema_version": CARD_PRESENTATION_EVIDENCE_SCHEMA_VERSION,
            "source": source.to_dict(),
            "text_payload_embedded": False,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="cardpresentationevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="qualify display-only card presentation against pinned BabelCDB"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--locale", default="en")
    parser.add_argument("--external-root", type=Path)
    parser.add_argument("--card-code", type=int, action="append", required=True)
    args = parser.parse_args()
    source = pinned_card_presentation_source(
        locale=args.locale,
        external_root=args.external_root,
    )
    evidence = build_card_presentation_evidence(source, args.card_code)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"card-presentation-evidence: wrote {args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
