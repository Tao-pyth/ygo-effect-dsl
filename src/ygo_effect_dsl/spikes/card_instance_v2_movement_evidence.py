from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.engine.bridge.ocgcore import (
    CARD_INSTANCE_TRACE_V2_LUA_SOURCE,
    CARD_INSTANCE_TRACE_V2_SCRIPT_NAME,
    CardInstanceTrackerV2,
    CardScriptsProvider,
    DuelConfig,
    NewCard,
    OcgcoreLibrary,
    OcgcoreMessageDecoder,
    PlayerConfig,
    SQLiteCardDataProvider,
    build_card_instance_scope_id_v2,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import (
    resolve_ocgcore_assets,
    resolve_ocgcore_runtime,
    verify_ocgcore,
)


MOVEMENT_EVIDENCE_SCHEMA_VERSION = "card-instance-movement-evidence-v2"
FIXTURE_CARD_CODE = 97268402
FIXTURE_SEED = (1, 2, 3, 4)
FIXTURE_SCRIPT_NAME = "ygo_effect_dsl_card_instance_v2_movement.lua"
FIXTURE_SCRIPT = b"""local function checkpoint()
    Duel.SelectYesNo(0,70)
end

function YGO_EFFECT_DSL_CARD_INSTANCE_STARTUP_HOOK()
    local own=Duel.GetFieldCard(0,LOCATION_MZONE,0)
    local opponent=Duel.GetFieldCard(1,LOCATION_MZONE,0)

    Duel.Draw(0,1,REASON_RULE)
    checkpoint()

    local deck=Duel.GetFieldGroup(0,LOCATION_DECK,0)
    Duel.SendtoHand(deck:GetFirst(),nil,REASON_EFFECT)
    checkpoint()

    local grave=Duel.GetFieldGroup(0,LOCATION_GRAVE,0)
    Duel.SendtoHand(grave:GetFirst(),nil,REASON_EFFECT)
    checkpoint()

    Duel.ShuffleDeck(0)
    checkpoint()
    Duel.ShuffleHand(0)
    checkpoint()

    local set_cards=Duel.GetMatchingGroup(Card.IsFacedown,0,LOCATION_SZONE,0,nil)
    Duel.ShuffleSetCard(set_cards)
    checkpoint()

    Duel.GetControl(opponent,0)
    checkpoint()
    Duel.SendtoGrave(own,REASON_EFFECT)
    checkpoint()
    Duel.Remove(opponent,POS_FACEUP,REASON_EFFECT)
    checkpoint()

    Duel.SelectMatchingCard(0,aux.TRUE,0,LOCATION_HAND,0,1,1,nil)
end
"""


def _add_card(
    duel: Any,
    *,
    controller: int,
    location: int,
    sequence: int,
    position: int,
) -> None:
    duel.add_card(
        NewCard(
            team=controller,
            duelist=0,
            code=FIXTURE_CARD_CODE,
            controller=controller,
            location=location,
            sequence=sequence,
            position=position,
        )
    )


def build_card_instance_v2_movement_run() -> dict[str, Any]:
    runtime = resolve_ocgcore_runtime()
    assets = resolve_ocgcore_assets()
    verification = verify_ocgcore()
    binary_sha256 = verification["build"]["binary"]["sha256"]
    scope_id = build_card_instance_scope_id_v2(
        {
            "binary_sha256": binary_sha256,
            "fixture_script": stable_digest(FIXTURE_SCRIPT.hex(), prefix="script_"),
            "seed": list(FIXTURE_SEED),
        }
    )
    tracker = CardInstanceTrackerV2(scope_id=scope_id)
    decoder = OcgcoreMessageDecoder()
    player = PlayerConfig(
        starting_lp=8000,
        starting_draw_count=0,
        draw_count_per_turn=0,
    )
    actions: list[dict[str, Any]] = []
    state_hashes: list[str] = []
    request_signatures: list[str] = []

    with OcgcoreLibrary(runtime) as library:
        with SQLiteCardDataProvider(assets.database_path) as database:
            scripts = CardScriptsProvider(assets.scripts_root)
            config = DuelConfig(seed=FIXTURE_SEED, team1=player, team2=player)
            with library.create_duel(config, database, scripts) as duel:
                duel.load_script("constant.lua", scripts.get_script("constant.lua"))
                duel.load_script("utility.lua", scripts.get_script("utility.lua"))
                duel.load_script(FIXTURE_SCRIPT_NAME, FIXTURE_SCRIPT)
                duel.load_script(
                    CARD_INSTANCE_TRACE_V2_SCRIPT_NAME,
                    CARD_INSTANCE_TRACE_V2_LUA_SOURCE,
                )
                for sequence in range(2):
                    _add_card(
                        duel,
                        controller=0,
                        location=0x02,
                        sequence=sequence,
                        position=0x01,
                    )
                for sequence in range(3):
                    _add_card(
                        duel,
                        controller=0,
                        location=0x01,
                        sequence=sequence,
                        position=0x01,
                    )
                _add_card(
                    duel,
                    controller=0,
                    location=0x10,
                    sequence=0,
                    position=0x01,
                )
                _add_card(
                    duel,
                    controller=0,
                    location=0x04,
                    sequence=0,
                    position=0x01,
                )
                for sequence in range(2):
                    _add_card(
                        duel,
                        controller=0,
                        location=0x08,
                        sequence=sequence,
                        position=0x08,
                    )
                _add_card(
                    duel,
                    controller=1,
                    location=0x04,
                    sequence=0,
                    position=0x01,
                )
                duel.start()

                for step in range(16):
                    native = duel.process()
                    decoded = decoder.decode_batch(
                        b"".join(native.messages),
                        request_id=f"movement:{step}",
                        logs=native.logs,
                    )
                    if decoded.request is None:
                        raise ValueError("movement fixture reached no supported Request")
                    scan_label = f"request_{step}"
                    scan_logs = duel.capture_card_instance_scan(
                        scan_nonce=scan_label
                    )
                    request = tracker.synchronize_request(
                        (*native.logs, *scan_logs),
                        decoded.request,
                        expected_scan_label=scan_label,
                        message_types=[frame.message_type for frame in decoded.frames],
                    )
                    snapshot = tracker.enrich_snapshot(
                        duel.capture_snapshot(
                            pending_request=request,
                            environment={
                                "card_instance_scope_id": scope_id,
                                "fixture": "movement_v2",
                            },
                        )
                    )
                    state_hashes.append(snapshot.state_hash)
                    request_signatures.append(request.request_signature)
                    if request.request_type == "select_card":
                        break
                    candidate = (
                        next(
                            item
                            for item in request.candidates
                            if item.candidate_id == "choice:1"
                        )
                        if request.request_type == "select_yes_no"
                        else request.candidates[0]
                    )
                    raw_kind = candidate.payload.get("action_kind")
                    action = Action(
                        kind=(
                            ActionKind(str(raw_kind))
                            if raw_kind is not None
                            else ActionKind.SELECT_OPTION
                        ),
                        player=request.player,
                        selections=(
                            Selection(
                                candidate_id=candidate.candidate_id,
                                payload_ref="candidate.payload",
                            ),
                        ),
                        request_signature=request.request_signature,
                    )
                    duel.respond_action(request, action)
                    actions.append(action.to_dict())
                else:
                    raise ValueError("movement fixture exceeded its Request budget")

    provenance = tracker.provenance_document()
    identity = to_canonical_data(
        {
            "action_ids": [action["action_id"] for action in actions],
            "final_request_signature": request_signatures[-1],
            "provenance": provenance,
            "request_signatures": request_signatures,
            "scope_id": scope_id,
            "state_hashes": state_hashes,
        }
    )
    return {**identity, "route_id": stable_digest(identity, prefix="route_")}


def _fresh_run() -> tuple[int, dict[str, Any]]:
    env = dict(os.environ)
    src_root = Path(__file__).resolve().parents[2]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(src_root) if not existing else str(src_root) + os.pathsep + existing
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ygo_effect_dsl.spikes.card_instance_v2_movement_evidence",
            "--single-run",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(result.stdout)
    return int(payload["pid"]), payload["run"]


def build_card_instance_v2_movement_evidence() -> dict[str, Any]:
    first_pid, first = _fresh_run()
    second_pid, second = _fresh_run()
    movement_kinds = {
        item["movement_kind"]
        for item in first["provenance"]["movement_transitions"]
    }
    shuffle_kinds = {
        item["mutation"] for item in first["provenance"]["shuffle_boundaries"]
    }
    checks = {
        "control_change_preserves_owner": any(
            item["movement_kind"] == "control_change" and item["owner"] == 1
            for item in first["provenance"]["movement_transitions"]
        ),
        "draw_search_and_salvage_are_distinguished": {
            "draw",
            "search",
            "salvage",
        }.issubset(movement_kinds),
        "field_grave_and_banished_moves_are_observed": any(
            item["after"]["location"] == 0x10
            for item in first["provenance"]["movement_transitions"]
        )
        and any(
            item["after"]["location"] == 0x20
            for item in first["provenance"]["movement_transitions"]
        ),
        "fresh_worker_route_identity_is_stable": first_pid != second_pid
        and first == second,
        "hand_deck_and_set_shuffles_are_observed": {
            "shuffle_deck",
            "shuffle_hand",
            "shuffle_set_card",
        }.issubset(shuffle_kinds),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError("movement evidence failed: " + ", ".join(failed))
    identity = to_canonical_data(
        {
            "checks": checks,
            "fresh_worker_process_count": 2,
            "run": first,
            "schema_version": MOVEMENT_EVIDENCE_SCHEMA_VERSION,
        }
    )
    return {**identity, "evidence_id": stable_digest(identity, prefix="cardmoveev_")}


def main() -> int:
    parser = argparse.ArgumentParser(description="build card movement v2 evidence")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--single-run", action="store_true")
    args = parser.parse_args()
    if args.single_run:
        print(
            json.dumps(
                {"pid": os.getpid(), "run": build_card_instance_v2_movement_run()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    evidence = build_card_instance_v2_movement_evidence()
    serialized = json.dumps(
        evidence, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"card-instance-movement-v2: wrote {args.out} "
            f"evidence_id={evidence['evidence_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
