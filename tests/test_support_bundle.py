from __future__ import annotations

import argparse
import json
from pathlib import Path

from ygo_effect_dsl.cli.cmd_support import cmd_support_bundle
from ygo_effect_dsl.support_bundle import (
    REDACTED_SUPPORT_BUNDLE_MANIFEST_SCHEMA_VERSION,
    REDACTED_SUPPORT_DIAGNOSTICS_SCHEMA_VERSION,
    write_redacted_support_bundle,
)


PRIVATE_CANARY = "private-support-card-360"


def test_support_bundle_redacts_private_canary_paths_and_raw_payloads(
    tmp_path: Path,
) -> None:
    recent_error = tmp_path / "recent-error.json"
    recent_error.write_text(
        json.dumps(
            {
                "absolute_path": str(tmp_path / "Users" / "name" / "deck.ydk"),
                "diagnostic_code": "worker_crash",
                "private_hand": [PRIVATE_CANARY],
                "raw_payload": f"payload:{PRIVATE_CANARY}",
                "token": "secret-token-value",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "support-bundle"

    manifest = write_redacted_support_bundle(
        output_dir=output,
        recent_error_json=recent_error,
        private_canaries=[PRIVATE_CANARY],
    )

    assert manifest["schema_version"] == REDACTED_SUPPORT_BUNDLE_MANIFEST_SCHEMA_VERSION
    assert manifest["automatic_upload"] is False
    assert manifest["retention_policy"]["raw_payloads_included"] is False
    assert (output / "manifest.json").is_file()
    assert (output / "diagnostics.json").is_file()
    assert (output / "redaction-report.json").is_file()
    assert (output / "README.json").is_file()
    combined = "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    assert PRIVATE_CANARY not in combined
    assert "secret-token-value" not in combined
    assert str(tmp_path) not in combined
    diagnostics = json.loads((output / "diagnostics.json").read_text(encoding="utf-8"))
    report = json.loads((output / "redaction-report.json").read_text(encoding="utf-8"))
    assert "raw_payload" not in json.dumps(diagnostics, sort_keys=True)
    assert diagnostics["schema_version"] == REDACTED_SUPPORT_DIAGNOSTICS_SCHEMA_VERSION
    assert diagnostics["automatic_upload"] is False
    assert diagnostics["redaction"]["hidden_payload_retained"] is False
    assert report["status"] == "passed"


def test_support_bundle_cli_writes_manifest_and_redaction_report(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "bundle"

    status = cmd_support_bundle(
        argparse.Namespace(
            external_root=None,
            out=output,
            private_canary=[PRIVATE_CANARY],
            recent_error_json=None,
            size_limit_bytes=64 * 1024,
        )
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "support-bundle: ok" in captured.out
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))[
        "bundle_id"
    ].startswith("supportbundle_")
    assert json.loads((output / "redaction-report.json").read_text(encoding="utf-8"))[
        "status"
    ] == "passed"
