from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.spikes.real_core_replay_benchmark import (
    REAL_CORE_REPLAY_BENCHMARK_SCHEMA_VERSION,
)


RESOLVER_INDEX_POLICY_SCHEMA_VERSION = "resolver-index-policy-v1"


def build_resolver_index_policy(
    benchmark: Mapping[str, Any],
) -> dict[str, Any]:
    if benchmark.get("schema_version") != REAL_CORE_REPLAY_BENCHMARK_SCHEMA_VERSION:
        raise ValueError("unsupported real-core Replay benchmark evidence")
    resolver = benchmark.get("resolver_index")
    if not isinstance(resolver, Mapping):
        raise ValueError("benchmark resolver evidence is missing")
    index = resolver.get("index")
    if not isinstance(index, Mapping) or index.get("persistence") != "process_local_only":
        raise ValueError("benchmark must use the checked process-local resolver")
    cold = float(resolver["cold_resolution_seconds"])
    warm = float(resolver["warm_resolution_seconds"])
    if cold <= 0 or warm <= 0:
        raise ValueError("resolver timing evidence must be positive")

    identity = to_canonical_data(
        {
            "benchmark_id": benchmark["benchmark_id"],
            "candidates": [
                {
                    "decision": "rejected",
                    "design": "asset-keyed-serialized-index",
                    "reason": (
                        "safe reuse still requires live directory identity, exact-case, "
                        "collision, reparse-point, and file identity checks; no measured "
                        "end-to-end advantage remains after preserving that boundary"
                    ),
                },
                {
                    "decision": "rejected_for_v0.3",
                    "design": "resident-native-worker",
                    "measured_resolver_speedup": cold / warm,
                    "reason": (
                        "warm resolver lookup is faster, but a resident native worker "
                        "changes duel isolation, crash replacement, and state cleanup"
                    ),
                },
            ],
            "mutation_contract": {
                "case_collision": "fail_close_before_read",
                "concurrent_readers": "same_content_identity",
                "directory_identity": "revalidate_before_index_reuse",
                "file_identity": "revalidate_before_during_after_read",
                "reparse_point": "fail_close_before_read",
            },
            "rollback": "discard process-local index by terminating the worker",
            "schema_version": RESOLVER_INDEX_POLICY_SCHEMA_VERSION,
            "selected_mode": "checked_process_local",
            "selection": "measured_rejection_of_cross_process_and_resident_reuse",
        }
    )
    return {
        **identity,
        "policy_id": stable_digest(identity, prefix="resolverpolicy_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="resolver-index-policy")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    benchmark = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    policy = build_resolver_index_policy(benchmark)
    atomic_write_text(args.out, canonical_json(policy) + "\n")
    print(f"resolver-index-policy: ok policy_id={policy['policy_id']} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
