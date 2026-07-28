from __future__ import annotations

import json

import pytest

from ygo_effect_dsl.engine.evaluation import (
    TerminalPreferenceProfile,
    TerminalPreferenceProfileCatalog,
)


CARD = 10000


def _profile(weight: int = 3) -> TerminalPreferenceProfile:
    return TerminalPreferenceProfile.from_mapping(
        {
            "name": "catalog profile",
            "rules": [
                {
                    "card_code": CARD,
                    "controller": 0,
                    "enabled": True,
                    "location": "HAND",
                    "max_count": None,
                    "min_count": 1,
                    "position": "ANY",
                    "rule_id": "hand-copy",
                    "scoring_mode": "once",
                    "weight": weight,
                }
            ],
            "schema_version": "terminal-preference-profile-v1",
        }
    )


def test_catalog_persists_profiles_by_content_id_and_deduplicates(tmp_path) -> None:
    catalog = TerminalPreferenceProfileCatalog(tmp_path)
    first = catalog.put(_profile())
    second = catalog.put(_profile())

    assert first.profile.profile_id == second.profile.profile_id
    assert first.path == second.path
    assert len(catalog.list()) == 1
    assert catalog.require(first.profile.profile_id).sha256 == second.sha256
    assert catalog.catalog_digest().startswith("termprefcatalog_")


def test_catalog_clone_on_edit_creates_new_immutable_record(tmp_path) -> None:
    catalog = TerminalPreferenceProfileCatalog(tmp_path)
    source = catalog.put(_profile())
    edited_rule = {
        **source.profile.to_dict()["rules"][0],
        "weight": 9,
    }
    edited = catalog.clone(
        source.profile.profile_id,
        name="edited",
        rules=(edited_rule,),
    )

    assert source.profile.profile_id != edited.profile.profile_id
    assert catalog.require(source.profile.profile_id).profile.to_dict()["rules"][0][
        "weight"
    ] == 3
    assert catalog.require(edited.profile.profile_id).profile.name == "edited"
    assert catalog.require(edited.profile.profile_id).profile.to_dict()["rules"][0][
        "weight"
    ] == 9


def test_catalog_rejects_profile_id_content_mismatch(tmp_path) -> None:
    catalog = TerminalPreferenceProfileCatalog(tmp_path)
    record = catalog.put(_profile())
    path = tmp_path / record.path
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["profile_id"] = "termpref_" + "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="profile_id does not match content"):
        catalog.require(record.profile.profile_id)


def test_catalog_ensures_default_empty_profile(tmp_path) -> None:
    catalog = TerminalPreferenceProfileCatalog(tmp_path)
    record = catalog.ensure_default()

    assert record.profile.name == "Default terminal preference"
    assert record.profile.to_dict()["rules"] == []
    assert catalog.ensure_default().profile.profile_id == record.profile.profile_id
