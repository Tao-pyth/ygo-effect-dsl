from __future__ import annotations

import argparse

from ygo_effect_dsl.engine.canonical import canonical_json
from ygo_effect_dsl.storage import JobCatalog, job_status_document


def cmd_job_inspect(args: argparse.Namespace) -> int:
    document = job_status_document(
        JobCatalog(args.catalog),
        args.job_id,
    )
    print(canonical_json(document))
    return 0


__all__ = ["cmd_job_inspect"]
