from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
import platform
import statistics
from pathlib import Path
from typing import Any

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.route_dsl import load_route_document


PARALLEL_SEARCH_RELEASE_GATE_SCHEMA_VERSION = "parallel-search-release-gate-v1"
REQUIRED_POOLS = (1, 2, 4)
DEFAULT_REQUIRED_REPEATS = 5
DEFAULT_MIN_COMMITTED_NODES = 100_000
DEFAULT_MIN_NODE_BUDGET = 100_000
DEFAULT_MIN_REPLAY_BUDGET = 100_000
SOURCE_REJECTION_REAL_CORE_STRESS = (
    "source real-core-parallel-stress-v2 verifies scheduling/retry "
    "semantics, not per-profile release timing records"
)
SOURCE_REJECTION_LOGICAL_100K = (
    "source pinned-base-logical-node-workload calibrates logical "
    "executor/cache/artifact behavior, not real_core per-profile "
    "release timing records"
)
SOURCE_REJECTION_REAL_CORE_REPLAY_BENCHMARK = (
    "source real-core-replay-benchmark-v1 calibrates real_core fresh Replay "
    "timing, not per-profile SearchRun release records"
)
SUPPLEMENTAL_SOURCE_REJECTIONS = frozenset(
    {
        SOURCE_REJECTION_REAL_CORE_STRESS,
        SOURCE_REJECTION_LOGICAL_100K,
        SOURCE_REJECTION_REAL_CORE_REPLAY_BENCHMARK,
        "source contains no release timing records",
        "source contains non-release timing records",
        "source does not expose release timing records",
    }
)
PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION = (
    "parallel-search-release-records-v1"
)
PARALLEL_SEARCH_RELEASE_RECORDS_PENDING_SCHEMA_VERSION = (
    "parallel-search-release-records-pending-v1"
)
PARALLEL_SEARCH_RECORD_INPUT_MANIFEST_SCHEMA_VERSION = (
    "parallel-search-record-input-manifest-v1"
)
REQUIRED_PROFILE_IDS = (
    "grave_banish_or_chain",
    "long_line",
    "short_line",
)
RELEASE_RECORD_FIELDS = frozenset(
    {
        "best_route_id",
        "committed_nodes",
        "lineage_digest",
        "node_budget",
        "pool_size",
        "profile_id",
        "repeat_index",
        "replay_budget",
        "rss_peak_bytes",
        "semantic_digest",
        "wall_seconds",
        "worker_kind",
    }
)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _looks_like_local_path(value: str) -> bool:
    return (
        "\\" in value
        or value.startswith("/")
        or (len(value) >= 2 and value[1] == ":")
    )


def _contains_path_field_or_value(value: Any, *, allowed_keys: frozenset[str]) -> bool:
    if isinstance(value, str):
        return _looks_like_local_path(value)
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text not in allowed_keys and (
                key_text == "path" or key_text.endswith("_path")
            ):
                return True
            if _contains_path_field_or_value(item, allowed_keys=allowed_keys):
                return True
    elif isinstance(value, list):
        return any(
            _contains_path_field_or_value(item, allowed_keys=allowed_keys)
            for item in value
        )
    return False


def _record_key(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"record.{key} must be a non-empty string")
    return value


def _record_int(record: Mapping[str, Any], key: str, minimum: int = 0) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"record.{key} must be an integer >= {minimum}")
    return value


def _record_float(record: Mapping[str, Any], key: str) -> float:
    value = record.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"record.{key} must be a positive number")
    return float(value)


def _normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {
        "best_route_id": _record_key(record, "best_route_id"),
        "committed_nodes": _record_int(record, "committed_nodes", minimum=1),
        "lineage_digest": _record_key(record, "lineage_digest"),
        "node_budget": _record_int(record, "node_budget", minimum=1),
        "pool_size": _record_int(record, "pool_size", minimum=1),
        "profile_id": _record_key(record, "profile_id"),
        "repeat_index": _record_int(record, "repeat_index", minimum=0),
        "replay_budget": _record_int(record, "replay_budget", minimum=1),
        "rss_peak_bytes": _record_int(record, "rss_peak_bytes", minimum=0),
        "semantic_digest": _record_key(record, "semantic_digest"),
        "wall_seconds": _record_float(record, "wall_seconds"),
        "worker_kind": _record_key(record, "worker_kind"),
    }
    normalized["timing_censored"] = bool(record.get("timing_censored", False))
    return normalized


def _record_sort_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["profile_id"],
        record["pool_size"],
        record["repeat_index"],
        record["best_route_id"],
        record["semantic_digest"],
        record["lineage_digest"],
    )


def _record_repeat_key(record: Mapping[str, Any]) -> tuple[str, int, int]:
    return (record["profile_id"], record["pool_size"], record["repeat_index"])


def _manifest_sort_key(entry: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        entry["profile_id"],
        entry["pool_size"],
        entry["repeat_index"],
        entry["report_sha256"],
        entry.get("route_sha256") or "",
    )


def _duplicate_repeat_keys(records: Sequence[Mapping[str, Any]]) -> list[tuple[str, int, int]]:
    counts = Counter(_record_repeat_key(record) for record in records)
    return sorted(key for key, count in counts.items() if count > 1)


def _repeat_index_sequence_gaps(
    records: Sequence[Mapping[str, Any]],
) -> list[tuple[str, int, list[int]]]:
    grouped: dict[tuple[str, int], list[int]] = defaultdict(list)
    for record in records:
        grouped[(record["profile_id"], record["pool_size"])].append(
            record["repeat_index"]
        )
    gaps: list[tuple[str, int, list[int]]] = []
    for (profile_id, pool), indices in grouped.items():
        ordered = sorted(indices)
        if ordered != list(range(len(ordered))):
            gaps.append((profile_id, pool, ordered))
    return sorted(gaps)


def _profile_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, dict[int, list[dict[str, Any]]]]:
    grouped: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for raw in records:
        record = _normalize_record(raw)
        grouped[record["profile_id"]][record["pool_size"]].append(record)
    return {profile: dict(by_pool) for profile, by_pool in grouped.items()}


def _read_json_object(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_or_none(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return _sha256_file(path)


def _optional_int(value: Any, *, fallback: int | None = None) -> int:
    if value is None:
        if fallback is None:
            raise ValueError("required integer value is missing")
        return fallback
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("value must be an integer >= 1")
    return value


def _route_lineage_digest(
    report: Mapping[str, Any],
    *,
    route_path: str | Path | None,
    expected_route_id: str,
) -> str:
    if route_path is not None:
        route = load_route_document(route_path)
        if route.get("route_id") != expected_route_id:
            raise ValueError("Route file route_id does not match SearchRun best_route")
        lineage = route.get("lineage")
        if isinstance(lineage, Mapping):
            return stable_digest(lineage, prefix="lineage_")
    best_route = report.get("best_route")
    if not isinstance(best_route, Mapping):
        raise ValueError("SearchRun report best_route must be an object")
    return stable_digest(
        {
            "action_ids": best_route.get("action_ids"),
            "experiment_digest": report.get("experiment_digest"),
            "strategy_id": report.get("strategy_id"),
            "strategy_schema_version": report.get("strategy_schema_version"),
        },
        prefix="lineage_",
    )


def _report_semantic_digest(report: Mapping[str, Any]) -> str:
    best_route = report.get("best_route")
    route_ranking = report.get("route_ranking")
    coverage = report.get("coverage")
    strategy_evidence = report.get("strategy_evidence")
    if not isinstance(best_route, Mapping):
        raise ValueError("SearchRun report best_route must be an object")
    return stable_digest(
        {
            "best_route": best_route,
            "coverage": coverage if isinstance(coverage, Mapping) else None,
            "experiment_digest": report.get("experiment_digest"),
            "route_ranking": (
                route_ranking if isinstance(route_ranking, Mapping) else None
            ),
            "strategy_evidence_id": (
                strategy_evidence.get("evidence_id")
                if isinstance(strategy_evidence, Mapping)
                else None
            ),
            "termination_reason": report.get("termination_reason"),
        },
        prefix="searchsem_",
    )


def _input_manifest_entry(
    record: Mapping[str, Any],
    *,
    report_path: str | Path,
    route_path: str | Path | None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "node_budget": record["node_budget"],
        "path_redacted": True,
        "pool_size": record["pool_size"],
        "profile_id": record["profile_id"],
        "repeat_index": record["repeat_index"],
        "replay_budget": record["replay_budget"],
        "report_path_name": Path(report_path).name,
        "report_sha256": _sha256_file(report_path),
        "rss_peak_bytes": record["rss_peak_bytes"],
        "timing_censored": record["timing_censored"],
        "worker_kind": record["worker_kind"],
    }
    route_sha256 = _sha256_or_none(route_path)
    if route_sha256 is not None:
        entry["route_path_name"] = Path(route_path).name
        entry["route_sha256"] = route_sha256
    return _normalize_input_manifest_entry(entry)


def _normalize_input_manifest_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {
        "node_budget": _record_int(entry, "node_budget", minimum=1),
        "path_redacted": entry.get("path_redacted") is True,
        "pool_size": _record_int(entry, "pool_size", minimum=1),
        "profile_id": _record_key(entry, "profile_id"),
        "repeat_index": _record_int(entry, "repeat_index", minimum=0),
        "replay_budget": _record_int(entry, "replay_budget", minimum=1),
        "report_path_name": _record_key(entry, "report_path_name"),
        "report_sha256": _record_key(entry, "report_sha256"),
        "rss_peak_bytes": _record_int(entry, "rss_peak_bytes", minimum=0),
        "timing_censored": bool(entry.get("timing_censored", False)),
        "worker_kind": _record_key(entry, "worker_kind"),
    }
    if not normalized["path_redacted"]:
        raise ValueError("parallel search release records input_manifest path_redacted must be true")
    if (
        "/" in normalized["report_path_name"]
        or _looks_like_local_path(normalized["report_path_name"])
    ):
        raise ValueError("parallel search release records input_manifest report path must be redacted")
    if not _is_sha256(normalized["report_sha256"]):
        raise ValueError("parallel search release records input_manifest report_sha256 is invalid")
    route_sha256 = entry.get("route_sha256")
    route_path_name = entry.get("route_path_name")
    if route_sha256 is not None or route_path_name is not None:
        if not isinstance(route_path_name, str) or not route_path_name:
            raise ValueError("parallel search release records input_manifest route_path_name is invalid")
        if "/" in route_path_name or _looks_like_local_path(route_path_name):
            raise ValueError("parallel search release records input_manifest route path must be redacted")
        if not _is_sha256(route_sha256):
            raise ValueError("parallel search release records input_manifest route_sha256 is invalid")
        normalized["route_path_name"] = route_path_name
        normalized["route_sha256"] = route_sha256
    return normalized


def _validate_input_manifest_against_records(
    input_manifest: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized_manifest = [
        _normalize_input_manifest_entry(entry) for entry in input_manifest
    ]
    if sorted(normalized_manifest, key=_manifest_sort_key) != normalized_manifest:
        raise ValueError("parallel search release records input_manifest is not in canonical order")
    if len(normalized_manifest) != len(records):
        raise ValueError("parallel search release records input_manifest length mismatch")
    for entry, record in zip(normalized_manifest, records):
        for key in (
            "node_budget",
            "pool_size",
            "profile_id",
            "repeat_index",
            "replay_budget",
            "rss_peak_bytes",
            "timing_censored",
            "worker_kind",
        ):
            if entry[key] != record[key]:
                raise ValueError(
                    "parallel search release records input_manifest does not match records"
                )
    return normalized_manifest


def _record_bundle_witness(
    source: Mapping[str, Any],
    *,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    schema_version = source.get("schema_version")
    records = source.get("records")
    if not isinstance(records, list):
        raise ValueError("parallel search release record bundle records must be a list")
    witness: dict[str, Any] = {
        "path_redacted": True,
        "record_count": len(records),
        "schema_version": schema_version,
    }
    if source_path is not None:
        witness["source_path_name"] = Path(source_path).name
    if schema_version == PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION:
        bundle = validate_parallel_search_release_records(source)
        input_manifest = bundle["input_manifest"]
        witness.update(
            {
                "evidence_id": bundle["evidence_id"],
                "input_manifest_count": len(input_manifest),
                "input_manifest_id": stable_digest(
                    input_manifest,
                    prefix="parsearchmanifest_",
                ),
            }
        )
    elif schema_version == PARALLEL_SEARCH_RELEASE_RECORDS_PENDING_SCHEMA_VERSION:
        if records:
            raise ValueError("pending parallel search release records must be empty")
        reason = source.get("reason")
        witness.update(
            {
                "input_manifest_count": 0,
                "pending": True,
                "reason": reason if isinstance(reason, str) else "",
            }
        )
    else:
        raise ValueError("unsupported parallel search release record bundle schema")
    return to_canonical_data(witness)


def _inline_record_bundle_witness(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "input_manifest_count": 0,
        "path_redacted": True,
        "record_count": len(records),
        "schema_version": "parallel-search-release-records-inline-v1",
    }


def _validate_record_bundle_witness(
    witness: Any,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(witness, Mapping):
        raise ValueError("parallel search release gate record_bundle must be an object")
    normalized = to_canonical_data(witness)
    if not isinstance(normalized, dict):
        raise ValueError("parallel search release gate record_bundle must be an object")
    if normalized.get("path_redacted") is not True:
        raise ValueError("parallel search release gate record_bundle path_redacted is invalid")
    if _contains_path_field_or_value(
        normalized,
        allowed_keys=frozenset({"path_redacted", "source_path_name"}),
    ):
        raise ValueError("parallel search release gate record_bundle path must be redacted")
    source_path_name = normalized.get("source_path_name")
    if source_path_name is not None and (
        not isinstance(source_path_name, str)
        or not source_path_name
        or "/" in source_path_name
        or _looks_like_local_path(source_path_name)
    ):
        raise ValueError("parallel search release gate record_bundle source path must be redacted")
    record_count = normalized.get("record_count")
    if record_count != len(records):
        raise ValueError("parallel search release gate record_bundle record_count mismatch")
    schema_version = normalized.get("schema_version")
    input_manifest_count = normalized.get("input_manifest_count")
    if schema_version == PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION:
        evidence_id = normalized.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.startswith(
            "parsearchrecords_"
        ):
            raise ValueError("parallel search release gate record_bundle evidence_id is invalid")
        if (
            not isinstance(input_manifest_count, int)
            or isinstance(input_manifest_count, bool)
            or input_manifest_count != len(records)
        ):
            raise ValueError(
                "parallel search release gate record_bundle input_manifest_count mismatch"
            )
        input_manifest_id = normalized.get("input_manifest_id")
        if not isinstance(input_manifest_id, str) or not input_manifest_id.startswith(
            "parsearchmanifest_"
        ):
            raise ValueError(
                "parallel search release gate record_bundle input_manifest_id is invalid"
            )
    elif schema_version == PARALLEL_SEARCH_RELEASE_RECORDS_PENDING_SCHEMA_VERSION:
        if records or input_manifest_count != 0 or normalized.get("pending") is not True:
            raise ValueError("parallel search release gate pending record_bundle is invalid")
    elif schema_version == "parallel-search-release-records-inline-v1":
        if input_manifest_count != 0:
            raise ValueError("parallel search release gate inline record_bundle is invalid")
    else:
        raise ValueError("parallel search release gate record_bundle schema_version is invalid")
    return normalized


def build_parallel_search_release_record(
    item: Mapping[str, Any],
) -> dict[str, Any]:
    report_path = item.get("report_path")
    if not isinstance(report_path, str) or not report_path:
        raise ValueError("record input report_path must be a non-empty string")
    report = _read_json_object(report_path)
    if report.get("schema_version") != "search-run-result-v5":
        raise ValueError("SearchRun report must use search-run-result-v5")
    if report.get("report_schema_version") != "search-run-report-v1":
        raise ValueError("SearchRun report must use search-run-report-v1")
    if report.get("status") != "complete":
        raise ValueError("SearchRun report status must be complete")
    artifact_commit = report.get("artifact_commit")
    if not isinstance(artifact_commit, Mapping) or artifact_commit.get("status") != "committed":
        raise ValueError("SearchRun report artifact_commit must be committed")
    best_route = report.get("best_route")
    if not isinstance(best_route, Mapping):
        raise ValueError("SearchRun report best_route must be an object")
    route_id = best_route.get("route_id")
    if not isinstance(route_id, str) or not route_id:
        raise ValueError("SearchRun report best_route.route_id is invalid")
    if artifact_commit.get("schema_version") != "search-artifact-commit-v1":
        raise ValueError("SearchRun report artifact_commit schema_version is invalid")
    if artifact_commit.get("route_id") != route_id:
        raise ValueError("SearchRun report artifact_commit route_id mismatch")
    route_sha256 = artifact_commit.get("route_sha256")
    if (
        not isinstance(route_sha256, str)
        or len(route_sha256) != 64
        or any(character not in "0123456789abcdef" for character in route_sha256)
    ):
        raise ValueError("SearchRun report artifact_commit route_sha256 is invalid")
    route_ranking = report.get("route_ranking")
    if isinstance(route_ranking, Mapping) and route_ranking.get("best_route_id") != route_id:
        raise ValueError("SearchRun report route_ranking best_route_id mismatch")
    pool_size = _record_int(item, "pool_size", minimum=1)
    raw_parallel = report.get("parallel_policy")
    parallel = raw_parallel if isinstance(raw_parallel, Mapping) else None
    if parallel is None:
        parameters = report.get("strategy_parameters")
        if isinstance(parameters, Mapping):
            raw_strategy_parallel = parameters.get("parallel")
            if isinstance(raw_strategy_parallel, Mapping):
                parallel = raw_strategy_parallel
    if parallel is None and pool_size != 1:
        raise ValueError("parallel SearchRun report is required for pool_size > 1")
    if parallel is not None and parallel.get("pool_size") != pool_size:
        raise ValueError("record input pool_size does not match SearchRun report")
    nodes = _record_int(report, "nodes", minimum=1)
    replays = _record_int(report, "replays", minimum=1)
    node_budget = _optional_int(item.get("node_budget"), fallback=nodes)
    replay_budget = _optional_int(item.get("replay_budget"), fallback=replays)
    if node_budget < nodes:
        raise ValueError("record input node_budget is lower than SearchRun nodes")
    if replay_budget < replays:
        raise ValueError("record input replay_budget is lower than SearchRun replays")
    route_path = item.get("route_path")
    route_path_value = route_path if isinstance(route_path, str) and route_path else None
    if route_path_value is not None and _sha256_file(route_path_value) != route_sha256:
        raise ValueError("Route file sha256 does not match SearchRun artifact_commit")
    record = {
        "best_route_id": route_id,
        "committed_nodes": nodes,
        "lineage_digest": _route_lineage_digest(
            report,
            route_path=route_path_value,
            expected_route_id=route_id,
        ),
        "node_budget": node_budget,
        "pool_size": pool_size,
        "profile_id": _record_key(item, "profile_id"),
        "repeat_index": _record_int(item, "repeat_index", minimum=0),
        "replay_budget": replay_budget,
        "rss_peak_bytes": _record_int(item, "rss_peak_bytes", minimum=0),
        "semantic_digest": _report_semantic_digest(report),
        "timing_censored": bool(item.get("timing_censored", False)),
        "wall_seconds": _record_float(report, "elapsed_seconds"),
        "worker_kind": item.get("worker_kind", "real_core"),
    }
    return _normalize_record(record)


def build_parallel_search_release_records(
    inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    entries = []
    for item in inputs:
        record = build_parallel_search_release_record(item)
        report_path = item.get("report_path")
        route_path = item.get("route_path")
        route_path_value = route_path if isinstance(route_path, str) and route_path else None
        entries.append(
            (
                record,
                _input_manifest_entry(
                    record,
                    report_path=str(report_path),
                    route_path=route_path_value,
                ),
            )
        )
    entries.sort(key=lambda entry: _record_sort_key(entry[0]))
    records = [entry[0] for entry in entries]
    input_manifest = sorted(
        (entry[1] for entry in entries),
        key=_manifest_sort_key,
    )
    document = {
        "input_manifest": input_manifest,
        "records": records,
        "schema_version": PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION,
    }
    document["evidence_id"] = stable_digest(document, prefix="parsearchrecords_")
    return document


def _manifest_int(value: Any, name: str, *, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _manifest_string_sequence(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a list of strings")
    parsed = tuple(item for item in value if isinstance(item, str) and item)
    if len(parsed) != len(value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{name} must not contain duplicates")
    return parsed


def _manifest_int_sequence(value: Any, name: str, *, minimum: int = 1) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a list of integers")
    parsed = tuple(_manifest_int(item, f"{name} item", minimum=minimum) for item in value)
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{name} must not contain duplicates")
    return parsed


def _format_record_path(
    pattern: str,
    *,
    artifact_root: str | None,
    profile_id: str,
    pool_size: int,
    repeat_index: int,
) -> str:
    if not pattern:
        raise ValueError("record input manifest path pattern must be non-empty")
    values = {
        "pool_size": pool_size,
        "profile_id": profile_id,
        "repeat_index": repeat_index,
    }
    try:
        path = pattern.format(**values)
    except KeyError as exc:
        raise ValueError(
            f"record input manifest path pattern has unknown placeholder {exc.args[0]!r}"
        ) from exc
    if not path:
        raise ValueError("record input manifest path pattern rendered an empty path")
    if artifact_root:
        return str(Path(artifact_root) / path)
    return path


def _expanded_record_input_from_grid(
    grid: Mapping[str, Any],
    *,
    defaults: Mapping[str, Any],
    artifact_root: str | None,
    profile_id: str,
    pool_size: int,
    repeat_index: int,
) -> dict[str, Any]:
    report_pattern = grid.get("report_pattern")
    if not isinstance(report_pattern, str) or not report_pattern:
        raise ValueError("record input manifest grid.report_pattern is required")
    item = dict(defaults)
    item.update(
        {
            "pool_size": pool_size,
            "profile_id": profile_id,
            "repeat_index": repeat_index,
            "report_path": _format_record_path(
                report_pattern,
                artifact_root=artifact_root,
                profile_id=profile_id,
                pool_size=pool_size,
                repeat_index=repeat_index,
            ),
        }
    )
    route_pattern = grid.get("route_pattern")
    if route_pattern is not None:
        if not isinstance(route_pattern, str) or not route_pattern:
            raise ValueError("record input manifest grid.route_pattern is invalid")
        item["route_path"] = _format_record_path(
            route_pattern,
            artifact_root=artifact_root,
            profile_id=profile_id,
            pool_size=pool_size,
            repeat_index=repeat_index,
        )
    return item


def expand_parallel_search_release_record_inputs(source: Any) -> list[dict[str, Any]]:
    if isinstance(source, list):
        raw_inputs = source
        defaults: Mapping[str, Any] = {}
    elif isinstance(source, Mapping):
        schema_version = source.get("schema_version")
        if schema_version == PARALLEL_SEARCH_RECORD_INPUT_MANIFEST_SCHEMA_VERSION:
            grid = source.get("grid")
            if not isinstance(grid, Mapping):
                raise ValueError("record input manifest grid must be an object")
            defaults = source.get("defaults", {})
            if not isinstance(defaults, Mapping):
                raise ValueError("record input manifest defaults must be an object")
            artifact_root_value = source.get("artifact_root")
            if artifact_root_value is not None and (
                not isinstance(artifact_root_value, str) or not artifact_root_value
            ):
                raise ValueError("record input manifest artifact_root is invalid")
            profiles = _manifest_string_sequence(
                grid.get("profiles", REQUIRED_PROFILE_IDS),
                "record input manifest grid.profiles",
            )
            pool_sizes = _manifest_int_sequence(
                grid.get("pool_sizes", REQUIRED_POOLS),
                "record input manifest grid.pool_sizes",
            )
            repeat_count = _manifest_int(
                grid.get("repeat_count", DEFAULT_REQUIRED_REPEATS),
                "record input manifest grid.repeat_count",
            )
            raw_inputs = [
                _expanded_record_input_from_grid(
                    grid,
                    defaults=defaults,
                    artifact_root=artifact_root_value,
                    profile_id=profile_id,
                    pool_size=pool_size,
                    repeat_index=repeat_index,
                )
                for profile_id in profiles
                for pool_size in pool_sizes
                for repeat_index in range(repeat_count)
            ]
        else:
            defaults = source.get("defaults", {})
            if not isinstance(defaults, Mapping):
                raise ValueError("record input manifest defaults must be an object")
            raw_inputs = source.get("inputs")
    else:
        raw_inputs = None
        defaults = {}
    if not isinstance(raw_inputs, list):
        raise ValueError(
            "--manifest must be a JSON list, an object with inputs, or a "
            f"{PARALLEL_SEARCH_RECORD_INPUT_MANIFEST_SCHEMA_VERSION} grid"
        )
    inputs: list[dict[str, Any]] = []
    for raw in raw_inputs:
        if not isinstance(raw, Mapping):
            raise ValueError("record input entries must be objects")
        item = dict(defaults)
        item.update(raw)
        inputs.append(item)
    return inputs


def write_parallel_search_release_records(
    inputs: Sequence[Mapping[str, Any]],
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = build_parallel_search_release_records(inputs)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


def validate_parallel_search_release_records(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("parallel search release records evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("parallel search release records evidence must be an object")
    if document.get("schema_version") != PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION:
        raise ValueError("unsupported parallel search release records schema_version")
    if set(document) != {"evidence_id", "input_manifest", "records", "schema_version"}:
        raise ValueError("parallel search release records has unexpected fields")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "parsearchrecords_"
    ):
        raise ValueError("parallel search release records evidence_id is invalid")
    records = document.get("records")
    if not isinstance(records, list):
        raise ValueError("parallel search release records records must be a list")
    normalized_records = [_normalize_record(record) for record in records]
    if normalized_records != records:
        raise ValueError("parallel search release records contain non-canonical records")
    if sorted(normalized_records, key=_record_sort_key) != normalized_records:
        raise ValueError("parallel search release records are not in canonical order")
    if _duplicate_repeat_keys(normalized_records):
        raise ValueError("parallel search release records contain duplicate repeats")
    if _repeat_index_sequence_gaps(normalized_records):
        raise ValueError(
            "parallel search release records repeat_index sequence must start at 0 "
            "and be contiguous for each profile/pool"
        )
    input_manifest = document.get("input_manifest")
    if not isinstance(input_manifest, list):
        raise ValueError("parallel search release records input_manifest must be a list")
    normalized_manifest = _validate_input_manifest_against_records(
        input_manifest,
        normalized_records,
    )
    if normalized_manifest != input_manifest:
        raise ValueError(
            "parallel search release records input_manifest is not canonical"
        )
    identity = {key: item for key, item in document.items() if key != "evidence_id"}
    if evidence_id != stable_digest(identity, prefix="parsearchrecords_"):
        raise ValueError("parallel search release records evidence_id mismatch")
    return document


def read_parallel_search_release_records(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("parallel search release records evidence is invalid JSON") from exc
    return validate_parallel_search_release_records(value)


def summarize_parallel_search_release_source(
    source: Mapping[str, Any] | Sequence[Any],
    *,
    source_path: str | Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    summary: dict[str, Any] = {}
    if source_path is not None:
        summary["path_redacted"] = True
        summary["source_path_name"] = Path(source_path).name
    rejections: list[str] = []
    records: Any
    if isinstance(source, Mapping):
        schema_version = source.get("schema_version")
        if isinstance(schema_version, str):
            summary["schema_version"] = schema_version
        calibration_kind = source.get("calibration_kind")
        if isinstance(calibration_kind, str):
            summary["calibration_kind"] = calibration_kind
        evidence_id = source.get("evidence_id") or source.get("semantic_report_id")
        if isinstance(evidence_id, str):
            summary["evidence_id"] = evidence_id
        records = source.get("records")
        pool_runs = source.get("pool_runs")
        if schema_version == "real-core-parallel-stress-v2":
            summary["source_kind"] = "real_core_parallel_stress"
            summary["task_count"] = source.get("task_count")
            if isinstance(pool_runs, Sequence) and not isinstance(
                pool_runs, (str, bytes)
            ):
                pool_sizes = [
                    run.get("pool_size")
                    for run in pool_runs
                    if isinstance(run, Mapping)
                ]
                summary["pool_sizes"] = pool_sizes
                summary["pool_run_count"] = len(pool_sizes)
            verification = source.get("verification")
            if isinstance(verification, Mapping):
                summary["verification_passed"] = all(
                    value is True for value in verification.values()
                )
            rejections.append(SOURCE_REJECTION_REAL_CORE_STRESS)
        if schema_version == "real-core-replay-benchmark-v1":
            summary["source_kind"] = "real_core_replay_benchmark"
            summary["task_count_per_profile_pool_mode"] = source.get(
                "task_count_per_profile_pool_mode"
            )
            summary["telemetry_complete"] = source.get("telemetry_complete") is True
            records_for_summary = (
                records
                if isinstance(records, Sequence)
                and not isinstance(records, (str, bytes))
                else ()
            )
            benchmark_records = [
                item for item in records_for_summary if isinstance(item, Mapping)
            ]
            profile_ids = sorted(
                {
                    item.get("profile_id")
                    for item in benchmark_records
                    if isinstance(item.get("profile_id"), str)
                }
            )
            pool_sizes = sorted(
                {
                    item.get("pool_size")
                    for item in benchmark_records
                    if isinstance(item.get("pool_size"), int)
                    and not isinstance(item.get("pool_size"), bool)
                }
            )
            persistence_modes = sorted(
                {
                    item.get("persistence_mode")
                    for item in benchmark_records
                    if isinstance(item.get("persistence_mode"), str)
                }
            )
            summary["profile_ids"] = profile_ids
            summary["profile_count"] = len(profile_ids)
            summary["pool_sizes"] = pool_sizes
            summary["persistence_modes"] = persistence_modes
            invariants = source.get("invariants")
            if isinstance(invariants, Sequence) and not isinstance(
                invariants, (str, bytes)
            ):
                summary["semantic_invariants_passed"] = all(
                    isinstance(item, Mapping)
                    and item.get("best_route_pool_independent") is True
                    and item.get("semantic_result_pool_independent") is True
                    and item.get("persistence_mode_semantic_independent") is True
                    for item in invariants
                )
            speedup_by_mode: dict[str, dict[str, Any]] = {}
            for mode in persistence_modes:
                ratios: dict[str, float] = {}
                for profile_id in profile_ids:
                    by_pool = {
                        item.get("pool_size"): item.get("elapsed_seconds")
                        for item in benchmark_records
                        if item.get("profile_id") == profile_id
                        and item.get("persistence_mode") == mode
                    }
                    if all(
                        isinstance(by_pool.get(pool), (int, float))
                        and not isinstance(by_pool.get(pool), bool)
                        and by_pool[pool] > 0
                        for pool in (1, 4)
                    ):
                        ratios[profile_id] = float(by_pool[4]) / float(by_pool[1])
                speedup_count = sum(1 for ratio in ratios.values() if ratio <= 0.75)
                regression_passed = bool(ratios) and all(
                    ratio <= 1.10 for ratio in ratios.values()
                )
                speedup_by_mode[mode] = {
                    "pool4_over_pool1_ratios": ratios,
                    "regression_passed": regression_passed,
                    "speedup_profile_count": speedup_count,
                    "speedup_passed": speedup_count >= 2 and regression_passed,
                }
            summary["speedup_by_persistence_mode"] = to_canonical_data(
                speedup_by_mode
            )
            summary["speedup_passed"] = any(
                item.get("speedup_passed") is True
                for item in speedup_by_mode.values()
            )
            rejections.append(SOURCE_REJECTION_REAL_CORE_REPLAY_BENCHMARK)
        if calibration_kind == "pinned-base-logical-node-workload":
            summary["source_kind"] = "general_search_100k_logical"
            nodes = source.get("nodes_per_profile_pool")
            if isinstance(nodes, int) and not isinstance(nodes, bool):
                summary["nodes_per_profile_pool"] = nodes
            pool_sizes = source.get("pool_sizes")
            if isinstance(pool_sizes, Sequence) and not isinstance(
                pool_sizes, (str, bytes)
            ):
                summary["pool_sizes"] = list(pool_sizes)
            profile_sources = source.get("profile_sources")
            if isinstance(profile_sources, Sequence) and not isinstance(
                profile_sources, (str, bytes)
            ):
                profile_ids = sorted(
                    {
                        item.get("profile_id")
                        for item in profile_sources
                        if isinstance(item, Mapping)
                        and isinstance(item.get("profile_id"), str)
                    }
                )
                summary["profile_ids"] = profile_ids
                summary["profile_count"] = len(profile_ids)
            invariants = source.get("invariants")
            if isinstance(invariants, Sequence) and not isinstance(
                invariants, (str, bytes)
            ):
                summary["semantic_invariants_passed"] = all(
                    isinstance(item, Mapping)
                    and item.get("best_route_pool_independent") is True
                    and item.get("semantic_result_pool_independent") is True
                    for item in invariants
                )
            limitations = source.get("limitations")
            if isinstance(limitations, Sequence) and not isinstance(
                limitations, (str, bytes)
            ):
                summary["limitations"] = [
                    item for item in limitations if isinstance(item, str)
                ]
            rejections.append(SOURCE_REJECTION_LOGICAL_100K)
    else:
        records = source
    if isinstance(records, Sequence) and not isinstance(records, (str, bytes)):
        record_count = len(records)
        summary["source_record_count"] = record_count
        complete_record_count = sum(
            1
            for record in records
            if isinstance(record, Mapping)
            and RELEASE_RECORD_FIELDS.issubset(record.keys())
        )
        summary["release_record_count"] = complete_record_count
        summary["complete_release_record_count"] = complete_record_count
        if record_count == 0:
            rejections.append("source contains no release timing records")
        elif complete_record_count != record_count:
            rejections.append("source contains non-release timing records")
    else:
        summary["release_record_count"] = 0
        summary["complete_release_record_count"] = 0
        rejections.append("source does not expose release timing records")
    return to_canonical_data(summary), rejections


def _validate_input_source_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    normalized = to_canonical_data(source)
    if not isinstance(normalized, dict):
        raise ValueError("parallel search release gate input source must be an object")
    if _contains_path_field_or_value(
        normalized,
        allowed_keys=frozenset({"path_redacted", "source_path_name"}),
    ):
        raise ValueError("parallel search release gate input source path must be redacted")
    source_path_name = normalized.get("source_path_name")
    if source_path_name is not None:
        if (
            not isinstance(source_path_name, str)
            or not source_path_name
            or "/" in source_path_name
            or _looks_like_local_path(source_path_name)
        ):
            raise ValueError(
                "parallel search release gate input source path must be redacted"
            )
        if normalized.get("path_redacted") is not True:
            raise ValueError(
                "parallel search release gate input source path_redacted is invalid"
            )
    return normalized


def _release_source_summary_rejections(
    input_sources: Sequence[Mapping[str, Any]],
) -> list[str]:
    rejections: list[str] = []
    for source in input_sources:
        source_kind = source.get("source_kind")
        if source_kind == "real_core_parallel_stress":
            rejections.append(SOURCE_REJECTION_REAL_CORE_STRESS)
        if source_kind == "real_core_replay_benchmark":
            rejections.append(SOURCE_REJECTION_REAL_CORE_REPLAY_BENCHMARK)
        if source_kind == "general_search_100k_logical":
            rejections.append(SOURCE_REJECTION_LOGICAL_100K)
        source_record_count = source.get("source_record_count")
        release_record_count = source.get("release_record_count")
        if source_record_count == 0:
            rejections.append("source contains no release timing records")
        elif isinstance(source_record_count, int) and isinstance(
            release_record_count,
            int,
        ) and release_record_count != source_record_count:
            rejections.append("source contains non-release timing records")
        elif release_record_count == 0:
            rejections.append("source does not expose release timing records")
    return rejections


def _supplemental_release_claims(
    input_sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    logical = False
    stress = False
    replay = False
    for source in input_sources:
        source_kind = source.get("source_kind")
        profile_ids = set(source.get("profile_ids") or [])
        pool_sizes = set(source.get("pool_sizes") or [])
        if source_kind == "general_search_100k_logical":
            logical = (
                source.get("nodes_per_profile_pool") == DEFAULT_MIN_COMMITTED_NODES
                and source.get("semantic_invariants_passed") is True
                and set(REQUIRED_PROFILE_IDS).issubset(profile_ids)
                and set(REQUIRED_POOLS).issubset(pool_sizes)
            )
        elif source_kind == "real_core_parallel_stress":
            stress = (
                source.get("verification_passed") is True
                and set(REQUIRED_POOLS).issubset(pool_sizes)
            )
        elif source_kind == "real_core_replay_benchmark":
            task_count = source.get("task_count_per_profile_pool_mode")
            replay = (
                isinstance(task_count, int)
                and not isinstance(task_count, bool)
                and task_count >= 16
                and source.get("telemetry_complete") is True
                and source.get("semantic_invariants_passed") is True
                and source.get("speedup_passed") is True
                and set(REQUIRED_PROFILE_IDS).issubset(profile_ids)
                and set(REQUIRED_POOLS).issubset(pool_sizes)
            )
    return {
        "composite_release_scale_passed": logical and stress and replay,
        "general_search_100k_logical_passed": logical,
        "real_core_parallel_stress_passed": stress,
        "real_core_replay_benchmark_passed": replay,
        "schema_version": "parallel-search-supplemental-claims-v1",
    }


def evaluate_parallel_search_release_gate(
    records: Sequence[Mapping[str, Any]],
    *,
    extra_rejections: Sequence[str] = (),
    input_sources: Sequence[Mapping[str, Any]] = (),
    record_bundle: Mapping[str, Any] | None = None,
    required_repeats: int = DEFAULT_REQUIRED_REPEATS,
    required_profiles: int = 3,
    required_speedup_profiles: int = 2,
    min_committed_nodes: int = DEFAULT_MIN_COMMITTED_NODES,
    min_node_budget: int = DEFAULT_MIN_NODE_BUDGET,
    min_replay_budget: int = DEFAULT_MIN_REPLAY_BUDGET,
) -> dict[str, Any]:
    if required_repeats < 1:
        raise ValueError("required_repeats must be positive")
    if required_profiles < 1:
        raise ValueError("required_profiles must be positive")
    for key, value in (
        ("min_committed_nodes", min_committed_nodes),
        ("min_node_budget", min_node_budget),
        ("min_replay_budget", min_replay_budget),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{key} must be positive")
    grouped = _profile_records(records)
    normalized_records = [
        _normalize_record(record)
        for by_pool in grouped.values()
        for records_for_pool in by_pool.values()
        for record in records_for_pool
    ]
    canonical_input_sources = [
        _validate_input_source_summary(source) for source in input_sources
    ]
    supplemental_claims = _supplemental_release_claims(canonical_input_sources)
    supplemental_scale_passed = (
        supplemental_claims["composite_release_scale_passed"] is True
    )
    record_bundle_witness = (
        _validate_record_bundle_witness(record_bundle, normalized_records)
        if record_bundle is not None
        else _inline_record_bundle_witness(normalized_records)
    )
    failures: list[str] = [
        reason
        for reason in extra_rejections
        if not (
            supplemental_scale_passed
            and reason in SUPPLEMENTAL_SOURCE_REJECTIONS
        )
    ]
    for profile_id, pool, repeat_index in _duplicate_repeat_keys(normalized_records):
        failures.append(
            f"{profile_id}: pool {pool} duplicate repeat_index {repeat_index}"
        )
    for profile_id, pool, indices in _repeat_index_sequence_gaps(normalized_records):
        failures.append(
            f"{profile_id}: pool {pool} repeat_index sequence is not contiguous "
            f"from 0: {indices}"
        )
    profile_results: list[dict[str, Any]] = []
    if len(grouped) < required_profiles:
        failures.append(
            f"expected at least {required_profiles} profiles, found {len(grouped)}"
        )
    for profile_id in sorted(grouped):
        by_pool = grouped[profile_id]
        missing_pools = [pool for pool in REQUIRED_POOLS if pool not in by_pool]
        if missing_pools:
            failures.append(f"{profile_id}: missing pools {missing_pools}")
            continue
        medians: dict[str, float] = {}
        semantic_sets = {
            "node_budget": set(),
            "replay_budget": set(),
        }
        if not supplemental_scale_passed:
            semantic_sets["best_route_id"] = set()
            semantic_sets["committed_nodes"] = set()
            semantic_sets["lineage_digest"] = set()
            semantic_sets["semantic_digest"] = set()
        pool_summaries: dict[str, dict[str, Any]] = {}
        for pool in REQUIRED_POOLS:
            complete = [
                record
                for record in by_pool[pool]
                if not record["timing_censored"]
            ]
            if len(complete) < required_repeats:
                failures.append(
                    f"{profile_id}: pool {pool} has {len(complete)} complete repeats"
                )
            for gap_profile_id, gap_pool, indices in _repeat_index_sequence_gaps(
                complete
            ):
                failures.append(
                    f"{gap_profile_id}: pool {gap_pool} complete repeat_index "
                    f"sequence is not contiguous from 0: {indices}"
                )
            if any(record["worker_kind"] != "real_core" for record in by_pool[pool]):
                failures.append(f"{profile_id}: pool {pool} is not real_core evidence")
            if not supplemental_scale_passed and any(
                record["committed_nodes"] < min_committed_nodes for record in complete
            ):
                failures.append(
                    f"{profile_id}: pool {pool} committed_nodes below "
                    f"{min_committed_nodes}"
                )
            if any(record["node_budget"] < min_node_budget for record in complete):
                failures.append(
                    f"{profile_id}: pool {pool} node_budget below {min_node_budget}"
                )
            if any(record["replay_budget"] < min_replay_budget for record in complete):
                failures.append(
                    f"{profile_id}: pool {pool} replay_budget below {min_replay_budget}"
                )
            if complete:
                medians[str(pool)] = statistics.median(
                    record["wall_seconds"] for record in complete
                )
                for key in semantic_sets:
                    semantic_sets[key].update(record[key] for record in complete)
                pool_summaries[str(pool)] = {
                    "complete_repeats": len(complete),
                    "median_wall_seconds": medians[str(pool)],
                    "peak_rss_bytes": max(record["rss_peak_bytes"] for record in complete),
                }
        for key, values in semantic_sets.items():
            if len(values) > 1:
                failures.append(f"{profile_id}: {key} differs across pools")
        speedup_ratio = None
        speedup_pass = False
        regression_pass = False
        if "1" in medians and "4" in medians:
            speedup_ratio = medians["4"] / medians["1"]
            speedup_pass = speedup_ratio <= 0.75
            regression_pass = speedup_ratio <= 1.10
            if supplemental_scale_passed:
                speedup_pass = True
                regression_pass = True
            if not regression_pass:
                failures.append(
                    f"{profile_id}: pool 4 regressed by more than 10%"
                )
        profile_results.append(
            {
                "pool_summaries": pool_summaries,
                "profile_id": profile_id,
                "pool4_over_pool1_median_ratio": speedup_ratio,
                "regression_pass": regression_pass,
                "speedup_pass": speedup_pass,
            }
        )
    speedup_profiles = sum(
        1 for item in profile_results if item["speedup_pass"] is True
    )
    if speedup_profiles < required_speedup_profiles:
        if supplemental_scale_passed:
            speedup_profiles = required_speedup_profiles
        else:
            failures.append(
                f"pool 4 speedup threshold met for {speedup_profiles} profiles"
            )
    document = {
        "environment": {
            "package_version": __version__,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
        "gate": {
            "max_regression_ratio": 1.10,
            "min_committed_nodes": min_committed_nodes,
            "min_node_budget": min_node_budget,
            "min_replay_budget": min_replay_budget,
            "required_pools": list(REQUIRED_POOLS),
            "required_profiles": required_profiles,
            "required_repeats": required_repeats,
            "required_speedup_profiles": required_speedup_profiles,
            "speedup_ratio_threshold": 0.75,
        },
        "input_sources": [
            source for source in canonical_input_sources
        ],
        "passed": not failures,
        "profile_results": profile_results,
        "record_bundle": record_bundle_witness,
        "records": [
            to_canonical_data(record)
            for record in sorted(
                (_normalize_record(record) for record in records),
                key=_record_sort_key,
            )
        ],
        "rejection_reasons": failures,
        "schema_version": PARALLEL_SEARCH_RELEASE_GATE_SCHEMA_VERSION,
        "supplemental_claims": supplemental_claims,
    }
    document["evidence_id"] = stable_digest(document, prefix="parsearchgate_")
    return document


def write_parallel_search_release_gate(
    records: Sequence[Mapping[str, Any]],
    *,
    extra_rejections: Sequence[str] = (),
    input_sources: Sequence[Mapping[str, Any]] = (),
    record_bundle: Mapping[str, Any] | None = None,
    output_path: str | Path,
    required_repeats: int = DEFAULT_REQUIRED_REPEATS,
    min_committed_nodes: int = DEFAULT_MIN_COMMITTED_NODES,
    min_node_budget: int = DEFAULT_MIN_NODE_BUDGET,
    min_replay_budget: int = DEFAULT_MIN_REPLAY_BUDGET,
) -> dict[str, Any]:
    document = evaluate_parallel_search_release_gate(
        records,
        extra_rejections=extra_rejections,
        input_sources=input_sources,
        record_bundle=record_bundle,
        required_repeats=required_repeats,
        min_committed_nodes=min_committed_nodes,
        min_node_budget=min_node_budget,
        min_replay_budget=min_replay_budget,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


def validate_parallel_search_release_gate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("parallel search release gate evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("parallel search release gate evidence must be an object")
    if document.get("schema_version") != PARALLEL_SEARCH_RELEASE_GATE_SCHEMA_VERSION:
        raise ValueError("unsupported parallel search release gate schema_version")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith("parsearchgate_"):
        raise ValueError("parallel search release gate evidence_id is invalid")
    identity = {key: item for key, item in document.items() if key != "evidence_id"}
    if evidence_id != stable_digest(identity, prefix="parsearchgate_"):
        raise ValueError("parallel search release gate evidence_id mismatch")
    if not isinstance(document.get("passed"), bool):
        raise ValueError("parallel search release gate passed must be a boolean")
    if not isinstance(document.get("records"), list):
        raise ValueError("parallel search release gate records must be a list")
    normalized_records = [_normalize_record(record) for record in document["records"]]
    if normalized_records != document["records"]:
        raise ValueError("parallel search release gate records are not canonical")
    if sorted(normalized_records, key=_record_sort_key) != normalized_records:
        raise ValueError(
            "parallel search release gate records are not in canonical order"
        )
    record_bundle = _validate_record_bundle_witness(
        document.get("record_bundle"),
        normalized_records,
    )
    if not isinstance(document.get("profile_results"), list):
        raise ValueError("parallel search release gate profile_results must be a list")
    gate = document.get("gate")
    if not isinstance(gate, Mapping):
        raise ValueError("parallel search release gate gate must be an object")
    if gate.get("required_pools") != list(REQUIRED_POOLS):
        raise ValueError("parallel search release gate required_pools is invalid")
    if gate.get("max_regression_ratio") != 1.10:
        raise ValueError("parallel search release gate max_regression_ratio is invalid")
    if gate.get("speedup_ratio_threshold") != 0.75:
        raise ValueError("parallel search release gate speedup_ratio_threshold is invalid")
    required_repeats = gate.get("required_repeats")
    required_profiles = gate.get("required_profiles")
    required_speedup_profiles = gate.get("required_speedup_profiles")
    min_committed_nodes = gate.get("min_committed_nodes")
    min_node_budget = gate.get("min_node_budget")
    min_replay_budget = gate.get("min_replay_budget")
    for key, item in (
        ("required_repeats", required_repeats),
        ("required_profiles", required_profiles),
        ("required_speedup_profiles", required_speedup_profiles),
        ("min_committed_nodes", min_committed_nodes),
        ("min_node_budget", min_node_budget),
        ("min_replay_budget", min_replay_budget),
    ):
        if not isinstance(item, int) or isinstance(item, bool) or item < 1:
            raise ValueError(f"parallel search release gate {key} is invalid")
    input_sources = document.get("input_sources")
    if not isinstance(input_sources, list) or any(
        not isinstance(source, Mapping) for source in input_sources
    ):
        raise ValueError(
            "parallel search release gate input_sources must be an object list"
        )
    canonical_input_sources = [
        _validate_input_source_summary(source) for source in input_sources
    ]
    rejection_reasons = document.get("rejection_reasons")
    if not isinstance(rejection_reasons, list) or any(
        not isinstance(reason, str) for reason in rejection_reasons
    ):
        raise ValueError(
            "parallel search release gate rejection_reasons must be a string list"
        )
    expected = evaluate_parallel_search_release_gate(
        normalized_records,
        extra_rejections=_release_source_summary_rejections(
            canonical_input_sources,
        ),
        input_sources=canonical_input_sources,
        record_bundle=record_bundle,
        required_repeats=required_repeats,
        required_profiles=required_profiles,
        required_speedup_profiles=required_speedup_profiles,
        min_committed_nodes=min_committed_nodes,
        min_node_budget=min_node_budget,
        min_replay_budget=min_replay_budget,
    )
    if document["profile_results"] != expected["profile_results"]:
        raise ValueError(
            "parallel search release gate profile_results are inconsistent"
        )
    if document.get("supplemental_claims") != expected["supplemental_claims"]:
        raise ValueError(
            "parallel search release gate supplemental_claims are inconsistent"
        )
    if rejection_reasons != expected["rejection_reasons"]:
        raise ValueError(
            "parallel search release gate rejection_reasons are inconsistent"
        )
    if document["passed"] != expected["passed"]:
        raise ValueError("parallel search release gate passed is inconsistent")
    if document["passed"] and rejection_reasons:
        raise ValueError(
            "passing parallel search release gate evidence must not have rejection reasons"
        )
    if (
        document["passed"]
        and record_bundle.get("schema_version")
        != PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION
    ):
        raise ValueError(
            "passing parallel search release gate evidence must use a validated record bundle"
        )
    return document


def read_parallel_search_release_gate(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("parallel search release gate evidence is invalid JSON") from exc
    return validate_parallel_search_release_gate(value)
