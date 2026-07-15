from __future__ import annotations

import sqlite3
from copy import deepcopy
from pathlib import Path

from ygo_effect_dsl.engine.information import InformationAccessPolicy
from ygo_effect_dsl.experiment import parse_ydk, preflight_scenario
from ygo_effect_dsl.external.ocgcore import OcgcoreAssets


CARD_CODES = tuple(range(10_001, 10_015))


def _experiment() -> dict:
    policy = InformationAccessPolicy(
        information_mode="complete_information",
        deck_order="known",
        opening_hand="fixed",
    )
    main = [code for code in CARD_CODES for _ in range(3)]
    return {
        "schema_version": "0.4",
        "experiment_id": "scenario_preflight_test",
        "objective": "preflight",
        "deck": {
            "id": "inline_test",
            "source": "inline",
            "main": main,
            "extra": [],
            "side": [],
        },
        "player": {"starting_player": 0, "perspective": 0},
        "turn_limit": 1,
        "information_mode": "complete_information",
        "information_policy": policy.to_experiment_dict(),
        "evaluate_at": "legal_stop",
        "success_predicate": {"id": "test", "version": "1", "config": {}},
        "evaluator": {"id": "test", "version": "1", "config": {}},
        "search": {
            "strategy": "random_search_v1",
            "budget": {"max_nodes": 10, "max_replays": 20, "max_depth": 8},
            "parameters": {"seed": 7},
        },
        "interruption": {"mode": "none", "definitions": []},
        "replay": {"strict_versions": True},
        "scenario": {
            "schema_version": "scenario-v1",
            "opening_hand": {
                "mode": "fixed",
                "cards": list(CARD_CODES[:5]),
            },
        },
    }


def _assets(
    tmp_path: Path,
    *,
    omit_database_row: int | None = None,
    omit_script: int | None = None,
) -> OcgcoreAssets:
    database_path = tmp_path / "cards.cdb"
    database_path.unlink(missing_ok=True)
    connection = sqlite3.connect(database_path)
    connection.execute(
        "CREATE TABLE datas (id INTEGER, alias INTEGER, setcode INTEGER, type INTEGER, "
        "atk INTEGER, def INTEGER, level INTEGER, race INTEGER, attribute INTEGER)"
    )
    connection.executemany(
        "INSERT INTO datas VALUES (?, 0, 0, 1, 0, 0, 1, 1, 1)",
        [(code,) for code in CARD_CODES if code != omit_database_row],
    )
    connection.commit()
    connection.close()
    scripts_root = tmp_path / "scripts"
    scripts_root.mkdir(exist_ok=True)
    for code in CARD_CODES:
        if code != omit_script:
            (scripts_root / f"c{code}.lua").write_text("return 0\n", encoding="utf-8")
    return OcgcoreAssets(
        scripts_root=scripts_root,
        database_path=database_path,
        manifest={
            "asset_lock_id": "test-assets",
            "asset_lock_sha256": "a" * 64,
            "repositories": {
                "card_database": {"commit": "db-commit"},
                "card_scripts": {"commit": "script-commit"},
            },
        },
    )


def test_inline_preflight_builds_reproducible_manifest(tmp_path: Path) -> None:
    experiment = _experiment()

    first = preflight_scenario(experiment, assets=_assets(tmp_path))
    second = preflight_scenario(experiment, assets=_assets(tmp_path))

    assert first.ok
    assert first.to_dict() == second.to_dict()
    assert first.manifest is not None
    assert first.manifest.deck_sha256
    assert first.manifest.opening_hand == CARD_CODES[:5]
    assert first.manifest.asset_lock_id == "test-assets"
    assert "initial_state" not in first.manifest.to_dict()


def test_public_board_break_initial_state_is_normalized_and_identified(
    tmp_path: Path,
) -> None:
    experiment = _experiment()
    experiment["scenario"]["initial_state"] = {
        "schema_version": "board-break-initial-state-v1",
        "turn_player": 0,
        "public_cards": [
            {
                "card_code": CARD_CODES[2],
                "owner": 1,
                "controller": 1,
                "location": "graveyard",
                "sequence": 0,
                "position": "face_up_attack",
                "visibility": "public",
            },
            {
                "card_code": CARD_CODES[1],
                "owner": 1,
                "controller": 1,
                "location": "monster_zone",
                "sequence": 0,
                "position": "face_up_attack",
                "visibility": "public",
            },
        ],
    }

    first = preflight_scenario(experiment, assets=_assets(tmp_path))
    experiment["scenario"]["initial_state"]["public_cards"].reverse()
    second = preflight_scenario(experiment, assets=_assets(tmp_path))

    assert first.ok and second.ok
    assert first.manifest is not None and second.manifest is not None
    assert first.manifest.initial_state_id == second.manifest.initial_state_id
    assert first.manifest.initial_state == second.manifest.initial_state
    assert first.manifest.initial_state_id.startswith("boardbreakstate_")
    assert first.manifest.initial_state["turn_player"] == 0


def test_board_break_initial_state_rejects_non_public_or_empty_cards(
    tmp_path: Path,
) -> None:
    experiment = _experiment()
    public_card = {
        "card_code": CARD_CODES[1],
        "owner": 1,
        "controller": 1,
        "location": "monster_zone",
        "sequence": 0,
        "position": "face_up_attack",
        "visibility": "public",
    }
    experiment["scenario"]["initial_state"] = {
        "schema_version": "board-break-initial-state-v1",
        "turn_player": 0,
        "public_cards": [public_card, dict(public_card)],
    }

    duplicate = preflight_scenario(experiment, assets=_assets(tmp_path))
    private = deepcopy(experiment)
    private["scenario"]["initial_state"]["public_cards"] = [dict(public_card)]
    private["scenario"]["initial_state"]["public_cards"][0]["visibility"] = "private"
    rejected_private = preflight_scenario(private, assets=_assets(tmp_path))
    face_down = deepcopy(experiment)
    face_down["scenario"]["initial_state"]["public_cards"] = [dict(public_card)]
    face_down["scenario"]["initial_state"]["public_cards"][0]["position"] = (
        "face_down_defense"
    )
    rejected_face_down = preflight_scenario(face_down, assets=_assets(tmp_path))
    invalid_sequence = deepcopy(experiment)
    invalid_sequence["scenario"]["initial_state"]["public_cards"] = [
        dict(public_card)
    ]
    invalid_sequence["scenario"]["initial_state"]["public_cards"][0]["sequence"] = 7
    rejected_sequence = preflight_scenario(
        invalid_sequence, assets=_assets(tmp_path)
    )
    empty = deepcopy(experiment)
    empty["scenario"]["initial_state"]["public_cards"] = []
    rejected_empty = preflight_scenario(empty, assets=_assets(tmp_path))

    assert not duplicate.ok
    assert {item.code for item in duplicate.diagnostics} == {
        "duplicate_initial_coordinate"
    }
    assert not rejected_private.ok
    assert rejected_private.diagnostics[0].code == "invalid_experiment"
    assert "private_initial_card_not_allowed" in rejected_private.diagnostics[0].message
    assert not rejected_face_down.ok
    assert "unsupported_initial_position" in rejected_face_down.diagnostics[0].message
    assert not rejected_sequence.ok
    assert "initial_sequence_out_of_range" in rejected_sequence.diagnostics[0].message
    assert not rejected_empty.ok
    assert "expected_non_empty_list" in rejected_empty.diagnostics[0].message


def test_ydk_normalization_and_content_hash(tmp_path: Path) -> None:
    experiment = _experiment()
    ydk = tmp_path / "deck.ydk"
    main = experiment["deck"]["main"]
    source = (
        "#created by test\n#main\n"
        + "\n".join(str(code) for code in main)
        + "\n#extra\n!side\n"
    )
    ydk.write_text(source, encoding="utf-8")
    experiment["deck"] = {"id": "ydk_test", "source": "ydk", "path": "deck.ydk"}

    parsed, source_hash = parse_ydk(ydk)
    result = preflight_scenario(
        experiment, experiment_path=tmp_path / "experiment.yaml", assets=_assets(tmp_path)
    )
    ydk.write_text(
        source.replace("#created by test", "#created by modified"),
        encoding="utf-8",
    )
    modified = preflight_scenario(
        experiment,
        experiment_path=tmp_path / "experiment.yaml",
        assets=_assets(tmp_path),
    )

    assert parsed["main"] == tuple(main)
    assert result.ok
    assert result.manifest is not None
    assert result.manifest.source_sha256 == source_hash
    assert modified.ok
    assert modified.manifest is not None
    assert modified.manifest.sections == result.manifest.sections
    assert modified.manifest.deck_sha256 == result.manifest.deck_sha256
    assert modified.manifest.source_sha256 != result.manifest.source_sha256


def test_conditional_hand_is_seeded_and_fails_closed(tmp_path: Path) -> None:
    experiment = _experiment()
    experiment["scenario"]["opening_hand"] = {
        "mode": "conditional",
        "seed": 91,
        "size": 5,
        "conditions": [{"code": CARD_CODES[0], "min_count": 1}],
    }
    assets = _assets(tmp_path)

    first = preflight_scenario(experiment, assets=assets)
    second = preflight_scenario(experiment, assets=assets)
    impossible = deepcopy(experiment)
    impossible["scenario"]["opening_hand"]["conditions"] = [
        {"code": CARD_CODES[0], "min_count": 4}
    ]
    impossible["scenario"]["opening_hand"]["max_attempts"] = 20
    failed = preflight_scenario(impossible, assets=assets)

    assert first.ok and second.ok
    assert first.manifest is not None and second.manifest is not None
    assert first.manifest.opening_hand == second.manifest.opening_hand
    assert not failed.ok
    assert failed.manifest is None
    assert {item.code for item in failed.diagnostics} == {"conditional_hand_unsatisfied"}


def test_fixed_registry_and_random_hand_are_deterministic(tmp_path: Path) -> None:
    experiment = _experiment()
    fixed_sections = {
        name: tuple(experiment["deck"][name]) for name in ("main", "extra", "side")
    }
    experiment["deck"] = {"id": "registered_test", "source": "fixed"}
    experiment["scenario"]["opening_hand"] = {
        "mode": "random",
        "seed": 713,
        "size": 5,
    }
    assets = _assets(tmp_path)

    first = preflight_scenario(
        experiment,
        assets=assets,
        fixed_decks={"registered_test": fixed_sections},
    )
    second = preflight_scenario(
        experiment,
        assets=assets,
        fixed_decks={"registered_test": fixed_sections},
    )

    assert first.ok and second.ok
    assert first.manifest is not None and second.manifest is not None
    assert first.manifest.deck_source == "fixed"
    assert first.manifest.opening_hand_mode == "random"
    assert first.manifest.opening_hand_seed == 713
    assert first.manifest.opening_hand == second.manifest.opening_hand


def test_missing_script_and_structural_errors_are_diagnostics(tmp_path: Path) -> None:
    experiment = _experiment()
    experiment["deck"]["main"].append(CARD_CODES[0])

    result = preflight_scenario(
        experiment, assets=_assets(tmp_path, omit_script=CARD_CODES[-1])
    )

    assert not result.ok
    assert result.manifest is None
    assert {item.code for item in result.diagnostics} == {
        "duplicate_card_limit_exceeded",
        "missing_card_script",
    }


def test_missing_database_row_fails_closed(tmp_path: Path) -> None:
    experiment = _experiment()

    result = preflight_scenario(
        experiment,
        assets=_assets(tmp_path, omit_database_row=CARD_CODES[-1]),
    )

    assert not result.ok
    assert result.manifest is None
    assert {item.code for item in result.diagnostics} == {
        "missing_card_database_row"
    }


def test_specified_interruption_source_is_included_in_asset_manifest(tmp_path: Path) -> None:
    experiment = _experiment()
    experiment["interruption"] = {
        "mode": "specified",
        "definitions": [
            {
                "id": "all_core_opportunities",
                "source_card_code": CARD_CODES[-1],
                "source_player": 1,
                "source_zone": "hand",
                "response_roles": ["target"],
            }
        ],
    }

    result = preflight_scenario(experiment, assets=_assets(tmp_path))

    assert result.ok
    assert result.manifest is not None
    assert result.manifest.interruption_source_codes == (CARD_CODES[-1],)
