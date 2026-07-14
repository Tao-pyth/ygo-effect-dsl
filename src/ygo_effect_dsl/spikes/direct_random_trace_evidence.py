from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.bridge.ocgcore import (
    DIRECT_RANDOM_TRACE_LUA_SOURCE,
    DIRECT_RANDOM_TRACE_SCRIPT_NAME,
    CardScriptsProvider,
    DuelConfig,
    NewCard,
    OcgcoreLibrary,
    OcgcoreMessageDecoder,
    PlayerConfig,
    SQLiteCardDataProvider,
    build_core_output_trace,
    direct_random_trace_metadata,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import (
    load_ocgcore_asset_lock,
    resolve_ocgcore_assets,
    resolve_ocgcore_runtime,
    verify_ocgcore,
)


DIRECT_RANDOM_EVIDENCE_SCHEMA_VERSION = "ocgcore-direct-random-evidence-v2"
DIRECT_RANDOM_FIXTURE_CARD_CODE = 97268402
DIRECT_RANDOM_FIXTURE_SCRIPT = "official/c97268402.lua"
DIRECT_RANDOM_FIXTURE_SEED = (1, 2, 3, 4)
DIRECT_RANDOM_PROBE_SCRIPT_NAME = "ygo_effect_dsl_direct_random_probe.lua"
DIRECT_RANDOM_PROBE_LUA_SOURCE = b"""local probe_results = {
    Duel.GetRandomNumber(4),
    Duel.GetRandomNumber(-2, 2),
    Duel.GetRandomNumber(0, 1),
    Duel.GetRandomNumber(0, 1),
    Duel.GetRandomNumber(-2147483648, -2147483648),
    Duel.GetRandomNumber(2147483647, 2147483647)
}
"""


def _run_fixture(
    *,
    instrumented: bool,
    external_root: str | Path | None,
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
    common_state_environment = {
        "audit_fixture": "direct_random_log_transport_equivalence_v2"
    }

    with OcgcoreLibrary(runtime) as library:
        with SQLiteCardDataProvider(assets.database_path) as database:
            config = DuelConfig(
                seed=DIRECT_RANDOM_FIXTURE_SEED,
                team1=player,
                team2=player,
            )
            with library.create_duel(config, database, scripts) as duel:
                duel.load_script("constant.lua", scripts.get_script("constant.lua"))
                duel.load_script("utility.lua", scripts.get_script("utility.lua"))
                if instrumented:
                    duel.load_script(
                        DIRECT_RANDOM_TRACE_SCRIPT_NAME,
                        DIRECT_RANDOM_TRACE_LUA_SOURCE,
                    )
                duel.load_script(
                    DIRECT_RANDOM_PROBE_SCRIPT_NAME,
                    DIRECT_RANDOM_PROBE_LUA_SOURCE,
                )
                for team in (0, 1):
                    duel.add_card(
                        NewCard(
                            team=team,
                            duelist=0,
                            code=DIRECT_RANDOM_FIXTURE_CARD_CODE,
                            controller=team,
                            location=0x02,
                            sequence=0,
                            position=0x01,
                        )
                    )
                duel.start()
                process_batch = duel.process()
                batch = decoder.decode_batch(
                    b"".join(process_batch.messages),
                    request_id="direct-random-audit:0",
                    logs=process_batch.logs,
                )
                request = batch.request
                if request is None:
                    raise ValueError("direct random fixture exposed no initial request")
                snapshot = duel.capture_snapshot(
                    pending_request=request,
                    environment=common_state_environment,
                )
                output = build_core_output_trace(
                    batch,
                    snapshot=snapshot.to_dict(),
                )

    return to_canonical_data(
        {
            "core_message_hex": [message.hex() for message in process_batch.messages],
            "instrumentation": direct_random_trace_metadata(enabled=instrumented),
            "random_events": output["random_events"],
            "request_signature": request.request_signature,
            "state_hash": snapshot.state_hash,
            "trace_logs": output["logs"],
        }
    )


def build_direct_random_trace_evidence(
    *, external_root: str | Path | None = None
) -> dict[str, Any]:
    verification = verify_ocgcore(external_root=external_root)
    asset_lock = load_ocgcore_asset_lock()
    assets = resolve_ocgcore_assets(external_root=external_root)
    scripts = CardScriptsProvider(assets.scripts_root)
    fixture_script = scripts.get_script(f"c{DIRECT_RANDOM_FIXTURE_CARD_CODE}.lua")
    control = _run_fixture(instrumented=False, external_root=external_root)
    instrumented = _run_fixture(instrumented=True, external_root=external_root)

    same_messages = control["core_message_hex"] == instrumented["core_message_hex"]
    same_request = control["request_signature"] == instrumented["request_signature"]
    same_state = control["state_hash"] == instrumented["state_hash"]
    runtime_identity_differs = (
        control["instrumentation"]["instrumentation_id"]
        != instrumented["instrumentation"]["instrumentation_id"]
    )
    control_direct_events = [
        event
        for event in control["random_events"]
        if event["kind"] == "direct_lua_random"
    ]
    direct_events = [
        event
        for event in instrumented["random_events"]
        if event["kind"] == "direct_lua_random"
    ]
    outcomes = [event["outcome"] for event in direct_events]
    checks = {
        "control_has_no_direct_random_events": not control_direct_events,
        "instrumentation_records_all_six_direct_draws": len(direct_events) == 6,
        "int32_boundary_fixed_ranges_preserved": (
            outcomes[4]["minimum"] == outcomes[4]["maximum"] == -(1 << 31)
            and outcomes[5]["minimum"] == outcomes[5]["maximum"] == (1 << 31) - 1
        ),
        "negative_range_preserved": (
            outcomes[1]["minimum"] == -2
            and outcomes[1]["maximum"] == 2
            and -2 <= outcomes[1]["result"] <= 2
        ),
        "one_argument_range_normalized": (
            outcomes[0]["minimum"] == 0
            and outcomes[0]["maximum"] == 4
            and 0 <= outcomes[0]["result"] <= 4
        ),
        "repeated_calls_have_contiguous_indices": [
            outcome["draw_index"] for outcome in outcomes
        ]
        == [1, 2, 3, 4, 5, 6],
        "runtime_identity_differs": runtime_identity_differs,
        "same_core_messages": same_messages,
        "same_request_signature": same_request,
        "same_state_transition": same_state,
        "transport_uses_no_core_message_frames": all(
            event["message_type"] is None for event in direct_events
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(
            "direct random trace fixture failed checks: " + ", ".join(failed)
        )

    identity = {
        "checks": checks,
        "control": control,
        "fixture": {
            "card_code": DIRECT_RANDOM_FIXTURE_CARD_CODE,
            "card_data_source": "pinned_babelcdb_record",
            "card_script_commit": asset_lock.repositories["card_scripts"]["commit"],
            "card_script_path": DIRECT_RANDOM_FIXTURE_SCRIPT,
            "card_script_sha256": sha256(fixture_script).hexdigest(),
            "probe_script_name": DIRECT_RANDOM_PROBE_SCRIPT_NAME,
            "probe_script_sha256": sha256(DIRECT_RANDOM_PROBE_LUA_SOURCE).hexdigest(),
            "seed": list(DIRECT_RANDOM_FIXTURE_SEED),
            "synthetic_card_data_codes": [],
        },
        "instrumented": instrumented,
        "ocgcore_binary_sha256": verification["build"]["binary"]["sha256"],
        "schema_version": DIRECT_RANDOM_EVIDENCE_SCHEMA_VERSION,
    }
    return {
        **to_canonical_data(identity),
        "evidence_id": stable_digest(identity, prefix="rngtraceev_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-root")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = build_direct_random_trace_evidence(external_root=args.external_root)
    serialized = json.dumps(evidence, ensure_ascii=True, indent=2) + "\n"
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"direct-random-trace-evidence: wrote {args.out} "
            f"evidence_id={evidence['evidence_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
