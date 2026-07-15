from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from ygo_effect_dsl.desktop import desktop_frontend_root
from ygo_effect_dsl.desktop.bridge import (
    DESKTOP_BRIDGE_CONTRACT_VERSION,
    DesktopBridge,
)
from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.storage import (
    ANALYTICS_EXPORT_CONTRACT_VERSION,
    AnalyticsExportFormat,
    AnalyticsExportRequest,
    AnalyticsExportService,
    AnalyticsExportSourceKind,
    AnalyticsFilter,
    AnalyticsQueryRequest,
    AnalyticsQueryRow,
    AnalyticsQueryService,
    AnalyticsSnapshot,
    AnalyticsSnapshotStore,
    AnalyticsSort,
    AnalyticsValue,
    decode_export_dataset,
)
from ygo_effect_dsl.version import __version__

ANALYTICS_EXPORT_EVIDENCE_VERSION = "analytics-export-evidence-v1"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _snapshot() -> AnalyticsSnapshot:
    return AnalyticsSnapshot(
        rows=(
            AnalyticsQueryRow.build(
                {
                    "deck": "deck_export_fixture",
                    "run": "=formula-fixture",
                    "score": 3.5,
                    "status": AnalyticsValue.redacted(),
                },
                row_id="=formula-row",
            ),
            AnalyticsQueryRow.build(
                {
                    "deck": "deck_export_fixture",
                    "run": "run_high",
                    "score": 9.0,
                    "status": "complete",
                },
                row_id="row_high",
            ),
            AnalyticsQueryRow.build(
                {
                    "deck": "other_deck",
                    "run": "run_filtered",
                    "score": 12.0,
                    "status": "complete",
                },
                row_id="row_filtered",
            ),
        ),
        source_ids=("corpusmanifest_export_fixture",),
    )


def _query() -> AnalyticsQueryRequest:
    return AnalyticsQueryRequest(
        fields=("run", "deck", "score", "status"),
        filters=(AnalyticsFilter("deck", "eq", "deck_export_fixture"),),
        sort=(AnalyticsSort("score", "desc"),),
        limit=500,
    )


def _bridge_request(payload: dict[str, Any], sequence: int) -> dict[str, Any]:
    return {
        "method": "analytics.export.enqueue",
        "payload": payload,
        "request_id": f"export-evidence-{sequence}",
        "version": DESKTOP_BRIDGE_CONTRACT_VERSION,
    }


def collect_analytics_export_evidence(artifact_dir: Path) -> dict[str, Any]:
    artifact_dir = artifact_dir.expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot()
    query = _query()
    snapshots = AnalyticsSnapshotStore()
    snapshots.register(snapshot)
    query_service = AnalyticsQueryService(snapshots)
    service = AnalyticsExportService(query_service)
    semantic_baseline: dict[str, Any] | None = None
    formats: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="analytics-export-evidence-") as raw:
        temporary = Path(raw)
        snapshot_path = temporary / "snapshot.json"
        query_path = temporary / "query.json"
        snapshot_path.write_text(
            json.dumps(snapshot.to_dict(), sort_keys=True), encoding="utf-8"
        )
        query_path.write_text(
            json.dumps(query.to_dict(), sort_keys=True), encoding="utf-8"
        )
        desktop = DesktopApplicationService(
            temporary / "desktop",
            analytics_service=query_service,
        )
        bridge = DesktopBridge(desktop.handlers())

        for sequence, export_format in enumerate(AnalyticsExportFormat, start=1):
            request = AnalyticsExportRequest(
                format=export_format,
                source_kind=AnalyticsExportSourceKind.QUERY,
                query=query,
            )
            direct = service.build(request)

            cli = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ygo_effect_dsl",
                    "analytics-export",
                    "--format",
                    export_format.value,
                    "--out",
                    str(temporary / "cli" / export_format.value),
                    "--query",
                    str(query_path),
                    "--snapshot",
                    str(snapshot_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            cli_result = json.loads(cli.stdout)
            cli_data = Path(cli_result["files"]["data"]).read_bytes()
            cli_manifest = Path(cli_result["files"]["manifest"]).read_bytes()

            response = bridge.invoke(
                _bridge_request(
                    {
                        "format": export_format.value,
                        "idempotency_key": None,
                        "priority": 0,
                        "source": query.to_dict(),
                        "source_kind": "query",
                    },
                    sequence,
                )
            )
            if not response["ok"]:
                raise RuntimeError(f"desktop export enqueue failed: {response}")
            outcome = desktop.analytics_export_worker.run_once()
            if outcome.status != "succeeded":
                raise RuntimeError(f"desktop export worker failed: {outcome}")
            status = desktop.job_catalog.status_snapshot(
                response["result"]["job"]["job_id"]
            )
            desktop_payloads = {
                artifact.kind: (
                    desktop.analytics_export_worker.publisher.root / artifact.path
                ).read_bytes()
                for artifact in status.artifacts
            }
            desktop_data = desktop_payloads["analytics_export_data"]
            desktop_manifest = desktop_payloads["analytics_export_manifest"]
            if not (
                direct.data == cli_data == desktop_data
                and direct.manifest_bytes == cli_manifest == desktop_manifest
            ):
                raise ValueError(
                    f"{export_format.value} CLI/API/UI export bytes diverged"
                )

            semantic = decode_export_dataset(
                export_format, direct.data, direct.manifest
            )
            if semantic_baseline is None:
                semantic_baseline = semantic
            elif semantic != semantic_baseline:
                raise ValueError(
                    f"{export_format.value} semantic export content diverged"
                )

            data_name = f"analytics.{export_format.value}"
            manifest_name = f"manifest-{export_format.value}.json"
            data_path = artifact_dir / data_name
            manifest_path = artifact_dir / manifest_name
            data_path.write_bytes(direct.data)
            manifest_path.write_bytes(direct.manifest_bytes)
            formats[export_format.value] = {
                "data": {
                    "bytes": len(direct.data),
                    "filename": data_name,
                    "sha256": _sha256(direct.data),
                },
                "export_id": direct.export_id,
                "manifest": {
                    "bytes": len(direct.manifest_bytes),
                    "filename": manifest_name,
                    "sha256": _sha256(direct.manifest_bytes),
                },
                "row_count": direct.row_count,
                "semantic_digest": direct.manifest["semantic_digest"],
                "surface_byte_parity": True,
            }

    csv_rows = list(
        csv.DictReader(io.StringIO((artifact_dir / "analytics.csv").read_text("utf-8")))
    )
    formula_row = next(row for row in csv_rows if "formula-row" in row["row_id_json"])
    if formula_row["row_id_json"].startswith(("=", "+", "-", "@", "\t", "\r")):
        raise ValueError("CSV export exposed a formula-capable leading character")

    frontend = desktop_frontend_root()
    app_script = (frontend / "app.js").read_text(encoding="utf-8")
    bridge_script = (frontend / "bridge.js").read_text(encoding="utf-8")
    if "analytics.export.enqueue" not in app_script or (
        "analytics.export.enqueue" not in bridge_script
    ):
        raise ValueError("desktop export command is not connected to the bridge")
    if "new Blob" in app_script or "URL.createObjectURL" in app_script:
        raise ValueError("renderer must not author analytics export bytes")

    semantic_digests = {item["semantic_digest"] for item in formats.values()}
    if len(semantic_digests) != 1:
        raise ValueError("export formats do not share one semantic digest")
    identity = to_canonical_data(
        {
            "contract_version": ANALYTICS_EXPORT_CONTRACT_VERSION,
            "formats": formats,
            "package_version": __version__,
            "safety": {
                "csv_formula_leading_character_exposed": False,
                "desktop_renderer_authors_bytes": False,
                "desktop_renderer_path_input": False,
            },
            "schema_version": ANALYTICS_EXPORT_EVIDENCE_VERSION,
            "source": {
                "query_fingerprint": service.bind_request(
                    AnalyticsExportRequest(
                        format=AnalyticsExportFormat.JSON,
                        source_kind=AnalyticsExportSourceKind.QUERY,
                        query=query,
                    )
                ).query.fingerprint,
                "snapshot_id": snapshot.snapshot_id,
                "source_ids": list(snapshot.source_ids),
            },
            "surfaces": ["service", "cli_subprocess", "desktop_bridge_worker"],
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="analyticsexportevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="prove versioned analytics export parity across public surfaces"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    evidence = collect_analytics_export_evidence(args.artifact_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"analytics-export-evidence: wrote {args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
