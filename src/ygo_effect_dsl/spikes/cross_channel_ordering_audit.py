from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

from ygo_effect_dsl.engine.bridge.ocgcore import (
    DIRECT_RANDOM_TRACE_LUA_SOURCE,
    DIRECT_RANDOM_TRACE_SCRIPT_NAME,
    CardScriptsProvider,
    DuelConfig,
    DuelProcessStatus,
    DuelState,
    NewCard,
    OcgcoreLibrary,
    OcgcoreMessageDecoder,
    PlayerConfig,
    SQLiteCardDataProvider,
    build_core_output_trace,
    build_cross_channel_ordering_evidence,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import (
    load_ocgcore_lock,
    resolve_ocgcore_assets,
    resolve_ocgcore_runtime,
    verify_ocgcore,
)


CROSS_CHANNEL_EVIDENCE_SCHEMA_VERSION = (
    "ocgcore-cross-channel-ordering-evidence-v1"
)
UPSTREAM_CORE_COMMIT = "0764db0c75b3d1d574880d365aa3695ab1f13b43"
FIXTURE_CARD_CODE = 97268402
FIXTURE_SEED = (1, 2, 3, 4)
MIXED_PROBE_SCRIPT_NAME = "ygo_effect_dsl_mixed_channel_probe.lua"
MIXED_PROBE_LUA_SOURCE = b"""local e=Effect.GlobalEffect()
e:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)
e:SetCode(EVENT_STARTUP)
e:SetOperation(function(e,tp,eg,ep,ev,re,r,rp)
    Duel.GetRandomNumber(0,6)
    Duel.TossCoin(0,1)
end)
Duel.RegisterEffect(e,0)
"""
_SOURCE_FILES = (
    "duel.cpp",
    "duel.h",
    "libdebug.cpp",
    "ocgapi.cpp",
    "ocgapi_types.h",
)


def _process_native_calls_until_boundary(
    duel: Any,
) -> list[tuple[Any, bytes, tuple[Any, ...]]]:
    calls: list[tuple[Any, bytes, tuple[Any, ...]]] = []
    duel._transition(DuelState.PROCESSING)
    for _ in range(100):
        raw_status = duel.library.native.OCG_DuelProcess(duel._duel)
        duel._raise_callback_error()
        status = DuelProcessStatus(raw_status)
        calls.append((status, duel._get_message(), duel._drain_logs()))
        if status == DuelProcessStatus.AWAITING:
            duel._transition(DuelState.AWAITING_RESPONSE)
            return calls
        if status == DuelProcessStatus.END:
            duel._transition(DuelState.ENDED)
            return calls
    duel._transition(DuelState.FAILED)
    raise ValueError("mixed-channel fixture exceeded 100 native process calls")


def _git(
    root: Path,
    *args: str,
    text: bool = True,
) -> str | bytes:
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
    api_types = files["ocgapi_types.h"].decode("utf-8")
    api = files["ocgapi.cpp"].decode("utf-8")
    duel = files["duel.cpp"].decode("utf-8")
    duel_header = files["duel.h"].decode("utf-8")
    debug = files["libdebug.cpp"].decode("utf-8")
    callback_signature = next(
        line.strip()
        for line in api_types.splitlines()
        if "typedef void (*OCG_LogHandler)" in line
    )
    checks = {
        "log_callback_has_no_sequence_coordinate": (
            "sequence" not in callback_signature
            and "timestamp" not in callback_signature
        ),
        "message_buffer_has_independent_queue_order": (
            "messages.emplace_back(message)" in duel
            and "std::deque<duel_message> messages" in duel_header
        ),
        "process_flushes_messages_without_log_coordinates": (
            "DuelProcess(OCG_Duel ocg_duel)" in api
            and "pduel->generate_buffer();" in api
        ),
        "script_debug_calls_log_handler_synchronously": (
            "pduel->handle_message(str, OCG_LOG_TYPE_FROM_SCRIPT)" in debug
        ),
    }
    return {
        "checks": checks,
        "commit": commit,
        "conclusion": (
            "public_api_exposes_independent_log_callback_and_message_buffer_"
            "coordinates_without_shared_sequence"
        ),
        "files": [
            {
                "path": relative,
                "sha256": sha256(content).hexdigest(),
                "size": len(content),
            }
            for relative, content in sorted(files.items())
        ],
        "log_callback_signature": callback_signature,
        "status": "no_public_cross_channel_chronology"
        if all(checks.values())
        else "inconclusive",
    }


def _mixed_process_fixture(
    *, external_root: str | Path | None,
) -> dict[str, Any]:
    runtime = resolve_ocgcore_runtime(external_root=external_root)
    assets = resolve_ocgcore_assets(external_root=external_root)
    scripts = CardScriptsProvider(assets.scripts_root)
    player = PlayerConfig(
        starting_lp=8000,
        starting_draw_count=0,
        draw_count_per_turn=0,
    )
    decoder = OcgcoreMessageDecoder()

    with OcgcoreLibrary(runtime) as library:
        with SQLiteCardDataProvider(assets.database_path) as database:
            config = DuelConfig(seed=FIXTURE_SEED, team1=player, team2=player)
            with library.create_duel(config, database, scripts) as duel:
                duel.load_script("constant.lua", scripts.get_script("constant.lua"))
                duel.load_script("utility.lua", scripts.get_script("utility.lua"))
                duel.load_script(
                    DIRECT_RANDOM_TRACE_SCRIPT_NAME,
                    DIRECT_RANDOM_TRACE_LUA_SOURCE,
                )
                duel.load_script(MIXED_PROBE_SCRIPT_NAME, MIXED_PROBE_LUA_SOURCE)
                for team in (0, 1):
                    duel.add_card(
                        NewCard(
                            team=team,
                            duelist=0,
                            code=FIXTURE_CARD_CODE,
                            controller=team,
                            location=0x02,
                            sequence=0,
                            position=0x01,
                        )
                    )
                duel.start()
                native_calls = _process_native_calls_until_boundary(duel)
                batch = decoder.decode_batch(
                    b"".join(message for _, message, _ in native_calls),
                    request_id="cross-channel-ordering:boundary",
                    logs=tuple(
                        log for _, _, logs in native_calls for log in logs
                    ),
                )
                if batch.request is None:
                    raise ValueError("mixed-channel fixture exposed no initial request")
                snapshot = duel.capture_snapshot(
                    pending_request=batch.request,
                    environment={"audit_fixture": "cross_channel_ordering_v1"},
                )
                matching_calls: list[tuple[int, Any, bytes, dict[str, Any]]] = []
                for call_index, (status, message, logs) in enumerate(native_calls):
                    call_batch = decoder.decode_batch(
                        message,
                        request_id=f"cross-channel-ordering:{call_index}",
                        logs=logs,
                    )
                    call_output = build_core_output_trace(
                        call_batch,
                        snapshot=snapshot.to_dict(),
                    )
                    kinds = {event["kind"] for event in call_output["random_events"]}
                    if {"direct_lua_random", "toss_coin"} <= kinds:
                        matching_calls.append(
                            (call_index, status, message, call_output)
                        )
                if len(matching_calls) != 1:
                    raise ValueError(
                        "expected exactly one native call with both channels, got "
                        f"{len(matching_calls)}"
                    )
                call_index, status, message, output = matching_calls[0]

    ordering = build_cross_channel_ordering_evidence(
        output["random_events"],
        native_process_call_count=1,
    )
    return to_canonical_data(
        {
            "core_message_hex": [message.hex()] if message else [],
            "logs": output["logs"],
            "native_call_index": call_index,
            "native_calls_until_request": len(native_calls),
            "ordering": ordering,
            "native_process_call_count": 1,
            "native_status": status.name.lower(),
            "random_events": output["random_events"],
            "request_signature": batch.request.request_signature,
            "state_hash": snapshot.state_hash,
        }
    )


def build_cross_channel_ordering_audit(
    *, external_root: str | Path | None = None,
) -> dict[str, Any]:
    runtime = resolve_ocgcore_runtime(external_root=external_root)
    source_root = runtime.parent.parent / "source"
    lock = load_ocgcore_lock()
    upstream_ref = _git(source_root, "rev-parse", "origin/master")
    assert isinstance(upstream_ref, str)
    if upstream_ref.strip() != UPSTREAM_CORE_COMMIT:
        raise ValueError(
            f"origin/master must be {UPSTREAM_CORE_COMMIT}, got {upstream_ref.strip()}"
        )
    pinned = _source_audit(source_root, str(lock.source["commit"]))
    upstream = _source_audit(source_root, UPSTREAM_CORE_COMMIT)
    mixed = _mixed_process_fixture(external_root=external_root)
    direct_events = [
        event
        for event in mixed["random_events"]
        if event["kind"] == "direct_lua_random"
    ]
    frame_events = [
        event
        for event in mixed["random_events"]
        if event["kind"] == "toss_coin"
    ]
    checks = {
        "canonical_order_is_explicitly_not_emission_order": (
            mixed["ordering"]["semantics"]
            == "canonical_storage_order_is_not_observed_emission_order"
        ),
        "mixed_channels_share_one_process_call": (
            mixed["native_process_call_count"] == 1
            and len(direct_events) == 1
            and len(frame_events) == 1
        ),
        "pinned_core_has_no_public_shared_sequence": (
            pinned["status"] == "no_public_cross_channel_chronology"
        ),
        "upstream_core_has_no_public_shared_sequence": (
            upstream["status"] == "no_public_cross_channel_chronology"
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError("cross-channel ordering audit failed: " + ", ".join(failed))
    verification = verify_ocgcore(external_root=external_root)
    identity = to_canonical_data(
        {
            "checks": checks,
            "decision": {
                "actual_cross_channel_chronology": "unavailable_without_core_patch",
                "canonical_storage_order": mixed["ordering"][
                    "canonical_storage_order"
                ],
                "custom_core_patch": False,
                "replay_trace_schema_changed": False,
            },
            "fixture": {
                "card_code": FIXTURE_CARD_CODE,
                "probe_script_name": MIXED_PROBE_SCRIPT_NAME,
                "probe_script_sha256": sha256(MIXED_PROBE_LUA_SOURCE).hexdigest(),
                "seed": list(FIXTURE_SEED),
            },
            "mixed_process_batch": mixed,
            "ocgcore_binary_sha256": verification["build"]["binary"]["sha256"],
            "schema_version": CROSS_CHANNEL_EVIDENCE_SCHEMA_VERSION,
            "source_audit": {"pinned": pinned, "upstream": upstream},
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="crossordev_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="audit cross-channel chronology for core logs and messages"
    )
    parser.add_argument("--external-root")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = build_cross_channel_ordering_audit(
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
            f"cross-channel-ordering-audit: wrote {args.out} "
            f"evidence_id={evidence['evidence_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
