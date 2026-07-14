from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation import (
    RESOURCE_CONSUMPTION_DEFAULT_CONFIG,
    RESOURCE_CONSUMPTION_EVALUATOR_ID,
    RESOURCE_CONSUMPTION_EVALUATOR_VERSION,
    RESOURCE_CONSUMPTION_METRIC,
    build_route_resource_consumption,
)
from ygo_effect_dsl.route_dsl import load_route_document, normalize_and_explain_routes


RESOURCE_CONSUMPTION_EVIDENCE_SCHEMA_VERSION = (
    "route-resource-consumption-evidence-v1"
)
_ROUTE_FILENAMES = (
    "real_core_action_aggregation.route.yaml",
    "real_core_effect_veiler.route.yaml",
    "real_core_effect_veiler_interrupted.route.yaml",
    "real_core_temporary_atk.route.yaml",
)


def build_resource_consumption_evidence(
    *, repo_root: str | Path | None = None
) -> dict[str, Any]:
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    prototype_dir = root / "examples" / "prototype"
    routes = [
        load_route_document(prototype_dir / filename)
        for filename in _ROUTE_FILENAMES
    ]
    reports = [build_route_resource_consumption(route) for route in routes]
    normalization = normalize_and_explain_routes(routes)
    route_evidence = []
    for filename, report in zip(_ROUTE_FILENAMES, reports, strict=True):
        perspective = str(report["perspective"])
        route_evidence.append(
            {
                "explicit_cost_record_count": len(
                    report["explicit_cost_evidence"]["records"]
                ),
                "filename": filename,
                "perspective_vector": report["players"][perspective]["dimensions"],
                "resource_report_id": report["resource_report_id"],
                "route_id": report["route_id"],
                "scalar_total": report["scalar"]["total"],
                "source_state_hashes": report["source_state_hashes"],
            }
        )
    identity = to_canonical_data(
        {
            "calibration": {
                "follow_up_issue": 108,
                "status": "provisional_expert_weights",
                "validation_required": (
                    "multi_deck_same_state_alternatives_and_blind_human_ranking"
                ),
            },
            "default_config": RESOURCE_CONSUMPTION_DEFAULT_CONFIG,
            "evaluator_id": RESOURCE_CONSUMPTION_EVALUATOR_ID,
            "evaluator_version": RESOURCE_CONSUMPTION_EVALUATOR_VERSION,
            "metric": RESOURCE_CONSUMPTION_METRIC,
            "normalization": {
                "minimum_consumption": normalization["rankings"][
                    "minimum_consumption"
                ],
                "report_id": normalization["report_id"],
                "schema_version": normalization["schema_version"],
            },
            "routes": route_evidence,
            "scalar_truth_source": (
                "initial_to_checkpoint_net_state_delta_plus_action_usage"
            ),
            "schema_version": RESOURCE_CONSUMPTION_EVIDENCE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="resourceevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="build checked Route resource-consumption evidence"
    )
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = build_resource_consumption_evidence(repo_root=args.repo_root)
    serialized = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"resource-consumption-evidence: wrote {args.out} "
            f"evidence_id={evidence['evidence_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
