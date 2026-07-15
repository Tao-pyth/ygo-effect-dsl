from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from typing import Any

from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.storage.comparison import (
    ANALYTICS_COMPARISON_RESPONSE_SCHEMA_VERSION,
    AnalyticsComparisonRequest,
)
from ygo_effect_dsl.storage.job_recovery import JobArtifactPublisher
from ygo_effect_dsl.storage.jobs import (
    JobCatalog,
    JobKind,
    JobLeaseError,
    JobRecord,
    JobRetryPolicy,
    JobSpec,
    JobState,
)
from ygo_effect_dsl.storage.query import (
    ANALYTICS_QUERY_VALUE_SCHEMA_VERSION,
    AnalyticsQueryRequest,
    AnalyticsQueryService,
)
from ygo_effect_dsl.version import __version__

ANALYTICS_EXPORT_CONTRACT_VERSION = "analytics-export-contract-v1"
ANALYTICS_EXPORT_REQUEST_SCHEMA_VERSION = "analytics-export-request-v1"
ANALYTICS_EXPORT_DATA_SCHEMA_VERSION = "analytics-export-data-v1"
ANALYTICS_EXPORT_MANIFEST_SCHEMA_VERSION = "analytics-export-manifest-v1"
ANALYTICS_EXPORT_RESULT_SCHEMA_VERSION = "analytics-export-result-v1"
ANALYTICS_EXPORT_WORKER_SCHEMA_VERSION = "analytics-export-worker-v1"

MAX_EXPORT_SCAN_ROWS = 100_000
MAX_EXPORT_OUTPUT_ROWS = 100_000
MAX_EXPORT_BYTES = 512 * 1024 * 1024
EXPORT_LEASE_SECONDS = 300.0
EXPORT_POLL_SECONDS = 0.1


class AnalyticsExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"


class AnalyticsExportSourceKind(str, Enum):
    QUERY = "query"
    COMPARISON = "comparison"


class AnalyticsExportRetryableError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _exact(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} fields must be exactly {sorted(expected)}")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _content_id(value: Any, name: str, prefix: str) -> str:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError(f"{name} must be a {prefix} content ID")
    digest = value.removeprefix(prefix)
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{name} must be a {prefix} content ID")
    return value


def _sync_write_bytes(path: Path, content: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _ensure_free_space(root: Path, required: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < required:
        raise AnalyticsExportRetryableError(
            "disk_full", "insufficient free disk space for atomic export"
        )


def _validate_comparison_report(value: Any) -> dict[str, Any]:
    report = to_canonical_data(_mapping(value, "comparison report"))
    expected = {
        "arm_statistics",
        "comparison_report_id",
        "compatibility_evidence",
        "metric_summaries",
        "pairs",
        "request",
        "request_id",
        "sample",
        "schema_version",
        "uncertainty",
    }
    _exact(report, expected, "comparison report")
    if report["schema_version"] != ANALYTICS_COMPARISON_RESPONSE_SCHEMA_VERSION:
        raise ValueError("unsupported analytics comparison response schema")
    for name in ("arm_statistics", "metric_summaries", "sample", "uncertainty"):
        _mapping(report[name], f"comparison report {name}")
    for name in ("compatibility_evidence", "pairs"):
        if not isinstance(report[name], list):
            raise ValueError(f"comparison report {name} must be a list")
    if not report["pairs"]:
        raise ValueError("comparison report pairs must not be empty")
    identity = {
        key: value for key, value in report.items() if key != "comparison_report_id"
    }
    if report["comparison_report_id"] != stable_digest(
        identity, prefix="comparisonreport_"
    ):
        raise ValueError("comparison report ID does not match its content")
    request = AnalyticsComparisonRequest.from_mapping(report["request"])
    _content_id(
        request.query_snapshot_id,
        "comparison request query_snapshot_id",
        "analyticssnapshot_",
    )
    if report["request_id"] != request.request_id:
        raise ValueError("comparison request ID does not match its content")
    if to_canonical_data(report["request"]) != request.to_dict():
        raise ValueError("comparison request is not canonical")
    return report


@dataclass(frozen=True)
class AnalyticsExportRequest:
    format: AnalyticsExportFormat
    source_kind: AnalyticsExportSourceKind
    query: AnalyticsQueryRequest | None = None
    comparison: Mapping[str, Any] | None = None
    schema_version: str = ANALYTICS_EXPORT_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_EXPORT_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported analytics export request schema")
        export_format = (
            self.format
            if isinstance(self.format, AnalyticsExportFormat)
            else AnalyticsExportFormat(self.format)
        )
        source_kind = (
            self.source_kind
            if isinstance(self.source_kind, AnalyticsExportSourceKind)
            else AnalyticsExportSourceKind(self.source_kind)
        )
        object.__setattr__(self, "format", export_format)
        object.__setattr__(self, "source_kind", source_kind)
        if source_kind == AnalyticsExportSourceKind.QUERY:
            if not isinstance(self.query, AnalyticsQueryRequest):
                raise ValueError("query export requires AnalyticsQueryRequest")
            if self.query.cursor is not None:
                raise ValueError("query export cursor must be null")
            if self.comparison is not None:
                raise ValueError("query export cannot include comparison data")
        else:
            if self.query is not None:
                raise ValueError("comparison export cannot include a query")
            object.__setattr__(
                self,
                "comparison",
                _validate_comparison_report(self.comparison),
            )

    @property
    def request_id(self) -> str:
        return stable_digest(self.to_dict(), prefix="analyticsexportrequest_")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "comparison": self.comparison,
                "format": self.format.value,
                "query": self.query.to_dict() if self.query is not None else None,
                "schema_version": self.schema_version,
                "source_kind": self.source_kind.value,
            }
        )

    @classmethod
    def from_mapping(cls, value: Any) -> "AnalyticsExportRequest":
        document = _mapping(value, "analytics export request")
        _exact(
            document,
            {"comparison", "format", "query", "schema_version", "source_kind"},
            "analytics export request",
        )
        query = document.get("query")
        return cls(
            format=document.get("format"),
            source_kind=document.get("source_kind"),
            query=(
                AnalyticsQueryRequest.from_mapping(query) if query is not None else None
            ),
            comparison=document.get("comparison"),
            schema_version=document.get("schema_version"),
        )


def _software_versions(export_format: AnalyticsExportFormat) -> dict[str, str | None]:
    pyarrow_version = None
    if export_format == AnalyticsExportFormat.PARQUET:
        try:
            pyarrow_version = importlib.metadata.version("pyarrow")
        except importlib.metadata.PackageNotFoundError:
            pyarrow_version = None
    return {
        "package": __version__,
        "pyarrow": pyarrow_version,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def _query_dataset(
    request: AnalyticsQueryRequest,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return to_canonical_data(
        {
            "columns": list(request.fields),
            "query": request.to_dict(),
            "rows": list(rows),
            "schema_version": ANALYTICS_EXPORT_DATA_SCHEMA_VERSION,
            "source_kind": AnalyticsExportSourceKind.QUERY.value,
        }
    )


def _comparison_dataset(report: Mapping[str, Any]) -> dict[str, Any]:
    return to_canonical_data(
        {
            "comparison": report,
            "schema_version": ANALYTICS_EXPORT_DATA_SCHEMA_VERSION,
            "source_kind": AnalyticsExportSourceKind.COMPARISON.value,
        }
    )


def _formula_safe(value: str) -> str:
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _formula_restore(value: str) -> str:
    if len(value) > 1 and value[0] == "'" and value[1] in "=+-@\t\r":
        return value[1:]
    return value


def _csv_query_bytes(dataset: Mapping[str, Any]) -> bytes:
    fields = tuple(dataset["columns"])
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    header = ["row_id_json"]
    for field in fields:
        header.extend((f"{field}__state", f"{field}__value_json"))
    writer.writerow(header)
    for index, row in enumerate(dataset["rows"]):
        if index > MAX_EXPORT_OUTPUT_ROWS:
            raise ValueError("export row count exceeded its hard limit")
        cells = [canonical_json(row["row_id"])]
        for field in fields:
            value = row["values"][field]
            cells.append(value["state"])
            cells.append(canonical_json(value["value"]) if "value" in value else "")
        writer.writerow([_formula_safe(str(cell)) for cell in cells])
    return output.getvalue().encode("utf-8")


def _csv_comparison_bytes(dataset: Mapping[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["comparison_json"])
    writer.writerow([_formula_safe(canonical_json(dataset["comparison"]))])
    return output.getvalue().encode("utf-8")


def _parquet_bytes(dataset: Mapping[str, Any]) -> bytes:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires the optional analytics dependency"
        ) from exc
    if dataset["source_kind"] == AnalyticsExportSourceKind.QUERY.value:
        fields = tuple(dataset["columns"])
        columns: dict[str, list[str]] = {"row_id_json": []}
        for field in fields:
            columns[f"{field}__state"] = []
            columns[f"{field}__value_json"] = []
        for row in dataset["rows"]:
            columns["row_id_json"].append(canonical_json(row["row_id"]))
            for field in fields:
                value = row["values"][field]
                columns[f"{field}__state"].append(value["state"])
                columns[f"{field}__value_json"].append(
                    canonical_json(value["value"]) if "value" in value else ""
                )
    else:
        columns = {"comparison_json": [canonical_json(dataset["comparison"])]}
    table = pa.table(columns).replace_schema_metadata(
        {
            b"analytics_export_data_schema": ANALYTICS_EXPORT_DATA_SCHEMA_VERSION.encode(),
            b"analytics_export_source_kind": dataset["source_kind"].encode(),
        }
    )
    sink = pa.BufferOutputStream()
    pq.write_table(
        table,
        sink,
        compression="NONE",
        version="2.6",
        write_statistics=False,
    )
    return sink.getvalue().to_pybytes()


def _serialize_dataset(
    export_format: AnalyticsExportFormat,
    dataset: Mapping[str, Any],
) -> tuple[str, bytes]:
    if export_format == AnalyticsExportFormat.JSON:
        return "analytics.json", (canonical_json(dataset) + "\n").encode("utf-8")
    if export_format == AnalyticsExportFormat.CSV:
        content = (
            _csv_query_bytes(dataset)
            if dataset["source_kind"] == AnalyticsExportSourceKind.QUERY.value
            else _csv_comparison_bytes(dataset)
        )
        return "analytics.csv", content
    return "analytics.parquet", _parquet_bytes(dataset)


def _row_from_flat_record(
    record: Mapping[str, str], fields: Sequence[str]
) -> dict[str, Any]:
    row_id = json.loads(_formula_restore(record["row_id_json"]))
    values: dict[str, Any] = {}
    for field in fields:
        state = _formula_restore(record[f"{field}__state"])
        value_json = _formula_restore(record[f"{field}__value_json"])
        value = {
            "schema_version": ANALYTICS_QUERY_VALUE_SCHEMA_VERSION,
            "state": state,
        }
        if value_json:
            value["value"] = json.loads(value_json)
        values[field] = value
    return {
        "row_id": row_id,
        "schema_version": "analytics-query-row-v1",
        "values": values,
    }


def decode_export_dataset(
    export_format: AnalyticsExportFormat | str,
    data: bytes,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    observed_format = (
        export_format
        if isinstance(export_format, AnalyticsExportFormat)
        else AnalyticsExportFormat(export_format)
    )
    if _sha256_bytes(data) != manifest.get("data", {}).get("sha256"):
        raise ValueError("export data checksum does not match the manifest")
    if observed_format == AnalyticsExportFormat.JSON:
        dataset = json.loads(data.decode("utf-8"))
    else:
        if observed_format == AnalyticsExportFormat.CSV:
            records = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
        else:
            try:
                import pyarrow.parquet as pq
            except ImportError as exc:
                raise RuntimeError(
                    "Parquet export decoding requires the analytics dependency"
                ) from exc
            records = pq.read_table(io.BytesIO(data)).to_pylist()
        source = manifest["source"]
        if source["kind"] == AnalyticsExportSourceKind.QUERY.value:
            fields = tuple(source["query"]["fields"])
            dataset = _query_dataset(
                AnalyticsQueryRequest.from_mapping(source["query"]),
                tuple(_row_from_flat_record(record, fields) for record in records),
            )
        else:
            if len(records) != 1:
                raise ValueError("comparison export must contain one semantic record")
            report = json.loads(_formula_restore(records[0]["comparison_json"]))
            dataset = _comparison_dataset(_validate_comparison_report(report))
    canonical = to_canonical_data(dataset)
    if stable_digest(canonical, prefix="exportsemantic_") != manifest.get(
        "semantic_digest"
    ):
        raise ValueError("export semantic digest does not match the manifest")
    return canonical


@dataclass(frozen=True)
class AnalyticsExportBundle:
    request: AnalyticsExportRequest
    dataset: Mapping[str, Any]
    data_filename: str
    data: bytes
    manifest: Mapping[str, Any]

    @property
    def manifest_bytes(self) -> bytes:
        return (canonical_json(self.manifest) + "\n").encode("utf-8")

    @property
    def export_id(self) -> str:
        return str(self.manifest["export_id"])

    @property
    def row_count(self) -> int:
        return int(self.manifest["row_count"])

    def result_document(self, *, root: Path | None = None) -> dict[str, Any]:
        files = {
            "data": self.data_filename,
            "manifest": "manifest.json",
        }
        if root is not None:
            files = {key: str((root / value).resolve()) for key, value in files.items()}
        return {
            "data_sha256": _sha256_bytes(self.data),
            "export_id": self.export_id,
            "files": files,
            "format": self.request.format.value,
            "manifest_sha256": _sha256_bytes(self.manifest_bytes),
            "row_count": self.row_count,
            "schema_version": ANALYTICS_EXPORT_RESULT_SCHEMA_VERSION,
            "semantic_digest": self.manifest["semantic_digest"],
        }


class AnalyticsExportService:
    def __init__(
        self,
        query_service: AnalyticsQueryService,
        *,
        max_scan_rows: int = MAX_EXPORT_SCAN_ROWS,
        max_output_rows: int = MAX_EXPORT_OUTPUT_ROWS,
        max_bytes: int = MAX_EXPORT_BYTES,
    ) -> None:
        self.query_service = query_service
        for value, name in (
            (max_scan_rows, "max_scan_rows"),
            (max_output_rows, "max_output_rows"),
            (max_bytes, "max_bytes"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be an integer >= 1")
        self.max_scan_rows = max_scan_rows
        self.max_output_rows = max_output_rows
        self.max_bytes = max_bytes

    def bind_request(self, request: AnalyticsExportRequest) -> AnalyticsExportRequest:
        if request.source_kind == AnalyticsExportSourceKind.COMPARISON:
            return request
        if request.query is None:
            raise AssertionError("query export request lost its query")
        bound = self.query_service.bind_snapshot(request.query)
        return AnalyticsExportRequest(
            format=request.format,
            source_kind=request.source_kind,
            query=bound,
        )

    def build(
        self,
        request: AnalyticsExportRequest,
        *,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> AnalyticsExportBundle:
        bound_request = self.bind_request(request)
        if bound_request.source_kind == AnalyticsExportSourceKind.QUERY:
            if bound_request.query is None:
                raise AssertionError("bound query export has no query")
            query, snapshot, rows = self.query_service.select_for_export(
                bound_request.query,
                max_scan_rows=self.max_scan_rows,
                max_output_rows=self.max_output_rows,
                cancel_requested=cancel_requested,
            )
            dataset = _query_dataset(query, rows)
            source = {
                "comparison_report_id": None,
                "kind": bound_request.source_kind.value,
                "query": query.to_dict(),
                "query_fingerprint": query.fingerprint,
                "snapshot_id": snapshot.snapshot_id,
                "source_ids": list(snapshot.source_ids),
            }
            row_count = len(rows)
        else:
            comparison = _validate_comparison_report(bound_request.comparison)
            dataset = _comparison_dataset(comparison)
            comparison_request = comparison["request"]
            source = {
                "comparison_report_id": comparison["comparison_report_id"],
                "kind": bound_request.source_kind.value,
                "query": None,
                "query_fingerprint": None,
                "snapshot_id": comparison_request["query_snapshot_id"],
                "source_ids": [],
            }
            row_count = len(comparison["pairs"])
        if cancel_requested():
            raise InterruptedError("analytics export was cancelled")
        data_filename, data = _serialize_dataset(bound_request.format, dataset)
        if len(data) > self.max_bytes:
            raise ValueError("export data exceeds the configured byte limit")
        semantic_digest = stable_digest(dataset, prefix="exportsemantic_")
        identity = to_canonical_data(
            {
                "contract_version": ANALYTICS_EXPORT_CONTRACT_VERSION,
                "csv_formula_policy": "canonical_json_cells_and_apostrophe_escape-v1",
                "data": {
                    "bytes": len(data),
                    "filename": data_filename,
                    "schema_version": ANALYTICS_EXPORT_DATA_SCHEMA_VERSION,
                    "sha256": _sha256_bytes(data),
                },
                "format": bound_request.format.value,
                "request": bound_request.to_dict(),
                "request_id": bound_request.request_id,
                "row_count": row_count,
                "schema_version": ANALYTICS_EXPORT_MANIFEST_SCHEMA_VERSION,
                "semantic_digest": semantic_digest,
                "software": _software_versions(bound_request.format),
                "source": source,
            }
        )
        manifest = {
            **identity,
            "export_id": stable_digest(identity, prefix="analyticsexport_"),
        }
        return AnalyticsExportBundle(
            request=bound_request,
            dataset=dataset,
            data_filename=data_filename,
            data=data,
            manifest=manifest,
        )

    def write(
        self,
        request: AnalyticsExportRequest,
        root: str | Path,
    ) -> dict[str, Any]:
        bundle = self.build(request)
        output_root = Path(root).expanduser().resolve()
        required = 2 * (len(bundle.data) + len(bundle.manifest_bytes))
        _ensure_free_space(output_root, required)
        target = (output_root / bundle.export_id).resolve()
        if not target.is_relative_to(output_root):
            raise ValueError("export path escaped the configured output root")
        if target.exists():
            data_path = target / bundle.data_filename
            manifest_path = target / "manifest.json"
            if (
                not data_path.is_file()
                or not manifest_path.is_file()
                or _sha256_bytes(data_path.read_bytes()) != _sha256_bytes(bundle.data)
                or _sha256_bytes(manifest_path.read_bytes())
                != _sha256_bytes(bundle.manifest_bytes)
            ):
                raise ValueError("existing export directory conflicts with export ID")
            return bundle.result_document(root=target)
        staging = Path(tempfile.mkdtemp(prefix=".export-", dir=output_root))
        try:
            data_path = staging / bundle.data_filename
            manifest_path = staging / "manifest.json"
            _sync_write_bytes(data_path, bundle.data)
            _sync_write_bytes(manifest_path, bundle.manifest_bytes)
            os.replace(staging, target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return bundle.result_document(root=target)


class AnalyticsExportQueue:
    def __init__(
        self,
        data_root: str | Path,
        service: AnalyticsExportService,
        *,
        catalog: JobCatalog | None = None,
    ) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.service = service
        self.catalog = catalog or JobCatalog(self.data_root / "jobs.sqlite3")
        self.request_root = (self.data_root / "export-requests").resolve()

    def _request_path(self, input_digest: str) -> Path:
        _content_id(input_digest, "export input digest", "jobinput_")
        path = (self.request_root / f"{input_digest}.json").resolve()
        if not path.is_relative_to(self.request_root):
            raise ValueError("export request path escaped its owned root")
        return path

    def enqueue(
        self,
        request: AnalyticsExportRequest,
        *,
        created_at: str,
        idempotency_key: str | None = None,
        priority: int = 0,
    ) -> JobRecord:
        bound = self.service.bind_request(request)
        input_digest = stable_digest(bound.to_dict(), prefix="jobinput_")
        path = self._request_path(input_digest)
        content = canonical_json(bound.to_dict()) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise ValueError("content-addressed export request file conflicts")
        atomic_write_text(path, content)
        if bound.source_kind == AnalyticsExportSourceKind.QUERY:
            if bound.query is None or bound.query.snapshot_id is None:
                raise AssertionError("bound export query lost its snapshot ID")
            query_snapshot_id = bound.query.snapshot_id
        else:
            comparison = _validate_comparison_report(bound.comparison)
            query_snapshot_id = comparison["request"]["query_snapshot_id"]
        spec = JobSpec(
            kind=JobKind.EXPORT,
            idempotency_key=(
                idempotency_key
                or f"analytics-export-{bound.format.value}-{bound.request_id}"
            ),
            input_digest=input_digest,
            payload={
                "format": bound.format.value,
                "query_snapshot_id": query_snapshot_id,
            },
            priority=priority,
            max_attempts=3,
            retry_policy=JobRetryPolicy(
                attempt_timeout_seconds=600.0,
                initial_backoff_seconds=0.0,
                retryable_error_codes=(
                    "disk_full",
                    "hard_timeout",
                    "lease_expired",
                    "transient_io",
                    "worker_crash",
                ),
            ),
        )
        return self.catalog.create_job(spec, created_at=created_at, actor="export-api")

    def load_request(self, input_digest: str) -> AnalyticsExportRequest:
        path = self._request_path(input_digest)
        if not path.is_file():
            raise FileNotFoundError(
                "content-addressed analytics export request is missing"
            )
        request = AnalyticsExportRequest.from_mapping(
            json.loads(path.read_text(encoding="utf-8"))
        )
        if stable_digest(request.to_dict(), prefix="jobinput_") != input_digest:
            raise ValueError("analytics export input digest does not match its content")
        return request


@dataclass(frozen=True)
class AnalyticsExportWorkerOutcome:
    status: str
    job_id: str | None
    attempt: int | None
    export_id: str | None = None


class AnalyticsExportWorker:
    def __init__(
        self,
        queue: AnalyticsExportQueue,
        *,
        worker_id: str = "analytics-export-worker",
        lease_seconds: float = EXPORT_LEASE_SECONDS,
        now: Callable[[], str] = _utc_now,
        build: Callable[..., AnalyticsExportBundle] | None = None,
    ) -> None:
        self.queue = queue
        self.catalog = queue.catalog
        self.publisher = JobArtifactPublisher(
            queue.data_root / "export-job-store", self.catalog
        )
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.now = now
        self.build = build or queue.service.build

    def recover(self) -> tuple[str, ...]:
        reclaimed = self.catalog.reclaim_orphans(now=self.now(), actor=self.worker_id)
        self.publisher.reconcile()
        return tuple(item.job_id for item in reclaimed)

    def run_once(self) -> AnalyticsExportWorkerOutcome:
        self.recover()
        job = self.catalog.claim_next(
            worker_id=self.worker_id,
            now=self.now(),
            lease_seconds=self.lease_seconds,
            kinds=(JobKind.EXPORT,),
        )
        if job is None:
            return AnalyticsExportWorkerOutcome("idle", None, None)
        if job.lease_token is None:
            raise JobLeaseError("claimed export job has no lease token")
        try:
            request = self.queue.load_request(job.spec.input_digest)
            bundle = self.build(
                request,
                cancel_requested=lambda: self._cancel_requested(job),
            )
            if self._cancel_requested(job):
                raise InterruptedError("analytics export was cancelled")
            _ensure_free_space(
                self.publisher.root,
                2 * (len(bundle.data) + len(bundle.manifest_bytes)),
            )
            staged = [
                self.publisher.stage_bytes(
                    job,
                    lease_token=job.lease_token,
                    now=self.now(),
                    logical_path=f"{bundle.export_id}/{bundle.data_filename}",
                    kind="analytics_export_data",
                    artifact_schema_version=ANALYTICS_EXPORT_DATA_SCHEMA_VERSION,
                    content=bundle.data,
                    row_count=bundle.row_count,
                ),
                self.publisher.stage_bytes(
                    job,
                    lease_token=job.lease_token,
                    now=self.now(),
                    logical_path=f"{bundle.export_id}/manifest.json",
                    kind="analytics_export_manifest",
                    artifact_schema_version=ANALYTICS_EXPORT_MANIFEST_SCHEMA_VERSION,
                    content=bundle.manifest_bytes,
                    row_count=bundle.row_count,
                ),
            ]
            self.catalog.save_checkpoint(
                job.job_id,
                lease_token=job.lease_token,
                now=self.now(),
                recovery_position=bundle.export_id,
                completed_units=bundle.row_count,
                total_units=bundle.row_count,
                payload={
                    "data_sha256": _sha256_bytes(bundle.data),
                    "manifest_sha256": _sha256_bytes(bundle.manifest_bytes),
                    "schema_version": ANALYTICS_EXPORT_RESULT_SCHEMA_VERSION,
                },
                semantic_result_digest=stable_digest(
                    bundle.manifest, prefix="jobsemantic_"
                ),
            )
            self.publisher.publish(
                job,
                actor=self.worker_id,
                now=self.now(),
                lease_token=job.lease_token,
                staged_artifacts=staged,
            )
            return AnalyticsExportWorkerOutcome(
                "succeeded", job.job_id, job.attempt, bundle.export_id
            )
        except InterruptedError:
            self.catalog.finish_cancelled(
                job.job_id,
                actor=self.worker_id,
                now=self.now(),
                reason="export_cancelled",
                lease_token=job.lease_token,
            )
            return AnalyticsExportWorkerOutcome("cancelled", job.job_id, job.attempt)
        except AnalyticsExportRetryableError as exc:
            return self._retry_or_fail(job, exc.code, str(exc))
        except OSError as exc:
            return self._retry_or_fail(job, "transient_io", str(exc))
        except (ValueError, RuntimeError) as exc:
            cancelled = self._finish_active_cancel(job)
            if cancelled is not None:
                return cancelled
            self.catalog.quarantine_job(
                job.job_id,
                actor=self.worker_id,
                now=self.now(),
                reason=str(exc),
                lease_token=job.lease_token,
            )
            return AnalyticsExportWorkerOutcome("quarantined", job.job_id, job.attempt)

    def _cancel_requested(self, job: JobRecord) -> bool:
        if job.lease_token is None:
            return True
        signal = self.catalog.control_signal(
            job.job_id,
            lease_token=job.lease_token,
            now=self.now(),
        )
        return signal.should_stop

    def _finish_active_cancel(
        self, job: JobRecord
    ) -> AnalyticsExportWorkerOutcome | None:
        current = self.catalog.get_job(job.job_id)
        if (
            current is None
            or current.state != JobState.CANCELLING
            or current.attempt != job.attempt
            or current.lease_token != job.lease_token
        ):
            return None
        self.catalog.finish_cancelled(
            job.job_id,
            actor=self.worker_id,
            now=self.now(),
            reason="export_cancelled",
            lease_token=job.lease_token,
        )
        return AnalyticsExportWorkerOutcome("cancelled", job.job_id, job.attempt)

    def _retry_or_fail(
        self, job: JobRecord, error_code: str, message: str
    ) -> AnalyticsExportWorkerOutcome:
        if job.lease_token is None:
            raise JobLeaseError("export retry requires an active lease")
        if (
            job.attempt < job.max_attempts
            and error_code in job.spec.retry_policy.retryable_error_codes
        ):
            self.catalog.schedule_retry(
                job.job_id,
                actor=self.worker_id,
                now=self.now(),
                reason=message or error_code,
                error_code=error_code,
                lease_token=job.lease_token,
            )
            return AnalyticsExportWorkerOutcome("retrying", job.job_id, job.attempt)
        self.catalog.fail_job(
            job.job_id,
            actor=self.worker_id,
            now=self.now(),
            error_code=error_code,
            error_message=message or error_code,
            lease_token=job.lease_token,
        )
        return AnalyticsExportWorkerOutcome("failed", job.job_id, job.attempt)


class AnalyticsExportSupervisor:
    def __init__(
        self,
        worker: AnalyticsExportWorker,
        *,
        idle_seconds: float = EXPORT_POLL_SECONDS,
    ) -> None:
        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        self.worker = worker
        self.idle_seconds = float(idle_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failure: BaseException | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def failure(self) -> BaseException | None:
        return self._failure

    @property
    def health(self) -> str:
        if self._failure is not None:
            return "failed"
        if self.running:
            return "running"
        return "stopped"

    def start(self) -> None:
        if self.running:
            raise RuntimeError("analytics export supervisor is already running")
        self._stop.clear()
        self._failure = None
        self._thread = threading.Thread(
            target=self._run,
            name="ygo-analytics-export-supervisor",
            daemon=False,
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                outcome = self.worker.run_once()
                if outcome.status == "idle":
                    self._stop.wait(self.idle_seconds)
        except BaseException as exc:
            self._failure = exc

    def stop(self, *, timeout: float = 15.0) -> None:
        self._stop.set()
        if self._thread is None:
            return
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise RuntimeError("analytics export supervisor did not stop cleanly")
        self._thread = None


def analytics_export_contract_document() -> dict[str, Any]:
    return {
        "formats": [item.value for item in AnalyticsExportFormat],
        "limits": {
            "max_bytes": MAX_EXPORT_BYTES,
            "max_output_rows": MAX_EXPORT_OUTPUT_ROWS,
            "max_scan_rows": MAX_EXPORT_SCAN_ROWS,
        },
        "parity": {
            "semantic_digest": "exportsemantic_ SHA-256 content identity",
            "surfaces": ["cli", "desktop_bridge", "desktop_ui"],
        },
        "safety": {
            "csv_formula_injection": "canonical JSON cells plus apostrophe escape",
            "output_paths": "caller-owned root with fixed filenames",
            "renderer_path_input": False,
        },
        "schemas": {
            "data": ANALYTICS_EXPORT_DATA_SCHEMA_VERSION,
            "manifest": ANALYTICS_EXPORT_MANIFEST_SCHEMA_VERSION,
            "request": ANALYTICS_EXPORT_REQUEST_SCHEMA_VERSION,
            "result": ANALYTICS_EXPORT_RESULT_SCHEMA_VERSION,
            "worker": ANALYTICS_EXPORT_WORKER_SCHEMA_VERSION,
        },
        "schema_version": ANALYTICS_EXPORT_CONTRACT_VERSION,
        "source_kinds": [item.value for item in AnalyticsExportSourceKind],
    }


__all__ = [
    "ANALYTICS_EXPORT_CONTRACT_VERSION",
    "ANALYTICS_EXPORT_DATA_SCHEMA_VERSION",
    "ANALYTICS_EXPORT_MANIFEST_SCHEMA_VERSION",
    "ANALYTICS_EXPORT_REQUEST_SCHEMA_VERSION",
    "ANALYTICS_EXPORT_RESULT_SCHEMA_VERSION",
    "ANALYTICS_EXPORT_WORKER_SCHEMA_VERSION",
    "AnalyticsExportBundle",
    "AnalyticsExportFormat",
    "AnalyticsExportQueue",
    "AnalyticsExportRequest",
    "AnalyticsExportRetryableError",
    "AnalyticsExportService",
    "AnalyticsExportSourceKind",
    "AnalyticsExportSupervisor",
    "AnalyticsExportWorker",
    "AnalyticsExportWorkerOutcome",
    "analytics_export_contract_document",
    "decode_export_dataset",
]
