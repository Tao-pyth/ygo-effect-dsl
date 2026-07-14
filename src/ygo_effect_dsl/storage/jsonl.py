from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data


RAW_EVENT_LOG_SCHEMA_VERSION = "raw-event-log-v1"


@dataclass(frozen=True)
class RawLogRecord:
    run_id: str
    sequence: int
    event_type: str
    payload: Mapping[str, Any]
    schema_version: str = RAW_EVENT_LOG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("run_id", "event_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload must be a mapping")
        if self.schema_version != RAW_EVENT_LOG_SCHEMA_VERSION:
            raise ValueError("unsupported raw event log schema")

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "event_type": self.event_type,
                "payload": self.payload,
                "run_id": self.run_id,
                "schema_version": self.schema_version,
                "sequence": self.sequence,
            }
        )
        return {**identity, "record_id": stable_digest(identity, prefix="log_")}

    @classmethod
    def from_dict(cls, value: Any) -> "RawLogRecord":
        if not isinstance(value, Mapping):
            raise ValueError("raw log record must be a mapping")
        record = cls(
            run_id=value.get("run_id"),
            sequence=value.get("sequence"),
            event_type=value.get("event_type"),
            payload=value.get("payload"),
            schema_version=value.get("schema_version"),
        )
        if record.to_dict() != to_canonical_data(value):
            raise ValueError("raw log record_id does not match its content")
        return record


def _validate_order(records: tuple[RawLogRecord, ...]) -> None:
    if not records:
        return
    run_id = records[0].run_id
    for expected, record in enumerate(records):
        if record.run_id != run_id:
            raise ValueError("one raw log file must contain exactly one run_id")
        if record.sequence != expected:
            raise ValueError(f"raw log sequence must be contiguous from 0; expected {expected}")


def write_raw_log(path: str | Path, records: Iterable[RawLogRecord]) -> None:
    destination = Path(path)
    ordered = tuple(records)
    _validate_order(ordered)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    text = "".join(canonical_json(record.to_dict()) + "\n" for record in ordered)
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(destination)


def read_raw_log(path: str | Path) -> tuple[RawLogRecord, ...]:
    source = Path(path)
    records: list[RawLogRecord] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"raw log line {line_number} must not be empty")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"raw log line {line_number} is invalid JSON") from exc
        records.append(RawLogRecord.from_dict(value))
    result = tuple(records)
    _validate_order(result)
    return result
