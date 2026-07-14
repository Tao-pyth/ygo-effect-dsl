from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


REPORT_SCHEMA_VERSION = "report-v1"


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def build_markdown_report(
    experiment: Mapping[str, Any],
    route: Mapping[str, Any],
) -> str:
    result = route["result"]
    peak = result["peak_board"]
    terminal = result["terminal_board"]
    evaluation_result = peak.get("evaluation_result", {})
    breakdown = evaluation_result.get("score_breakdown", {})
    lines = [
        f"<!-- schema_version: {REPORT_SCHEMA_VERSION} -->",
        f"# Experiment Report: {experiment['experiment_id']}",
        "",
        "## Summary",
        "",
        f"- Route ID: `{route['route_id']}`",
        f"- Status: `{route['status']}`",
        f"- Success: `{str(result['success']).lower()}`",
        f"- Events: `{len(route['replay']['events'])}`",
        f"- Peak score: `{peak['score']}` at checkpoint `{peak['checkpoint_step']}`",
        f"- Terminal score: `{terminal['score']}` at checkpoint `{terminal['checkpoint_step']}`",
        "",
        "## Peak Score Breakdown",
        "",
        "| Metric | Raw | Resolved | Weight | Contribution | Resolution |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for term in breakdown.get("terms", []):
        lines.append(
            "| "
            + " | ".join(
                _cell(term.get(field))
                for field in (
                    "metric",
                    "raw_value",
                    "resolved_value",
                    "weight",
                    "contribution",
                    "resolution",
                )
            )
            + " |"
        )
    durability = result.get("durability")
    if isinstance(durability, Mapping):
        lines.extend(
            [
                "",
                "## Durability",
                "",
                f"- Before: turn `{durability['before']['turn']}` phase `{durability['before']['phase']}` score `{durability['before']['score']}`",
                f"- After: turn `{durability['after']['turn']}` phase `{durability['after']['phase']}` score `{durability['after']['score']}`",
                f"- Score delta: `{durability['delta']['score']}`",
                f"- Success retained: `{str(durability['success_retained']).lower()}`",
            ]
        )
    prototype = experiment.get("prototype")
    pending = prototype.get("pending_validation", []) if isinstance(prototype, Mapping) else []
    lines.extend(["", "## Pending Validation", ""])
    if pending:
        for item in pending:
            lines.append(f"- Issue #{item['issue']}: `{item['contract']}`")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "This report is derived from the versioned Route DSL. It is not the replay source of truth.",
            "",
        ]
    )
    return "\n".join(lines)


def write_markdown_report(
    experiment: Mapping[str, Any],
    route: Mapping[str, Any],
    path: str | Path,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        build_markdown_report(experiment, route),
        encoding="utf-8",
    )
