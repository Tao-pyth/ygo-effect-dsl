from __future__ import annotations

from collections.abc import Mapping
from collections import Counter
import hashlib
import json
import platform
from pathlib import Path
from typing import Any

from ygo_effect_dsl import __version__
from ygo_effect_dsl.desktop import DESKTOP_BRIDGE_CONTRACT_VERSION
from ygo_effect_dsl.desktop.service import DESKTOP_RESULT_VIEW_VERSION
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation import (
    ROUTE_RANDOMNESS_SUMMARY_SCHEMA_VERSION,
    ROUTE_RANKING_POLICY_SCHEMA_VERSION,
    ROUTE_RANKING_SCHEMA_VERSION,
    TERMINAL_BOARD_PROJECTION_SCHEMA_VERSION,
    TERMINAL_PREFERENCE_CATALOG_SCHEMA_VERSION,
    TERMINAL_PREFERENCE_EVALUATION_SCHEMA_VERSION,
    TERMINAL_PREFERENCE_PROFILE_SCHEMA_VERSION,
)
from ygo_effect_dsl.engine.search import (
    SEARCH_RUN_REPORT_SCHEMA_VERSION,
    SEARCH_RUN_RESULT_SCHEMA_VERSION,
)
from ygo_effect_dsl.engine.search.executor import (
    SEARCH_CANDIDATE_EVIDENCE_SCHEMA_VERSION,
    SEARCH_COVERAGE_SCHEMA_VERSION,
)
from ygo_effect_dsl.experiment import read_fresh_replay_verification_report
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.route_dsl import load_route_document
from ygo_effect_dsl.storage.query import ANALYTICS_QUERY_CONTRACT_VERSION


RESEARCH_DASHBOARD_RELEASE_GATE_SCHEMA_VERSION = (
    "research-dashboard-release-gate-v1"
)
RESEARCH_DASHBOARD_QUALIFICATION_SCHEMA_VERSION = (
    "research-dashboard-qualification-v1"
)
RESEARCH_DASHBOARD_QUALIFICATION_ARTIFACT_MANIFEST_SCHEMA_VERSION = (
    "research-dashboard-qualification-artifact-manifest-v1"
)
REQUIRED_QUALIFICATION_CHECKS = (
    "committed-artifact-e2e",
    "fresh-replay-e2e",
    "desktop-screenshot-a11y",
    "security-redaction",
    "resource-budget",
)
QUALIFICATION_SCREENSHOT_VIEWPORTS = (
    "1440x900",
    "960x600",
    "360x800",
)
REQUIRED_STATIC_GATE_CHECKS = (
    ("A", "committed-result-artifact-service"),
    ("A", "independent-replay-verification-service"),
    ("B", "terminal-preference-contracts"),
    ("C", "route-randomness-and-ranking-contracts"),
    ("D", "candidate-coverage-and-drilldown-contracts"),
    ("E", "typed-research-scenario-and-cohort-ui"),
    ("E", "neuron-direct-import-rejection-adr"),
)
REQUIRED_MANUAL_GATE_CHECKS = (
    ("release", "real-core-dashboard-qualification"),
)
DEFAULT_QUALIFICATION_PATH = (
    "docs/release/evidence/research_dashboard_qualification.json"
)


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _text_contains(root: Path, relative_path: str, needles: tuple[str, ...]) -> bool:
    path = root / relative_path
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return all(needle in text for needle in needles)


def _test_file_exists(root: Path, relative_path: str) -> bool:
    return (root / relative_path).is_file()


def _bridge_method_check(
    bridge: Mapping[str, Any],
    method: str,
    *,
    required_fields: tuple[str, ...] = (),
) -> bool:
    methods = bridge.get("methods")
    if not isinstance(methods, Mapping):
        return False
    record = methods.get(method)
    if not isinstance(record, Mapping):
        return False
    fields = record.get("payload_fields", ())
    return all(field in fields for field in required_fields)


def _bridge_method_record(
    bridge: Mapping[str, Any],
    method: str,
) -> Mapping[str, Any]:
    methods = bridge.get("methods")
    if not isinstance(methods, Mapping):
        return {}
    record = methods.get(method)
    return record if isinstance(record, Mapping) else {}


def _analytics_fields_check(
    contract: Mapping[str, Any],
    fields: tuple[str, ...],
) -> bool:
    raw_fields = contract.get("fields")
    return isinstance(raw_fields, Mapping) and all(field in raw_fields for field in fields)


def _check(
    gate: str,
    check_id: str,
    passed: bool,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "evidence": to_canonical_data(evidence),
        "gate": gate,
        "passed": bool(passed),
    }


def _source_path_name(path: Path) -> str:
    return path.name


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _require_literals(
    evidence: Mapping[str, Any],
    expectations: Mapping[str, Any],
    issues: list[str],
) -> None:
    for field, expected in expectations.items():
        if evidence.get(field) != expected:
            issues.append(field)


def _string_has_path_leak(value: str) -> bool:
    return "/" in value or "\\" in value or (len(value) >= 3 and value[1:3] in (":/", ":\\"))


def _evidence_contains_path_leak(
    value: Any,
    *,
    allowed_path_keys: frozenset[str] = frozenset(
        {"path_redacted", "source_path_name"}
    ),
) -> bool:
    if isinstance(value, str):
        return _string_has_path_leak(value)
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text not in allowed_path_keys and (
                key_text == "path" or key_text.endswith("_path")
            ):
                return True
            if _evidence_contains_path_leak(item, allowed_path_keys=allowed_path_keys):
                return True
        return False
    if isinstance(value, list):
        return any(
            _evidence_contains_path_leak(
                item,
                allowed_path_keys=allowed_path_keys,
            )
            for item in value
        )
    return False


def _artifact_sha256_by_name(evidence: Mapping[str, Any]) -> dict[str, str]:
    artifacts = evidence.get("evidence_artifacts")
    if not isinstance(artifacts, list):
        return {}
    index: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        name = artifact.get("name")
        sha256 = artifact.get("sha256")
        if isinstance(name, str) and _is_sha256(sha256):
            index[name] = sha256
    return index


def _require_artifact_sha256(
    evidence: Mapping[str, Any],
    artifact_name: str,
    expected_sha256: Any,
    issues: list[str],
) -> None:
    if _artifact_sha256_by_name(evidence).get(artifact_name) != expected_sha256:
        issues.append("evidence_artifacts.sha256")


def _prepared_artifacts(
    evidence: Mapping[str, Any],
    *,
    base_dir: Path,
) -> tuple[list[dict[str, Any]] | None, bool]:
    raw_artifacts = evidence.get("evidence_artifacts")
    if not isinstance(raw_artifacts, list):
        return None, False
    prepared: list[dict[str, Any]] = []
    used_paths = False
    for raw_artifact in raw_artifacts:
        if not isinstance(raw_artifact, Mapping):
            prepared.append(to_canonical_data(raw_artifact))
            continue
        artifact = dict(raw_artifact)
        raw_path = artifact.pop("path", None)
        if isinstance(raw_path, str) and raw_path:
            path = Path(raw_path)
            if not path.is_absolute():
                path = base_dir / path
            artifact.setdefault("name", path.name)
            artifact["sha256"] = _sha256_file(path)
            used_paths = True
        prepared.append(to_canonical_data(artifact))
    return prepared, used_paths


def _fill_artifact_sha_witnesses(check_id: str, evidence: dict[str, Any]) -> None:
    artifact_sha256 = _artifact_sha256_by_name(evidence)
    if check_id == "committed-artifact-e2e":
        for field, artifact_name in (
            ("report_sha256", "search-report.json"),
            ("result_view_sha256", "result-view.json"),
            ("route_sha256", "route.yaml"),
        ):
            if field not in evidence and artifact_name in artifact_sha256:
                evidence[field] = artifact_sha256[artifact_name]
    elif check_id == "fresh-replay-e2e":
        if (
            "replay_report_sha256" not in evidence
            and "fresh-replay-report.json" in artifact_sha256
        ):
            evidence["replay_report_sha256"] = artifact_sha256[
                "fresh-replay-report.json"
            ]
    elif check_id == "desktop-screenshot-a11y":
        screenshot_sha256 = evidence.get("screenshot_sha256")
        if not isinstance(screenshot_sha256, Mapping):
            screenshot_sha256 = {}
        else:
            screenshot_sha256 = dict(screenshot_sha256)
        for viewport in QUALIFICATION_SCREENSHOT_VIEWPORTS:
            artifact_name = f"desktop-{viewport}.png"
            if viewport not in screenshot_sha256 and artifact_name in artifact_sha256:
                screenshot_sha256[viewport] = artifact_sha256[artifact_name]
        if screenshot_sha256:
            evidence["screenshot_sha256"] = screenshot_sha256
    elif check_id == "security-redaction":
        if (
            "review_sha256" not in evidence
            and "security-redaction-review.json" in artifact_sha256
        ):
            evidence["review_sha256"] = artifact_sha256[
                "security-redaction-review.json"
            ]
    elif check_id == "resource-budget":
        if (
            "resource_report_sha256" not in evidence
            and "resource-budget.json" in artifact_sha256
        ):
            evidence["resource_report_sha256"] = artifact_sha256[
                "resource-budget.json"
            ]


def prepare_research_dashboard_qualification_checks(
    checks: list[Mapping[str, Any]],
    *,
    base_dir: str | Path = ".",
) -> list[dict[str, Any]]:
    root = Path(base_dir)
    prepared_checks: list[dict[str, Any]] = []
    for raw_check in checks:
        if not isinstance(raw_check, Mapping):
            prepared_checks.append(to_canonical_data(raw_check))
            continue
        check = dict(raw_check)
        check_id = check.get("check_id")
        raw_evidence = check.get("evidence")
        if isinstance(raw_evidence, Mapping):
            evidence = dict(raw_evidence)
            artifacts, used_paths = _prepared_artifacts(evidence, base_dir=root)
            if artifacts is not None:
                evidence["evidence_artifacts"] = artifacts
            if used_paths and "path_redacted" not in evidence:
                evidence["path_redacted"] = True
            if isinstance(check_id, str):
                _fill_artifact_sha_witnesses(check_id, evidence)
            check["evidence"] = evidence
        prepared_checks.append(to_canonical_data(check))
    return prepared_checks


def _manifest_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _manifest_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _manifest_required_bool(source: Mapping[str, Any], name: str) -> bool:
    value = source.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _manifest_int(
    source: Mapping[str, Any],
    name: str,
    *,
    minimum: int = 1,
) -> int:
    value = source.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _manifest_number(
    source: Mapping[str, Any],
    name: str,
    *,
    minimum: float = 0.0,
) -> float:
    value = source.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= minimum:
        raise ValueError(f"{name} must be a number > {minimum}")
    return float(value)


def _required_json_object(path: str | Path, name: str, *, base_dir: Path) -> Mapping[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{name} must point to a readable JSON object") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must point to valid JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must point to a JSON object")
    return value


def _required_route_document(path: str | Path, name: str, *, base_dir: Path) -> Mapping[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    try:
        return load_route_document(candidate)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{name} must point to a Route DSL document") from exc


def _resolve_manifest_artifact_path(path: str | Path, *, base_dir: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate


def _matching_report_value(
    report: Mapping[str, Any],
    manifest: Mapping[str, Any],
    name: str,
) -> None:
    if name in report and name in manifest and report.get(name) != manifest.get(name):
        raise ValueError(f"{name} does not match artifact manifest")


def _viewport_dimensions(viewport: str) -> tuple[int, int]:
    width_text, separator, height_text = viewport.partition("x")
    if not separator:
        raise ValueError(f"invalid viewport label {viewport!r}")
    return int(width_text), int(height_text)


def _validate_png_viewport(
    path: str | Path,
    viewport: str,
    *,
    base_dir: Path,
) -> None:
    candidate = _resolve_manifest_artifact_path(path, base_dir=base_dir)
    try:
        header = candidate.read_bytes()[:24]
    except OSError as exc:
        raise ValueError(f"screenshot {viewport} must be readable") from exc
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"screenshot {viewport} must be a PNG file")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    expected_width, expected_height = _viewport_dimensions(viewport)
    if (width, height) != (expected_width, expected_height):
        raise ValueError(
            f"screenshot {viewport} dimensions {width}x{height} do not match"
        )


def _artifact_entry(name: str, path: str, kind: str) -> dict[str, str]:
    return {"kind": kind, "name": name, "path": path}


def _artifact_id_from_file(
    path: str | Path,
    *,
    base_dir: Path,
    prefix: str,
) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return stable_digest({"sha256": _sha256_file(candidate)}, prefix=prefix)


def build_research_dashboard_qualification_checks_from_artifact_manifest(
    source: Mapping[str, Any],
    *,
    base_dir: str | Path = ".",
) -> list[dict[str, Any]]:
    if source.get("schema_version") != (
        RESEARCH_DASHBOARD_QUALIFICATION_ARTIFACT_MANIFEST_SCHEMA_VERSION
    ):
        raise ValueError("unsupported research dashboard qualification artifact manifest")
    root = Path(base_dir)
    committed = _manifest_mapping(source.get("committed_artifact"), "committed_artifact")
    fresh = _manifest_mapping(source.get("fresh_replay"), "fresh_replay")
    desktop = _manifest_mapping(source.get("desktop"), "desktop")
    security = _manifest_mapping(source.get("security_redaction"), "security_redaction")
    resource = _manifest_mapping(source.get("resource_budget"), "resource_budget")

    result_view_path = _manifest_path(committed.get("result_view"), "result_view")
    route_path = _manifest_path(committed.get("route"), "route")
    search_report_path = _manifest_path(committed.get("search_report"), "search_report")
    result_view = _required_json_object(
        result_view_path,
        "committed_artifact.result_view",
        base_dir=root,
    )
    if result_view.get("schema_version") != DESKTOP_RESULT_VIEW_VERSION:
        raise ValueError("committed_artifact.result_view schema_version is invalid")
    search_report = _required_json_object(
        search_report_path,
        "committed_artifact.search_report",
        base_dir=root,
    )
    if search_report.get("schema_version") != SEARCH_RUN_RESULT_SCHEMA_VERSION:
        raise ValueError("committed_artifact.search_report schema_version is invalid")
    if search_report.get("report_schema_version") != SEARCH_RUN_REPORT_SCHEMA_VERSION:
        raise ValueError(
            "committed_artifact.search_report report_schema_version is invalid"
        )
    route_document = _required_route_document(
        route_path,
        "committed_artifact.route",
        base_dir=root,
    )
    artifact_commit = search_report.get("artifact_commit")
    if not isinstance(artifact_commit, Mapping):
        raise ValueError("committed_artifact.search_report artifact_commit is required")
    if artifact_commit.get("status") != "committed":
        raise ValueError("committed_artifact.search_report artifact is not committed")
    best_route = search_report.get("best_route")
    route_id = committed.get("route_id")
    if not isinstance(route_id, str) or not route_id:
        route_id = artifact_commit.get("route_id")
        if (not isinstance(route_id, str) or not route_id) and isinstance(
            best_route,
            Mapping,
        ):
            route_id = best_route.get("route_id")
        if not isinstance(route_id, str) or not route_id:
            route_id = route_document.get("route_id")
    if not isinstance(route_id, str) or not route_id:
        raise ValueError("committed_artifact.route_id is required")
    route_id_sources = {
        "artifact_commit": artifact_commit.get("route_id"),
        "route": route_document.get("route_id"),
    }
    if isinstance(best_route, Mapping):
        route_id_sources["best_route"] = best_route.get("route_id")
    for source_name, source_route_id in route_id_sources.items():
        if source_route_id is not None and source_route_id != route_id:
            raise ValueError(
                "committed_artifact.route_id mismatch between manifest and "
                f"{source_name}"
            )
    search_run_id = committed.get("search_run_id", search_report.get("run_id"))
    if not isinstance(search_run_id, str) or not search_run_id:
        search_run_id = _artifact_id_from_file(
            search_report_path,
            base_dir=root,
            prefix="searchrunartifact_",
        )

    fresh_report_path = _manifest_path(fresh.get("report"), "fresh_replay.report")
    try:
        fresh_report = read_fresh_replay_verification_report(
            _resolve_manifest_artifact_path(fresh_report_path, base_dir=root)
        )
    except ValueError as exc:
        raise ValueError("fresh_replay.report must be a valid fresh Replay report") from exc
    fresh_route = fresh_report.get("route")
    if (
        not isinstance(fresh_route, Mapping)
        or fresh_route.get("route_id") != route_id
    ):
        raise ValueError("fresh_replay.report route_id does not match committed Route")
    screenshots = _manifest_mapping(desktop.get("screenshots"), "desktop.screenshots")
    screenshot_paths = {
        viewport: _manifest_path(screenshots.get(viewport), f"screenshots.{viewport}")
        for viewport in QUALIFICATION_SCREENSHOT_VIEWPORTS
    }
    for viewport, screenshot_path in screenshot_paths.items():
        _validate_png_viewport(screenshot_path, viewport, base_dir=root)
    review_path = _manifest_path(
        security.get("review"),
        "security_redaction.review",
    )
    security_review = _required_json_object(
        review_path,
        "security_redaction.review",
        base_dir=root,
    )
    for field in (
        "absolute_paths_redacted",
        "csp_checked",
        "deck_contents_redacted",
        "renderer_path_input_rejected",
        "secret_scan_passed",
    ):
        _matching_report_value(security_review, security, field)
    resource_report_path = _manifest_path(
        resource.get("report"),
        "resource_budget.report",
    )
    resource_report = _required_json_object(
        resource_report_path,
        "resource_budget.report",
        base_dir=root,
    )
    for field in (
        "budget_wall_seconds",
        "censor_state_recorded",
        "max_artifact_bytes",
        "max_peak_rss_bytes",
        "max_wall_seconds",
        "measured_runs",
        "node_budget",
        "replay_budget",
        "within_budget",
    ):
        _matching_report_value(resource_report, resource, field)

    checks = [
        {
            "check_id": "committed-artifact-e2e",
            "evidence": {
                "artifact_id": committed.get("artifact_id")
                or _artifact_id_from_file(
                    result_view_path,
                    base_dir=root,
                    prefix="resultartifact_",
                ),
                "artifact_kind": "committed-dashboard-result",
                "artifact_commit_status": "committed",
                "evidence_artifacts": [
                    _artifact_entry("result-view.json", result_view_path, "result-view"),
                    _artifact_entry("route.yaml", route_path, "route-dsl"),
                    _artifact_entry(
                        "search-report.json",
                        search_report_path,
                        "search-run-report",
                    ),
                ],
                "renderer_path_input": _manifest_required_bool(
                    committed,
                    "renderer_path_input",
                ),
                "report_sha256_verified": _manifest_required_bool(
                    committed,
                    "report_sha256_verified",
                ),
                "result_view_schema_version": committed.get(
                    "result_view_schema_version",
                    DESKTOP_RESULT_VIEW_VERSION,
                ),
                "route_artifact_schema_version": committed.get(
                    "route_artifact_schema_version",
                    "route-dsl",
                ),
                "route_id": route_id,
                "route_id_verified": _manifest_required_bool(
                    committed,
                    "route_id_verified",
                ),
                "route_sha256_verified": _manifest_required_bool(
                    committed,
                    "route_sha256_verified",
                ),
                "search_run_id": search_run_id,
                "search_run_schema_version": committed.get(
                    "search_run_schema_version",
                    search_report.get("schema_version", "search-run-result-v5"),
                ),
            },
            "passed": True,
        },
        {
            "check_id": "fresh-replay-e2e",
            "evidence": {
                "action_sequence_verified": _manifest_required_bool(
                    fresh,
                    "action_sequence_verified",
                ),
                "artifact_id": fresh.get("artifact_id")
                or _artifact_id_from_file(
                    fresh_report_path,
                    base_dir=root,
                    prefix="freshreplayartifact_",
                ),
                "artifact_kind": "fresh-replay-verification",
                "evidence_artifacts": [
                    _artifact_entry(
                        "fresh-replay-report.json",
                        fresh_report_path,
                        "fresh-replay-report",
                    ),
                ],
                "fresh_worker": _manifest_required_bool(fresh, "fresh_worker"),
                "route_id_verified": _manifest_required_bool(
                    fresh,
                    "route_id_verified",
                ),
                "schema_version": fresh.get(
                    "schema_version",
                    "fresh-replay-verification-v1",
                ),
                "search_worker_shared_state": _manifest_required_bool(
                    fresh,
                    "search_worker_shared_state",
                ),
                "terminal_state_verified": _manifest_required_bool(
                    fresh,
                    "terminal_state_verified",
                ),
            },
            "passed": True,
        },
        {
            "check_id": "desktop-screenshot-a11y",
            "evidence": {
                "artifact_kind": "desktop-quality-evidence",
                "axe_violations": _manifest_int(
                    desktop,
                    "axe_violations",
                    minimum=0,
                ),
                "evidence_artifacts": [
                    _artifact_entry(f"desktop-{viewport}.png", path, "screenshot")
                    for viewport, path in sorted(
                        screenshot_paths.items(),
                        key=lambda item: f"desktop-{item[0]}.png",
                    )
                ],
                "high_contrast_passed": _manifest_required_bool(
                    desktop,
                    "high_contrast_passed",
                ),
                "keyboard_smoke_passed": _manifest_required_bool(
                    desktop,
                    "keyboard_smoke_passed",
                ),
                "reduced_motion_passed": _manifest_required_bool(
                    desktop,
                    "reduced_motion_passed",
                ),
                "viewports": list(QUALIFICATION_SCREENSHOT_VIEWPORTS),
            },
            "passed": True,
        },
        {
            "check_id": "security-redaction",
            "evidence": {
                "absolute_paths_redacted": _manifest_required_bool(
                    security,
                    "absolute_paths_redacted",
                ),
                "artifact_kind": "security-redaction-review",
                "csp_checked": _manifest_required_bool(security, "csp_checked"),
                "deck_contents_redacted": _manifest_required_bool(
                    security,
                    "deck_contents_redacted",
                ),
                "evidence_artifacts": [
                    _artifact_entry(
                        "security-redaction-review.json",
                        review_path,
                        "security-review",
                    ),
                ],
                "renderer_path_input_rejected": _manifest_required_bool(
                    security,
                    "renderer_path_input_rejected",
                ),
                "secret_scan_passed": _manifest_required_bool(
                    security,
                    "secret_scan_passed",
                ),
            },
            "passed": True,
        },
        {
            "check_id": "resource-budget",
            "evidence": {
                "artifact_kind": "resource-budget",
                "budget_wall_seconds": _manifest_number(
                    resource,
                    "budget_wall_seconds",
                ),
                "censor_state_recorded": _manifest_required_bool(
                    resource,
                    "censor_state_recorded",
                ),
                "evidence_artifacts": [
                    _artifact_entry(
                        "resource-budget.json",
                        resource_report_path,
                        "resource-budget",
                    ),
                ],
                "max_artifact_bytes": _manifest_int(
                    resource,
                    "max_artifact_bytes",
                ),
                "max_peak_rss_bytes": _manifest_int(
                    resource,
                    "max_peak_rss_bytes",
                ),
                "max_wall_seconds": _manifest_number(resource, "max_wall_seconds"),
                "measured_runs": _manifest_int(resource, "measured_runs"),
                "node_budget": _manifest_int(resource, "node_budget", minimum=100_000),
                "replay_budget": _manifest_int(
                    resource,
                    "replay_budget",
                    minimum=100_000,
                ),
                "within_budget": _manifest_required_bool(resource, "within_budget"),
            },
            "passed": True,
        },
    ]
    return to_canonical_data(checks)


def _qualification_common_passing_evidence_issues(
    evidence: Mapping[str, Any],
) -> list[str]:
    issues: list[str] = []
    if evidence.get("path_redacted") is not True:
        issues.append("path_redacted")
    artifacts = evidence.get("evidence_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        issues.append("evidence_artifacts")
    else:
        names: list[str] = []
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                issues.append("evidence_artifacts")
                continue
            name = artifact.get("name")
            if (
                not isinstance(name, str)
                or not name
                or _string_has_path_leak(name)
            ):
                issues.append("evidence_artifacts.name")
            else:
                names.append(name)
            if not _is_sha256(artifact.get("sha256")):
                issues.append("evidence_artifacts.sha256")
            kind = artifact.get("kind")
            if kind is not None and (
                not isinstance(kind, str) or not kind or _string_has_path_leak(kind)
            ):
                issues.append("evidence_artifacts.kind")
        if len(names) != len(set(names)) or names != sorted(names):
            issues.append("evidence_artifacts")
    if _evidence_contains_path_leak(evidence):
        issues.append("path_leak")
    return issues


def _qualification_passing_evidence_issues(
    check_id: str,
    evidence: Mapping[str, Any],
) -> list[str]:
    issues: list[str] = _qualification_common_passing_evidence_issues(evidence)
    if check_id == "committed-artifact-e2e":
        _require_literals(
            evidence,
            {
                "artifact_kind": "committed-dashboard-result",
                "artifact_commit_status": "committed",
                "renderer_path_input": False,
                "result_view_schema_version": DESKTOP_RESULT_VIEW_VERSION,
                "route_artifact_schema_version": "route-dsl",
                "search_run_schema_version": "search-run-result-v5",
                "report_sha256_verified": True,
                "route_id_verified": True,
                "route_sha256_verified": True,
            },
            issues,
        )
        for field in ("artifact_id", "route_id", "search_run_id"):
            if not isinstance(evidence.get(field), str) or not evidence[field]:
                issues.append(field)
        for field in ("report_sha256", "result_view_sha256", "route_sha256"):
            if not _is_sha256(evidence.get(field)):
                issues.append(field)
        _require_artifact_sha256(
            evidence,
            "search-report.json",
            evidence.get("report_sha256"),
            issues,
        )
        _require_artifact_sha256(
            evidence,
            "result-view.json",
            evidence.get("result_view_sha256"),
            issues,
        )
        _require_artifact_sha256(
            evidence,
            "route.yaml",
            evidence.get("route_sha256"),
            issues,
        )
    elif check_id == "fresh-replay-e2e":
        _require_literals(
            evidence,
            {
                "artifact_kind": "fresh-replay-verification",
                "schema_version": "fresh-replay-verification-v1",
                "action_sequence_verified": True,
                "fresh_worker": True,
                "route_id_verified": True,
                "search_worker_shared_state": False,
                "terminal_state_verified": True,
            },
            issues,
        )
        if not isinstance(evidence.get("artifact_id"), str) or not evidence["artifact_id"]:
            issues.append("artifact_id")
        if not _is_sha256(evidence.get("replay_report_sha256")):
            issues.append("replay_report_sha256")
        _require_artifact_sha256(
            evidence,
            "fresh-replay-report.json",
            evidence.get("replay_report_sha256"),
            issues,
        )
    elif check_id == "desktop-screenshot-a11y":
        _require_literals(
            evidence,
            {
                "artifact_kind": "desktop-quality-evidence",
                "axe_violations": 0,
                "high_contrast_passed": True,
                "keyboard_smoke_passed": True,
                "reduced_motion_passed": True,
            },
            issues,
        )
        if evidence.get("viewports") != list(QUALIFICATION_SCREENSHOT_VIEWPORTS):
            issues.append("viewports")
        screenshot_sha256 = evidence.get("screenshot_sha256")
        if not isinstance(screenshot_sha256, Mapping) or set(screenshot_sha256) != set(
            QUALIFICATION_SCREENSHOT_VIEWPORTS
        ):
            issues.append("screenshot_sha256")
        elif any(not _is_sha256(digest) for digest in screenshot_sha256.values()):
            issues.append("screenshot_sha256")
        elif isinstance(screenshot_sha256, Mapping):
            for viewport, sha256 in screenshot_sha256.items():
                _require_artifact_sha256(
                    evidence,
                    f"desktop-{viewport}.png",
                    sha256,
                    issues,
                )
    elif check_id == "security-redaction":
        _require_literals(
            evidence,
            {
                "artifact_kind": "security-redaction-review",
                "absolute_paths_redacted": True,
                "csp_checked": True,
                "deck_contents_redacted": True,
                "renderer_path_input_rejected": True,
                "secret_scan_passed": True,
            },
            issues,
        )
        if not _is_sha256(evidence.get("review_sha256")):
            issues.append("review_sha256")
        _require_artifact_sha256(
            evidence,
            "security-redaction-review.json",
            evidence.get("review_sha256"),
            issues,
        )
    elif check_id == "resource-budget":
        _require_literals(
            evidence,
            {
                "artifact_kind": "resource-budget",
                "censor_state_recorded": True,
                "within_budget": True,
            },
            issues,
        )
        if not _is_positive_int(evidence.get("measured_runs")):
            issues.append("measured_runs")
        for field in ("max_artifact_bytes", "max_peak_rss_bytes"):
            if not _is_positive_int(evidence.get(field)):
                issues.append(field)
        for field in ("budget_wall_seconds", "max_wall_seconds"):
            if not _is_positive_number(evidence.get(field)):
                issues.append(field)
        if (
            _is_positive_number(evidence.get("budget_wall_seconds"))
            and _is_positive_number(evidence.get("max_wall_seconds"))
            and evidence["max_wall_seconds"] > evidence["budget_wall_seconds"]
        ):
            issues.append("max_wall_seconds")
        for field in ("node_budget", "replay_budget"):
            if not _is_positive_int(evidence.get(field)) or evidence[field] < 100_000:
                issues.append(field)
        if not _is_sha256(evidence.get("resource_report_sha256")):
            issues.append("resource_report_sha256")
        _require_artifact_sha256(
            evidence,
            "resource-budget.json",
            evidence.get("resource_report_sha256"),
            issues,
        )
    return issues


def _qualification_check(raw: Mapping[str, Any]) -> dict[str, Any]:
    check_id = raw.get("check_id")
    if not isinstance(check_id, str) or not check_id:
        raise ValueError("research dashboard qualification check_id is invalid")
    passed = raw.get("passed")
    if not isinstance(passed, bool):
        raise ValueError("research dashboard qualification check passed must be boolean")
    evidence = raw.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("research dashboard qualification evidence must be an object")
    evidence = to_canonical_data(evidence)
    if (
        passed
        and check_id in REQUIRED_QUALIFICATION_CHECKS
        and isinstance(evidence, Mapping)
    ):
        issues = _qualification_passing_evidence_issues(check_id, evidence)
        if issues:
            raise ValueError(
                "research dashboard qualification passing evidence is insufficient "
                f"for {check_id}: {', '.join(sorted(issues))}"
            )
    return {
        "check_id": check_id,
        "evidence": evidence,
        "passed": passed,
    }


def evaluate_research_dashboard_qualification(
    checks: list[Mapping[str, Any]],
) -> dict[str, Any]:
    normalized_checks = sorted(
        (_qualification_check(check) for check in checks),
        key=lambda check: (
            REQUIRED_QUALIFICATION_CHECKS.index(check["check_id"])
            if check["check_id"] in REQUIRED_QUALIFICATION_CHECKS
            else len(REQUIRED_QUALIFICATION_CHECKS),
            check["check_id"],
        ),
    )
    check_ids = [check["check_id"] for check in normalized_checks]
    present = set(check_ids)
    duplicates = sorted(
        check_id for check_id, count in Counter(check_ids).items() if count > 1
    )
    unexpected = sorted(present - set(REQUIRED_QUALIFICATION_CHECKS))
    rejection_reasons = [
        f"missing:{check_id}"
        for check_id in REQUIRED_QUALIFICATION_CHECKS
        if check_id not in present
    ]
    rejection_reasons.extend(f"unexpected:{check_id}" for check_id in unexpected)
    rejection_reasons.extend(f"duplicate:{check_id}" for check_id in duplicates)
    rejection_reasons.extend(
        f"failed:{check['check_id']}"
        for check in normalized_checks
        if check["passed"] is not True
    )
    document = {
        "checks": normalized_checks,
        "environment": {
            "package_version": __version__,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
        "gate": {
            "required_checks": list(REQUIRED_QUALIFICATION_CHECKS),
            "work_item": "docs/spec/v0.7.0/20_work_breakdown_and_acceptance.md#29",
        },
        "passed": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "schema_version": RESEARCH_DASHBOARD_QUALIFICATION_SCHEMA_VERSION,
    }
    document["evidence_id"] = stable_digest(document, prefix="researchdashqual_")
    return document


def validate_research_dashboard_qualification(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("research dashboard qualification must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("research dashboard qualification must be an object")
    if document.get("schema_version") != RESEARCH_DASHBOARD_QUALIFICATION_SCHEMA_VERSION:
        raise ValueError("unsupported research dashboard qualification schema_version")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "researchdashqual_"
    ):
        raise ValueError("research dashboard qualification evidence_id is invalid")
    identity = {key: item for key, item in document.items() if key != "evidence_id"}
    if evidence_id != stable_digest(identity, prefix="researchdashqual_"):
        raise ValueError("research dashboard qualification evidence_id mismatch")
    if not isinstance(document.get("passed"), bool):
        raise ValueError("research dashboard qualification passed must be a boolean")
    if not isinstance(document.get("checks"), list):
        raise ValueError("research dashboard qualification checks must be a list")
    checks = []
    for check in document["checks"]:
        if not isinstance(check, Mapping):
            raise ValueError("research dashboard qualification check must be an object")
        checks.append(_qualification_check(check))
    check_ids = [check["check_id"] for check in checks]
    present = set(check_ids)
    missing = [
        check_id for check_id in REQUIRED_QUALIFICATION_CHECKS if check_id not in present
    ]
    if missing:
        raise ValueError(
            "research dashboard qualification missing required checks: "
            + ", ".join(missing)
        )
    unexpected = sorted(present - set(REQUIRED_QUALIFICATION_CHECKS))
    if unexpected:
        raise ValueError(
            "research dashboard qualification contains unexpected checks: "
            + ", ".join(unexpected)
        )
    duplicates = sorted(
        check_id for check_id, count in Counter(check_ids).items() if count > 1
    )
    if duplicates:
        raise ValueError(
            "research dashboard qualification contains duplicate checks: "
            + ", ".join(duplicates)
        )
    expected_order = list(REQUIRED_QUALIFICATION_CHECKS)
    if check_ids != expected_order:
        raise ValueError(
            "research dashboard qualification checks must be ordered as required"
        )
    derived_rejections = [
        f"missing:{check_id}"
        for check_id in REQUIRED_QUALIFICATION_CHECKS
        if check_id not in present
    ]
    derived_rejections.extend(f"unexpected:{check_id}" for check_id in unexpected)
    derived_rejections.extend(f"duplicate:{check_id}" for check_id in duplicates)
    derived_rejections.extend(
        f"failed:{check['check_id']}" for check in checks if check["passed"] is not True
    )
    rejection_reasons = document.get("rejection_reasons")
    if not isinstance(rejection_reasons, list) or any(
        not isinstance(reason, str) for reason in rejection_reasons
    ):
        raise ValueError(
            "research dashboard qualification rejection_reasons must be a string list"
        )
    if rejection_reasons != derived_rejections:
        raise ValueError("research dashboard qualification rejections are inconsistent")
    if document["passed"] != (not derived_rejections):
        raise ValueError("research dashboard qualification passed is inconsistent")
    if document["passed"] and rejection_reasons:
        raise ValueError("passing research dashboard qualification has rejections")
    return document


def write_research_dashboard_qualification(
    checks: list[Mapping[str, Any]],
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_research_dashboard_qualification(checks)
    validate_research_dashboard_qualification(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


def _static_checks(root: Path) -> list[dict[str, Any]]:
    bridge = _read_json(root / "src/ygo_effect_dsl/resources/desktop-bridge-v1.json")
    analytics = _read_json(
        root / "src/ygo_effect_dsl/resources/analytics-query-contract-v1.json"
    )
    job_result = _bridge_method_record(bridge, "job.result")
    deck_register_inline = _bridge_method_record(bridge, "deck.register_inline")
    scenario_compose = _bridge_method_record(bridge, "scenario.compose_search")
    job_result_fields_valid = _bridge_method_check(
        bridge,
        "job.result",
        required_fields=("job_id",),
    )
    desktop_bridge_test_exists = _test_file_exists(
        root,
        "tests/test_desktop_bridge.py",
    )
    replay_bridge_fields_valid = _bridge_method_check(
        bridge,
        "job.enqueue_replay_verification",
        required_fields=("search_job_id",),
    )
    replay_worker_source_contains = _text_contains(
        root,
        "src/ygo_effect_dsl/desktop/lifecycle.py",
        ("fresh-replay-verification", "_run_replay_verification"),
    )
    terminal_bridge_methods_valid = all(
        _bridge_method_check(bridge, method, required_fields=fields)
        for method, fields in (
            ("profile.list", ()),
            ("profile.get", ("profile_id",)),
            ("profile.clone", ("profile_id", "rules")),
        )
    )
    terminal_tests_exist = {
        "tests/test_terminal_preference.py": _test_file_exists(
            root,
            "tests/test_terminal_preference.py",
        ),
        "tests/test_terminal_preference_catalog.py": _test_file_exists(
            root,
            "tests/test_terminal_preference_catalog.py",
        ),
    }
    terminal_result_service_source_contains = _text_contains(
        root,
        "src/ygo_effect_dsl/desktop/service.py",
        ("terminal score", "terminal preference evaluation"),
    )
    terminal_desktop_test_contains = _text_contains(
        root,
        "tests/test_desktop_bridge.py",
        ("test_result_view_rejects_terminal_score_drift_from_preference_evaluation",),
    )
    route_randomness_test_exists = _test_file_exists(
        root,
        "tests/test_route_randomness_ranking.py",
    )
    route_randomness_source_contains = _text_contains(
        root,
        "src/ygo_effect_dsl/engine/search/executor.py",
        ("build_route_randomness_summary", "rank_route_candidates"),
    )
    route_ranking_service_source_contains = _text_contains(
        root,
        "src/ygo_effect_dsl/desktop/service.py",
        ("ranking summary", "rank_route_candidates"),
    )
    route_ranking_desktop_test_contains = _text_contains(
        root,
        "tests/test_desktop_bridge.py",
        ("test_result_view_rejects_ranking_summary_drift_from_best_route",),
    )
    candidate_app_source_contains = _text_contains(
        root,
        "src/ygo_effect_dsl/desktop/static/app.js",
        ("candidate", "coverage", "Top-K"),
    )
    candidate_service_source_contains = _text_contains(
        root,
        "src/ygo_effect_dsl/desktop/service.py",
        (
            "_validate_candidate_evidence",
            "_validate_coverage_certificate",
            "candidate evidence counts",
            "frontier exhausted",
        ),
    )
    candidate_test_exists = _test_file_exists(root, "tests/test_search_executor.py")
    candidate_desktop_test_contains = _text_contains(
        root,
        "tests/test_desktop_bridge.py",
        (
            "test_result_view_rejects_candidate_count_mismatch",
            "test_result_view_rejects_invalid_frontier_exhausted_claim",
        ),
    )
    typed_bridge_methods_valid = _bridge_method_check(
        bridge,
        "deck.register_inline",
        required_fields=("main", "name"),
    ) and _bridge_method_check(
        bridge,
        "scenario.compose_search",
        required_fields=("configuration", "deck_id"),
    )
    typed_analytics_fields_present = _analytics_fields_check(
        analytics,
        (
            "opening_hand_cohort",
            "profile",
            "success_predicate",
            "ranking_policy",
            "termination",
            "censor_state",
            "core_lock",
            "asset_lock",
        ),
    )
    typed_app_source_contains = _text_contains(
        root,
        "src/ygo_effect_dsl/desktop/static/app.js",
        ("openingHandConfiguration", "register_inline", "scenario_preset_id"),
    )
    neuron_adr_exists = _test_file_exists(
        root,
        "docs/adr/0019_reject_neuron_direct_import_without_official_api.md",
    )
    return [
        _check(
            "A",
            "committed-result-artifact-service",
            bridge.get("schema_version") == DESKTOP_BRIDGE_CONTRACT_VERSION
            and
            DESKTOP_RESULT_VIEW_VERSION == "desktop-result-view-v1"
            and job_result_fields_valid
            and job_result.get("renderer_path_input") is False
            and job_result.get("requires_committed_artifacts")
            == ["route-dsl", "search-run-report"]
            and desktop_bridge_test_exists,
            {
                "bridge_method": "job.result",
                "bridge_schema_version": bridge.get("schema_version"),
                "expected_bridge_schema_version": DESKTOP_BRIDGE_CONTRACT_VERSION,
                "method_payload_fields_valid": job_result_fields_valid,
                "renderer_path_input": job_result.get("renderer_path_input"),
                "requires_committed_artifacts": job_result.get(
                    "requires_committed_artifacts"
                ),
                "schema_version": DESKTOP_RESULT_VIEW_VERSION,
                "test": "tests/test_desktop_bridge.py",
                "test_exists": desktop_bridge_test_exists,
            },
        ),
        _check(
            "A",
            "independent-replay-verification-service",
            replay_bridge_fields_valid and replay_worker_source_contains,
            {
                "bridge_method": "job.enqueue_replay_verification",
                "method_payload_fields_valid": replay_bridge_fields_valid,
                "worker": "desktop.lifecycle._run_replay_verification",
                "worker_source_contains": replay_worker_source_contains,
            },
        ),
        _check(
            "B",
            "terminal-preference-contracts",
            {
                TERMINAL_BOARD_PROJECTION_SCHEMA_VERSION,
                TERMINAL_PREFERENCE_CATALOG_SCHEMA_VERSION,
                TERMINAL_PREFERENCE_EVALUATION_SCHEMA_VERSION,
                TERMINAL_PREFERENCE_PROFILE_SCHEMA_VERSION,
            }
            == {
                "terminal-board-projection-v1",
                "terminal-preference-catalog-v1",
                "terminal-preference-evaluation-v1",
                "terminal-preference-profile-v1",
            }
            and terminal_bridge_methods_valid
            and all(terminal_tests_exist.values())
            and terminal_result_service_source_contains
            and terminal_desktop_test_contains,
            {
                "bridge_methods": ["profile.list", "profile.get", "profile.clone"],
                "bridge_methods_valid": terminal_bridge_methods_valid,
                "desktop_test": "tests/test_desktop_bridge.py",
                "desktop_test_contains": terminal_desktop_test_contains,
                "result_service_source_contains": terminal_result_service_source_contains,
                "schema_versions": [
                    TERMINAL_BOARD_PROJECTION_SCHEMA_VERSION,
                    TERMINAL_PREFERENCE_CATALOG_SCHEMA_VERSION,
                    TERMINAL_PREFERENCE_EVALUATION_SCHEMA_VERSION,
                    TERMINAL_PREFERENCE_PROFILE_SCHEMA_VERSION,
                ],
                "tests": terminal_tests_exist,
            },
        ),
        _check(
            "C",
            "route-randomness-and-ranking-contracts",
            {
                ROUTE_RANDOMNESS_SUMMARY_SCHEMA_VERSION,
                ROUTE_RANKING_POLICY_SCHEMA_VERSION,
                ROUTE_RANKING_SCHEMA_VERSION,
            }
            == {
                "route-randomness-summary-v1",
                "route-ranking-policy-v1",
                "route-ranking-v1",
            }
            and route_randomness_test_exists
            and route_randomness_source_contains
            and route_ranking_service_source_contains
            and route_ranking_desktop_test_contains,
            {
                "desktop_test": "tests/test_desktop_bridge.py",
                "desktop_test_contains": route_ranking_desktop_test_contains,
                "result_service_source_contains": route_ranking_service_source_contains,
                "schema_versions": [
                    ROUTE_RANDOMNESS_SUMMARY_SCHEMA_VERSION,
                    ROUTE_RANKING_POLICY_SCHEMA_VERSION,
                    ROUTE_RANKING_SCHEMA_VERSION,
                ],
                "test": "tests/test_route_randomness_ranking.py",
                "test_exists": route_randomness_test_exists,
                "source_contains": route_randomness_source_contains,
            },
        ),
        _check(
            "D",
            "candidate-coverage-and-drilldown-contracts",
            {
                SEARCH_CANDIDATE_EVIDENCE_SCHEMA_VERSION,
                SEARCH_COVERAGE_SCHEMA_VERSION,
            }
            == {"search-candidate-evidence-v1", "search-coverage-v1"}
            and candidate_app_source_contains
            and candidate_service_source_contains
            and candidate_test_exists
            and candidate_desktop_test_contains,
            {
                "schema_versions": [
                    SEARCH_CANDIDATE_EVIDENCE_SCHEMA_VERSION,
                    SEARCH_COVERAGE_SCHEMA_VERSION,
                ],
                "desktop_test_contains": candidate_desktop_test_contains,
                "desktop_test": "tests/test_desktop_bridge.py",
                "result_service_source_contains": candidate_service_source_contains,
                "source_contains": candidate_app_source_contains,
                "test": "tests/test_search_executor.py",
                "test_exists": candidate_test_exists,
            },
        ),
        _check(
            "E",
            "typed-research-scenario-and-cohort-ui",
            analytics.get("version") == ANALYTICS_QUERY_CONTRACT_VERSION
            and typed_bridge_methods_valid
            and deck_register_inline.get("renderer_path_input") is False
            and scenario_compose.get("renderer_path_input") is False
            and scenario_compose.get("renderer_rule_inference") is False
            and typed_analytics_fields_present
            and typed_app_source_contains,
            {
                "analytics_contract_version": analytics.get("version"),
                "analytics_fields": [
                    "opening_hand_cohort",
                    "profile",
                    "success_predicate",
                    "ranking_policy",
                    "termination",
                    "censor_state",
                    "core_lock",
                    "asset_lock",
                ],
                "expected_analytics_contract_version": (
                    ANALYTICS_QUERY_CONTRACT_VERSION
                ),
                "bridge_methods": ["deck.register_inline", "scenario.compose_search"],
                "bridge_methods_valid": typed_bridge_methods_valid,
                "analytics_fields_present": typed_analytics_fields_present,
                "deck_register_inline_renderer_path_input": (
                    deck_register_inline.get("renderer_path_input")
                ),
                "scenario_compose_renderer_path_input": (
                    scenario_compose.get("renderer_path_input")
                ),
                "scenario_compose_renderer_rule_inference": (
                    scenario_compose.get("renderer_rule_inference")
                ),
                "source_contains": typed_app_source_contains,
            },
        ),
        _check(
            "E",
            "neuron-direct-import-rejection-adr",
            neuron_adr_exists,
            {
                "adr": (
                    "docs/adr/"
                    "0019_reject_neuron_direct_import_without_official_api.md"
                ),
                "adr_exists": neuron_adr_exists,
            },
        ),
    ]


def _manual_release_checks(
    root: Path,
    qualification_path: str | Path | None,
) -> list[dict[str, Any]]:
    path = root / (qualification_path or DEFAULT_QUALIFICATION_PATH)
    if not path.exists():
        return [
            _check(
                "release",
                "real-core-dashboard-qualification",
                False,
                {
                    "path_redacted": True,
                    "reason": "missing real-core dashboard qualification evidence",
                    "source_path_name": _source_path_name(path),
                },
            )
        ]
    try:
        qualification = _read_json(path)
        qualification = validate_research_dashboard_qualification(qualification)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [
            _check(
                "release",
                "real-core-dashboard-qualification",
                False,
                {
                    "path_redacted": True,
                    "reason": f"invalid qualification evidence: {exc}",
                    "source_path_name": _source_path_name(path),
                },
            )
        ]
    return [
        _check(
            "release",
            "real-core-dashboard-qualification",
            qualification.get("passed") is True,
            {
                "evidence_id": qualification.get("evidence_id"),
                "path_redacted": True,
                "rejection_reasons": qualification.get("rejection_reasons"),
                "schema_version": qualification.get("schema_version"),
                "check_count": len(qualification.get("checks", ())),
                "source_path_name": _source_path_name(path),
            },
        )
    ]


def _expected_static_gate_pass(check_id: str, evidence: Mapping[str, Any]) -> bool:
    if check_id == "committed-result-artifact-service":
        return (
            evidence.get("bridge_method") == "job.result"
            and evidence.get("bridge_schema_version") == DESKTOP_BRIDGE_CONTRACT_VERSION
            and evidence.get("expected_bridge_schema_version")
            == DESKTOP_BRIDGE_CONTRACT_VERSION
            and evidence.get("schema_version") == DESKTOP_RESULT_VIEW_VERSION
            and evidence.get("method_payload_fields_valid") is True
            and evidence.get("renderer_path_input") is False
            and evidence.get("requires_committed_artifacts")
            == ["route-dsl", "search-run-report"]
            and evidence.get("test") == "tests/test_desktop_bridge.py"
            and evidence.get("test_exists") is True
        )
    if check_id == "independent-replay-verification-service":
        return (
            evidence.get("bridge_method") == "job.enqueue_replay_verification"
            and evidence.get("method_payload_fields_valid") is True
            and evidence.get("worker") == "desktop.lifecycle._run_replay_verification"
            and evidence.get("worker_source_contains") is True
        )
    if check_id == "terminal-preference-contracts":
        return (
            evidence.get("bridge_methods")
            == ["profile.list", "profile.get", "profile.clone"]
            and evidence.get("bridge_methods_valid") is True
            and evidence.get("schema_versions")
            == [
                TERMINAL_BOARD_PROJECTION_SCHEMA_VERSION,
                TERMINAL_PREFERENCE_CATALOG_SCHEMA_VERSION,
                TERMINAL_PREFERENCE_EVALUATION_SCHEMA_VERSION,
                TERMINAL_PREFERENCE_PROFILE_SCHEMA_VERSION,
            ]
            and evidence.get("tests")
            == {
                "tests/test_terminal_preference.py": True,
                "tests/test_terminal_preference_catalog.py": True,
            }
            and evidence.get("result_service_source_contains") is True
            and evidence.get("desktop_test") == "tests/test_desktop_bridge.py"
            and evidence.get("desktop_test_contains") is True
        )
    if check_id == "route-randomness-and-ranking-contracts":
        return (
            evidence.get("schema_versions")
            == [
                ROUTE_RANDOMNESS_SUMMARY_SCHEMA_VERSION,
                ROUTE_RANKING_POLICY_SCHEMA_VERSION,
                ROUTE_RANKING_SCHEMA_VERSION,
            ]
            and evidence.get("test") == "tests/test_route_randomness_ranking.py"
            and evidence.get("test_exists") is True
            and evidence.get("source_contains") is True
            and evidence.get("result_service_source_contains") is True
            and evidence.get("desktop_test") == "tests/test_desktop_bridge.py"
            and evidence.get("desktop_test_contains") is True
        )
    if check_id == "candidate-coverage-and-drilldown-contracts":
        return (
            evidence.get("schema_versions")
            == [
                SEARCH_CANDIDATE_EVIDENCE_SCHEMA_VERSION,
                SEARCH_COVERAGE_SCHEMA_VERSION,
            ]
            and evidence.get("source_contains") is True
            and evidence.get("result_service_source_contains") is True
            and evidence.get("test") == "tests/test_search_executor.py"
            and evidence.get("test_exists") is True
            and evidence.get("desktop_test") == "tests/test_desktop_bridge.py"
            and evidence.get("desktop_test_contains") is True
        )
    if check_id == "typed-research-scenario-and-cohort-ui":
        return (
            evidence.get("analytics_contract_version")
            == ANALYTICS_QUERY_CONTRACT_VERSION
            and evidence.get("expected_analytics_contract_version")
            == ANALYTICS_QUERY_CONTRACT_VERSION
            and evidence.get("analytics_fields")
            == [
                "opening_hand_cohort",
                "profile",
                "success_predicate",
                "ranking_policy",
                "termination",
                "censor_state",
                "core_lock",
                "asset_lock",
            ]
            and evidence.get("analytics_fields_present") is True
            and evidence.get("bridge_methods")
            == ["deck.register_inline", "scenario.compose_search"]
            and evidence.get("bridge_methods_valid") is True
            and evidence.get("deck_register_inline_renderer_path_input") is False
            and evidence.get("scenario_compose_renderer_path_input") is False
            and evidence.get("scenario_compose_renderer_rule_inference") is False
            and evidence.get("source_contains") is True
        )
    if check_id == "neuron-direct-import-rejection-adr":
        return (
            evidence.get("adr")
            == "docs/adr/0019_reject_neuron_direct_import_without_official_api.md"
            and evidence.get("adr_exists") is True
        )
    raise ValueError(
        f"unsupported research dashboard static gate check {check_id!r}"
    )


def _expected_manual_gate_pass(check_id: str, evidence: Mapping[str, Any]) -> bool:
    if check_id != "real-core-dashboard-qualification":
        raise ValueError(
            f"unsupported research dashboard manual gate check {check_id!r}"
        )
    if "path" in evidence or "required_path" in evidence:
        raise ValueError("research dashboard manual gate evidence leaks a path")
    if evidence.get("path_redacted") is not True:
        raise ValueError("research dashboard manual gate evidence is not redacted")
    source_path_name = evidence.get("source_path_name")
    if (
        not isinstance(source_path_name, str)
        or not source_path_name
        or _string_has_path_leak(source_path_name)
    ):
        raise ValueError("research dashboard manual gate source path is invalid")
    if _evidence_contains_path_leak(evidence):
        raise ValueError("research dashboard manual gate evidence leaks a path")

    has_loaded_qualification = any(
        key in evidence
        for key in ("check_count", "evidence_id", "rejection_reasons", "schema_version")
    )
    if not has_loaded_qualification:
        reason = evidence.get("reason")
        if not isinstance(reason, str) or not reason:
            raise ValueError("research dashboard manual gate evidence is incomplete")
        return False

    evidence_id = evidence.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "researchdashqual_"
    ):
        raise ValueError("research dashboard manual gate qualification ID is invalid")
    if evidence.get("schema_version") != RESEARCH_DASHBOARD_QUALIFICATION_SCHEMA_VERSION:
        raise ValueError("research dashboard manual gate qualification schema is invalid")
    if evidence.get("check_count") != len(REQUIRED_QUALIFICATION_CHECKS):
        raise ValueError("research dashboard manual gate check count is invalid")
    rejections = evidence.get("rejection_reasons")
    if not isinstance(rejections, list) or any(
        not isinstance(reason, str) or not reason for reason in rejections
    ):
        raise ValueError("research dashboard manual gate rejections are invalid")
    return not rejections


def evaluate_research_dashboard_release_gate(
    repo_root: str | Path,
    *,
    qualification_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    static_checks = _static_checks(root)
    manual_checks = _manual_release_checks(root, qualification_path)
    all_checks = [*static_checks, *manual_checks]
    rejection_reasons = [
        f"{check['gate']}:{check['check_id']}"
        for check in all_checks
        if check["passed"] is not True
    ]
    document = {
        "environment": {
            "package_version": __version__,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
        "gate": {
            "manual_release_evidence_required": True,
            "static_gate_count": len(static_checks),
            "work_breakdown": "docs/spec/v0.7.0/20_work_breakdown_and_acceptance.md",
        },
        "manual_checks": manual_checks,
        "passed": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "schema_version": RESEARCH_DASHBOARD_RELEASE_GATE_SCHEMA_VERSION,
        "static_checks": static_checks,
    }
    document["evidence_id"] = stable_digest(document, prefix="researchdashgate_")
    return document


def validate_research_dashboard_release_gate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("research dashboard release gate evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("research dashboard release gate evidence must be an object")
    if document.get("schema_version") != RESEARCH_DASHBOARD_RELEASE_GATE_SCHEMA_VERSION:
        raise ValueError("unsupported research dashboard release gate schema_version")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "researchdashgate_"
    ):
        raise ValueError("research dashboard release gate evidence_id is invalid")
    identity = {key: item for key, item in document.items() if key != "evidence_id"}
    if evidence_id != stable_digest(identity, prefix="researchdashgate_"):
        raise ValueError("research dashboard release gate evidence_id mismatch")
    if not isinstance(document.get("passed"), bool):
        raise ValueError("research dashboard release gate passed must be a boolean")
    for key in ("static_checks", "manual_checks", "rejection_reasons"):
        if not isinstance(document.get(key), list):
            raise ValueError(f"research dashboard release gate {key} must be a list")
    all_checks: list[dict[str, Any]] = []
    for key in ("static_checks", "manual_checks"):
        for check in document[key]:
            if not isinstance(check, Mapping):
                raise ValueError(f"research dashboard release gate {key} must contain objects")
            gate = check.get("gate")
            check_id = check.get("check_id")
            passed = check.get("passed")
            evidence = check.get("evidence")
            if not isinstance(gate, str) or not gate:
                raise ValueError("research dashboard release gate check gate is invalid")
            if not isinstance(check_id, str) or not check_id:
                raise ValueError("research dashboard release gate check_id is invalid")
            if not isinstance(passed, bool):
                raise ValueError("research dashboard release gate check passed is invalid")
            if not isinstance(evidence, Mapping):
                raise ValueError("research dashboard release gate check evidence is invalid")
            all_checks.append(
                {
                    "check_id": check_id,
                    "evidence": to_canonical_data(evidence),
                    "gate": gate,
                    "passed": passed,
                }
            )
    duplicate_checks = sorted(
        f"{gate}:{check_id}"
        for (gate, check_id), count in Counter(
            (check["gate"], check["check_id"]) for check in all_checks
        ).items()
        if count > 1
    )
    if duplicate_checks:
        raise ValueError(
            "research dashboard release gate contains duplicate checks: "
            + ", ".join(duplicate_checks)
        )
    static_pairs = [
        (check["gate"], check["check_id"]) for check in document["static_checks"]
    ]
    if static_pairs != list(REQUIRED_STATIC_GATE_CHECKS):
        raise ValueError(
            "research dashboard release gate static checks must match required checks"
        )
    manual_pairs = [
        (check["gate"], check["check_id"]) for check in document["manual_checks"]
    ]
    if manual_pairs != list(REQUIRED_MANUAL_GATE_CHECKS):
        raise ValueError(
            "research dashboard release gate manual checks must match required checks"
        )
    for check in document["static_checks"]:
        expected_passed = _expected_static_gate_pass(
            check["check_id"],
            check["evidence"],
        )
        if check["passed"] != expected_passed:
            raise ValueError(
                "research dashboard release gate static check evidence is inconsistent"
            )
    for check in document["manual_checks"]:
        expected_passed = _expected_manual_gate_pass(
            check["check_id"],
            check["evidence"],
        )
        if check["passed"] != expected_passed:
            raise ValueError(
                "research dashboard release gate manual check evidence is inconsistent"
            )
    derived_rejections = [
        f"{check['gate']}:{check['check_id']}"
        for check in all_checks
        if check["passed"] is not True
    ]
    if document["rejection_reasons"] != derived_rejections:
        raise ValueError("research dashboard release gate rejections are inconsistent")
    if document["passed"] != (not derived_rejections):
        raise ValueError("research dashboard release gate passed is inconsistent")
    if document["passed"] and document["rejection_reasons"]:
        raise ValueError("passing research dashboard gate must not have rejections")
    return document


def read_research_dashboard_release_gate(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("research dashboard release gate is invalid JSON") from exc
    return validate_research_dashboard_release_gate(value)


def write_research_dashboard_release_gate(
    repo_root: str | Path,
    *,
    output_path: str | Path,
    qualification_path: str | Path | None = None,
) -> dict[str, Any]:
    document = evaluate_research_dashboard_release_gate(
        repo_root,
        qualification_path=qualification_path,
    )
    validate_research_dashboard_release_gate(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document
