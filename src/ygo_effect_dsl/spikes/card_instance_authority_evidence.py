from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from ygo_effect_dsl.engine.action import Action, ActionKind, CardRef, Selection
from ygo_effect_dsl.engine.bridge.ocgcore import (
    CARD_INSTANCE_AUTHORITY,
    CARD_INSTANCE_TRACE_LUA_SOURCE,
    CARD_INSTANCE_TRACE_SCHEMA_VERSION,
    CARD_INSTANCE_TRACE_SCRIPT_NAME,
    CardInstanceTracker,
    CardScriptsProvider,
    DuelConfig,
    NewCard,
    OcgcoreLibrary,
    OcgcoreMessageDecoder,
    PlayerConfig,
    RandomMessageType,
    SQLiteCardDataProvider,
    build_card_instance_scope_id,
    project_card_instance_observations,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.state import InformationMode
from ygo_effect_dsl.external.ocgcore import (
    load_ocgcore_lock,
    resolve_ocgcore_assets,
    resolve_ocgcore_runtime,
    verify_ocgcore,
)


CARD_INSTANCE_EVIDENCE_SCHEMA_VERSION = "ocgcore-card-instance-evidence-v1"
CARD_INSTANCE_ROUTE_SCHEMA_VERSION = "ocgcore-card-instance-route-v1"
UPSTREAM_CORE_COMMIT = "0764db0c75b3d1d574880d365aa3695ab1f13b43"
FIXTURE_CARD_CODE = 97268402
FIXTURE_TOKEN_CODE = 176393
FIXTURE_TOKEN_SCRIPT = b"local s,id=GetID()\nfunction s.initial_effect(c) end\n"
FIXTURE_SEED = (1, 2, 3, 4)
FIXTURE_SCRIPT_NAME = "ygo_effect_dsl_card_instance_fixture.lua"
FIXTURE_SCRIPT = f"""function YGO_EFFECT_DSL_CARD_INSTANCE_STARTUP_HOOK()
    local token=Duel.CreateToken(0,{FIXTURE_TOKEN_CODE})
    YGO_EFFECT_DSL_CARD_INSTANCE_OBSERVE("token_created",token)
    YGO_EFFECT_DSL_CARD_INSTANCE_SCAN("before_first_request")
    local first=Duel.SelectMatchingCard(0,aux.TRUE,0,LOCATION_HAND,0,1,1,nil)
    Duel.SendtoGrave(first:GetFirst(),REASON_RULE)
    YGO_EFFECT_DSL_CARD_INSTANCE_SCAN("after_compression")
    Duel.ShuffleHand(0)
    YGO_EFFECT_DSL_CARD_INSTANCE_SCAN("after_shuffle")
    local second=Duel.SelectMatchingCard(0,aux.TRUE,0,LOCATION_HAND,0,1,1,nil)
    Duel.SendtoGrave(second:GetFirst(),REASON_RULE)
    YGO_EFFECT_DSL_CARD_INSTANCE_SCAN("final")
end
""".encode("ascii")
_SOURCE_FILES = (
    "card.cpp",
    "card.h",
    "common.h",
    "field.cpp",
    "field.h",
    "interpreter.cpp",
    "libcard.cpp",
    "libduel.cpp",
)


class _FixtureScriptProvider:
    def __init__(self, base: CardScriptsProvider) -> None:
        self.base = base

    def get_script(self, name: str) -> bytes:
        if name == f"c{FIXTURE_TOKEN_CODE}.lua":
            return FIXTURE_TOKEN_SCRIPT
        return self.base.get_script(name)


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def _source_file(root: Path, commit: str, relative: str) -> bytes:
    value = _git(root, "show", f"{commit}:{relative}", text=False)
    assert isinstance(value, bytes)
    return value


def _source_audit(root: Path, commit: str) -> dict[str, Any]:
    files = {
        relative: _source_file(root, commit, relative)
        for relative in _SOURCE_FILES
    }
    text = {
        relative: content.decode("utf-8")
        for relative, content in files.items()
    }
    checks = {
        "card_id_is_assigned_once_at_card_registration": (
            text["interpreter.cpp"].count(
                "pcard->cardid = pduel->game_field->infos.card_id++"
            )
            == 1
            and "uint32_t card_id{ 1 };" in text["field.h"]
        ),
        "card_lua_api_exposes_card_id": (
            "LUA_FUNCTION(GetCardID)" in text["libcard.cpp"]
            and "lua_pushinteger(L, self->cardid);" in text["libcard.cpp"]
        ),
        "duel_lua_api_resolves_card_id_to_same_object": (
            "LUA_STATIC_FUNCTION(GetCardFromCardID)" in text["libduel.cpp"]
            and "if(pcard->cardid == id)" in text["libduel.cpp"]
        ),
        "query_api_exposes_no_card_id_field": (
            "QUERY_CARD_ID" not in text["common.h"]
            and "CHECK_AND_INSERT(QUERY_CARD_ID" not in text["card.cpp"]
        ),
        "field_id_is_not_persistent_card_authority": (
            text["field.cpp"].count("pcard->fieldid = infos.field_id++") >= 1
        ),
    }
    return {
        "checks": checks,
        "commit": commit,
        "files": [
            {
                "path": relative,
                "sha256": sha256(content).hexdigest(),
                "size": len(content),
            }
            for relative, content in sorted(files.items())
        ],
        "status": (
            "lua_card_id_authority_available_query_card_id_unavailable"
            if all(checks.values())
            else "inconclusive"
        ),
    }


def _scope_identity(binary_sha256: str) -> dict[str, Any]:
    return {
        "card_code": FIXTURE_CARD_CODE,
        "copies_by_player": {"0": 3, "1": 1},
        "fixture_script_sha256": sha256(FIXTURE_SCRIPT).hexdigest(),
        "instrumentation_sha256": sha256(
            CARD_INSTANCE_TRACE_LUA_SOURCE
        ).hexdigest(),
        "ocgcore_binary_sha256": binary_sha256,
        "seed": list(FIXTURE_SEED),
        "token_code": FIXTURE_TOKEN_CODE,
        "token_script_sha256": sha256(FIXTURE_TOKEN_SCRIPT).hexdigest(),
    }


def _card_ref(raw: dict[str, Any]) -> CardRef:
    location = {
        0x01: "deck",
        0x02: "hand",
        0x04: "monster_zone",
        0x08: "spell_trap_zone",
        0x10: "graveyard",
        0x20: "banished",
        0x40: "extra_deck",
    }.get(raw["location"], f"core_location_{raw['location']}")
    return CardRef(
        controller=raw["controller"],
        owner=raw["owner"],
        location=location,
        sequence=raw["sequence"],
        public_card_id=raw.get("public_card_id"),
        instance_id=raw["instance_id"],
    )


def _selection_action(request: Any, candidate_index: int = 0) -> Action:
    if request.request_type != "select_card":
        raise ValueError(
            f"card instance fixture expected select_card, got {request.request_type!r}"
        )
    candidate = request.candidates[candidate_index]
    if not isinstance(candidate.card_ref, dict):
        raise ValueError("card instance fixture expected a card candidate")
    return Action(
        kind=ActionKind(
            candidate.payload.get("action_kind", ActionKind.SELECT_CARD.value)
        ),
        player=request.player,
        request_signature=request.request_signature,
        selections=(
            Selection(
                candidate_id=candidate.candidate_id,
                card_ref=_card_ref(candidate.card_ref),
                payload_ref="candidate.payload",
            ),
        ),
    )


def _decode(decoder: OcgcoreMessageDecoder, batch: Any, request_id: str) -> Any:
    return decoder.decode_batch(
        b"".join(batch.messages),
        request_id=request_id,
        logs=batch.logs,
    )


def _run_fixture_once(
    *,
    external_root: str | Path | None = None,
) -> dict[str, Any]:
    runtime = resolve_ocgcore_runtime(external_root=external_root)
    assets = resolve_ocgcore_assets(external_root=external_root)
    verification = verify_ocgcore(external_root=external_root)
    binary_sha256 = verification["build"]["binary"]["sha256"]
    scope_id = build_card_instance_scope_id(_scope_identity(binary_sha256))
    tracker = CardInstanceTracker(scope_id=scope_id)
    scripts = CardScriptsProvider(assets.scripts_root)
    fixture_scripts = _FixtureScriptProvider(scripts)
    decoder = OcgcoreMessageDecoder()
    player = PlayerConfig(
        starting_lp=8000,
        starting_draw_count=0,
        draw_count_per_turn=0,
    )
    batches: list[dict[str, Any]] = []
    actions: list[Action] = []
    request_signatures: list[str] = []
    responses: list[dict[str, Any]] = []

    with OcgcoreLibrary(runtime) as library:
        with SQLiteCardDataProvider(assets.database_path) as database:
            config = DuelConfig(seed=FIXTURE_SEED, team1=player, team2=player)
            with library.create_duel(config, database, fixture_scripts) as duel:
                duel.load_script("constant.lua", scripts.get_script("constant.lua"))
                duel.load_script("utility.lua", scripts.get_script("utility.lua"))
                duel.load_script(FIXTURE_SCRIPT_NAME, FIXTURE_SCRIPT)
                duel.load_script(
                    CARD_INSTANCE_TRACE_SCRIPT_NAME,
                    CARD_INSTANCE_TRACE_LUA_SOURCE,
                )
                for sequence in range(3):
                    duel.add_card(
                        NewCard(
                            team=0,
                            duelist=0,
                            code=FIXTURE_CARD_CODE,
                            controller=0,
                            location=0x02,
                            sequence=sequence,
                            position=0x01,
                        )
                    )
                duel.add_card(
                    NewCard(
                        team=1,
                        duelist=0,
                        code=FIXTURE_CARD_CODE,
                        controller=1,
                        location=0x02,
                        sequence=0,
                        position=0x01,
                    )
                )
                duel.start()

                first_native = duel.process()
                first_batch = _decode(decoder, first_native, "card-instance:0")
                tracker.consume(first_native.logs)
                if first_batch.request is None:
                    raise ValueError("fixture exposed no first selection request")
                first_request = tracker.enrich_request(first_batch.request)
                if first_request.request_type != "select_card":
                    log_records = [
                        (log.log_type.name, log.message)
                        for log in first_native.logs
                    ]
                    raise ValueError(
                        "fixture expected first select_card after observations "
                        f"{[item.label for item in tracker.observations]}, got "
                        f"{first_request.request_type!r}; logs="
                        f"{log_records}"
                    )
                initial_snapshot = duel.capture_snapshot(
                    pending_request=first_request,
                    environment={"card_instance_scope_id": scope_id},
                )
                first_action = _selection_action(first_request)
                first_response = duel.respond_action(first_request, first_action)
                actions.append(first_action)
                request_signatures.append(first_request.request_signature)
                responses.append(first_response.to_trace_dict())
                batches.append(
                    {
                        "frame_types": [
                            frame.message_type for frame in first_batch.frames
                        ],
                        "native_steps": first_native.steps,
                    }
                )

                second_native = duel.process()
                second_batch = _decode(decoder, second_native, "card-instance:1")
                tracker.consume(second_native.logs)
                if second_batch.request is None:
                    raise ValueError("fixture exposed no second selection request")
                second_request = tracker.enrich_request(second_batch.request)
                second_action = _selection_action(second_request)
                second_response = duel.respond_action(second_request, second_action)
                actions.append(second_action)
                request_signatures.append(second_request.request_signature)
                responses.append(second_response.to_trace_dict())
                batches.append(
                    {
                        "frame_types": [
                            frame.message_type for frame in second_batch.frames
                        ],
                        "native_steps": second_native.steps,
                    }
                )

                final_native = duel.process()
                final_batch = _decode(decoder, final_native, "card-instance:2")
                tracker.consume(final_native.logs)
                if final_batch.request is None:
                    raise ValueError("fixture exposed no final checkpoint request")
                final_request = tracker.enrich_request(final_batch.request)
                final_snapshot = duel.capture_snapshot(
                    pending_request=final_request,
                    environment={"card_instance_scope_id": scope_id},
                )
                batches.append(
                    {
                        "frame_types": [
                            frame.message_type for frame in final_batch.frames
                        ],
                        "native_steps": final_native.steps,
                    }
                )

    observations = tracker.observations
    action_dicts = [action.to_dict() for action in actions]
    route_identity = to_canonical_data(
        {
            "action_ids": [action.action_id for action in actions],
            "final_request_signature": final_request.request_signature,
            "final_state_hash": final_snapshot.state_hash,
            "initial_state_hash": initial_snapshot.state_hash,
            "request_signatures": request_signatures,
            "responses": responses,
            "schema_version": CARD_INSTANCE_ROUTE_SCHEMA_VERSION,
            "scope_id": scope_id,
        }
    )
    complete = project_card_instance_observations(
        observations,
        information_mode=InformationMode.COMPLETE_INFORMATION,
    )
    player0 = project_card_instance_observations(
        observations,
        information_mode=InformationMode.PLAYER_VIEW,
        viewer=0,
    )
    player1 = project_card_instance_observations(
        observations,
        information_mode=InformationMode.PLAYER_VIEW,
        viewer=1,
    )
    sampled_player0 = project_card_instance_observations(
        observations,
        information_mode=InformationMode.SAMPLED_PRIVATE_STATE,
        viewer=0,
    )
    return to_canonical_data(
        {
            "action_ids": [action.action_id for action in actions],
            "actions": action_dicts,
            "batches": batches,
            "final_state_hash": final_snapshot.state_hash,
            "initial_state_hash": initial_snapshot.state_hash,
            "instance_observations": complete,
            "projections": {
                "player0": player0,
                "player1": player1,
                "sampled_player0": sampled_player0,
            },
            "request_signatures": request_signatures,
            "route_id": stable_digest(route_identity, prefix="route_"),
            "route_identity": route_identity,
            "scope_id": scope_id,
        }
    )


def _fresh_process_run(
    *,
    external_root: str | Path | None,
) -> tuple[int, dict[str, Any]]:
    command = [
        sys.executable,
        "-m",
        "ygo_effect_dsl.spikes.card_instance_authority_evidence",
        "--single-run",
    ]
    if external_root is not None:
        command.extend(["--external-root", str(external_root)])
    env = dict(os.environ)
    src_root = Path(__file__).resolve().parents[2]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(src_root) if not existing else str(src_root) + os.pathsep + existing
    )
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(result.stdout)
    return int(payload["pid"]), payload["run"]


def _label_map(run: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for observation in run["instance_observations"]:
        result.setdefault(observation["label"], []).append(observation)
    return result


def build_card_instance_authority_evidence(
    *,
    external_root: str | Path | None = None,
) -> dict[str, Any]:
    first_pid, first = _fresh_process_run(external_root=external_root)
    second_pid, second = _fresh_process_run(external_root=external_root)
    if first_pid == second_pid:
        raise ValueError("fresh replay workers must use different processes")
    runtime = resolve_ocgcore_runtime(external_root=external_root)
    source_root = runtime.parent.parent / "source"
    lock = load_ocgcore_lock()
    upstream_ref = _git(source_root, "rev-parse", "origin/master")
    assert isinstance(upstream_ref, str)
    if upstream_ref.strip() != UPSTREAM_CORE_COMMIT:
        raise ValueError(
            f"origin/master must be {UPSTREAM_CORE_COMMIT}, got {upstream_ref.strip()}"
        )
    source = {
        "pinned": _source_audit(source_root, str(lock.source["commit"])),
        "upstream": _source_audit(source_root, UPSTREAM_CORE_COMMIT),
    }
    labels = _label_map(first)
    before = labels["before_first_request"]
    compressed = labels["after_compression"]
    shuffled = labels["after_shuffle"]
    own_before = [
        item
        for item in before
        if item["owner"] == 0 and item["card_code"] == FIXTURE_CARD_CODE
    ]
    opponent_before = [
        item
        for item in before
        if item["owner"] == 1 and item["card_code"] == FIXTURE_CARD_CODE
    ]
    token = labels["token_created"]
    action_instance_ids = [
        action["selections"][0]["card_ref"]["instance_id"]
        for action in first["actions"]
    ]
    compressed_by_id = {item["instance_id"]: item for item in compressed}
    shuffled_by_id = {item["instance_id"]: item for item in shuffled}
    own_hand_compressed = [
        item
        for item in compressed
        if item["owner"] == 0
        and item["location"] == 0x02
        and item["card_code"] == FIXTURE_CARD_CODE
    ]
    own_hand_shuffled = [
        item
        for item in shuffled
        if item["owner"] == 0
        and item["location"] == 0x02
        and item["card_code"] == FIXTURE_CARD_CODE
    ]
    hidden_opponent_ids = {
        item["instance_id"] for item in opponent_before
    }
    player0_projection_ids = {
        item["instance_id"] for item in first["projections"]["player0"]
    }
    sampled_projection_ids = {
        item["instance_id"]
        for item in first["projections"]["sampled_player0"]
    }
    checks = {
        "duplicate_same_code_instances_are_distinct": (
            len(own_before) == 3
            and len({item["instance_id"] for item in own_before}) == 3
        ),
        "fresh_worker_replay_is_identical": first == second,
        "hidden_opponent_identity_is_not_projected": (
            len(opponent_before) == 1
            and hidden_opponent_ids.isdisjoint(player0_projection_ids)
            and hidden_opponent_ids.isdisjoint(sampled_projection_ids)
            and all(
                "card_id" not in item
                for item in first["projections"]["player0"]
            )
        ),
        "instance_identity_survives_sequence_compression": (
            all(instance_id in compressed_by_id for instance_id in action_instance_ids)
            and compressed_by_id[action_instance_ids[0]]["location"] == 0x10
            and sorted(item["sequence"] for item in own_hand_compressed) == [0, 1]
        ),
        "instance_identity_survives_hand_shuffle": (
            {item["instance_id"] for item in own_hand_compressed}
            == {item["instance_id"] for item in own_hand_shuffled}
            and shuffled_by_id[action_instance_ids[1]]["sequence"] == 0
            and any(
                int(RandomMessageType.SHUFFLE_HAND) in batch["frame_types"]
                for batch in first["batches"]
            )
        ),
        "opponent_and_token_have_distinct_authority_ids": (
            len(token) == 1
            and token[0]["is_token"] is True
            and token[0]["instance_id"]
            not in {item["instance_id"] for item in before}
        ),
        "source_authority_is_pinned_and_available": all(
            audit["status"]
            == "lua_card_id_authority_available_query_card_id_unavailable"
            for audit in source.values()
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError("card instance authority audit failed: " + ", ".join(failed))
    identity = to_canonical_data(
        {
            "authority": {
                "field_id_policy": "rejected_as_non_persistent",
                "primary": CARD_INSTANCE_AUTHORITY,
                "query_card_id": "unavailable",
                "runtime_requirement": "pinned_source_audit_must_pass",
            },
            "checks": checks,
            "fixture": {
                **_scope_identity(
                    verify_ocgcore(external_root=external_root)["build"]["binary"][
                        "sha256"
                    ]
                ),
                "fixture_script_name": FIXTURE_SCRIPT_NAME,
            },
            "fresh_worker_replay": {
                "action_ids": first["action_ids"],
                "final_state_hash": first["final_state_hash"],
                "initial_state_hash": first["initial_state_hash"],
                "process_count": 2,
                "request_signatures": first["request_signatures"],
                "route_id": first["route_id"],
                "runs_identical": True,
            },
            "run": first,
            "schema_version": CARD_INSTANCE_EVIDENCE_SCHEMA_VERSION,
            "source_audit": source,
            "trace_schema_version": CARD_INSTANCE_TRACE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="cardinstev_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="audit persistent ocgcore card instance identity"
    )
    parser.add_argument("--external-root")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--single-run", action="store_true")
    args = parser.parse_args()
    if args.single_run:
        print(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "run": _run_fixture_once(external_root=args.external_root),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    evidence = build_card_instance_authority_evidence(
        external_root=args.external_root
    )
    serialized = (
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"card-instance-authority: wrote {args.out} "
            f"evidence_id={evidence['evidence_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
