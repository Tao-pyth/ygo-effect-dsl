from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.storage import (
    ANALYTICS_EXPORT_CONTRACT_VERSION,
    AnalyticsComparisonRequest,
    AnalyticsExportFormat,
    AnalyticsExportQueue,
    AnalyticsExportRequest,
    AnalyticsExportRetryableError,
    AnalyticsExportService,
    AnalyticsExportSourceKind,
    AnalyticsExportWorker,
    AnalyticsFilter,
    AnalyticsQueryRequest,
    AnalyticsQueryRow,
    AnalyticsQueryService,
    AnalyticsSnapshot,
    AnalyticsSnapshotStore,
    AnalyticsSort,
    AnalyticsValue,
    JobKind,
    JobSpec,
    JobState,
    analytics_export_contract_document,
    decode_export_dataset,
)

T0 = "2026-01-01T00:00:00Z"


def _snapshot() -> AnalyticsSnapshot:
    return AnalyticsSnapshot(
        rows=(
            AnalyticsQueryRow.build(
                {
                    "run": "=spreadsheet-command",
                    "deck": "deck_a",
                    "score": 1.5,
                    "status": AnalyticsValue.redacted(),
                    "success": True,
                },
                row_id="=dangerous-row-id",
            ),
            AnalyticsQueryRow.build(
                {
                    "run": "run_b",
                    "deck": "deck_b",
                    "score": 9.0,
                    "status": "complete",
                    "success": False,
                },
                row_id="row_b",
            ),
            AnalyticsQueryRow.build(
                {
                    "run": "run_c",
                    "deck": "deck_a",
                    "score": 4.0,
                    "status": "partial",
                    "success": True,
                },
                row_id="row_c",
            ),
        ),
        source_ids=("source_a", "source_b"),
    )


def _service() -> tuple[AnalyticsExportService, AnalyticsSnapshot]:
    snapshot = _snapshot()
    store = AnalyticsSnapshotStore()
    store.register(snapshot)
    return AnalyticsExportService(AnalyticsQueryService(store)), snapshot


def _request(export_format: AnalyticsExportFormat) -> AnalyticsExportRequest:
    return AnalyticsExportRequest(
        format=export_format,
        source_kind=AnalyticsExportSourceKind.QUERY,
        query=AnalyticsQueryRequest(
            fields=("run", "deck", "score", "status"),
            filters=(AnalyticsFilter("deck", "eq", "deck_a"),),
            sort=(AnalyticsSort("score", "desc"),),
            limit=500,
        ),
    )


def test_snapshot_document_round_trip_is_content_addressed() -> None:
    snapshot = _snapshot()

    assert AnalyticsSnapshot.from_mapping(snapshot.to_dict()) == snapshot
    changed = snapshot.to_dict()
    changed["snapshot_id"] = "analyticssnapshot_" + "0" * 64
    with pytest.raises(ValueError, match="snapshot_id"):
        AnalyticsSnapshot.from_mapping(changed)


def test_json_csv_and_parquet_share_one_semantic_dataset() -> None:
    service, snapshot = _service()
    bundles = {
        export_format: service.build(_request(export_format))
        for export_format in AnalyticsExportFormat
    }
    semantic = {
        export_format: decode_export_dataset(
            export_format, bundle.data, bundle.manifest
        )
        for export_format, bundle in bundles.items()
    }

    assert semantic[AnalyticsExportFormat.JSON] == semantic[AnalyticsExportFormat.CSV]
    assert (
        semantic[AnalyticsExportFormat.JSON] == semantic[AnalyticsExportFormat.PARQUET]
    )
    assert [row["row_id"] for row in semantic[AnalyticsExportFormat.JSON]["rows"]] == [
        "row_c",
        "=dangerous-row-id",
    ]
    assert semantic[AnalyticsExportFormat.JSON]["rows"][1]["values"]["status"] == {
        "schema_version": "analytics-query-value-v1",
        "state": "redacted",
    }
    csv_lines = bundles[AnalyticsExportFormat.CSV].data.splitlines()
    assert any(line.startswith(b'"""=dangerous-row-id') for line in csv_lines[1:])
    for bundle in bundles.values():
        assert bundle.manifest["schema_version"] == "analytics-export-manifest-v1"
        assert bundle.manifest["source"]["snapshot_id"] == snapshot.snapshot_id
        assert bundle.manifest["source"]["source_ids"] == ["source_a", "source_b"]
        assert (
            bundle.manifest["data"]["sha256"] == hashlib.sha256(bundle.data).hexdigest()
        )


def test_comparison_export_preserves_one_validated_report_across_formats() -> None:
    comparison_request = AnalyticsComparisonRequest(
        query_snapshot_id="analyticssnapshot_" + "a" * 64,
        metrics=("score",),
    )
    identity = {
        "arm_statistics": {},
        "compatibility_evidence": [],
        "metric_summaries": {},
        "pairs": [{"pair_id": "pair_fixture", "status": "complete"}],
        "request": comparison_request.to_dict(),
        "request_id": comparison_request.request_id,
        "sample": {"total_lineage_count": 1},
        "schema_version": "analytics-comparison-response-v1",
        "uncertainty": {"confidence_method": "normal_mean_v1"},
    }
    report = {
        **identity,
        "comparison_report_id": stable_digest(identity, prefix="comparisonreport_"),
    }
    service = AnalyticsExportService(AnalyticsQueryService(AnalyticsSnapshotStore()))
    bundles = {
        export_format: service.build(
            AnalyticsExportRequest(
                format=export_format,
                source_kind=AnalyticsExportSourceKind.COMPARISON,
                comparison=report,
            )
        )
        for export_format in AnalyticsExportFormat
    }
    decoded = {
        export_format: decode_export_dataset(
            export_format, bundle.data, bundle.manifest
        )
        for export_format, bundle in bundles.items()
    }

    assert decoded[AnalyticsExportFormat.JSON] == decoded[AnalyticsExportFormat.CSV]
    assert decoded[AnalyticsExportFormat.JSON] == decoded[AnalyticsExportFormat.PARQUET]
    assert decoded[AnalyticsExportFormat.JSON]["comparison"] == report
    assert {bundle.row_count for bundle in bundles.values()} == {1}


def test_export_is_deterministic_and_enforces_byte_limit(tmp_path: Path) -> None:
    service, _ = _service()
    request = _request(AnalyticsExportFormat.JSON)

    first = service.build(request)
    second = service.build(request)
    result = service.write(request, tmp_path)
    repeated = service.write(request, tmp_path)

    assert first.data == second.data
    assert first.manifest == second.manifest
    assert result == repeated
    assert Path(result["files"]["data"]).is_file()
    assert Path(result["files"]["manifest"]).is_file()
    constrained = AnalyticsExportService(service.query_service, max_bytes=1)
    with pytest.raises(ValueError, match="byte limit"):
        constrained.build(request)


def test_export_fails_closed_on_cursor_scan_and_output_limits() -> None:
    service, snapshot = _service()
    request = _request(AnalyticsExportFormat.JSON)
    with pytest.raises(ValueError, match="cursor"):
        AnalyticsExportRequest(
            format=AnalyticsExportFormat.JSON,
            source_kind=AnalyticsExportSourceKind.QUERY,
            query=AnalyticsQueryRequest(
                fields=request.query.fields,
                cursor="opaque-cursor",
                snapshot_id=snapshot.snapshot_id,
            ),
        )
    with pytest.raises(ValueError, match="scan limit"):
        AnalyticsExportService(
            service.query_service,
            max_scan_rows=2,
        ).build(request)
    with pytest.raises(ValueError, match="row limit"):
        AnalyticsExportService(
            service.query_service,
            max_output_rows=1,
        ).build(request)


def test_export_job_publishes_atomic_data_and_manifest(tmp_path: Path) -> None:
    service, _ = _service()
    queue = AnalyticsExportQueue(tmp_path, service)
    job = queue.enqueue(_request(AnalyticsExportFormat.JSON), created_at=T0)
    worker = AnalyticsExportWorker(queue, now=lambda: T0)

    outcome = worker.run_once()
    status = queue.catalog.status_snapshot(job.job_id)

    assert outcome.status == "succeeded"
    assert status.job.state == JobState.SUCCEEDED
    assert {artifact.kind for artifact in status.artifacts} == {
        "analytics_export_data",
        "analytics_export_manifest",
    }
    assert status.latest_checkpoint is not None
    assert status.latest_checkpoint.completed_units == 2
    for artifact in status.artifacts:
        path = tmp_path / "export-job-store" / artifact.path
        assert path.is_file()


def test_export_worker_only_claims_export_jobs(tmp_path: Path) -> None:
    service, _ = _service()
    queue = AnalyticsExportQueue(tmp_path, service)
    catalog = queue.catalog
    search = JobSpec(
        kind=JobKind.SEARCH,
        idempotency_key="search-before-export",
        input_digest="jobinput_" + "1" * 64,
        payload={
            "experiment_digest": "experiment_" + "2" * 64,
            "experiment_id": "experiment-fixture",
        },
    )
    search_job = catalog.create_job(search, created_at=T0)
    export_job = queue.enqueue(_request(AnalyticsExportFormat.CSV), created_at=T0)

    outcome = AnalyticsExportWorker(queue, now=lambda: T0).run_once()

    assert outcome.job_id == export_job.job_id
    assert catalog.get_job(export_job.job_id).state == JobState.SUCCEEDED
    assert catalog.get_job(search_job.job_id).state == JobState.QUEUED


def test_export_worker_honors_cancel_and_retry(tmp_path: Path) -> None:
    service, _ = _service()
    cancel_queue = AnalyticsExportQueue(tmp_path / "cancel", service)
    cancel_job = cancel_queue.enqueue(
        _request(AnalyticsExportFormat.JSON), created_at=T0
    )

    def cancel_build(request: AnalyticsExportRequest, **_: object):
        active = cancel_queue.catalog.get_job(cancel_job.job_id)
        assert active is not None
        cancel_queue.catalog.request_cancel(
            active.job_id,
            actor="test",
            now=T0,
            reason="operator_cancel",
        )
        raise InterruptedError("cancelled")

    cancelled = AnalyticsExportWorker(
        cancel_queue, now=lambda: T0, build=cancel_build
    ).run_once()
    assert cancelled.status == "cancelled"
    assert cancel_queue.catalog.get_job(cancel_job.job_id).state == JobState.CANCELLED

    retry_queue = AnalyticsExportQueue(tmp_path / "retry", service)
    retry_job = retry_queue.enqueue(_request(AnalyticsExportFormat.JSON), created_at=T0)
    attempts = 0

    def retry_build(request: AnalyticsExportRequest, **kwargs: object):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AnalyticsExportRetryableError("transient_io", "retry fixture")
        return service.build(request, **kwargs)

    worker = AnalyticsExportWorker(retry_queue, now=lambda: T0, build=retry_build)
    assert worker.run_once().status == "retrying"
    assert retry_queue.catalog.get_job(retry_job.job_id).state == JobState.RETRYING
    assert worker.run_once().status == "succeeded"
    assert retry_queue.catalog.get_job(retry_job.job_id).attempt == 2


def test_cli_desktop_api_and_service_publish_identical_export_bytes(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    store = AnalyticsSnapshotStore()
    store.register(snapshot)
    query_service = AnalyticsQueryService(store)
    request = _request(AnalyticsExportFormat.JSON)
    direct = AnalyticsExportService(query_service).build(request)

    app = DesktopApplicationService(
        tmp_path / "desktop", analytics_service=query_service
    )
    queued = app.analytics_export_enqueue(
        {
            "format": "json",
            "idempotency_key": None,
            "priority": 0,
            "source": request.query.to_dict(),
            "source_kind": "query",
        }
    )
    assert app.analytics_export_worker.run_once().status == "succeeded"
    status = app.job_catalog.status_snapshot(queued["job"]["job_id"])
    desktop_payloads = {
        artifact.kind: (
            app.analytics_export_worker.publisher.root / artifact.path
        ).read_bytes()
        for artifact in status.artifacts
    }

    snapshot_path = tmp_path / "snapshot.json"
    query_path = tmp_path / "query.json"
    snapshot_path.write_text(json.dumps(snapshot.to_dict()), encoding="utf-8")
    query_path.write_text(json.dumps(request.query.to_dict()), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ygo_effect_dsl",
            "analytics-export",
            "--format",
            "json",
            "--out",
            str(tmp_path / "cli"),
            "--query",
            str(query_path),
            "--snapshot",
            str(snapshot_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    cli_result = json.loads(completed.stdout)

    assert Path(cli_result["files"]["data"]).read_bytes() == direct.data
    assert Path(cli_result["files"]["manifest"]).read_bytes() == (direct.manifest_bytes)
    assert desktop_payloads["analytics_export_data"] == direct.data
    assert desktop_payloads["analytics_export_manifest"] == direct.manifest_bytes


def test_export_contract_resource_matches_runtime() -> None:
    resource = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ygo_effect_dsl"
        / "resources"
        / "analytics-export-contract-v1.json"
    )
    assert analytics_export_contract_document()["schema_version"] == (
        ANALYTICS_EXPORT_CONTRACT_VERSION
    )
    assert json.loads(resource.read_text(encoding="utf-8")) == (
        analytics_export_contract_document()
    )
