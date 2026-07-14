from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation import (
    assert_valid_temporary_modifier_observation,
)
from ygo_effect_dsl.route_dsl import (
    assert_valid_route_document,
    load_route_document,
)


TEMPORARY_MODIFIER_EVIDENCE_SCHEMA_VERSION = (
    "ocgcore-temporary-modifier-evidence-v1"
)


def _proof_from_route(
    route: Mapping[str, Any],
    *,
    expected_kind: str,
    expected_values: tuple[int, int, int],
) -> dict[str, Any]:
    assert_valid_route_document(route)
    result = route.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("Route result must be a mapping")
    observation = result.get("temporary_modifier_observation")
    if not isinstance(observation, Mapping):
        raise ValueError("Route is missing its temporary modifier observation")
    assert_valid_temporary_modifier_observation(observation)
    if observation.get("modifier_kind") != expected_kind:
        raise ValueError(
            "temporary modifier kind mismatch: "
            f"expected {expected_kind!r}, got {observation.get('modifier_kind')!r}"
        )
    points = observation["points"]
    actual_values = tuple(
        points[name]["value"] for name in ("baseline", "active", "expired")
    )
    if actual_values != expected_values:
        raise ValueError(
            f"temporary modifier values must be {expected_values}, got {actual_values}"
        )
    if observation.get("boundary_evidence") != "observed_expired":
        raise ValueError("temporary modifier expiration was not observed")
    metric = observation["metric"]
    temporary_report = result.get("evaluation_explanation", {}).get(
        "temporary_effects", {}
    )
    metric_values = temporary_report.get("values", {}).get(metric)
    active_delta = abs(observation["transition"]["active_delta"])
    if metric_values != {
        "durable": 0,
        "excluded_temporary": active_delta,
        "raw": active_delta,
    }:
        raise ValueError(
            f"temporary metric {metric!r} was not excluded from durable value"
        )
    return to_canonical_data(
        {
            "boundary_evidence": observation["boundary_evidence"],
            "durable_evaluation": metric_values,
            "expiration": observation["expiration"],
            "metric": metric,
            "modifier_kind": observation["modifier_kind"],
            "observation_id": observation["observation_id"],
            "points": {
                name: {
                    "checkpoint_step": points[name]["checkpoint_step"],
                    "phase": points[name]["phase"],
                    "state_hash": points[name]["state_hash"],
                    "turn": points[name]["turn"],
                    "value": points[name]["value"],
                }
                for name in ("baseline", "active", "expired")
            },
            "route_id": route["route_id"],
            "source_ref": observation["source_ref"],
            "transition": observation["transition"],
        }
    )


def build_temporary_modifier_evidence(
    *,
    attack_route: Mapping[str, Any],
    effect_negate_route: Mapping[str, Any],
) -> dict[str, Any]:
    identity = to_canonical_data(
        {
            "expiration_normalization": [
                {
                    "dsl_boundary": "end_of_chain",
                    "ocgcore_reset": "RESET_CHAIN",
                    "required_evidence": "post-chain query transition",
                },
                {
                    "dsl_boundary": "end_of_phase",
                    "ocgcore_reset": "RESET_PHASE with a non-End-Phase flag",
                    "required_evidence": "post-phase query transition",
                },
                {
                    "dsl_boundary": "end_of_turn",
                    "ocgcore_reset": "RESET_PHASE with PHASE_END",
                    "required_evidence": "post-END_TURN query transition",
                },
            ],
            "proofs": {
                "effect_negate": _proof_from_route(
                    effect_negate_route,
                    expected_kind="effect_disabled",
                    expected_values=(0, 1, 0),
                ),
                "temporary_attack": _proof_from_route(
                    attack_route,
                    expected_kind="attack_delta",
                    expected_values=(0, 500, 0),
                ),
            },
            "schema_version": TEMPORARY_MODIFIER_EVIDENCE_SCHEMA_VERSION,
            "unverified_policy": {
                "durable_value": 0,
                "rule": (
                    "A modifier without a pinned reset source and a query-observed "
                    "return to baseline remains unverified."
                ),
            },
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="tempevidence_"),
    }


def run_checked_temporary_modifier_evidence(
    *, repo_root: str | Path | None = None
) -> dict[str, Any]:
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    return build_temporary_modifier_evidence(
        attack_route=load_route_document(
            root / "examples" / "prototype" / "real_core_temporary_atk.route.yaml"
        ),
        effect_negate_route=load_route_document(
            root
            / "examples"
            / "prototype"
            / "real_core_effect_veiler_interrupted.route.yaml"
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="collect checked ocgcore temporary modifier evidence"
    )
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = run_checked_temporary_modifier_evidence(repo_root=args.repo_root)
    serialized = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"temporary-modifier-evidence: wrote {args.out} "
            f"evidence_id={evidence['evidence_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
