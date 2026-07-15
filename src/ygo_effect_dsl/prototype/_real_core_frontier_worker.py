from __future__ import annotations

import argparse
import json
import sys

from ygo_effect_dsl.engine.canonical import canonical_json
from ygo_effect_dsl.engine.failures import classify_failure
from ygo_effect_dsl.prototype.real_core import (
    WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION,
    run_real_core_worker,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="ygo-effect-dsl-real-core-frontier-worker")
    parser.add_argument("--external-root")
    parser.add_argument("--experiment-path")
    args = parser.parse_args()
    envelope = json.loads(sys.stdin.read())
    if not isinstance(envelope, dict):
        raise ValueError("frontier worker input must be a mapping")
    experiment = envelope.get("experiment")
    action_prefix = envelope.get("action_prefix", [])
    if not isinstance(experiment, dict) or not isinstance(action_prefix, list):
        raise ValueError("frontier worker requires experiment and action_prefix")
    document_kind = envelope.get("document_kind", "search_frontier")
    if document_kind not in {"player_view", "search_frontier"}:
        raise ValueError("frontier worker document_kind is unsupported")
    source_route = envelope.get("source_route")
    viewer = envelope.get("viewer", 0)
    result = run_real_core_worker(
        external_root=args.external_root,
        experiment=experiment,
        experiment_path=args.experiment_path,
        action_prefix=action_prefix,
        source_route=source_route,
        viewer=viewer,
        document_kind=document_kind,
    )
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        failure = classify_failure(exc)
        print(
            canonical_json(
                {
                    "failure": failure.to_dict(),
                    "schema_version": WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION,
                    "status": "failure",
                }
            )
        )
        raise SystemExit(1) from None
