from __future__ import annotations

import argparse
import json
import os
import sys
import time

from ygo_effect_dsl.engine.failures import classify_failure
from ygo_effect_dsl.engine.canonical import canonical_json
from ygo_effect_dsl.prototype.real_core import run_real_core_worker
from ygo_effect_dsl.prototype.real_core import (
    WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="ygo-effect-dsl-real-core-worker")
    parser.add_argument("--external-root")
    parser.add_argument(
        "--document-kind",
        choices=("route", "activation_rollback_probe"),
        default="route",
    )
    parser.add_argument("--experiment-stdin", action="store_true")
    parser.add_argument(
        "--stress-failure",
        choices=("worker_crash", "worker_timeout", "callback_error"),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    experiment = None
    if args.experiment_stdin:
        try:
            experiment = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            raise ValueError("worker received invalid Experiment JSON") from exc
    if args.stress_failure == "worker_crash":
        os._exit(86)
    if args.stress_failure == "worker_timeout":
        time.sleep(5.0)
    route = run_real_core_worker(
        external_root=args.external_root,
        experiment=experiment,
        stress_failure=args.stress_failure,
        document_kind=args.document_kind,
    )
    print(json.dumps(route, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
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
