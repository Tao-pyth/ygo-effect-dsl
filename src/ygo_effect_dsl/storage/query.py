from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timezone
from enum import Enum
from functools import cmp_to_key
import hashlib
import json
import math
import threading
from types import MappingProxyType
from typing import Any

from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.storage.parquet import AggregationRecord

ANALYTICS_QUERY_CONTRACT_VERSION = "analytics-query-contract-v1"
ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION = "analytics-query-request-v1"
ANALYTICS_QUERY_RESPONSE_SCHEMA_VERSION = "analytics-query-response-v1"
ANALYTICS_QUERY_ERROR_SCHEMA_VERSION = "analytics-query-error-v1"
ANALYTICS_QUERY_ROW_SCHEMA_VERSION = "analytics-query-row-v1"
ANALYTICS_QUERY_VALUE_SCHEMA_VERSION = "analytics-query-value-v1"
ANALYTICS_SNAPSHOT_SCHEMA_VERSION = "analytics-snapshot-v1"
ANALYTICS_CURSOR_SCHEMA_VERSION = "analytics-cursor-v1"

DEFAULT_QUERY_LIMIT = 100
MAX_QUERY_LIMIT = 500
MAX_QUERY_FIELDS = 32
MAX_QUERY_FILTERS = 16
MAX_QUERY_SORTS = 4
MAX_FILTER_LIST_ITEMS = 100
DEFAULT_MAX_SYNC_SCAN_ROWS = 10_000


@dataclass(frozen=True)
class _FieldSpec:
    value_type: str
    filter_operators: tuple[str, ...]
    sortable: bool = True


_SCALAR_OPERATORS = ("eq", "in", "state_is")
_RANGE_OPERATORS = ("eq", "in", "gte", "lte", "between", "state_is")
_LIST_OPERATORS = ("contains", "contains_any", "contains_all", "state_is")
_FIELD_SPECS: dict[str, _FieldSpec] = {
    "run": _FieldSpec("string", _SCALAR_OPERATORS),
    "deck": _FieldSpec("string", _SCALAR_OPERATORS),
    "card": _FieldSpec("string_list", _LIST_OPERATORS, sortable=False),
    "strategy": _FieldSpec("string", _SCALAR_OPERATORS),
    "interruption": _FieldSpec("string_list", _LIST_OPERATORS, sortable=False),
    "success": _FieldSpec("boolean", _SCALAR_OPERATORS),
    "score": _FieldSpec("number", _RANGE_OPERATORS),
    "time": _FieldSpec("timestamp", _RANGE_OPERATORS),
    "version": _FieldSpec("string", _SCALAR_OPERATORS),
    "status": _FieldSpec("string", _SCALAR_OPERATORS),
    "route": _FieldSpec("string", _SCALAR_OPERATORS),
    "experiment": _FieldSpec("string", _SCALAR_OPERATORS),
    "evaluator": _FieldSpec("string", _SCALAR_OPERATORS),
    "target_board": _FieldSpec("string", _SCALAR_OPERATORS),
    "action_count": _FieldSpec("integer", _RANGE_OPERATORS),
    "resource_consumption": _FieldSpec("number", _RANGE_OPERATORS),
    "state_hash": _FieldSpec("string", _SCALAR_OPERATORS),
}


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    observed = set(value)
    if observed != expected:
        raise ValueError(
            f"{name} fields must be exactly {sorted(expected)}; "
            f"observed {sorted(observed)}"
        )


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{name} must be a sequence")
    return value


def _validate_json_value(value: Any, name: str) -> Any:
    def validate(item: Any, path: str) -> None:
        if item is None or isinstance(item, (str, bool)):
            return
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            if not math.isfinite(float(item)):
                raise ValueError(f"{path} must be finite")
            return
        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                validate(child, f"{path}[{index}]")
            return
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            for key, child in item.items():
                validate(child, f"{path}.{key}")
            return
        raise ValueError(f"{path} must be a JSON value")

    validate(value, name)
    canonical = to_canonical_data(value)

    def freeze(item: Any) -> Any:
        if isinstance(item, list):
            return tuple(freeze(child) for child in item)
        if isinstance(item, dict):
            return MappingProxyType({key: freeze(child) for key, child in item.items()})
        return item

    return freeze(canonical)


def _thaw_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json_value(child) for key, child in sorted(value.items())}
    if isinstance(value, tuple):
        return [_thaw_json_value(child) for child in value]
    return value


class AnalyticsValueState(str, Enum):
    VALUE = "value"
    EMPTY = "empty"
    MISSING = "missing"
    UNKNOWN = "unknown"
    REDACTED = "redacted"
    NOT_APPLICABLE = "not_applicable"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class AnalyticsValue:
    state: AnalyticsValueState
    value: Any = None
    schema_version: str = ANALYTICS_QUERY_VALUE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_QUERY_VALUE_SCHEMA_VERSION:
            raise ValueError("unsupported analytics value schema")
        state = (
            self.state
            if isinstance(self.state, AnalyticsValueState)
            else AnalyticsValueState(self.state)
        )
        object.__setattr__(self, "state", state)
        if state == AnalyticsValueState.VALUE:
            if self.value is None:
                raise ValueError("value state requires a non-null value")
            object.__setattr__(self, "value", _validate_json_value(self.value, "value"))
        elif state == AnalyticsValueState.EMPTY:
            if self.value not in ("", [], (), {}):
                raise ValueError("empty state requires '', [], or {}")
            object.__setattr__(self, "value", _validate_json_value(self.value, "value"))
        elif self.value is not None:
            raise ValueError(f"{state.value} state must not carry a value")

    @classmethod
    def present(cls, value: Any) -> "AnalyticsValue":
        return cls(AnalyticsValueState.VALUE, value)

    @classmethod
    def empty(cls, value: Any = "") -> "AnalyticsValue":
        return cls(AnalyticsValueState.EMPTY, value)

    @classmethod
    def missing(cls) -> "AnalyticsValue":
        return cls(AnalyticsValueState.MISSING)

    @classmethod
    def unknown(cls) -> "AnalyticsValue":
        return cls(AnalyticsValueState.UNKNOWN)

    @classmethod
    def redacted(cls) -> "AnalyticsValue":
        return cls(AnalyticsValueState.REDACTED)

    @classmethod
    def not_applicable(cls) -> "AnalyticsValue":
        return cls(AnalyticsValueState.NOT_APPLICABLE)

    @classmethod
    def quarantined(cls) -> "AnalyticsValue":
        return cls(AnalyticsValueState.QUARANTINED)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "state": self.state.value,
        }
        if self.state in {AnalyticsValueState.VALUE, AnalyticsValueState.EMPTY}:
            result["value"] = _thaw_json_value(self.value)
        return result

    @classmethod
    def from_mapping(cls, value: Any) -> "AnalyticsValue":
        if not isinstance(value, Mapping):
            raise ValueError("analytics value must be a mapping")
        state = AnalyticsValueState(value.get("state"))
        expected = {"schema_version", "state"}
        if state in {AnalyticsValueState.VALUE, AnalyticsValueState.EMPTY}:
            expected.add("value")
        _exact_keys(value, expected, "analytics value")
        return cls(
            state=state,
            value=value.get("value"),
            schema_version=value.get("schema_version"),
        )


def _validate_field_value(field: str, value: AnalyticsValue) -> None:
    if value.state not in {AnalyticsValueState.VALUE, AnalyticsValueState.EMPTY}:
        return
    observed = value.value
    value_type = _FIELD_SPECS[field].value_type
    if value.state == AnalyticsValueState.EMPTY:
        if value_type == "string" and observed == "":
            return
        if value_type == "string_list" and observed in ([], ()):
            return
        raise ValueError(f"field {field!r} cannot use that empty representation")
    if value_type in {"string", "timestamp"}:
        _non_empty_string(observed, field)
        if value_type == "timestamp":
            try:
                _timestamp_value(observed)
            except ValueError as exc:
                raise ValueError(
                    f"field {field!r} must be an ISO date or UTC date/time"
                ) from exc
    elif value_type == "boolean":
        if not isinstance(observed, bool):
            raise ValueError(f"field {field!r} must be boolean")
    elif value_type == "integer":
        if not isinstance(observed, int) or isinstance(observed, bool):
            raise ValueError(f"field {field!r} must be an integer")
    elif value_type == "number":
        if (
            not isinstance(observed, (int, float))
            or isinstance(observed, bool)
            or not math.isfinite(float(observed))
        ):
            raise ValueError(f"field {field!r} must be a finite number")
    elif value_type == "string_list":
        items = _sequence(observed, field)
        if not items:
            raise ValueError(f"field {field!r} must use empty state for []")
        parsed = tuple(_non_empty_string(item, field) for item in items)
        if len(parsed) != len(set(parsed)):
            raise ValueError(f"field {field!r} must not contain duplicates")


@dataclass(frozen=True)
class AnalyticsQueryRow:
    row_id: str
    values: Mapping[str, AnalyticsValue]
    schema_version: str = ANALYTICS_QUERY_ROW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _non_empty_string(self.row_id, "row_id")
        if self.schema_version != ANALYTICS_QUERY_ROW_SCHEMA_VERSION:
            raise ValueError("unsupported analytics row schema")
        if set(self.values) != set(_FIELD_SPECS):
            raise ValueError("analytics row must represent every contract field")
        normalized: dict[str, AnalyticsValue] = {}
        for field in _FIELD_SPECS:
            value = self.values[field]
            if not isinstance(value, AnalyticsValue):
                value = AnalyticsValue.from_mapping(value)
            _validate_field_value(field, value)
            normalized[field] = value
        object.__setattr__(self, "values", MappingProxyType(normalized))

    @classmethod
    def build(
        cls,
        values: Mapping[str, AnalyticsValue | Any],
        *,
        row_id: str | None = None,
    ) -> "AnalyticsQueryRow":
        unknown = set(values) - set(_FIELD_SPECS)
        if unknown:
            raise ValueError(f"unknown analytics fields: {sorted(unknown)}")
        normalized: dict[str, AnalyticsValue] = {}
        for field in _FIELD_SPECS:
            raw = values.get(field, AnalyticsValue.missing())
            if isinstance(raw, AnalyticsValue):
                normalized[field] = raw
            elif raw in ("", [], (), {}):
                normalized[field] = AnalyticsValue.empty(raw)
            else:
                normalized[field] = AnalyticsValue.present(raw)
        identity = row_id or stable_digest(
            {field: value.to_dict() for field, value in normalized.items()},
            prefix="analyticsrow_",
        )
        return cls(identity, normalized)

    def to_dict(self, fields: Sequence[str] | None = None) -> dict[str, Any]:
        selected = tuple(_FIELD_SPECS) if fields is None else tuple(fields)
        return {
            "row_id": self.row_id,
            "schema_version": self.schema_version,
            "values": {field: self.values[field].to_dict() for field in selected},
        }

    @classmethod
    def from_mapping(cls, value: Any) -> "AnalyticsQueryRow":
        if not isinstance(value, Mapping):
            raise ValueError("analytics row must be a mapping")
        _exact_keys(value, {"row_id", "schema_version", "values"}, "analytics row")
        values = value.get("values")
        if not isinstance(values, Mapping):
            raise ValueError("analytics row values must be a mapping")
        return cls(
            row_id=value.get("row_id"),
            values={
                key: AnalyticsValue.from_mapping(item) for key, item in values.items()
            },
            schema_version=value.get("schema_version"),
        )


def analytics_row_from_aggregation(
    record: AggregationRecord,
    *,
    dimensions: Mapping[str, AnalyticsValue | Any] | None = None,
) -> AnalyticsQueryRow:
    if not isinstance(record, AggregationRecord):
        raise TypeError("record must be an AggregationRecord")
    supplied = dict(dimensions or {})
    protected = {
        "run",
        "route",
        "experiment",
        "evaluator",
        "success",
        "score",
        "time",
        "target_board",
        "action_count",
        "resource_consumption",
        "state_hash",
        "version",
    }
    overlap = protected & set(supplied)
    if overlap:
        raise ValueError(
            f"dimensions cannot replace aggregation fields: {sorted(overlap)}"
        )
    supplied.update(
        {
            "run": record.run_id,
            "route": record.route_id,
            "experiment": record.experiment_id,
            "evaluator": record.evaluator_id,
            "success": record.success,
            "score": record.score,
            "time": record.run_date,
            "version": record.evaluator_version,
            "target_board": record.target_board,
            "action_count": record.action_count,
            "resource_consumption": (
                AnalyticsValue.missing()
                if record.resource_consumption is None
                else record.resource_consumption
            ),
            "state_hash": record.state_hash,
        }
    )
    return AnalyticsQueryRow.build(supplied, row_id=record.record_id)


@dataclass(frozen=True)
class AnalyticsSnapshot:
    rows: tuple[AnalyticsQueryRow, ...]
    source_ids: tuple[str, ...] = ()
    schema_version: str = ANALYTICS_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported analytics snapshot schema")
        source_rows = tuple(self.rows)
        if any(not isinstance(row, AnalyticsQueryRow) for row in source_rows):
            raise ValueError("snapshot rows must be AnalyticsQueryRow values")
        rows = tuple(sorted(source_rows, key=lambda item: item.row_id))
        if len({row.row_id for row in rows}) != len(rows):
            raise ValueError("analytics snapshot contains duplicate row IDs")
        sources = tuple(sorted(self.source_ids))
        if len(set(sources)) != len(sources):
            raise ValueError("analytics snapshot contains duplicate source IDs")
        for source_id in sources:
            _non_empty_string(source_id, "source_id")
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "source_ids", sources)

    @property
    def snapshot_id(self) -> str:
        return stable_digest(
            {
                "rows": [row.to_dict() for row in self.rows],
                "schema_version": self.schema_version,
                "source_ids": list(self.source_ids),
            },
            prefix="analyticssnapshot_",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [row.to_dict() for row in self.rows],
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_mapping(cls, value: Any) -> "AnalyticsSnapshot":
        if not isinstance(value, Mapping):
            raise ValueError("analytics snapshot must be a mapping")
        _exact_keys(
            value,
            {"rows", "schema_version", "snapshot_id", "source_ids"},
            "analytics snapshot",
        )
        snapshot = cls(
            rows=tuple(
                AnalyticsQueryRow.from_mapping(item)
                for item in _sequence(value.get("rows"), "snapshot rows")
            ),
            source_ids=tuple(
                _non_empty_string(item, "source_id")
                for item in _sequence(value.get("source_ids"), "snapshot source_ids")
            ),
            schema_version=value.get("schema_version"),
        )
        if value.get("snapshot_id") != snapshot.snapshot_id:
            raise ValueError("analytics snapshot_id does not match its content")
        return snapshot


class AnalyticsSnapshotStore:
    def __init__(self) -> None:
        self._snapshots: dict[str, AnalyticsSnapshot] = {}
        self._current_id: str | None = None
        self._lock = threading.RLock()

    def register(
        self, snapshot: AnalyticsSnapshot, *, make_current: bool = True
    ) -> str:
        if not isinstance(snapshot, AnalyticsSnapshot):
            raise TypeError("snapshot must be an AnalyticsSnapshot")
        snapshot_id = snapshot.snapshot_id
        with self._lock:
            self._snapshots.setdefault(snapshot_id, snapshot)
            if make_current:
                self._current_id = snapshot_id
        return snapshot_id

    def get(self, snapshot_id: str) -> AnalyticsSnapshot | None:
        with self._lock:
            return self._snapshots.get(snapshot_id)

    def current(self) -> AnalyticsSnapshot | None:
        with self._lock:
            if self._current_id is None:
                return None
            return self._snapshots[self._current_id]


@dataclass(frozen=True)
class AnalyticsFilter:
    field: str
    operator: str
    value: Any

    def __post_init__(self) -> None:
        _non_empty_string(self.field, "filter field")
        _non_empty_string(self.operator, "filter operator")
        if self.field not in _FIELD_SPECS:
            raise ValueError(f"unsupported filter field {self.field!r}")
        spec = _FIELD_SPECS[self.field]
        if self.operator not in spec.filter_operators:
            raise ValueError(
                f"operator {self.operator!r} is not supported for {self.field!r}"
            )
        normalized = _validate_filter_operand(self.field, self.operator, self.value)
        object.__setattr__(self, "value", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator,
            "value": to_canonical_data(self.value),
        }

    @classmethod
    def from_mapping(cls, value: Any) -> "AnalyticsFilter":
        if not isinstance(value, Mapping):
            raise ValueError("filter must be a mapping")
        _exact_keys(value, {"field", "operator", "value"}, "filter")
        return cls(value.get("field"), value.get("operator"), value.get("value"))


def _validate_filter_operand(field: str, operator: str, value: Any) -> Any:
    if operator == "state_is":
        return AnalyticsValueState(value).value
    if operator in {"in", "contains_any", "contains_all"}:
        items = tuple(_sequence(value, f"filter {operator}"))
        if not items or len(items) > MAX_FILTER_LIST_ITEMS:
            raise ValueError(
                f"filter {operator} requires 1..{MAX_FILTER_LIST_ITEMS} items"
            )
        normalized = [_validate_filter_scalar(field, item) for item in items]
        if len({canonical_json(item) for item in normalized}) != len(normalized):
            raise ValueError(f"filter {operator} must not contain duplicates")
        return tuple(normalized)
    if operator == "between":
        items = tuple(_sequence(value, "filter between"))
        if len(items) != 2:
            raise ValueError("filter between requires exactly two bounds")
        lower = _validate_filter_scalar(field, items[0])
        upper = _validate_filter_scalar(field, items[1])
        if _comparable_value(field, lower) > _comparable_value(field, upper):
            raise ValueError("filter between lower bound must not exceed upper bound")
        return (lower, upper)
    return _validate_filter_scalar(field, value)


def _validate_filter_scalar(field: str, value: Any) -> Any:
    value_type = _FIELD_SPECS[field].value_type
    if value_type in {"string", "timestamp", "string_list"}:
        parsed = _non_empty_string(value, f"filter {field}")
        if value_type == "timestamp":
            _validate_field_value(field, AnalyticsValue.present(parsed))
        return parsed
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"filter {field} must be boolean")
        return value
    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"filter {field} must be an integer")
        return value
    if value_type == "number":
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            raise ValueError(f"filter {field} must be a finite number")
        return float(value)
    raise AssertionError(f"unsupported field type {value_type}")


@dataclass(frozen=True)
class AnalyticsSort:
    field: str
    direction: str = "asc"

    def __post_init__(self) -> None:
        _non_empty_string(self.field, "sort field")
        _non_empty_string(self.direction, "sort direction")
        if self.field not in _FIELD_SPECS or not _FIELD_SPECS[self.field].sortable:
            raise ValueError(f"field {self.field!r} is not sortable")
        if self.direction not in {"asc", "desc"}:
            raise ValueError("sort direction must be asc or desc")

    def to_dict(self) -> dict[str, str]:
        return {"direction": self.direction, "field": self.field}

    @classmethod
    def from_mapping(cls, value: Any) -> "AnalyticsSort":
        if not isinstance(value, Mapping):
            raise ValueError("sort must be a mapping")
        _exact_keys(value, {"direction", "field"}, "sort")
        return cls(value.get("field"), value.get("direction"))


@dataclass(frozen=True)
class AnalyticsQueryRequest:
    fields: tuple[str, ...]
    filters: tuple[AnalyticsFilter, ...] = ()
    sort: tuple[AnalyticsSort, ...] = ()
    limit: int = DEFAULT_QUERY_LIMIT
    cursor: str | None = None
    snapshot_id: str | None = None
    schema_version: str = ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported analytics query request schema")
        fields = tuple(self.fields)
        filters = tuple(self.filters)
        sorts = tuple(self.sort)
        if not fields or len(fields) > MAX_QUERY_FIELDS:
            raise ValueError(f"fields must contain 1..{MAX_QUERY_FIELDS} items")
        if len(fields) != len(set(fields)) or any(
            field not in _FIELD_SPECS for field in fields
        ):
            raise ValueError("fields must be unique supported field names")
        if len(filters) > MAX_QUERY_FILTERS:
            raise ValueError(f"at most {MAX_QUERY_FILTERS} filters are supported")
        if any(not isinstance(item, AnalyticsFilter) for item in filters):
            raise ValueError("filters must contain AnalyticsFilter values")
        if len(sorts) > MAX_QUERY_SORTS:
            raise ValueError(f"at most {MAX_QUERY_SORTS} sorts are supported")
        if any(not isinstance(item, AnalyticsSort) for item in sorts):
            raise ValueError("sort must contain AnalyticsSort values")
        if len({item.field for item in sorts}) != len(sorts):
            raise ValueError("sort fields must be unique")
        if not isinstance(self.limit, int) or isinstance(self.limit, bool):
            raise ValueError("limit must be an integer")
        if self.limit < 1 or self.limit > MAX_QUERY_LIMIT:
            raise ValueError(f"limit must be in 1..{MAX_QUERY_LIMIT}")
        if self.cursor is not None:
            _non_empty_string(self.cursor, "cursor")
        if self.snapshot_id is not None:
            _non_empty_string(self.snapshot_id, "snapshot_id")
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "filters", filters)
        object.__setattr__(self, "sort", sorts)

    @property
    def fingerprint(self) -> str:
        return stable_digest(self.query_identity(), prefix="analyticsquery_")

    def query_identity(self) -> dict[str, Any]:
        return {
            "fields": list(self.fields),
            "filters": [item.to_dict() for item in self.filters],
            "limit": self.limit,
            "schema_version": self.schema_version,
            "sort": [item.to_dict() for item in self.sort],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.query_identity(),
            "cursor": self.cursor,
            "snapshot_id": self.snapshot_id,
        }

    @classmethod
    def from_mapping(cls, value: Any) -> "AnalyticsQueryRequest":
        if not isinstance(value, Mapping):
            raise ValueError("query request must be a mapping")
        _exact_keys(
            value,
            {
                "cursor",
                "fields",
                "filters",
                "limit",
                "schema_version",
                "snapshot_id",
                "sort",
            },
            "query request",
        )
        return cls(
            fields=tuple(_sequence(value.get("fields"), "fields")),
            filters=tuple(
                AnalyticsFilter.from_mapping(item)
                for item in _sequence(value.get("filters"), "filters")
            ),
            sort=tuple(
                AnalyticsSort.from_mapping(item)
                for item in _sequence(value.get("sort"), "sort")
            ),
            limit=value.get("limit"),
            cursor=value.get("cursor"),
            snapshot_id=value.get("snapshot_id"),
            schema_version=value.get("schema_version"),
        )


class AnalyticsQueryError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        async_job_required: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = _non_empty_string(code, "code")
        self.message = _non_empty_string(message, "message")
        self.async_job_required = async_job_required
        self.details = to_canonical_data(dict(details or {}))
        self.schema_version = ANALYTICS_QUERY_ERROR_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "async_job_required": self.async_job_required,
            "code": self.code,
            "details": self.details,
            "message": self.message,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class AnalyticsQueryResponse:
    snapshot_id: str
    request_fingerprint: str
    rows: tuple[Mapping[str, Any], ...]
    matched_rows: int
    scanned_rows: int
    next_cursor: str | None
    schema_version: str = ANALYTICS_QUERY_RESPONSE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "matched_rows": self.matched_rows,
                "next_cursor": self.next_cursor,
                "request_fingerprint": self.request_fingerprint,
                "rows": list(self.rows),
                "scanned_rows": self.scanned_rows,
                "schema_version": self.schema_version,
                "snapshot_id": self.snapshot_id,
            }
        )


def _cursor_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _encode_cursor(payload: Mapping[str, Any]) -> str:
    envelope = {"digest": _cursor_digest(payload), "payload": payload}
    encoded = base64.urlsafe_b64encode(canonical_json(envelope).encode("utf-8"))
    return encoded.decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> Mapping[str, Any]:
    try:
        padding = "=" * (-len(value) % 4)
        envelope = json.loads(base64.urlsafe_b64decode(value + padding).decode("utf-8"))
        if not isinstance(envelope, Mapping):
            raise ValueError
        _exact_keys(envelope, {"digest", "payload"}, "cursor envelope")
        payload = envelope["payload"]
        if not isinstance(payload, Mapping):
            raise ValueError
        if envelope["digest"] != _cursor_digest(payload):
            raise ValueError
        _exact_keys(
            payload,
            {
                "last_row_id",
                "request_fingerprint",
                "schema_version",
                "snapshot_id",
                "sort_values",
            },
            "cursor payload",
        )
        if payload["schema_version"] != ANALYTICS_CURSOR_SCHEMA_VERSION:
            raise ValueError
        _non_empty_string(payload["last_row_id"], "last_row_id")
        _non_empty_string(payload["request_fingerprint"], "request_fingerprint")
        _non_empty_string(payload["snapshot_id"], "snapshot_id")
        _sequence(payload["sort_values"], "sort_values")
        return payload
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise AnalyticsQueryError(
            "invalid_cursor", "cursor is malformed or has been modified"
        ) from exc


_STATE_ORDER = {state: index for index, state in enumerate(AnalyticsValueState)}


def _timestamp_value(value: str) -> datetime:
    if "T" not in value:
        return datetime.combine(date.fromisoformat(value), time(), timezone.utc)
    if not value.endswith("Z"):
        raise ValueError("timestamp values with time must use UTC Z suffix")
    timestamp = value[:-1]
    if "." in timestamp:
        whole, fraction = timestamp.rsplit(".", 1)
        if not fraction.isdigit() or len(fraction) > 6:
            raise ValueError("timestamp fraction must contain 1..6 digits")
        timestamp = f"{whole}.{fraction.ljust(6, '0')}"
    parsed = datetime.fromisoformat(timestamp + "+00:00")
    return parsed.astimezone(timezone.utc)


def _comparable_value(field: str, value: Any) -> Any:
    if _FIELD_SPECS[field].value_type == "timestamp":
        return _timestamp_value(value)
    return value


def _sort_token(field: str, value: AnalyticsValue) -> tuple[Any, ...]:
    state_order = _STATE_ORDER[value.state]
    if value.state not in {AnalyticsValueState.VALUE, AnalyticsValueState.EMPTY}:
        return (state_order, 0, "")
    raw = value.value
    if isinstance(raw, bool):
        return (state_order, 0, int(raw))
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return (state_order, 1, float(raw))
    if _FIELD_SPECS[field].value_type == "timestamp":
        return (state_order, 2, _timestamp_value(raw))
    if isinstance(raw, str):
        return (state_order, 2, raw)
    return (state_order, 3, canonical_json(_thaw_json_value(raw)))


def _compare_rows(
    left: AnalyticsQueryRow,
    right: AnalyticsQueryRow,
    sorts: tuple[AnalyticsSort, ...],
) -> int:
    for sort in sorts:
        left_value = _sort_token(sort.field, left.values[sort.field])
        right_value = _sort_token(sort.field, right.values[sort.field])
        if left_value != right_value:
            result = -1 if left_value < right_value else 1
            return result if sort.direction == "asc" else -result
    return (left.row_id > right.row_id) - (left.row_id < right.row_id)


def _matches(row: AnalyticsQueryRow, item: AnalyticsFilter) -> bool:
    value = row.values[item.field]
    if item.operator == "state_is":
        return value.state.value == item.value
    if value.state != AnalyticsValueState.VALUE:
        return False
    observed = value.value
    if item.operator == "eq":
        return _comparable_value(item.field, observed) == _comparable_value(
            item.field, item.value
        )
    if item.operator == "in":
        comparable = _comparable_value(item.field, observed)
        return any(
            comparable == _comparable_value(item.field, candidate)
            for candidate in item.value
        )
    if item.operator == "gte":
        return _comparable_value(item.field, observed) >= _comparable_value(
            item.field, item.value
        )
    if item.operator == "lte":
        return _comparable_value(item.field, observed) <= _comparable_value(
            item.field, item.value
        )
    if item.operator == "between":
        comparable = _comparable_value(item.field, observed)
        return (
            _comparable_value(item.field, item.value[0])
            <= comparable
            <= _comparable_value(item.field, item.value[1])
        )
    if item.operator == "contains":
        return item.value in observed
    if item.operator == "contains_any":
        return any(candidate in observed for candidate in item.value)
    if item.operator == "contains_all":
        return all(candidate in observed for candidate in item.value)
    raise AssertionError(f"unsupported filter operator {item.operator}")


class AnalyticsQueryService:
    def __init__(
        self,
        snapshots: AnalyticsSnapshotStore,
        *,
        max_sync_scan_rows: int = DEFAULT_MAX_SYNC_SCAN_ROWS,
    ) -> None:
        if (
            not isinstance(max_sync_scan_rows, int)
            or isinstance(max_sync_scan_rows, bool)
            or max_sync_scan_rows < 1
        ):
            raise ValueError("max_sync_scan_rows must be an integer >= 1")
        self.snapshots = snapshots
        self.max_sync_scan_rows = max_sync_scan_rows

    def execute(self, request: AnalyticsQueryRequest) -> AnalyticsQueryResponse:
        if not isinstance(request, AnalyticsQueryRequest):
            raise TypeError("request must be an AnalyticsQueryRequest")
        cursor = _decode_cursor(request.cursor) if request.cursor else None
        cursor_snapshot_id = cursor["snapshot_id"] if cursor else None
        if (
            cursor_snapshot_id is not None
            and request.snapshot_id is not None
            and request.snapshot_id != cursor_snapshot_id
        ):
            raise AnalyticsQueryError(
                "cursor_snapshot_mismatch",
                "cursor and request refer to different snapshots",
            )
        snapshot = self._resolve_snapshot(request.snapshot_id or cursor_snapshot_id)
        snapshot_id = snapshot.snapshot_id
        if cursor and cursor["request_fingerprint"] != request.fingerprint:
            raise AnalyticsQueryError(
                "cursor_query_mismatch",
                "cursor cannot be reused with changed fields, filters, sort, or limit",
            )
        if len(snapshot.rows) > self.max_sync_scan_rows:
            raise AnalyticsQueryError(
                "sync_scan_limit_exceeded",
                "query must be submitted as an asynchronous export job",
                async_job_required=True,
                details={
                    "max_sync_scan_rows": self.max_sync_scan_rows,
                    "query_snapshot_id": snapshot_id,
                    "scanned_rows": len(snapshot.rows),
                    "suggested_job_kind": "export",
                },
            )
        rows = self._select_rows(snapshot, request)
        start = 0
        if cursor:
            start = self._cursor_start(rows, request, cursor)
        page = rows[start : start + request.limit]
        has_more = start + len(page) < len(rows)
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = _encode_cursor(
                {
                    "last_row_id": last.row_id,
                    "request_fingerprint": request.fingerprint,
                    "schema_version": ANALYTICS_CURSOR_SCHEMA_VERSION,
                    "snapshot_id": snapshot_id,
                    "sort_values": [
                        last.values[item.field].to_dict() for item in request.sort
                    ],
                }
            )
        return AnalyticsQueryResponse(
            snapshot_id=snapshot_id,
            request_fingerprint=request.fingerprint,
            rows=tuple(row.to_dict(request.fields) for row in page),
            matched_rows=len(rows),
            scanned_rows=len(snapshot.rows),
            next_cursor=next_cursor,
        )

    def bind_snapshot(self, request: AnalyticsQueryRequest) -> AnalyticsQueryRequest:
        if not isinstance(request, AnalyticsQueryRequest):
            raise TypeError("request must be an AnalyticsQueryRequest")
        if request.cursor is not None:
            raise AnalyticsQueryError(
                "export_cursor_forbidden",
                "an export request must start at the beginning of its snapshot",
            )
        snapshot = self._resolve_snapshot(request.snapshot_id)
        return replace(request, snapshot_id=snapshot.snapshot_id)

    def select_for_export(
        self,
        request: AnalyticsQueryRequest,
        *,
        max_scan_rows: int,
        max_output_rows: int,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> tuple[AnalyticsQueryRequest, AnalyticsSnapshot, tuple[dict[str, Any], ...]]:
        if (
            not isinstance(max_scan_rows, int)
            or isinstance(max_scan_rows, bool)
            or max_scan_rows < 1
        ):
            raise ValueError("max_scan_rows must be an integer >= 1")
        if (
            not isinstance(max_output_rows, int)
            or isinstance(max_output_rows, bool)
            or max_output_rows < 1
        ):
            raise ValueError("max_output_rows must be an integer >= 1")
        bound = self.bind_snapshot(request)
        snapshot = self._resolve_snapshot(bound.snapshot_id)
        if len(snapshot.rows) > max_scan_rows:
            raise AnalyticsQueryError(
                "export_scan_limit_exceeded",
                "export source exceeds the configured scan limit",
                async_job_required=True,
                details={
                    "max_scan_rows": max_scan_rows,
                    "query_snapshot_id": snapshot.snapshot_id,
                    "scanned_rows": len(snapshot.rows),
                },
            )
        rows = self._select_rows(snapshot, bound, cancel_requested=cancel_requested)
        if len(rows) > max_output_rows:
            raise AnalyticsQueryError(
                "export_row_limit_exceeded",
                "export result exceeds the configured row limit",
                async_job_required=True,
                details={
                    "matched_rows": len(rows),
                    "max_output_rows": max_output_rows,
                    "query_snapshot_id": snapshot.snapshot_id,
                },
            )
        return (
            bound,
            snapshot,
            tuple(row.to_dict(bound.fields) for row in rows),
        )

    def _resolve_snapshot(self, snapshot_id: str | None) -> AnalyticsSnapshot:
        snapshot = (
            self.snapshots.get(snapshot_id)
            if snapshot_id is not None
            else self.snapshots.current()
        )
        if snapshot is None:
            raise AnalyticsQueryError(
                "snapshot_unavailable",
                "requested analytics snapshot is not available",
                details={"snapshot_id": snapshot_id},
            )
        return snapshot

    @staticmethod
    def _select_rows(
        snapshot: AnalyticsSnapshot,
        request: AnalyticsQueryRequest,
        *,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> list[AnalyticsQueryRow]:
        rows: list[AnalyticsQueryRow] = []
        for index, row in enumerate(snapshot.rows):
            if index % 512 == 0 and cancel_requested():
                raise InterruptedError("analytics export was cancelled")
            if all(_matches(row, item) for item in request.filters):
                rows.append(row)
        rows.sort(
            key=cmp_to_key(lambda left, right: _compare_rows(left, right, request.sort))
        )
        return rows

    @staticmethod
    def _cursor_start(
        rows: Sequence[AnalyticsQueryRow],
        request: AnalyticsQueryRequest,
        cursor: Mapping[str, Any],
    ) -> int:
        expected_values = cursor["sort_values"]
        if len(expected_values) != len(request.sort):
            raise AnalyticsQueryError(
                "invalid_cursor", "cursor sort shape does not match the query"
            )
        for index, row in enumerate(rows):
            if row.row_id != cursor["last_row_id"]:
                continue
            observed = [row.values[item.field].to_dict() for item in request.sort]
            if observed != expected_values:
                raise AnalyticsQueryError(
                    "invalid_cursor", "cursor sort position does not match its row"
                )
            return index + 1
        raise AnalyticsQueryError(
            "cursor_position_unavailable",
            "cursor position is not present in its bound snapshot and query",
        )


def analytics_query_contract_document() -> dict[str, Any]:
    value_states = {
        "value": "observed non-null value",
        "empty": "observed empty string, list, or object",
        "missing": "field was absent from the source schema or artifact",
        "unknown": "source represented the field but could not determine it",
        "redacted": "value was withheld by the information policy",
        "not_applicable": "field does not apply to this row",
        "quarantined": "source value is retained only as untrusted evidence",
    }
    field_document = {
        name: {
            "filter_operators": list(spec.filter_operators),
            "sortable": spec.sortable,
            "value_type": spec.value_type,
        }
        for name, spec in _FIELD_SPECS.items()
    }
    return to_canonical_data(
        {
            "consistency": {
                "concurrent_ingest": "a new ingest creates a new immutable snapshot",
                "cursor_reuse": "idempotent while the referenced snapshot is retained",
                "response_series": "all pages remain bound to the cursor snapshot",
            },
            "cursor": {
                "opaque": True,
                "schema_version": ANALYTICS_CURSOR_SCHEMA_VERSION,
                "tie_breaker": "row_id ascending",
                "validates": [
                    "checksum",
                    "request_fingerprint",
                    "snapshot_id",
                    "last_row_id",
                    "sort_values",
                ],
            },
            "fields": field_document,
            "limits": {
                "default_limit": DEFAULT_QUERY_LIMIT,
                "default_max_sync_scan_rows": DEFAULT_MAX_SYNC_SCAN_ROWS,
                "max_fields": MAX_QUERY_FIELDS,
                "max_filter_list_items": MAX_FILTER_LIST_ITEMS,
                "max_filters": MAX_QUERY_FILTERS,
                "max_limit": MAX_QUERY_LIMIT,
                "max_sorts": MAX_QUERY_SORTS,
            },
            "schemas": {
                "error": {
                    "required": [
                        "async_job_required",
                        "code",
                        "details",
                        "message",
                        "schema_version",
                    ],
                    "schema_version": ANALYTICS_QUERY_ERROR_SCHEMA_VERSION,
                    "type": "object",
                },
                "request": {
                    "required": [
                        "cursor",
                        "fields",
                        "filters",
                        "limit",
                        "schema_version",
                        "snapshot_id",
                        "sort",
                    ],
                    "schema_version": ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION,
                    "type": "object",
                },
                "response": {
                    "required": [
                        "matched_rows",
                        "next_cursor",
                        "request_fingerprint",
                        "rows",
                        "scanned_rows",
                        "schema_version",
                        "snapshot_id",
                    ],
                    "schema_version": ANALYTICS_QUERY_RESPONSE_SCHEMA_VERSION,
                    "type": "object",
                },
                "row": {
                    "schema_version": ANALYTICS_QUERY_ROW_SCHEMA_VERSION,
                    "type": "object",
                },
                "snapshot": {
                    "schema_version": ANALYTICS_SNAPSHOT_SCHEMA_VERSION,
                    "type": "object",
                },
                "value": {
                    "schema_version": ANALYTICS_QUERY_VALUE_SCHEMA_VERSION,
                    "states": value_states,
                    "type": "object",
                },
            },
            "sync_scan_policy": {
                "fallback_job_kind": "export",
                "rule": "reject when snapshot row count exceeds max_sync_scan_rows",
            },
            "version": ANALYTICS_QUERY_CONTRACT_VERSION,
        }
    )
