from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

from ygo_effect_dsl.engine.bridge.ocgcore import (
    CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION,
    CARD_INSTANCE_TRACE_V2_LOG_PREFIX,
    CARD_INSTANCE_TRACE_V2_SCHEMA_VERSION,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.interruption import (
    InterruptionTarget,
    build_additional_card_attribution_v2,
)
from ygo_effect_dsl.prototype.real_core import run_real_core_worker


CARD_INSTANCE_V2_EVIDENCE_SCHEMA_VERSION = "card-instance-route-evidence-v2"
_EXPERIMENTS = Path(__file__).resolve().parents[3] / "examples" / "experiments"
_ROUTE_NAMES = (
    "control_no_card",
    "interrupted_no_card",
    "control_with_card",
    "interrupted_with_card",
)


def _experiment(name: str) -> dict[str, Any]:
    path = _EXPERIMENTS / f"real_core_recovery_{name}.yaml"
    experiment = yaml.safe_load(path.read_text(encoding="utf-8"))
    experiment["runner"]["card_instance_provenance"] = "v2"
    return experiment


def _interrupted_route(name: str, control: dict[str, Any]) -> dict[str, Any]:
    experiment = _experiment(name)
    definition = experiment["interruption"]["definitions"][0]
    step = int(definition["target"]["step"])
    definition["base_route_id"] = control["route_id"]
    definition["target"] = InterruptionTarget.from_replay_event(
        control["replay"]["events"][step]
    ).to_dict()
    return run_real_core_worker(experiment=experiment)


def _route_summary(route: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(route, ensure_ascii=False, sort_keys=True)
    provenance = route["presentation"]["card_instance_provenance"]
    return to_canonical_data(
        {
            "action_ids": [
                event["action"]["action_id"] for event in route["replay"]["events"]
            ],
            "checkpoint_state_hashes": [
                checkpoint["state_hash"] for checkpoint in route["checkpoints"]
            ],
            "initial_state_hash": route["replay"]["initial_snapshot"]["state_hash"],
            "instance_owners": sorted(
                {item["owner"] for item in provenance["instances"]}
            ),
            "movement_kinds": sorted(
                {
                    item["movement_kind"]
                    for item in provenance["movement_transitions"]
                }
            ),
            "private_trace_absent": (
                '"card_id"' not in serialized
                and CARD_INSTANCE_TRACE_V2_LOG_PREFIX not in serialized
            ),
            "provenance_id": provenance["provenance_id"],
            "request_boundaries": provenance["request_boundaries"],
            "shuffle_kinds": sorted(
                {item["mutation"] for item in provenance["shuffle_boundaries"]}
            ),
            "request_signatures": route["result"]["request_signatures"],
            "route_id": route["route_id"],
            "terminal_state_hash": route["result"]["terminal_board"]["state_hash"],
        }
    )


def build_card_instance_v2_run() -> dict[str, Any]:
    control_no_card = run_real_core_worker(
        experiment=_experiment("control_no_card")
    )
    interrupted_no_card = _interrupted_route(
        "interrupted_no_card", control_no_card
    )
    control_with_card = run_real_core_worker(
        experiment=_experiment("control_with_card")
    )
    interrupted_with_card = _interrupted_route(
        "interrupted_with_card", control_with_card
    )
    routes = {
        "control_no_card": control_no_card,
        "interrupted_no_card": interrupted_no_card,
        "control_with_card": control_with_card,
        "interrupted_with_card": interrupted_with_card,
    }
    attribution = build_additional_card_attribution_v2(
        control_no_card,
        interrupted_no_card,
        [
            {
                "trial_id": "recovery_card_23434538",
                "control_route": control_with_card,
                "interrupted_route": interrupted_with_card,
            }
        ],
    )
    return to_canonical_data(
        {
            "attribution": attribution,
            "routes": {
                name: _route_summary(routes[name]) for name in _ROUTE_NAMES
            },
        }
    )


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
            "ygo_effect_dsl.spikes.card_instance_v2_evidence",
            "--single-run",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(result.stdout)
    return int(payload["pid"]), payload["run"]


def build_card_instance_v2_evidence() -> dict[str, Any]:
    first_pid, first = _fresh_run()
    second_pid, second = _fresh_run()
    checks = {
        "action_state_route_and_attribution_repeat_across_fresh_workers": (
            first_pid != second_pid and first == second
        ),
        "all_card_candidate_requests_use_complete_boundary_scans": all(
            summary["request_boundaries"]
            and all(
                boundary["mode"] == "complete_scan_in_request_batch"
                for boundary in summary["request_boundaries"]
            )
            for summary in first["routes"].values()
        ),
        "attribution_uses_persistent_instance_identity": (
            first["attribution"]["instance_identity_scope"][
                "duplicate_same_code_policy"
            ]
            == "compare_persistent_instance_id"
        ),
        "public_route_json_omits_raw_card_id_and_probe_logs": all(
            summary["private_trace_absent"]
            for summary in first["routes"].values()
        ),
        "representative_route_identity_covers_token_owner_and_compaction": (
            {0, 1}
            == {
                owner
                for summary in first["routes"].values()
                for owner in summary["instance_owners"]
            }
            and {"generated_token", "location_move", "sequence_change"}.issubset(
                {
                    kind
                    for summary in first["routes"].values()
                    for kind in summary["movement_kinds"]
                }
            )
            and "shuffle_hand"
            in {
                kind
                for summary in first["routes"].values()
                for kind in summary["shuffle_kinds"]
            }
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError("card instance v2 evidence failed: " + ", ".join(failed))
    identity = to_canonical_data(
        {
            "attribution": first["attribution"],
            "checks": checks,
            "fresh_worker_process_count": 2,
            "routes": first["routes"],
            "schema_version": CARD_INSTANCE_V2_EVIDENCE_SCHEMA_VERSION,
            "trace_schema_version": CARD_INSTANCE_TRACE_V2_SCHEMA_VERSION,
            "provenance_schema_version": (
                CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION
            ),
        }
    )
    return {**identity, "evidence_id": stable_digest(identity, prefix="cardv2ev_")}


def main() -> int:
    parser = argparse.ArgumentParser(description="build card-instance v2 evidence")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--single-run", action="store_true")
    args = parser.parse_args()
    if args.single_run:
        print(
            json.dumps(
                {"pid": os.getpid(), "run": build_card_instance_v2_run()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    evidence = build_card_instance_v2_evidence()
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.report_out is not None:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(
            json.dumps(
                evidence["attribution"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        "card-instance-v2: "
        f"evidence_id={evidence['evidence_id']} "
        f"attribution_id={evidence['attribution']['attribution_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
