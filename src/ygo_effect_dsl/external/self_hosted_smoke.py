from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text


SELF_HOSTED_SMOKE_SCHEMA_VERSION = "self-hosted-real-core-smoke-v1"


def build_success_summary(
    search: Mapping[str, Any],
    replay: Mapping[str, Any],
    lua: Mapping[str, Any],
    *,
    commit: str,
    workflow_run_id: str,
) -> dict[str, Any]:
    if search.get("status") != "complete":
        raise ValueError("search report is not complete")
    if replay.get("status") != "verified":
        raise ValueError("Replay report is not verified")
    if lua.get("status") not in {"smoke_only", "qualified"}:
        raise ValueError("Lua qualification did not succeed")
    route_id = search.get("best_route", {}).get("route_id")
    if not route_id or replay.get("route", {}).get("route_id") != route_id:
        raise ValueError("Search and Replay Route IDs differ")
    runtime = replay.get("runtime", {})
    lua_runtime = lua.get("runtime", {})
    if runtime.get("core_lock_id") != lua_runtime.get("lock_id"):
        raise ValueError("Lua and Replay core locks differ")
    if runtime.get("core_binary_sha256") != lua_runtime.get("binary_sha256"):
        raise ValueError("Lua and Replay core binaries differ")
    identity = to_canonical_data(
        {
            "asset_lock_id": runtime.get("asset_lock_id"),
            "commit": commit,
            "core_api": runtime.get("core_api"),
            "core_binary_sha256": runtime.get("core_binary_sha256"),
            "core_lock_id": runtime.get("core_lock_id"),
            "lua_qualification_id": lua.get("qualification_id"),
            "lua_status": lua.get("status"),
            "replay_verification_id": replay.get("verification_id"),
            "route_id": route_id,
            "schema_version": SELF_HOSTED_SMOKE_SCHEMA_VERSION,
            "search_run_id": search.get("run_id"),
            "status": "success",
            "terminal_state_hash": replay.get("replay", {}).get(
                "terminal_state_hash"
            ),
            "workflow_run_id": workflow_run_id,
        }
    )
    return {**identity, "evidence_id": stable_digest(identity, prefix="realcoresmoke_")}


def main() -> int:
    parser = argparse.ArgumentParser(prog="self-hosted-real-core-smoke-evidence")
    parser.add_argument("--search", required=True)
    parser.add_argument("--replay", required=True)
    parser.add_argument("--lua", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", "local"))
    parser.add_argument(
        "--workflow-run-id", default=os.environ.get("GITHUB_RUN_ID", "local")
    )
    args = parser.parse_args()
    load = lambda path: json.loads(Path(path).read_text(encoding="utf-8-sig"))
    evidence = build_success_summary(
        load(args.search),
        load(args.replay),
        load(args.lua),
        commit=args.commit,
        workflow_run_id=args.workflow_run_id,
    )
    atomic_write_text(args.out, canonical_json(evidence) + "\n")
    print(f"self-hosted-real-core-smoke-evidence: ok evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
