from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import tempfile
import threading
import time
from typing import Any, TypeVar

from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.storage import (
    AggregationRecord,
    AnalyticsExportFormat,
    AnalyticsExportQueue,
    AnalyticsExportRequest,
    AnalyticsExportService,
    AnalyticsExportSourceKind,
    AnalyticsExportWorker,
    AnalyticsFilter,
    AnalyticsQueryError,
    AnalyticsQueryRequest,
    AnalyticsQueryService,
    AnalyticsSnapshot,
    AnalyticsSnapshotStore,
    AnalyticsSort,
    JobState,
    ParquetLayoutPolicy,
    RawLogRecord,
    RunCatalog,
    RunRecord,
    RunStatus,
    activate_aggregation_snapshot,
    aggregation_arrow_schema,
    analytics_row_from_aggregation,
    compact_aggregation_dataset,
    current_aggregation_snapshot_id,
    migrate_aggregation_snapshot,
    parquet_fault_at,
    read_aggregation_dataset,
    read_aggregation_snapshot,
    rollback_aggregation_snapshot,
    write_raw_log,
)
from ygo_effect_dsl.storage.export import (
    MAX_EXPORT_BYTES,
    MAX_EXPORT_OUTPUT_ROWS,
    MAX_EXPORT_SCAN_ROWS,
)
from ygo_effect_dsl.storage.parquet_lifecycle import (
    InjectedParquetLifecycleFault,
    ParquetLifecycleFaultPoint,
)
from ygo_effect_dsl.version import __version__


ANALYTICS_SCALE_CALIBRATION_SCHEMA_VERSION = "analytics-scale-calibration-v1"
ANALYTICS_SCALE_SAMPLE_SCHEMA_VERSION = "analytics-scale-sample-v1"
FULL_RUN_COUNT = 100_000
FULL_EVENT_ROW_COUNT = 1_000_000
FULL_ANALYTICAL_ROW_COUNT = 100_000
_RUN_DATE = "2026-07-16"
_T = TypeVar("_T")


def analytics_scale_calibration_contract_document() -> dict[str, Any]:
    return to_canonical_data(
        {
            "execution": {
                "ci": "same harness with reduced positive row counts",
                "full_scale": "manual or self-hosted workflow",
            },
            "limits": {
                "analytical_rows_minimum": FULL_ANALYTICAL_ROW_COUNT,
                "event_decision_rows_minimum": FULL_EVENT_ROW_COUNT,
                "runs_minimum": FULL_RUN_COUNT,
            },
            "operations": [
                "raw_event_ingest",
                "catalog_batch_create_finish",
                "aggregation_publish_read",
                "aggregation_compaction",
                "aggregation_migration_rollback",
                "aggregation_crash_recovery",
                "persistent_filter_sort_drill_down_comparison",
                "application_query",
                "desktop_bridge_query",
                "json_csv_parquet_export",
                "concurrent_catalog_ingest_query",
                "concurrent_compaction_read",
                "concurrent_export_cancel",
            ],
            "outputs": {
                "samples": "Parquet operation samples with latency, throughput, and RSS",
                "summary": "content-addressed JSON with hardware/software/workload manifest",
            },
            "ui_boundary": {
                "persistent": "Python desktop bridge query measurement",
                "renderer": "separate deterministic 100k-row Playwright evidence",
            },
            "version": ANALYTICS_SCALE_CALIBRATION_SCHEMA_VERSION,
        }
    )


@dataclass(frozen=True)
class AnalyticsScaleWorkload:
    run_count: int = FULL_RUN_COUNT
    event_row_count: int = FULL_EVENT_ROW_COUNT
    analytical_row_count: int = FULL_ANALYTICAL_ROW_COUNT
    query_samples: int = 9
    legacy_batch_rows: int = 1_000

    def __post_init__(self) -> None:
        for value, name in (
            (self.run_count, "run_count"),
            (self.event_row_count, "event_row_count"),
            (self.analytical_row_count, "analytical_row_count"),
            (self.query_samples, "query_samples"),
            (self.legacy_batch_rows, "legacy_batch_rows"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be an integer >= 1")
        if self.event_row_count < self.run_count:
            raise ValueError("event_row_count must be at least run_count")
        if self.analytical_row_count < self.run_count:
            raise ValueError("analytical_row_count must be at least run_count")

    @property
    def full_scale(self) -> bool:
        return (
            self.run_count >= FULL_RUN_COUNT
            and self.event_row_count >= FULL_EVENT_ROW_COUNT
            and self.analytical_row_count >= FULL_ANALYTICAL_ROW_COUNT
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "analytical_row_count": self.analytical_row_count,
            "event_row_count": self.event_row_count,
            "full_scale": self.full_scale,
            "legacy_batch_rows": self.legacy_batch_rows,
            "query_samples": self.query_samples,
            "run_count": self.run_count,
        }


class _RssMonitor:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.peak = _rss_bytes()

    def __enter__(self) -> "_RssMonitor":
        def sample() -> None:
            while not self._stop.wait(0.01):
                self.peak = max(self.peak, _rss_bytes())

        self._thread = threading.Thread(target=sample, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.peak = max(self.peak, _rss_bytes())


class _Measurements:
    def __init__(self) -> None:
        self.samples: list[dict[str, Any]] = []

    def measure(
        self,
        operation: str,
        callback: Callable[[], _T],
        *,
        rows: int,
        detail: Mapping[str, Any] | None = None,
    ) -> _T:
        rss_before = _rss_bytes()
        print(f"calibration: start {operation} rows={rows}", flush=True)
        started = time.perf_counter()
        with _RssMonitor() as monitor:
            result = callback()
        elapsed = time.perf_counter() - started
        rss_after = _rss_bytes()
        self.samples.append(
            {
                "detail": to_canonical_data(dict(detail or {})),
                "elapsed_ms": round(elapsed * 1_000, 6),
                "operation": operation,
                "rows": rows,
                "rss_after_bytes": rss_after,
                "rss_before_bytes": rss_before,
                "rss_peak_bytes": monitor.peak,
                "sample_index": sum(
                    item["operation"] == operation for item in self.samples
                ),
                "schema_version": ANALYTICS_SCALE_SAMPLE_SCHEMA_VERSION,
                "throughput_rows_per_second": round(rows / elapsed, 3),
            }
        )
        print(
            f"calibration: complete {operation} elapsed_ms={elapsed * 1_000:.3f} "
            f"peak_rss_bytes={monitor.peak}",
            flush=True,
        )
        return result

    def summary(self) -> dict[str, Any]:
        operations = sorted({item["operation"] for item in self.samples})
        result: dict[str, Any] = {}
        for operation in operations:
            selected = [
                item for item in self.samples if item["operation"] == operation
            ]
            elapsed = [float(item["elapsed_ms"]) for item in selected]
            throughput = [
                float(item["throughput_rows_per_second"]) for item in selected
            ]
            result[operation] = {
                "elapsed_ms": _distribution(elapsed),
                "peak_rss_bytes": max(
                    int(item["rss_peak_bytes"]) for item in selected
                ),
                "sample_count": len(selected),
                "throughput_rows_per_second": _distribution(throughput),
            }
        return result


def _rss_bytes() -> int:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return 0


def _distribution(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise ValueError("a distribution requires at least one value")
    ordered = sorted(values)
    return {
        "max": round(max(ordered), 6),
        "min": round(min(ordered), 6),
        "p50": round(_percentile(ordered, 0.50), 6),
        "p95": round(_percentile(ordered, 0.95), 6),
        "p99": round(_percentile(ordered, 0.99), 6),
    }


def _percentile(ordered: Sequence[float], percentile: float) -> float:
    if not ordered:
        raise ValueError("percentile input must not be empty")
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_stats(root: Path) -> dict[str, int]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "bytes": sum(path.stat().st_size for path in files),
        "file_count": len(files),
    }


def _run_id(index: int) -> str:
    return f"run_scale_{index:08d}"


def _route_id(index: int) -> str:
    return f"route_scale_{index:08d}"


def _write_raw_workload(root: Path, workload: AnalyticsScaleWorkload) -> None:
    quotient, remainder = divmod(workload.event_row_count, workload.run_count)
    for run_index in range(workload.run_count):
        count = quotient + int(run_index < remainder)
        run_id = _run_id(run_index)
        shard = root / f"shard-{run_index // 1_000:05d}"
        records = tuple(
            RawLogRecord(
                run_id=run_id,
                sequence=sequence,
                event_type=(
                    "run_started"
                    if sequence == 0
                    else "decision_observed"
                ),
                payload={
                    "decision_index": sequence,
                    "experiment_id": "experiment_scale_v05",
                },
            )
            for sequence in range(count)
        )
        write_raw_log(shard / f"{run_id}.jsonl", records)


def _catalog_records(workload: AnalyticsScaleWorkload) -> tuple[RunRecord, ...]:
    return tuple(
        RunRecord(
            run_id=_run_id(index),
            experiment_id="experiment_scale_v05",
            status=RunStatus.RUNNING,
            started_at="2026-07-16T00:00:00Z",
        )
        for index in range(workload.run_count)
    )


def _aggregation_records(
    workload: AnalyticsScaleWorkload,
) -> tuple[AggregationRecord, ...]:
    return tuple(
        AggregationRecord(
            run_id=_run_id(index % workload.run_count),
            route_id=_route_id(index),
            experiment_id="experiment_scale_v05",
            evaluator_id="board-score",
            evaluator_version="1",
            evaluator_config_hash="evalcfg_scale_v05",
            run_date=_RUN_DATE,
            target_board=("peak_board" if index % 2 == 0 else "terminal_board"),
            state_hash=f"state_scale_{index:08d}",
            success=index % 5 != 0,
            score=float((index * 17) % 101) / 10,
            action_count=(index * 7) % 80,
        )
        for index in range(workload.analytical_row_count)
    )


def _write_legacy_batches(
    root: Path,
    records: Sequence[AggregationRecord],
    *,
    rows_per_file: int,
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    destination = (
        root
        / "evaluator_version=1"
        / "experiment_id=experiment_scale_v05"
        / f"run_date={_RUN_DATE}"
    )
    destination.mkdir(parents=True, exist_ok=True)
    schema = aggregation_arrow_schema()
    for start in range(0, len(records), rows_per_file):
        chunk = records[start : start + rows_per_file]
        table = pa.Table.from_pylist(
            [record.to_dict() for record in chunk], schema=schema
        )
        pq.write_table(
            table,
            destination / f"batch-{start // rows_per_file:06d}.parquet",
            compression="zstd",
            compression_level=3,
            row_group_size=min(16_384, len(chunk)),
        )


def _active_arrow_table(root: Path) -> Any:
    import pyarrow as pa
    import pyarrow.parquet as pq

    snapshot = read_aggregation_snapshot(root)
    tables = [
        pq.read_table(
            snapshot.manifest_path.parent / item.relative_path,
            schema=aggregation_arrow_schema(),
        )
        for item in snapshot.manifest.files
    ]
    return pa.concat_tables(tables) if len(tables) > 1 else tables[0]


def _persistent_query(table: Any) -> dict[str, Any]:
    import pyarrow.compute as pc

    selected = table.filter(
        pc.and_(pc.greater_equal(table["score"], 5.0), table["success"])
    ).sort_by([("score", "descending"), ("run_id", "ascending")])
    page = selected.slice(0, min(500, selected.num_rows))
    return {
        "matched_rows": selected.num_rows,
        "page_digest": stable_digest(page.to_pylist(), prefix="scalepage_"),
        "page_rows": page.num_rows,
    }


def _persistent_drill_down(table: Any, run_id: str) -> dict[str, Any]:
    import pyarrow.compute as pc

    selected = table.filter(pc.equal(table["run_id"], run_id))
    return {
        "row_count": selected.num_rows,
        "row_digest": stable_digest(selected.to_pylist(), prefix="scaledrill_"),
    }


def _persistent_comparison(table: Any) -> dict[str, Any]:
    grouped = table.group_by("success").aggregate(
        [("score", "mean"), ("action_count", "mean"), ("run_id", "count")]
    )
    rows = sorted(grouped.to_pylist(), key=lambda item: str(item["success"]))
    return {
        "group_count": len(rows),
        "result_digest": stable_digest(rows, prefix="scalecomparison_"),
    }


def _application_snapshot(
    records: Sequence[AggregationRecord],
) -> AnalyticsSnapshot:
    rows = tuple(
        analytics_row_from_aggregation(
            record,
            dimensions={
                "card": ["scale-card-a", "scale-card-b"],
                "deck": f"deck_scale_{index % 8}",
                "interruption": ["none" if index % 3 else "ash-blossom"],
                "status": "complete",
                "strategy": "random-search-v1",
            },
        )
        for index, record in enumerate(records)
    )
    return AnalyticsSnapshot(rows=rows, source_ids=("scale-calibration-v1",))


def _query_request(snapshot_id: str | None = None) -> AnalyticsQueryRequest:
    return AnalyticsQueryRequest(
        fields=("run", "deck", "score", "success", "status", "route"),
        filters=(AnalyticsFilter("score", "gte", 5.0),),
        sort=(AnalyticsSort("score", "desc"), AnalyticsSort("run", "asc")),
        limit=500,
        snapshot_id=snapshot_id,
    )


def _measure_cancel(
    root: Path,
    export_service: AnalyticsExportService,
    request: AnalyticsExportRequest,
) -> dict[str, Any]:
    queue = AnalyticsExportQueue(root, export_service)
    job = queue.enqueue(request, created_at="2026-07-16T00:00:00Z")
    started = threading.Event()

    def blocking_build(
        export_request: AnalyticsExportRequest,
        *,
        cancel_requested: Callable[[], bool],
    ) -> Any:
        started.set()
        while not cancel_requested():
            time.sleep(0.001)
        raise InterruptedError("scale export cancellation requested")

    worker = AnalyticsExportWorker(
        queue,
        now=lambda: "2026-07-16T00:00:00Z",
        build=blocking_build,
    )
    outcomes: list[Any] = []
    thread = threading.Thread(target=lambda: outcomes.append(worker.run_once()))
    thread.start()
    if not started.wait(5.0):
        raise RuntimeError("scale export worker did not start")
    requested_at = time.perf_counter()
    queue.catalog.request_cancel(
        job.job_id,
        actor="scale-calibration",
        now="2026-07-16T00:00:00Z",
        reason="scale_cancel_probe",
    )
    thread.join(timeout=10.0)
    if thread.is_alive() or not outcomes:
        raise RuntimeError("scale export worker did not acknowledge cancellation")
    final = queue.catalog.get_job(job.job_id)
    if final is None or final.state != JobState.CANCELLED:
        raise RuntimeError("scale export cancellation did not reach cancelled")
    return {
        "acknowledgement_ms": round(
            (time.perf_counter() - requested_at) * 1_000, 6
        ),
        "outcome": outcomes[0].status,
        "state": final.state.value,
    }


def _measure_concurrent_catalog_ingest_query(
    catalog: RunCatalog,
    query_service: AnalyticsQueryService,
    request: AnalyticsQueryRequest,
    *,
    delta_count: int,
) -> dict[str, Any]:
    ready = threading.Barrier(2)
    failures: list[BaseException] = []

    def ingest() -> None:
        try:
            records = tuple(
                RunRecord(
                    run_id=f"run_scale_delta_{index:08d}",
                    experiment_id="experiment_scale_v05",
                    status=RunStatus.RUNNING,
                    started_at="2026-07-16T00:20:00Z",
                )
                for index in range(delta_count)
            )
            ready.wait(timeout=5.0)
            catalog.create_runs(records)
            catalog.finish_runs(
                (record.run_id for record in records),
                status=RunStatus.COMPLETE,
                finished_at="2026-07-16T00:21:00Z",
            )
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=ingest)
    thread.start()
    ready.wait(timeout=5.0)
    response = query_service.execute(request)
    thread.join(timeout=30.0)
    if thread.is_alive():
        raise RuntimeError("concurrent catalog ingest did not finish")
    if failures:
        raise RuntimeError("concurrent catalog ingest failed") from failures[0]
    return {
        "delta_runs": delta_count,
        "query_rows": len(response.rows),
        "query_snapshot_id": response.snapshot_id,
    }


def _measure_concurrent_compaction_read(
    root: Path,
    policy: ParquetLayoutPolicy,
    *,
    expected_rows: int,
) -> dict[str, Any]:
    before_id = current_aggregation_snapshot_id(root)
    failures: list[BaseException] = []

    def compact() -> None:
        try:
            compact_aggregation_dataset(
                root,
                created_by_job_id="job_scale_concurrent_compaction",
                policy=policy,
            )
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=compact)
    thread.start()
    observed = _active_arrow_table(root)
    thread.join(timeout=120.0)
    if thread.is_alive():
        raise RuntimeError("concurrent compaction did not finish")
    if failures:
        raise RuntimeError("concurrent compaction failed") from failures[0]
    after = _active_arrow_table(root)
    after_id = current_aggregation_snapshot_id(root)
    if observed.num_rows != expected_rows or after.num_rows != expected_rows:
        raise ValueError("concurrent compaction exposed an incomplete snapshot")
    observed_digest = _persistent_comparison(observed)["result_digest"]
    after_digest = _persistent_comparison(after)["result_digest"]
    if observed_digest != after_digest:
        raise ValueError("concurrent compaction changed query semantics")
    return {
        "after_snapshot_id": after_id,
        "before_snapshot_id": before_id,
        "observed_complete_rows": observed.num_rows,
        "semantic_digest": after_digest,
    }


def _write_sample_parquet(path: Path, samples: Sequence[Mapping[str, Any]]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [
        {
            "detail_json": json.dumps(
                sample["detail"], separators=(",", ":"), sort_keys=True
            ),
            "elapsed_ms": sample["elapsed_ms"],
            "operation": sample["operation"],
            "rows": sample["rows"],
            "rss_after_bytes": sample["rss_after_bytes"],
            "rss_before_bytes": sample["rss_before_bytes"],
            "rss_peak_bytes": sample["rss_peak_bytes"],
            "sample_index": sample["sample_index"],
            "schema_version": sample["schema_version"],
            "throughput_rows_per_second": sample[
                "throughput_rows_per_second"
            ],
        }
        for sample in samples
    ]
    table = pa.Table.from_pylist(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        pq.write_table(table, temporary, compression="zstd")
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _hardware_manifest(root: Path) -> dict[str, Any]:
    memory_total = None
    try:
        import psutil

        memory_total = int(psutil.virtual_memory().total)
    except (ImportError, OSError):
        pass
    usage = shutil.disk_usage(root)
    return {
        "cpu_logical_count": os.cpu_count(),
        "memory_total_bytes": memory_total,
        "platform": platform.platform(),
        "work_disk_free_bytes_at_start": usage.free,
        "work_disk_total_bytes": usage.total,
    }


def _renderer_evidence_summary() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "docs" / "ui" / "evidence" / "desktop_virtual_table.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "backend": document["scope"]["backend"],
        "dom_rows_max": document["scale"]["maximum_observed_dom_rows"],
        "evidence_id": document["evidence_id"],
        "filter_response_ms": round(
            float(document["pagination"]["filter_response_seconds"]) * 1_000,
            6,
        ),
        "keyboard_response_ms": round(
            float(document["accessibility"]["keyboard_response_seconds"]) * 1_000,
            6,
        ),
        "loaded_rows": document["scale"]["loaded_rows"],
        "total_page_load_ms": round(
            float(document["scale"]["elapsed_seconds"]) * 1_000, 6
        ),
    }


def run_analytics_scale_calibration(
    workload: AnalyticsScaleWorkload,
    *,
    work_root: Path,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    import pyarrow

    root = work_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    hardware = _hardware_manifest(root)
    measurements = _Measurements()
    raw_root = root / "raw"
    catalog_path = root / "runs.sqlite3"
    analytics_root = root / "analytics"

    measurements.measure(
        "raw_event_ingest",
        lambda: _write_raw_workload(raw_root, workload),
        rows=workload.event_row_count,
    )
    raw_stats = _directory_stats(raw_root)
    if raw_stats["file_count"] != workload.run_count:
        raise ValueError("raw event workload did not create one file per run")

    catalog = RunCatalog(catalog_path)
    catalog_records = measurements.measure(
        "catalog_record_materialization",
        lambda: _catalog_records(workload),
        rows=workload.run_count,
    )
    measurements.measure(
        "catalog_batch_create",
        lambda: catalog.create_runs(catalog_records),
        rows=workload.run_count,
    )
    measurements.measure(
        "catalog_batch_finish",
        lambda: catalog.finish_runs(
            (record.run_id for record in catalog_records),
            status=RunStatus.COMPLETE,
            finished_at="2026-07-16T00:10:00Z",
        ),
        rows=workload.run_count,
    )
    with closing(sqlite3.connect(catalog_path)) as connection:
        catalog_complete = int(
            connection.execute(
                "SELECT COUNT(*) FROM runs WHERE status='complete'"
            ).fetchone()[0]
        )
    if catalog_complete != workload.run_count:
        raise ValueError("run catalog completion count does not match workload")

    records = measurements.measure(
        "aggregation_record_materialization",
        lambda: _aggregation_records(workload),
        rows=workload.analytical_row_count,
    )
    measurements.measure(
        "aggregation_legacy_publish",
        lambda: _write_legacy_batches(
            analytics_root,
            records,
            rows_per_file=workload.legacy_batch_rows,
        ),
        rows=workload.analytical_row_count,
    )
    legacy_stats = _directory_stats(analytics_root)
    validated = measurements.measure(
        "aggregation_legacy_read",
        lambda: read_aggregation_dataset(analytics_root),
        rows=workload.analytical_row_count,
    )
    if validated != tuple(sorted(records, key=lambda item: item.record_id)):
        raise ValueError("legacy aggregation semantic round trip failed")

    layout = ParquetLayoutPolicy()
    compacted = measurements.measure(
        "aggregation_compaction",
        lambda: compact_aggregation_dataset(
            analytics_root,
            created_by_job_id="job_scale_compaction",
            policy=layout,
        ),
        rows=workload.analytical_row_count,
    )
    compacted_stats = _directory_stats(analytics_root)
    compacted_id = compacted.manifest.snapshot_id

    crash_pointer = current_aggregation_snapshot_id(analytics_root)

    def crash_migration() -> None:
        try:
            migrate_aggregation_snapshot(
                analytics_root,
                created_by_job_id="job_scale_migration_crash",
                migration_id="resource-backfill-crash-v1",
                transform=lambda item: replace(
                    item, resource_consumption=float(item.action_count)
                ),
                policy=layout,
                injector=parquet_fault_at(
                    ParquetLifecycleFaultPoint.AFTER_SNAPSHOT_RENAME
                ),
            )
        except InjectedParquetLifecycleFault:
            return
        raise ValueError("crash migration did not reach the injected fault")

    measurements.measure(
        "aggregation_crash_before_pointer",
        crash_migration,
        rows=workload.analytical_row_count,
    )
    if current_aggregation_snapshot_id(analytics_root) != crash_pointer:
        raise ValueError("crash migration changed the active snapshot pointer")

    migrated = measurements.measure(
        "aggregation_migration_recovery",
        lambda: migrate_aggregation_snapshot(
            analytics_root,
            created_by_job_id="job_scale_migration_recovery",
            migration_id="resource-backfill-recovery-v1",
            transform=lambda item: replace(
                item, resource_consumption=float(item.action_count)
            ),
            policy=layout,
        ),
        rows=workload.analytical_row_count,
    )
    measurements.measure(
        "aggregation_rollback",
        lambda: rollback_aggregation_snapshot(
            analytics_root,
            compacted_id,
            expected_current_snapshot_id=migrated.manifest.snapshot_id,
        ),
        rows=workload.analytical_row_count,
    )
    activate_aggregation_snapshot(
        analytics_root,
        migrated.manifest.snapshot_id,
        expected_current_snapshot_id=compacted_id,
    )
    concurrent_compaction = measurements.measure(
        "concurrent_compaction_read",
        lambda: _measure_concurrent_compaction_read(
            analytics_root,
            layout,
            expected_rows=workload.analytical_row_count,
        ),
        rows=workload.analytical_row_count,
    )
    migrated_records = read_aggregation_snapshot(analytics_root).records
    if len(migrated_records) != workload.analytical_row_count or any(
        item.resource_consumption is None for item in migrated_records
    ):
        raise ValueError("migration recovery did not publish the expected rows")

    table = measurements.measure(
        "persistent_cold_read",
        lambda: _active_arrow_table(analytics_root),
        rows=workload.analytical_row_count,
    )
    for _ in range(workload.query_samples):
        measurements.measure(
            "persistent_warm_filter_sort",
            lambda: _persistent_query(table),
            rows=workload.analytical_row_count,
        )
        measurements.measure(
            "persistent_run_drill_down",
            lambda: _persistent_drill_down(
                table, _run_id(workload.run_count // 2)
            ),
            rows=workload.analytical_row_count,
        )
        measurements.measure(
            "persistent_comparison",
            lambda: _persistent_comparison(table),
            rows=workload.analytical_row_count,
        )

    snapshot = measurements.measure(
        "application_snapshot_materialization",
        lambda: _application_snapshot(migrated_records),
        rows=workload.analytical_row_count,
    )
    snapshot_id = measurements.measure(
        "application_snapshot_identity",
        lambda: snapshot.snapshot_id,
        rows=workload.analytical_row_count,
    )
    snapshots = AnalyticsSnapshotStore()
    snapshots.register(snapshot)
    default_rejected = False
    try:
        AnalyticsQueryService(snapshots).execute(_query_request(snapshot_id))
    except AnalyticsQueryError as exc:
        default_rejected = exc.code == "sync_scan_limit_exceeded"
    query_service = AnalyticsQueryService(
        snapshots, max_sync_scan_rows=workload.analytical_row_count
    )
    query_request = _query_request(snapshot_id)
    query_result = None
    for _ in range(workload.query_samples):
        query_result = measurements.measure(
            "application_query",
            lambda: query_service.execute(query_request),
            rows=workload.analytical_row_count,
        )
    assert query_result is not None
    concurrent_ingest = measurements.measure(
        "concurrent_catalog_ingest_query",
        lambda: _measure_concurrent_catalog_ingest_query(
            catalog,
            query_service,
            query_request,
            delta_count=max(1, min(1_000, workload.run_count // 100)),
        ),
        rows=workload.analytical_row_count,
    )
    if concurrent_ingest["query_snapshot_id"] != snapshot_id:
        raise ValueError("concurrent catalog ingest changed the bound query snapshot")

    desktop = DesktopApplicationService(
        root / "desktop", analytics_service=query_service
    )
    for _ in range(workload.query_samples):
        measurements.measure(
            "desktop_bridge_query",
            lambda: desktop.analytics_query({"request": query_request.to_dict()}),
            rows=workload.analytical_row_count,
        )

    export_service = AnalyticsExportService(query_service)
    export_results: dict[str, Any] = {}
    semantic_digests: set[str] = set()
    unfiltered = replace(query_request, filters=(), sort=())
    for export_format in AnalyticsExportFormat:
        request = AnalyticsExportRequest(
            format=export_format,
            source_kind=AnalyticsExportSourceKind.QUERY,
            query=unfiltered,
        )
        bundle = measurements.measure(
            f"application_export_{export_format.value}",
            lambda request=request: export_service.build(request),
            rows=workload.analytical_row_count,
        )
        semantic_digests.add(bundle.manifest["semantic_digest"])
        target = root / "exports" / export_format.value
        result = measurements.measure(
            f"application_export_{export_format.value}_publish",
            lambda request=request, target=target: export_service.write(
                request, target
            ),
            rows=workload.analytical_row_count,
        )
        export_results[export_format.value] = {
            "data_bytes": bundle.manifest["data"]["bytes"],
            "export_id": result["export_id"],
            "row_count": result["row_count"],
            "semantic_digest": result["semantic_digest"],
        }
    if len(semantic_digests) != 1:
        raise ValueError("scale exports do not share one semantic digest")

    cancel_request = AnalyticsExportRequest(
        format=AnalyticsExportFormat.JSON,
        source_kind=AnalyticsExportSourceKind.QUERY,
        query=unfiltered,
    )
    cancel_result = measurements.measure(
        "concurrent_export_cancel",
        lambda: _measure_cancel(root / "cancel", export_service, cancel_request),
        rows=workload.analytical_row_count,
    )

    final_stats = _directory_stats(root)
    measured = measurements.summary()
    application_memory_samples = [
        item
        for item in measurements.samples
        if item["operation"] == "application_snapshot_materialization"
    ]
    application_memory_delta = max(
        0,
        max(
            int(item["rss_peak_bytes"]) - int(item["rss_before_bytes"])
            for item in application_memory_samples
        ),
    )
    measured_application_bytes_per_row = math.ceil(
        application_memory_delta / workload.analytical_row_count
    )
    identity = to_canonical_data(
        {
            "acceptance": {
                "application_export_semantic_parity": len(semantic_digests) == 1,
                "catalog_complete_runs": catalog_complete,
                "concurrent_compaction_reader_complete": concurrent_compaction[
                    "observed_complete_rows"
                ]
                == workload.analytical_row_count,
                "concurrent_ingest_kept_query_snapshot": concurrent_ingest[
                    "query_snapshot_id"
                ]
                == snapshot_id,
                "crash_kept_previous_snapshot": crash_pointer == compacted_id,
                "default_sync_query_failed_closed": default_rejected,
                "event_rows": workload.event_row_count,
                "full_scale": workload.full_scale,
                "migration_recovered": len(migrated_records)
                == workload.analytical_row_count,
                "raw_file_per_run": raw_stats["file_count"]
                == workload.run_count,
            },
            "artifacts": {
                "compacted": compacted_stats,
                "exports": export_results,
                "final_work_root": final_stats,
                "legacy": legacy_stats,
                "lifecycle_writes": {
                    "compaction": compacted.manifest.write_metrics.to_dict(),
                    "migration": migrated.manifest.write_metrics.to_dict(),
                },
                "raw": raw_stats,
            },
            "hardware": hardware,
            "measurements": measured,
            "policy_decision": {
                "export": {
                    "max_bytes": MAX_EXPORT_BYTES,
                    "max_output_rows": MAX_EXPORT_OUTPUT_ROWS,
                    "max_scan_rows": MAX_EXPORT_SCAN_ROWS,
                    "status": "reduced_to_measured_fail_close_hard_caps",
                    "validated_rows": workload.analytical_row_count,
                },
                "parquet": {
                    **layout.to_dict(),
                    "status": "retained_after_scale_calibration",
                },
                "query": {
                    "default_max_sync_scan_rows": 10_000,
                    "measured_application_bytes_per_row": (
                        measured_application_bytes_per_row
                    ),
                    "measured_snapshot_materialization_rss_delta_bytes": (
                        application_memory_delta
                    ),
                    "status": "retained; larger scans require async or explicit service policy",
                },
            },
            "recovery": {
                "cancel": cancel_result,
                "compacted_snapshot_id": compacted_id,
                "concurrent_compaction": concurrent_compaction,
                "concurrent_ingest": concurrent_ingest,
                "migrated_snapshot_id": migrated.manifest.snapshot_id,
            },
            "runtime": {
                "package": __version__,
                "pyarrow": pyarrow.__version__,
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
            },
            "schema_version": ANALYTICS_SCALE_CALIBRATION_SCHEMA_VERSION,
            "ui_evidence_boundary": {
                "persistent_bridge_operation": "desktop_bridge_query",
                "renderer_evidence": _renderer_evidence_summary(),
                "renderer_fixture_is_persistent_storage": False,
            },
            "workload": workload.to_dict(),
        }
    )
    evidence = {
        **identity,
        "evidence_id": stable_digest(identity, prefix="analyticsscaleevidence_"),
    }
    return evidence, tuple(measurements.samples)


def write_analytics_scale_evidence(
    *,
    workload: AnalyticsScaleWorkload,
    work_root: Path,
    out: Path,
    samples_out: Path,
) -> dict[str, Any]:
    evidence, samples = run_analytics_scale_calibration(
        workload, work_root=work_root
    )
    _write_sample_parquet(samples_out, samples)
    sample_artifact = {
        "bytes": samples_out.stat().st_size,
        "path": samples_out.name,
        "row_count": len(samples),
        "sha256": _sha256_file(samples_out),
    }
    identity = {
        key: value for key, value in evidence.items() if key != "evidence_id"
    }
    identity["sample_artifact"] = sample_artifact
    final = {
        **to_canonical_data(identity),
        "evidence_id": stable_digest(
            to_canonical_data(identity), prefix="analyticsscaleevidence_"
        ),
    }
    atomic_write_text(
        out,
        json.dumps(final, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return final


def main() -> int:
    parser = argparse.ArgumentParser(
        description="calibrate v0.5 analytics at persistent-storage scale"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples-out", type=Path, required=True)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--runs", type=int, default=FULL_RUN_COUNT)
    parser.add_argument("--event-rows", type=int, default=FULL_EVENT_ROW_COUNT)
    parser.add_argument(
        "--analytical-rows", type=int, default=FULL_ANALYTICAL_ROW_COUNT
    )
    parser.add_argument("--query-samples", type=int, default=9)
    parser.add_argument("--legacy-batch-rows", type=int, default=1_000)
    args = parser.parse_args()
    workload = AnalyticsScaleWorkload(
        run_count=args.runs,
        event_row_count=args.event_rows,
        analytical_row_count=args.analytical_rows,
        query_samples=args.query_samples,
        legacy_batch_rows=args.legacy_batch_rows,
    )
    if args.work_root is not None:
        evidence = write_analytics_scale_evidence(
            workload=workload,
            work_root=args.work_root,
            out=args.out,
            samples_out=args.samples_out,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="ygo-analytics-scale-") as temporary:
            evidence = write_analytics_scale_evidence(
                workload=workload,
                work_root=Path(temporary),
                out=args.out,
                samples_out=args.samples_out,
            )
    print(f"analytics-scale-evidence: wrote {args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
