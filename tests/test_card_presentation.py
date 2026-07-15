from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from ygo_effect_dsl.engine.bridge.ocgcore import SQLiteCardDataProvider
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.presentation import (
    CARD_PRESENTATION_CONTRACT_VERSION,
    CARD_PRESENTATION_PROVIDER_VERSION,
    CardPresentationQuery,
    CardPresentationSource,
    CardPresentationSourceError,
    LocalizedCardPresentationProvider,
    card_presentation_contract_document,
)
from ygo_effect_dsl.spikes.card_presentation_evidence import (
    CARD_PRESENTATION_EVIDENCE_SCHEMA_VERSION,
    build_card_presentation_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _database(
    path: Path,
    *,
    name: str | None = "検証カード",
    text: str | None = "First line\nSecond line: 効果",
    include_text_schema: bool = True,
    type_bits: int = 0x1 | 0x20 | 0x1000000,
    defense: int = 1200,
) -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE datas (id INTEGER PRIMARY KEY, ot INTEGER, alias INTEGER, "
            "setcode INTEGER, type INTEGER, atk INTEGER, def INTEGER, level INTEGER, "
            "race INTEGER, attribute INTEGER, category INTEGER)"
        )
        if include_text_schema:
            columns = ", ".join(f"str{i} TEXT" for i in range(1, 17))
            connection.execute(
                "CREATE TABLE texts (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, "
                f"{columns})"
            )
        packed_level = 4 | (2 << 16) | (8 << 24)
        connection.execute(
            "INSERT INTO datas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                10000,
                1,
                9999,
                0x1234 | (0x5678 << 16),
                type_bits,
                1800,
                defense,
                packed_level,
                0x2000,
                0x10,
                0,
            ),
        )
        if include_text_schema and text is not None:
            values = [10000, name, text, "Option A", *("" for _ in range(15))]
            placeholders = ", ".join("?" for _ in values)
            connection.execute(f"INSERT INTO texts VALUES ({placeholders})", values)
    return path


def _source(path: Path, *, locale: str = "en") -> CardPresentationSource:
    return CardPresentationSource(
        locale=locale,
        database_path=path,
        database_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        asset_lock_id="ocgcore-assets-test-v1",
        source_commit="a" * 40,
        source_tree="b" * 40,
        license_status="NOASSERTION",
        repository="https://example.invalid/cards.git",
    )


def test_available_presentation_preserves_text_and_decodes_metadata(
    tmp_path: Path,
) -> None:
    source = _source(_database(tmp_path / "cards.cdb"))

    with LocalizedCardPresentationProvider((source,)) as provider:
        card = provider.get_card(
            CardPresentationQuery(
                card_code=10000,
                requested_locale="en",
                fallback_locales=(),
            )
        )

    assert card.availability == "available"
    assert card.locale_status == "exact"
    assert card.name == "検証カード"
    assert card.effect_text == "First line\nSecond line: 効果"
    assert [item.to_dict() for item in card.auxiliary_texts] == [
        {
            "key": "string_1",
            "schema_version": "card-text-region-v1",
            "text": "Option A",
        }
    ]
    assert card.metadata is not None
    assert card.metadata.level == 4
    assert card.metadata.rank is None
    assert card.metadata.left_scale == 8
    assert card.metadata.right_scale == 2
    assert card.metadata.setcodes == (0x1234, 0x5678)
    assert "Monster" in card.metadata.type_labels
    assert "Pendulum" in card.metadata.type_labels
    assert card.metadata.race_labels == ("Dragon",)
    assert card.metadata.attribute_labels == ("Light",)
    assert card.source == source
    assert card.to_dict()["presentation_id"] == card.presentation_id


def test_link_and_xyz_fields_do_not_masquerade_as_level_or_defense(
    tmp_path: Path,
) -> None:
    link_source = _source(
        _database(
            tmp_path / "link.cdb",
            type_bits=0x1 | 0x20 | 0x4000000,
            defense=0x45,
        )
    )
    xyz_source = _source(
        _database(
            tmp_path / "xyz.cdb",
            type_bits=0x1 | 0x20 | 0x800000,
        ),
        locale="ja",
    )

    with LocalizedCardPresentationProvider((link_source,)) as provider:
        link = provider.get_card(
            CardPresentationQuery(10000, "en", fallback_locales=())
        )
    with LocalizedCardPresentationProvider((xyz_source,)) as provider:
        xyz = provider.get_card(
            CardPresentationQuery(10000, "ja", fallback_locales=())
        )

    assert link.metadata is not None
    assert link.metadata.level is None
    assert link.metadata.defense is None
    assert link.metadata.link_rating == 4
    assert link.metadata.link_markers == 0x45
    assert xyz.metadata is not None
    assert xyz.metadata.level is None
    assert xyz.metadata.rank == 4


def test_spell_does_not_expose_monster_stats_or_pendulum_scales(
    tmp_path: Path,
) -> None:
    source = _source(
        _database(
            tmp_path / "spell.cdb",
            type_bits=0x2 | 0x10000,
        )
    )

    with LocalizedCardPresentationProvider((source,)) as provider:
        card = provider.get_card(
            CardPresentationQuery(10000, "en", fallback_locales=())
        )

    assert card.metadata is not None
    assert card.metadata.attack is None
    assert card.metadata.defense is None
    assert card.metadata.level is None
    assert card.metadata.rank is None
    assert card.metadata.link_rating is None
    assert card.metadata.left_scale is None
    assert card.metadata.right_scale is None


def test_explicit_locale_fallback_is_visible(tmp_path: Path) -> None:
    source = _source(_database(tmp_path / "cards.cdb"), locale="en")

    with LocalizedCardPresentationProvider((source,)) as provider:
        card = provider.get_card(
            CardPresentationQuery(10000, "ja", fallback_locales=("en",))
        )

    assert card.availability == "available"
    assert card.requested_locale == "ja"
    assert card.resolved_locale == "en"
    assert card.locale_status == "fallback"
    assert [item.code for item in card.diagnostics] == ["locale_fallback"]


def test_missing_text_and_unknown_card_return_structured_diagnostics(
    tmp_path: Path,
) -> None:
    source = _source(_database(tmp_path / "cards.cdb", text=None))

    with LocalizedCardPresentationProvider((source,)) as provider:
        missing_text = provider.get_card(
            CardPresentationQuery(10000, "en", fallback_locales=())
        )
        missing_card = provider.get_card(
            CardPresentationQuery(99999, "en", fallback_locales=())
        )

    assert missing_text.availability == "missing_text"
    assert missing_text.metadata is not None
    assert missing_text.name is None
    assert [item.code for item in missing_text.diagnostics] == ["card_text_missing"]
    assert missing_card.availability == "missing_card"
    assert missing_card.card_code == 99999
    assert missing_card.metadata is None
    assert [item.code for item in missing_card.diagnostics] == ["card_data_missing"]


def test_effect_body_without_name_is_not_reported_as_available(
    tmp_path: Path,
) -> None:
    source = _source(_database(tmp_path / "cards.cdb", name=None))

    with LocalizedCardPresentationProvider((source,)) as provider:
        card = provider.get_card(
            CardPresentationQuery(10000, "en", fallback_locales=())
        )

    assert card.availability == "missing_text"
    assert card.metadata is not None
    assert card.effect_text is None


def test_redaction_and_version_mismatches_fail_without_source_data(
    tmp_path: Path,
) -> None:
    source = _source(_database(tmp_path / "cards.cdb"))

    with LocalizedCardPresentationProvider((source,)) as provider:
        redacted = provider.get_card(
            CardPresentationQuery(None, "en", fallback_locales=(), redacted=True)
        )
        stale = provider.get_card(
            CardPresentationQuery(
                10000,
                "en",
                fallback_locales=(),
                expected_asset_lock_id="different-lock-v1",
            )
        )
        mismatch = provider.get_card(
            CardPresentationQuery(
                10000,
                "en",
                fallback_locales=(),
                expected_provider_version="future-provider-v2",
            )
        )

    assert redacted.availability == "redacted"
    assert redacted.card_code is None
    assert redacted.source is None
    assert stale.availability == "stale_source"
    assert stale.source is None
    assert mismatch.availability == "version_mismatch"
    assert mismatch.source is None


def test_source_hash_and_schema_are_verified_before_queries(tmp_path: Path) -> None:
    path = _database(tmp_path / "cards.cdb")
    mismatched = CardPresentationSource(
        locale="en",
        database_path=path,
        database_sha256="0" * 64,
        asset_lock_id="ocgcore-assets-test-v1",
        source_commit="a" * 40,
        source_tree="b" * 40,
        license_status="NOASSERTION",
        repository="https://example.invalid/cards.git",
    )
    with pytest.raises(CardPresentationSourceError, match="SHA-256"):
        LocalizedCardPresentationProvider((mismatched,))

    invalid_path = _database(
        tmp_path / "invalid.cdb",
        include_text_schema=False,
    )
    with pytest.raises(CardPresentationSourceError, match="required columns"):
        LocalizedCardPresentationProvider((_source(invalid_path),))


def test_presentation_text_cannot_change_core_card_data(tmp_path: Path) -> None:
    first_path = _database(tmp_path / "first.cdb", text="Text A")
    second_path = _database(tmp_path / "second.cdb", text="Text B")

    with SQLiteCardDataProvider(first_path) as core_first:
        first_core_card = core_first.get_card(10000)
    with SQLiteCardDataProvider(second_path) as core_second:
        second_core_card = core_second.get_card(10000)
    with LocalizedCardPresentationProvider((_source(first_path),)) as provider:
        first_presentation = provider.get_card(
            CardPresentationQuery(10000, "en", fallback_locales=())
        )
    with LocalizedCardPresentationProvider((_source(second_path),)) as provider:
        second_presentation = provider.get_card(
            CardPresentationQuery(10000, "en", fallback_locales=())
        )

    assert first_core_card == second_core_card
    assert first_presentation.effect_text != second_presentation.effect_text
    assert first_presentation.presentation_id != second_presentation.presentation_id

    protected_roots = (
        REPO_ROOT / "src" / "ygo_effect_dsl" / "engine",
        REPO_ROOT / "src" / "ygo_effect_dsl" / "experiment",
        REPO_ROOT / "src" / "ygo_effect_dsl" / "prototype",
    )
    for root in protected_roots:
        for source_path in root.rglob("*.py"):
            assert "ygo_effect_dsl.presentation" not in source_path.read_text(
                encoding="utf-8"
            )


def test_machine_contract_matches_public_versions() -> None:
    contract = card_presentation_contract_document()

    assert contract["schema_version"] == CARD_PRESENTATION_CONTRACT_VERSION
    assert contract["provider_version"] == CARD_PRESENTATION_PROVIDER_VERSION
    assert contract["authority"] == {
        "effect_interpretation": "forbidden",
        "legality_or_timing": "ocgcore_only",
        "provider": "read_only_presentation",
        "search_input": False,
    }
    assert contract["audit"] == {
        "presentation_identity": "source_and_content_digest",
        "render_timestamp_owner": "caller_audit_envelope",
    }
    assert set(contract["availability"]) == {
        "available",
        "missing_text",
        "missing_card",
        "redacted",
        "source_unavailable",
        "stale_source",
        "version_mismatch",
    }
    resource = (
        REPO_ROOT
        / "src"
        / "ygo_effect_dsl"
        / "resources"
        / "card-presentation-contract-v1.json"
    )
    assert json.loads(resource.read_text(encoding="utf-8")) == contract


def test_evidence_records_capability_without_embedding_card_text(
    tmp_path: Path,
) -> None:
    source = _source(_database(tmp_path / "cards.cdb"))

    evidence = build_card_presentation_evidence(source, (10000,))

    assert evidence["schema_version"] == CARD_PRESENTATION_EVIDENCE_SCHEMA_VERSION
    assert evidence["text_payload_embedded"] is False
    assert evidence["authority"]["search_input"] is False
    assert evidence["cards"] == [
        {
            "auxiliary_region_count": 1,
            "availability": "available",
            "card_code": 10000,
            "effect_text_chars": len("First line\nSecond line: 効果"),
            "effect_text_present": True,
            "locale_status": "exact",
            "metadata_fields_present": [
                "alias",
                "attack",
                "attribute_bits",
                "attribute_labels",
                "defense",
                "left_scale",
                "level",
                "race_bits",
                "race_labels",
                "right_scale",
                "setcodes",
                "type_bits",
                "type_labels",
            ],
            "name_chars": len("検証カード"),
            "name_present": True,
            "presentation_id": evidence["cards"][0]["presentation_id"],
            "resolved_locale": "en",
        }
    ]
    serialized = json.dumps(evidence, ensure_ascii=False)
    assert "検証カード" not in serialized
    assert "First line" not in serialized


def test_committed_pinned_evidence_is_sanitized_and_content_addressed() -> None:
    path = REPO_ROOT / "docs" / "adr" / "evidence" / "0183_card_presentation.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="cardpresentationevidence_",
    )
    assert evidence["text_payload_embedded"] is False
    assert evidence["source"]["asset_lock_id"] == "ocgcore-assets-202504-v1"
    assert evidence["source"]["database_sha256"] == (
        "c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225"
    )
    assert "database_path" not in evidence["source"]
    assert all(item["availability"] == "available" for item in evidence["cards"])
