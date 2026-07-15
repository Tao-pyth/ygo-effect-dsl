from __future__ import annotations

import argparse
import json
from pathlib import Path

from ygo_effect_dsl.storage.export import (
    AnalyticsExportFormat,
    AnalyticsExportRequest,
    AnalyticsExportService,
    AnalyticsExportSourceKind,
)
from ygo_effect_dsl.storage.query import (
    AnalyticsQueryRequest,
    AnalyticsQueryService,
    AnalyticsSnapshot,
    AnalyticsSnapshotStore,
)


def _load_json(path: str | Path) -> object:
    return json.loads(Path(path).expanduser().resolve(strict=True).read_text("utf-8"))


def cmd_analytics_export(args: argparse.Namespace) -> int:
    store = AnalyticsSnapshotStore()
    if args.query is not None:
        if args.snapshot is None:
            raise ValueError("--snapshot is required with --query")
        snapshot = AnalyticsSnapshot.from_mapping(_load_json(args.snapshot))
        store.register(snapshot)
        request = AnalyticsExportRequest(
            format=AnalyticsExportFormat(args.format),
            source_kind=AnalyticsExportSourceKind.QUERY,
            query=AnalyticsQueryRequest.from_mapping(_load_json(args.query)),
        )
    else:
        if args.snapshot is not None:
            raise ValueError("--snapshot is only valid with --query")
        request = AnalyticsExportRequest(
            format=AnalyticsExportFormat(args.format),
            source_kind=AnalyticsExportSourceKind.COMPARISON,
            comparison=_load_json(args.comparison),
        )
    service = AnalyticsExportService(AnalyticsQueryService(store))
    result = service.write(request, args.out)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


__all__ = ["cmd_analytics_export"]
