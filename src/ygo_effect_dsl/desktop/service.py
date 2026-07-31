from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
from typing import Any, Protocol

import yaml

from ygo_effect_dsl.desktop.bridge import DesktopHandler, DesktopServiceError
from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.engine.evaluation import (
    RouteRankingPolicy,
    TerminalPreferenceProfile,
    TerminalPreferenceProfileCatalog,
    build_terminal_board_projection,
    build_route_randomness_summary,
    evaluate_terminal_preferences,
    rank_route_candidates,
)
from ygo_effect_dsl.engine.information import InformationAccessPolicy
from ygo_effect_dsl.engine.search import strategy_from_experiment
from ygo_effect_dsl.experiment.schema import assert_valid_experiment
from ygo_effect_dsl.experiment.scenario import parse_ydk, preflight_scenario
from ygo_effect_dsl.presentation import CardPresentationQuery
from ygo_effect_dsl.presentation.cards import CARD_PRESENTATION_QUERY_VERSION
from ygo_effect_dsl.storage.export import (
    AnalyticsExportFormat,
    AnalyticsExportQueue,
    AnalyticsExportRequest,
    AnalyticsExportService,
    AnalyticsExportSourceKind,
    AnalyticsExportWorker,
)
from ygo_effect_dsl.storage.jobs import (
    JobCatalog,
    JobKind,
    JobRetryPolicy,
    JobSpec,
    JobState,
)
from ygo_effect_dsl.storage.query import (
    AnalyticsQueryRequest,
    AnalyticsQueryService,
    AnalyticsSnapshot,
    AnalyticsSnapshotStore,
)
from ygo_effect_dsl.version import __version__

DESKTOP_DECK_CATALOG_VERSION = "desktop-deck-catalog-v1"
DESKTOP_DECK_METADATA_CATALOG_VERSION = "desktop-deck-metadata-catalog-v1"
DESKTOP_DECK_TERMINAL_PROFILE_CATALOG_VERSION = (
    "desktop-deck-terminal-profile-catalog-v1"
)
DESKTOP_SERVICE_VERSION = "desktop-application-service-v1"
DESKTOP_RESULT_VIEW_VERSION = "desktop-result-view-v1"
MAX_CATALOG_DECKS = 10_000
MAX_DESKTOP_SEARCH_NODES = 100_000
MAX_DESKTOP_SEARCH_DEPTH = 256
MAX_DESKTOP_SEARCH_SECONDS = 3_600.0
MAX_DESKTOP_SEARCH_POOL_SIZE = 8
DEFAULT_SCENARIO_PRESET_ID = "terminal_board_min_monster_v1"
CANDIDATE_COUNT_STATUSES = (
    "explored",
    "unexplored",
    "pruned",
    "failed",
    "censored",
)
DESKTOP_SCENARIO_PRESETS: dict[str, dict[str, Any]] = {
    DEFAULT_SCENARIO_PRESET_ID: {
        "evaluate_at": "legal_stop",
        "evaluator": {
            "config": {
                "hand_weight": 1,
                "missing_value_policy": "error",
                "monster_weight": 10,
                "temporary_value_policy": "exclude_expired_or_unverified_v1",
            },
            "id": "real_core_board_count",
            "version": "1",
        },
        "objective": "maximize_terminal_board",
        "success_predicate": {
            "config": {"min_count": 1, "player": 0, "zone": "monster_zone"},
            "id": "real_core_min_monster_count",
            "version": "1",
        },
    }
}


class YdkPicker(Protocol):
    def __call__(self) -> str | Path | None: ...


class CardProvider(Protocol):
    def get_card(self, query: CardPresentationQuery) -> Any: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_empty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DesktopServiceError(
            "invalid_method_payload",
            f"{field} must be a non-empty string",
            path=f"$.payload.{field}",
        )
    return value.strip()


def _tags(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DesktopServiceError(
            "invalid_method_payload",
            f"{field} must be a tag list",
            path=f"$.payload.{field}",
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for index, tag in enumerate(value):
        if not isinstance(tag, str):
            raise DesktopServiceError(
                "invalid_method_payload",
                "tags must contain strings",
                path=f"$.payload.{field}[{index}]",
            )
        clean = tag.strip()
        if not clean:
            continue
        if len(clean) > 32:
            raise DesktopServiceError(
                "invalid_deck_tags",
                "deck tags must contain at most 32 characters",
                path=f"$.payload.{field}[{index}]",
            )
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(clean)
    if len(normalized) > 12:
        raise DesktopServiceError(
            "invalid_deck_tags",
            "a desktop deck can have at most 12 tags",
            path=f"$.payload.{field}",
        )
    return tuple(normalized)


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _exact(payload: Mapping[str, Any], expected: set[str], method: str) -> None:
    if set(payload) != expected:
        raise DesktopServiceError(
            "invalid_method_payload",
            f"{method} payload fields must be exactly {sorted(expected)}",
        )


def _coverage_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DesktopServiceError(
            "artifact_schema_mismatch",
            f"search report coverage {field} must be a non-negative integer",
        )
    return value


def _validate_coverage_certificate(coverage: Mapping[str, Any]) -> None:
    if coverage.get("schema_version") != "search-coverage-v1":
        raise DesktopServiceError(
            "artifact_schema_mismatch",
            "search report coverage certificate schema_version is invalid",
        )
    coverage_status = coverage.get("coverage_status")
    frontier_exhausted = coverage.get("frontier_exhausted")
    if not isinstance(frontier_exhausted, bool):
        raise DesktopServiceError(
            "artifact_schema_mismatch",
            "search report coverage frontier_exhausted must be boolean",
        )
    expected_status = "frontier_exhausted" if frontier_exhausted else "best_observed"
    if coverage_status != expected_status:
        raise DesktopServiceError(
            "artifact_identity_mismatch",
            "search report coverage status does not match frontier exhaustion",
        )
    counts = coverage.get("candidate_counts")
    if not isinstance(counts, Mapping):
        raise DesktopServiceError(
            "artifact_schema_mismatch",
            "search report coverage candidate_counts must be an object",
        )
    unexplored = _coverage_int(counts.get("unexplored"), "candidate_counts.unexplored")
    censored = _coverage_int(counts.get("censored"), "candidate_counts.censored")
    pruned = _coverage_int(counts.get("pruned"), "candidate_counts.pruned")
    pending_frontier = _coverage_int(
        coverage.get("pending_frontier_count"),
        "pending_frontier_count",
    )
    unknown_candidates = _coverage_int(
        coverage.get("unknown_candidate_count"),
        "unknown_candidate_count",
    )
    if pending_frontier != unexplored:
        raise DesktopServiceError(
            "artifact_identity_mismatch",
            "search report coverage pending frontier does not match candidate counts",
        )
    if frontier_exhausted:
        if coverage.get("candidate_accounting_complete") is not True:
            raise DesktopServiceError(
                "artifact_identity_mismatch",
                "frontier exhausted requires complete candidate accounting",
            )
        if coverage.get("termination_reason") != "frontier_exhausted":
            raise DesktopServiceError(
                "artifact_identity_mismatch",
                "frontier exhausted requires frontier_exhausted termination",
            )
        if pending_frontier or unknown_candidates or unexplored or censored or pruned:
            raise DesktopServiceError(
                "artifact_identity_mismatch",
                "frontier exhausted requires zero pending, unknown, censored, and pruned candidates",
            )


def _candidate_counts_from_records(candidates: Sequence[Any]) -> dict[str, int]:
    counts = {status: 0 for status in CANDIDATE_COUNT_STATUSES}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise DesktopServiceError(
                "artifact_schema_mismatch",
                f"search report candidate evidence candidates[{index}] must be an object",
            )
        status = candidate.get("status")
        if status not in counts:
            raise DesktopServiceError(
                "artifact_schema_mismatch",
                f"search report candidate evidence candidates[{index}].status is invalid",
            )
        counts[status] += 1
    counts["total"] = len(candidates)
    return counts


def _candidate_counts_from_mapping(counts: Mapping[str, Any], field: str) -> dict[str, int]:
    parsed = {
        status: _coverage_int(counts.get(status), f"{field}.{status}")
        for status in CANDIDATE_COUNT_STATUSES
    }
    parsed["total"] = _coverage_int(counts.get("total"), f"{field}.total")
    return parsed


def _validate_candidate_evidence(search_evidence: Mapping[str, Any]) -> dict[str, int]:
    if search_evidence.get("schema_version") != "search-candidate-evidence-v1":
        raise DesktopServiceError(
            "artifact_schema_mismatch",
            "search report candidate evidence schema_version is invalid",
        )
    candidates = search_evidence.get("candidates")
    if not isinstance(candidates, list):
        raise DesktopServiceError(
            "artifact_schema_mismatch",
            "search report candidate evidence candidates must be a list",
        )
    raw_counts = search_evidence.get("candidate_counts")
    if not isinstance(raw_counts, Mapping):
        raise DesktopServiceError(
            "artifact_schema_mismatch",
            "search report candidate evidence candidate_counts must be an object",
        )
    declared_counts = _candidate_counts_from_mapping(
        raw_counts,
        "candidate_counts",
    )
    observed_counts = _candidate_counts_from_records(candidates)
    if declared_counts != observed_counts:
        raise DesktopServiceError(
            "artifact_identity_mismatch",
            "search report candidate evidence counts do not match candidate records",
        )
    return declared_counts


def _cards(value: Any, field: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DesktopServiceError(
            "invalid_deck_section",
            f"{field} must be a card-code list",
            path=f"$.payload.{field}",
        )
    result: list[int] = []
    for index, code in enumerate(value):
        if not isinstance(code, int) or isinstance(code, bool) or code <= 0:
            raise DesktopServiceError(
                "invalid_card_code",
                "card code must be a positive integer",
                path=f"$.payload.{field}[{index}]",
            )
        result.append(code)
    return tuple(result)


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise DesktopServiceError(
            "invalid_search_configuration",
            f"{field} must be an integer between {minimum} and {maximum}",
            path=f"$.payload.configuration.{field}",
        )
    return value


def _number(value: Any, field: str, *, minimum: float, maximum: float) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not minimum <= float(value) <= maximum
    ):
        raise DesktopServiceError(
            "invalid_search_configuration",
            f"{field} must be between {minimum:g} and {maximum:g}",
            path=f"$.payload.configuration.{field}",
        )
    return float(value)


def _validate_structure(sections: Mapping[str, tuple[int, ...]]) -> None:
    if not 40 <= len(sections["main"]) <= 60:
        raise DesktopServiceError(
            "invalid_main_deck_size",
            "main deck must contain 40..60 cards",
            path="$.payload.main",
        )
    for section in ("extra", "side"):
        if len(sections[section]) > 15:
            raise DesktopServiceError(
                f"invalid_{section}_deck_size",
                f"{section} deck must contain at most 15 cards",
                path=f"$.payload.{section}",
            )
    for code, count in Counter(
        code for section in sections.values() for code in section
    ).items():
        if count > 3:
            raise DesktopServiceError(
                "duplicate_card_limit_exceeded",
                f"card code {code} occurs {count} times",
                path="$.payload",
            )


@dataclass(frozen=True)
class DesktopDeckRecord:
    deck_id: str
    name: str
    source: str
    source_sha256: str | None
    deck_sha256: str
    main: tuple[int, ...]
    extra: tuple[int, ...]
    side: tuple[int, ...]
    registered_at: str

    def __post_init__(self) -> None:
        if not self.name or self.name != self.name.strip() or len(self.name) > 200:
            raise ValueError("desktop deck name is invalid")
        if self.source not in {"inline", "ydk"}:
            raise ValueError("desktop deck source is invalid")
        for field in ("main", "extra", "side"):
            object.__setattr__(self, field, _cards(getattr(self, field), field))
        _validate_structure(self.sections)
        _sha256(self.deck_sha256, "deck_sha256")
        if self.source == "ydk":
            _sha256(self.source_sha256, "source_sha256")
        elif self.source_sha256 is not None:
            raise ValueError("inline desktop deck must not have a source SHA-256")
        if not self.registered_at.endswith("Z"):
            raise ValueError("registered_at must be an ISO-8601 UTC timestamp")
        datetime.fromisoformat(self.registered_at[:-1] + "+00:00")
        normalized = {
            key: list(self.sections[key]) for key in ("main", "extra", "side")
        }
        observed_deck_sha256 = hashlib.sha256(
            canonical_json(normalized).encode("utf-8")
        ).hexdigest()
        if observed_deck_sha256 != self.deck_sha256:
            raise ValueError("desktop deck SHA-256 does not match normalized sections")
        expected_deck_id = stable_digest(
            {
                "deck_sha256": self.deck_sha256,
                "name": self.name,
                "source": self.source,
            },
            prefix="desktopdeck_",
        )
        if self.deck_id != expected_deck_id:
            raise ValueError("desktop deck ID does not match semantic content")

    @property
    def sections(self) -> dict[str, tuple[int, ...]]:
        return {"extra": self.extra, "main": self.main, "side": self.side}

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(asdict(self))

    def summary(self) -> dict[str, Any]:
        counts = Counter((*self.main, *self.extra, *self.side))
        return {
            "card_counts": [
                {"card_code": code, "count": count}
                for code, count in sorted(counts.items())
            ],
            "deck_id": self.deck_id,
            "deck_sha256": self.deck_sha256,
            "extra_count": len(self.extra),
            "main_count": len(self.main),
            "name": self.name,
            "registered_at": self.registered_at,
            "side_count": len(self.side),
            "source": self.source,
            "status": "registered",
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DesktopDeckRecord":
        expected = {
            "deck_id",
            "deck_sha256",
            "extra",
            "main",
            "name",
            "registered_at",
            "side",
            "source",
            "source_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("invalid desktop deck record")
        return cls(
            deck_id=str(value["deck_id"]),
            name=str(value["name"]),
            source=str(value["source"]),
            source_sha256=(
                str(value["source_sha256"])
                if value["source_sha256"] is not None
                else None
            ),
            deck_sha256=str(value["deck_sha256"]),
            main=_cards(value["main"], "main"),
            extra=_cards(value["extra"], "extra"),
            side=_cards(value["side"], "side"),
            registered_at=str(value["registered_at"]),
        )


class DesktopDeckCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self._lock = threading.RLock()

    def _read(self) -> dict[str, DesktopDeckRecord]:
        if not self.path.exists():
            return {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(document, Mapping) or set(document) != {
                "decks",
                "schema_version",
            }:
                raise ValueError("desktop deck catalog has invalid fields")
            if document["schema_version"] != DESKTOP_DECK_CATALOG_VERSION:
                raise ValueError("desktop deck catalog requires explicit migration")
            decks = document["decks"]
            if not isinstance(decks, list) or len(decks) > MAX_CATALOG_DECKS:
                raise ValueError("desktop deck catalog has invalid deck count")
            records = [DesktopDeckRecord.from_mapping(item) for item in decks]
            if len({item.deck_id for item in records}) != len(records):
                raise ValueError("desktop deck catalog contains duplicate IDs")
            return {item.deck_id: item for item in records}
        except (OSError, TypeError, ValueError) as exc:
            raise DesktopServiceError(
                "deck_catalog_corrupt",
                "desktop deck catalog failed integrity validation",
            ) from exc

    def _write(self, records: Mapping[str, DesktopDeckRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        document = {
            "decks": [records[key].to_dict() for key in sorted(records)],
            "schema_version": DESKTOP_DECK_CATALOG_VERSION,
        }
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(self.path)

    def register(
        self,
        *,
        name: str,
        source: str,
        sections: Mapping[str, tuple[int, ...]],
        source_sha256: str | None = None,
    ) -> DesktopDeckRecord:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200:
            raise DesktopServiceError(
                "invalid_deck_name",
                "deck name must contain 1..200 characters",
                path="$.payload.name",
            )
        if source not in {"inline", "ydk"}:
            raise ValueError("unsupported desktop deck source")
        _validate_structure(sections)
        normalized = {key: list(sections[key]) for key in ("main", "extra", "side")}
        deck_sha256 = hashlib.sha256(
            canonical_json(normalized).encode("utf-8")
        ).hexdigest()
        identity = {
            "deck_sha256": deck_sha256,
            "name": name.strip(),
            "source": source,
        }
        record = DesktopDeckRecord(
            deck_id=stable_digest(identity, prefix="desktopdeck_"),
            name=name.strip(),
            source=source,
            source_sha256=source_sha256,
            deck_sha256=deck_sha256,
            main=sections["main"],
            extra=sections["extra"],
            side=sections["side"],
            registered_at=_now(),
        )
        with self._lock:
            records = self._read()
            if record.deck_id not in records and len(records) >= MAX_CATALOG_DECKS:
                raise DesktopServiceError(
                    "deck_catalog_capacity_exceeded",
                    f"desktop deck catalog is limited to {MAX_CATALOG_DECKS} entries",
                )
            records.setdefault(record.deck_id, record)
            self._write(records)
            return records[record.deck_id]

    def list(self) -> tuple[DesktopDeckRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._read().values(),
                    key=lambda item: (item.name.casefold(), item.deck_id),
                )
            )

    def get(self, deck_id: str) -> DesktopDeckRecord:
        with self._lock:
            record = self._read().get(deck_id)
        if record is None:
            raise DesktopServiceError(
                "deck_not_found",
                "desktop deck ID is not registered",
                path="$.payload.deck_id",
            )
        return record


@dataclass(frozen=True)
class DesktopDeckMetadataRecord:
    deck_id: str
    display_name: str
    tags: tuple[str, ...]
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if not self.deck_id.startswith("desktopdeck_"):
            raise ValueError("deck_id must be a desktop deck ID")
        if (
            not self.display_name
            or self.display_name != self.display_name.strip()
            or len(self.display_name) > 200
        ):
            raise ValueError("display_name must contain 1..200 trimmed characters")
        object.__setattr__(self, "tags", _tags(self.tags, "tags"))
        for field in ("created_at", "updated_at"):
            value = getattr(self, field)
            if not value.endswith("Z"):
                raise ValueError(f"{field} must be an ISO-8601 UTC timestamp")
            datetime.fromisoformat(value[:-1] + "+00:00")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(asdict(self))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DesktopDeckMetadataRecord":
        expected = {"created_at", "deck_id", "display_name", "tags", "updated_at"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("invalid desktop deck metadata record")
        return cls(
            deck_id=str(value["deck_id"]),
            display_name=str(value["display_name"]),
            tags=_tags(value["tags"], "tags"),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
        )


class DesktopDeckMetadataCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self._lock = threading.RLock()

    def _read(self) -> dict[str, DesktopDeckMetadataRecord]:
        if not self.path.exists():
            return {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(document, Mapping) or set(document) != {
                "metadata",
                "schema_version",
            }:
                raise ValueError("desktop deck metadata catalog has invalid fields")
            if document["schema_version"] != DESKTOP_DECK_METADATA_CATALOG_VERSION:
                raise ValueError("desktop deck metadata catalog requires migration")
            rows = document["metadata"]
            if not isinstance(rows, list) or len(rows) > MAX_CATALOG_DECKS:
                raise ValueError("desktop deck metadata catalog has invalid count")
            records = [DesktopDeckMetadataRecord.from_mapping(item) for item in rows]
            if len({item.deck_id for item in records}) != len(records):
                raise ValueError("desktop deck metadata catalog contains duplicate IDs")
            return {item.deck_id: item for item in records}
        except (OSError, TypeError, ValueError) as exc:
            raise DesktopServiceError(
                "deck_metadata_catalog_corrupt",
                "desktop deck metadata catalog failed integrity validation",
            ) from exc

    def _write(self, records: Mapping[str, DesktopDeckMetadataRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        document = {
            "metadata": [records[key].to_dict() for key in sorted(records)],
            "schema_version": DESKTOP_DECK_METADATA_CATALOG_VERSION,
        }
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(self.path)

    def get_or_default(
        self, deck: DesktopDeckRecord
    ) -> DesktopDeckMetadataRecord:
        with self._lock:
            record = self._read().get(deck.deck_id)
        if record is not None:
            return record
        now = _now()
        return DesktopDeckMetadataRecord(
            deck_id=deck.deck_id,
            display_name=deck.name,
            tags=(deck.source, "registered"),
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        deck: DesktopDeckRecord,
        *,
        display_name: str,
        tags: tuple[str, ...],
    ) -> DesktopDeckMetadataRecord:
        display_name = _non_empty_text(display_name, "display_name")
        if len(display_name) > 200:
            raise DesktopServiceError(
                "invalid_deck_display_name",
                "display_name must contain at most 200 characters",
                path="$.payload.display_name",
            )
        with self._lock:
            records = self._read()
            current = records.get(deck.deck_id)
            now = _now()
            updated = DesktopDeckMetadataRecord(
                deck_id=deck.deck_id,
                display_name=display_name,
                tags=tags,
                created_at=current.created_at if current else now,
                updated_at=now,
            )
            records[deck.deck_id] = updated
            self._write(records)
        return updated


@dataclass(frozen=True)
class DesktopDeckTerminalProfileRecord:
    deck_profile_id: str
    deck_id: str
    display_name: str
    active_profile_id: str
    state: str
    revision: int
    created_at: str
    updated_at: str
    archived_at: str | None = None

    def __post_init__(self) -> None:
        if not self.deck_profile_id.startswith("decktermpref_"):
            raise ValueError("deck_profile_id must be a desktop profile ID")
        if not self.deck_id.startswith("desktopdeck_"):
            raise ValueError("deck_id must be a desktop deck ID")
        if (
            not self.display_name
            or self.display_name != self.display_name.strip()
            or len(self.display_name) > 80
        ):
            raise ValueError("display_name must contain 1..80 trimmed characters")
        if not self.active_profile_id.startswith("termpref_"):
            raise ValueError("active_profile_id must be a terminal preference profile ID")
        if self.state not in {"active", "archived"}:
            raise ValueError("unsupported deck terminal profile state")
        if self.revision < 1:
            raise ValueError("revision must be positive")
        for field in ("created_at", "updated_at"):
            value = getattr(self, field)
            if not value.endswith("Z"):
                raise ValueError(f"{field} must be an ISO-8601 UTC timestamp")
            datetime.fromisoformat(value[:-1] + "+00:00")
        if self.archived_at is not None:
            if not self.archived_at.endswith("Z"):
                raise ValueError("archived_at must be an ISO-8601 UTC timestamp")
            datetime.fromisoformat(self.archived_at[:-1] + "+00:00")
        if self.state == "active" and self.archived_at is not None:
            raise ValueError("active deck terminal profile must not have archived_at")
        if self.state == "archived" and self.archived_at is None:
            raise ValueError("archived deck terminal profile requires archived_at")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(asdict(self))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DesktopDeckTerminalProfileRecord":
        expected = {
            "active_profile_id",
            "archived_at",
            "created_at",
            "deck_id",
            "deck_profile_id",
            "display_name",
            "revision",
            "state",
            "updated_at",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("invalid desktop deck terminal profile record")
        return cls(
            deck_profile_id=str(value["deck_profile_id"]),
            deck_id=str(value["deck_id"]),
            display_name=str(value["display_name"]),
            active_profile_id=str(value["active_profile_id"]),
            state=str(value["state"]),
            revision=int(value["revision"]),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            archived_at=(
                str(value["archived_at"]) if value["archived_at"] is not None else None
            ),
        )


class DesktopDeckTerminalProfileCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self._lock = threading.RLock()

    def _read(self) -> dict[str, DesktopDeckTerminalProfileRecord]:
        if not self.path.exists():
            return {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(document, Mapping) or set(document) != {
                "profiles",
                "schema_version",
            }:
                raise ValueError("desktop deck terminal profile catalog has invalid fields")
            if (
                document["schema_version"]
                != DESKTOP_DECK_TERMINAL_PROFILE_CATALOG_VERSION
            ):
                raise ValueError(
                    "desktop deck terminal profile catalog requires explicit migration"
                )
            profiles = document["profiles"]
            if not isinstance(profiles, list):
                raise ValueError("desktop deck terminal profile catalog profiles invalid")
            records = [
                DesktopDeckTerminalProfileRecord.from_mapping(item)
                for item in profiles
            ]
            if len({item.deck_profile_id for item in records}) != len(records):
                raise ValueError(
                    "desktop deck terminal profile catalog contains duplicate IDs"
                )
            return {item.deck_profile_id: item for item in records}
        except (OSError, TypeError, ValueError) as exc:
            raise DesktopServiceError(
                "deck_profile_catalog_corrupt",
                "desktop deck terminal profile catalog failed integrity validation",
            ) from exc

    def _write(
        self, records: Mapping[str, DesktopDeckTerminalProfileRecord]
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        document = {
            "profiles": [records[key].to_dict() for key in sorted(records)],
            "schema_version": DESKTOP_DECK_TERMINAL_PROFILE_CATALOG_VERSION,
        }
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(self.path)

    def list(
        self, deck_id: str, *, include_archived: bool = False
    ) -> tuple[DesktopDeckTerminalProfileRecord, ...]:
        with self._lock:
            records = [
                item
                for item in self._read().values()
                if item.deck_id == deck_id and (include_archived or item.state == "active")
            ]
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    item.state != "active",
                    item.display_name.casefold(),
                    item.deck_profile_id,
                ),
            )
        )

    def require(self, deck_profile_id: str) -> DesktopDeckTerminalProfileRecord:
        with self._lock:
            record = self._read().get(deck_profile_id)
        if record is None:
            raise DesktopServiceError(
                "deck_profile_not_found",
                "desktop deck terminal profile is not registered",
                path="$.payload.deck_profile_id",
            )
        return record

    def create(
        self,
        *,
        deck_id: str,
        display_name: str,
        active_profile_id: str,
    ) -> DesktopDeckTerminalProfileRecord:
        created_at = _now()
        record = DesktopDeckTerminalProfileRecord(
            deck_profile_id=stable_digest(
                {
                    "active_profile_id": active_profile_id,
                    "created_at": created_at,
                    "deck_id": deck_id,
                    "display_name": display_name,
                    "schema_version": DESKTOP_DECK_TERMINAL_PROFILE_CATALOG_VERSION,
                },
                prefix="decktermpref_",
            ),
            deck_id=deck_id,
            display_name=display_name,
            active_profile_id=active_profile_id,
            state="active",
            revision=1,
            created_at=created_at,
            updated_at=created_at,
            archived_at=None,
        )
        with self._lock:
            records = self._read()
            records[record.deck_profile_id] = record
            self._write(records)
        return record

    def update(
        self,
        deck_profile_id: str,
        *,
        display_name: str,
        active_profile_id: str,
    ) -> DesktopDeckTerminalProfileRecord:
        with self._lock:
            records = self._read()
            current = records.get(deck_profile_id)
            if current is None:
                raise DesktopServiceError(
                    "deck_profile_not_found",
                    "desktop deck terminal profile is not registered",
                    path="$.payload.deck_profile_id",
                )
            if current.state != "active":
                raise DesktopServiceError(
                    "deck_profile_archived",
                    "archived deck terminal profiles cannot be edited",
                    path="$.payload.deck_profile_id",
                )
            updated = DesktopDeckTerminalProfileRecord(
                deck_profile_id=current.deck_profile_id,
                deck_id=current.deck_id,
                display_name=display_name,
                active_profile_id=active_profile_id,
                state="active",
                revision=current.revision + 1,
                created_at=current.created_at,
                updated_at=_now(),
                archived_at=None,
            )
            records[deck_profile_id] = updated
            self._write(records)
        return updated

    def archive(self, deck_profile_id: str) -> DesktopDeckTerminalProfileRecord:
        with self._lock:
            records = self._read()
            current = records.get(deck_profile_id)
            if current is None:
                raise DesktopServiceError(
                    "deck_profile_not_found",
                    "desktop deck terminal profile is not registered",
                    path="$.payload.deck_profile_id",
                )
            if current.state == "archived":
                return current
            archived_at = _now()
            archived = DesktopDeckTerminalProfileRecord(
                deck_profile_id=current.deck_profile_id,
                deck_id=current.deck_id,
                display_name=current.display_name,
                active_profile_id=current.active_profile_id,
                state="archived",
                revision=current.revision,
                created_at=current.created_at,
                updated_at=archived_at,
                archived_at=archived_at,
            )
            records[deck_profile_id] = archived
            self._write(records)
        return archived


class DesktopApplicationService:
    def __init__(
        self,
        data_root: str | Path,
        *,
        external_root: str | Path | None = None,
        ydk_picker: YdkPicker | None = None,
        card_provider: CardProvider | None = None,
        analytics_service: AnalyticsQueryService | None = None,
        comparison_handler: (
            Callable[[Mapping[str, Any]], Mapping[str, Any]] | None
        ) = None,
        preflight: Callable[..., Any] = preflight_scenario,
        worker_execution: str = "external_worker_required",
        worker_health: Callable[[], str] | None = None,
        export_worker_health: Callable[[], str] | None = None,
    ) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.external_root = (
            Path(external_root).expanduser().resolve()
            if external_root is not None
            else None
        )
        self.deck_catalog = DesktopDeckCatalog(self.data_root / "decks.json")
        self.deck_metadata_catalog = DesktopDeckMetadataCatalog(
            self.data_root / "deck-metadata.json"
        )
        self.job_catalog = JobCatalog(self.data_root / "jobs.sqlite3")
        self.preference_catalog = TerminalPreferenceProfileCatalog(
            self.data_root / "terminal-preference-profiles"
        )
        self.preference_catalog.ensure_default()
        self.deck_profile_catalog = DesktopDeckTerminalProfileCatalog(
            self.data_root / "deck-terminal-profiles.json"
        )
        self.ydk_picker = ydk_picker
        self.card_provider = card_provider
        self.comparison_handler = comparison_handler
        self.preflight = preflight
        if worker_execution not in {
            "desktop-supervisor-v1",
            "external_worker_required",
        }:
            raise ValueError("unsupported desktop worker execution mode")
        self.worker_execution = worker_execution
        self.worker_health = worker_health
        self.export_worker_health = export_worker_health
        if analytics_service is None:
            snapshots = AnalyticsSnapshotStore()
            snapshots.register(AnalyticsSnapshot(rows=()))
            analytics_service = AnalyticsQueryService(snapshots)
        self.analytics_service = analytics_service
        self.analytics_export_service = AnalyticsExportService(analytics_service)
        self.analytics_export_queue = AnalyticsExportQueue(
            self.data_root,
            self.analytics_export_service,
            catalog=self.job_catalog,
        )
        self.analytics_export_worker = AnalyticsExportWorker(
            self.analytics_export_queue
        )

    def handlers(self) -> dict[str, DesktopHandler]:
        return {
            "analytics.compare": self.analytics_compare,
            "analytics.export.enqueue": self.analytics_export_enqueue,
            "analytics.query": self.analytics_query,
            "card.get": self.card_get,
            "deck.card_options": self.deck_card_options,
            "deck.catalog": self.deck_catalog_list,
            "deck.import_ydk": self.deck_import_ydk,
            "deck.metadata.get": self.deck_metadata_get,
            "deck.metadata.update": self.deck_metadata_update,
            "deck.profile.archive": self.deck_profile_archive,
            "deck.profile.create": self.deck_profile_create,
            "deck.profile.get": self.deck_profile_get,
            "deck.profile.list": self.deck_profile_list,
            "deck.profile.update": self.deck_profile_update,
            "deck.register_inline": self.deck_register_inline,
            "job.cancel": self.job_cancel,
            "job.enqueue_replay_verification": self.job_enqueue_replay_verification,
            "job.enqueue_search": self.job_enqueue_search,
            "job.result": self.job_result,
            "job.status": self.job_status,
            "profile.clone": self.profile_clone,
            "profile.get": self.profile_get,
            "profile.list": self.profile_list,
            "scenario.compose_search": self.scenario_compose_search,
            "scenario.preflight": self.scenario_preflight,
            "system.describe": self.system_describe,
        }

    def system_describe(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, set(), "system.describe")
        return {
            "capabilities": {
                "analytics_query": True,
                "analytics_export": True,
                "analytics_export_formats": [
                    item.value for item in AnalyticsExportFormat
                ],
                "card_presentation": self.card_provider is not None,
                "deck_card_options": self.card_provider is not None,
                "deck_metadata": True,
                "deck_terminal_profiles": True,
                "comparison": self.comparison_handler is not None,
                "native_ydk_import": self.ydk_picker is not None,
                "terminal_preference_profiles": True,
                "search_job_queue": True,
                "verified_result_view": True,
                "worker_execution": self.worker_execution,
                "worker_health": (
                    self.worker_health()
                    if self.worker_health is not None
                    else "unknown"
                ),
                "export_worker_health": (
                    self.export_worker_health()
                    if self.export_worker_health is not None
                    else "unknown"
                ),
            },
            "package_version": __version__,
            "schema_version": DESKTOP_SERVICE_VERSION,
        }

    def deck_catalog_list(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, set(), "deck.catalog")
        records = self.deck_catalog.list()
        return {
            "decks": [self._deck_summary(item) for item in records],
            "schema_version": DESKTOP_DECK_CATALOG_VERSION,
            "total": len(records),
        }

    def _card_presentation_summary(self, card_code: int) -> dict[str, Any]:
        if self.card_provider is None:
            return {
                "availability": "unavailable",
                "card_code": card_code,
                "name_ja": None,
                "presentation_id": None,
                "resolved_locale": None,
            }
        presentation = self.card_provider.get_card(
            CardPresentationQuery(
                card_code=card_code,
                requested_locale="ja",
                fallback_locales=(),
                redacted=False,
                expected_asset_lock_id=None,
                schema_version=CARD_PRESENTATION_QUERY_VERSION,
            )
        ).to_dict()
        available = (
            presentation.get("availability") == "available"
            and presentation.get("resolved_locale") == "ja"
            and isinstance(presentation.get("name"), str)
            and bool(presentation.get("name"))
        )
        return {
            "availability": presentation.get("availability"),
            "card_code": card_code,
            "name_ja": presentation.get("name") if available else None,
            "presentation_id": presentation.get("presentation_id"),
            "resolved_locale": presentation.get("resolved_locale"),
        }

    def _deck_summary(self, deck: DesktopDeckRecord) -> dict[str, Any]:
        metadata = self.deck_metadata_catalog.get_or_default(deck)
        summary = deck.summary()
        summary["canonical_name"] = deck.name
        summary["name"] = metadata.display_name
        summary["metadata"] = metadata.to_dict()
        summary["tags"] = list(metadata.tags)
        summary["card_counts"] = [
            {
                **item,
                **self._card_presentation_summary(int(item["card_code"])),
            }
            for item in summary["card_counts"]
        ]
        return summary

    def deck_metadata_get(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"deck_id"}, "deck.metadata.get")
        deck = self.deck_catalog.get(_non_empty_text(payload["deck_id"], "deck_id"))
        metadata = self.deck_metadata_catalog.get_or_default(deck)
        return {
            "deck_id": deck.deck_id,
            "metadata": metadata.to_dict(),
            "schema_version": DESKTOP_DECK_METADATA_CATALOG_VERSION,
        }

    def deck_metadata_update(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"deck_id", "display_name", "tags"}, "deck.metadata.update")
        deck = self.deck_catalog.get(_non_empty_text(payload["deck_id"], "deck_id"))
        metadata = self.deck_metadata_catalog.update(
            deck,
            display_name=_non_empty_text(payload["display_name"], "display_name"),
            tags=_tags(payload["tags"], "tags"),
        )
        return {
            "deck_id": deck.deck_id,
            "deck_sha256": deck.deck_sha256,
            "metadata": metadata.to_dict(),
            "schema_version": DESKTOP_DECK_METADATA_CATALOG_VERSION,
        }

    def deck_import_ydk(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, set(), "deck.import_ydk")
        if self.ydk_picker is None:
            raise DesktopServiceError(
                "native_picker_unavailable",
                "native YDK file selection is unavailable",
            )
        selected = self.ydk_picker()
        if selected is None:
            return {"cancelled": True, "deck": None}
        path = Path(selected).expanduser().resolve(strict=True)
        if path.suffix.casefold() != ".ydk" or not path.is_file():
            raise DesktopServiceError(
                "invalid_ydk_selection",
                "native selection must be an existing .ydk file",
            )
        sections, source_sha256 = parse_ydk(path)
        record = self.deck_catalog.register(
            name=path.stem,
            source="ydk",
            sections=sections,
            source_sha256=source_sha256,
        )
        return {"cancelled": False, "deck": self._deck_summary(record)}

    def deck_register_inline(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(
            payload,
            {"extra", "main", "name", "side"},
            "deck.register_inline",
        )
        sections = {
            name: _cards(payload[name], name) for name in ("main", "extra", "side")
        }
        record = self.deck_catalog.register(
            name=payload["name"],
            source="inline",
            sections=sections,
        )
        return {"deck": self._deck_summary(record)}

    def profile_list(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, set(), "profile.list")
        return {
            "catalog_digest": self.preference_catalog.catalog_digest(),
            "profiles": [
                record.to_dict() for record in self.preference_catalog.list()
            ],
        }

    def profile_get(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"profile_id"}, "profile.get")
        profile_id = payload["profile_id"]
        if not isinstance(profile_id, str):
            raise DesktopServiceError(
                "invalid_profile_id",
                "profile_id must be a string",
                path="$.payload.profile_id",
            )
        try:
            record = self.preference_catalog.require(profile_id)
        except (KeyError, ValueError) as exc:
            raise DesktopServiceError(
                "profile_not_found",
                "terminal preference profile is not present in the catalog",
                path="$.payload.profile_id",
            ) from exc
        return {"profile": record.to_dict()}

    def profile_clone(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"name", "profile_id", "rules"}, "profile.clone")
        profile_id = payload["profile_id"]
        if not isinstance(profile_id, str):
            raise DesktopServiceError(
                "invalid_profile_id",
                "profile_id must be a string",
                path="$.payload.profile_id",
            )
        name = payload["name"]
        if name is not None and (not isinstance(name, str) or not name):
            raise DesktopServiceError(
                "invalid_profile_name",
                "name must be null or a non-empty string",
                path="$.payload.name",
            )
        rules = payload["rules"]
        if rules is not None and not isinstance(rules, list):
            raise DesktopServiceError(
                "invalid_profile_rules",
                "rules must be null or a list",
                path="$.payload.rules",
            )
        try:
            record = self.preference_catalog.clone(
                profile_id,
                name=name,
                rules=rules,
            )
        except (KeyError, ValueError) as exc:
            raise DesktopServiceError(
                "invalid_profile_clone",
                "terminal preference profile clone request is invalid",
            ) from exc
        return {"profile": record.to_dict()}

    def _deck_profile_payload(
        self, record: DesktopDeckTerminalProfileRecord
    ) -> dict[str, Any]:
        content = self.preference_catalog.require(record.active_profile_id)
        return {
            **record.to_dict(),
            "active_profile": content.profile.to_dict(),
            "catalog_schema_version": DESKTOP_DECK_TERMINAL_PROFILE_CATALOG_VERSION,
        }

    def _deck_profile_rules(
        self,
        deck: DesktopDeckRecord,
        rules: Any,
        *,
        method: str,
    ) -> list[Mapping[str, Any]]:
        if not isinstance(rules, list):
            raise DesktopServiceError(
                "invalid_deck_profile_rules",
                "rules must be a list",
                path="$.payload.rules",
            )
        deck_codes = set((*deck.main, *deck.extra, *deck.side))
        normalized: list[Mapping[str, Any]] = []
        for index, rule in enumerate(rules):
            if not isinstance(rule, Mapping):
                raise DesktopServiceError(
                    "invalid_deck_profile_rule",
                    "rules must contain objects",
                    path=f"$.payload.rules[{index}]",
                )
            code = rule.get("card_code")
            if code not in deck_codes:
                raise DesktopServiceError(
                    "deck_profile_card_not_in_deck",
                    "terminal evaluation rules can only reference cards in the selected deck",
                    path=f"$.payload.rules[{index}].card_code",
                )
            normalized.append(rule)
        try:
            TerminalPreferenceProfile.from_mapping(
                {
                    "name": f"{method} validation",
                    "rules": normalized,
                    "schema_version": "terminal-preference-profile-v1",
                }
            )
        except ValueError as exc:
            raise DesktopServiceError(
                "invalid_deck_profile_rules",
                "terminal evaluation rules are invalid",
                path="$.payload.rules",
            ) from exc
        return normalized

    def _put_deck_profile_content(
        self,
        *,
        display_name: str,
        rules: list[Mapping[str, Any]],
    ) -> str:
        profile = TerminalPreferenceProfile.from_mapping(
            {
                "name": display_name,
                "rules": rules,
                "schema_version": "terminal-preference-profile-v1",
            }
        )
        return self.preference_catalog.put(profile).profile.profile_id

    def deck_profile_list(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"deck_id", "include_archived"}, "deck.profile.list")
        deck_id = _non_empty_text(payload["deck_id"], "deck_id")
        include_archived = payload["include_archived"]
        if not isinstance(include_archived, bool):
            raise DesktopServiceError(
                "invalid_method_payload",
                "include_archived must be a boolean",
                path="$.payload.include_archived",
            )
        self.deck_catalog.get(deck_id)
        records = self.deck_profile_catalog.list(
            deck_id, include_archived=include_archived
        )
        return {
            "deck_id": deck_id,
            "profiles": [self._deck_profile_payload(record) for record in records],
            "schema_version": DESKTOP_DECK_TERMINAL_PROFILE_CATALOG_VERSION,
            "total": len(records),
        }

    def deck_profile_get(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"deck_profile_id"}, "deck.profile.get")
        deck_profile_id = _non_empty_text(payload["deck_profile_id"], "deck_profile_id")
        return {
            "profile": self._deck_profile_payload(
                self.deck_profile_catalog.require(deck_profile_id)
            )
        }

    def deck_profile_create(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"deck_id", "display_name", "rules"}, "deck.profile.create")
        deck = self.deck_catalog.get(_non_empty_text(payload["deck_id"], "deck_id"))
        display_name = _non_empty_text(payload["display_name"], "display_name")
        if len(display_name) > 80:
            raise DesktopServiceError(
                "invalid_deck_profile_name",
                "display_name must contain at most 80 characters",
                path="$.payload.display_name",
            )
        rules = self._deck_profile_rules(
            deck, payload["rules"], method="deck.profile.create"
        )
        active_profile_id = self._put_deck_profile_content(
            display_name=display_name, rules=rules
        )
        record = self.deck_profile_catalog.create(
            deck_id=deck.deck_id,
            display_name=display_name,
            active_profile_id=active_profile_id,
        )
        return {"profile": self._deck_profile_payload(record)}

    def deck_profile_update(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(
            payload,
            {"deck_profile_id", "display_name", "rules"},
            "deck.profile.update",
        )
        current = self.deck_profile_catalog.require(
            _non_empty_text(payload["deck_profile_id"], "deck_profile_id")
        )
        deck = self.deck_catalog.get(current.deck_id)
        display_name = _non_empty_text(payload["display_name"], "display_name")
        if len(display_name) > 80:
            raise DesktopServiceError(
                "invalid_deck_profile_name",
                "display_name must contain at most 80 characters",
                path="$.payload.display_name",
            )
        rules = self._deck_profile_rules(
            deck, payload["rules"], method="deck.profile.update"
        )
        active_profile_id = self._put_deck_profile_content(
            display_name=display_name, rules=rules
        )
        record = self.deck_profile_catalog.update(
            current.deck_profile_id,
            display_name=display_name,
            active_profile_id=active_profile_id,
        )
        return {"profile": self._deck_profile_payload(record)}

    def deck_profile_archive(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"deck_profile_id"}, "deck.profile.archive")
        record = self.deck_profile_catalog.archive(
            _non_empty_text(payload["deck_profile_id"], "deck_profile_id")
        )
        return {"profile": self._deck_profile_payload(record)}

    def deck_card_options(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"deck_id"}, "deck.card_options")
        deck = self.deck_catalog.get(_non_empty_text(payload["deck_id"], "deck_id"))
        if self.card_provider is None:
            raise DesktopServiceError(
                "card_presentation_source_unavailable",
                "no verified Japanese card-presentation source is configured",
            )
        counts = Counter((*deck.main, *deck.extra, *deck.side))
        items: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for code, count in sorted(counts.items()):
            payload = self._card_presentation_summary(code)
            selectable = isinstance(payload.get("name_ja"), str)
            items.append(
                {
                    "availability": payload.get("availability"),
                    "card_code": code,
                    "count": count,
                    "name_ja": payload.get("name_ja"),
                    "presentation_id": payload.get("presentation_id"),
                    "selectable": selectable,
                }
            )
            if not selectable:
                diagnostics.append(
                    {
                        "card_code": code,
                        "code": "japanese_card_name_unavailable",
                        "message": "Japanese card name is unavailable for this deck card.",
                        "severity": "warning",
                    }
                )
        return {
            "deck_id": deck.deck_id,
            "diagnostics": diagnostics,
            "items": items,
            "schema_version": "deck-card-options-v1",
        }

    def _resolved_experiment(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        experiment = payload.get("experiment")
        if not isinstance(experiment, Mapping):
            raise DesktopServiceError(
                "invalid_experiment",
                "experiment must be an object",
                path="$.payload.experiment",
            )
        deck_id = payload.get("deck_id")
        if not isinstance(deck_id, str) or not deck_id:
            raise DesktopServiceError(
                "invalid_deck_id",
                "deck_id must be a non-empty string",
                path="$.payload.deck_id",
            )
        record = self.deck_catalog.get(deck_id)
        resolved = json.loads(json.dumps(experiment, ensure_ascii=False))
        resolved["deck"] = {
            "extra": list(record.extra),
            "id": record.deck_id,
            "main": list(record.main),
            "side": list(record.side),
            "source": "inline",
        }
        return resolved

    def scenario_compose_search(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"configuration", "deck_id"}, "scenario.compose_search")
        configuration = payload["configuration"]
        if not isinstance(configuration, Mapping):
            raise DesktopServiceError(
                "invalid_search_configuration",
                "configuration must be an object",
                path="$.payload.configuration",
            )
        expected = {
            "interruption_card_code",
            "max_depth",
            "max_nodes",
            "max_seconds",
            "seed",
            "strategy",
        }
        optional = {
            "opening_hand",
            "pool_size",
            "preference_profile_id",
            "scenario_preset_id",
        }
        unknown = sorted(set(configuration) - expected - optional)
        missing = sorted(expected - set(configuration))
        if unknown or missing:
            raise DesktopServiceError(
                "invalid_search_configuration",
                "configuration fields are invalid",
                details={"missing": missing, "unknown": unknown},
                path="$.payload.configuration",
            )
        record = self.deck_catalog.get(payload["deck_id"])
        seed = _integer(configuration["seed"], "seed", minimum=0, maximum=2**63 - 1)
        max_nodes = _integer(
            configuration["max_nodes"],
            "max_nodes",
            minimum=1,
            maximum=MAX_DESKTOP_SEARCH_NODES,
        )
        max_depth = _integer(
            configuration["max_depth"],
            "max_depth",
            minimum=1,
            maximum=MAX_DESKTOP_SEARCH_DEPTH,
        )
        max_seconds = _number(
            configuration["max_seconds"],
            "max_seconds",
            minimum=1,
            maximum=MAX_DESKTOP_SEARCH_SECONDS,
        )
        pool_size = _integer(
            configuration.get("pool_size", 1),
            "pool_size",
            minimum=1,
            maximum=MAX_DESKTOP_SEARCH_POOL_SIZE,
        )
        strategy = configuration["strategy"]
        strategy_parameters: dict[str, Any]
        if strategy == "random_search_v1":
            strategy_parameters = {"seed": seed}
        elif strategy == "beam_search_v1":
            strategy_parameters = {"beam_width": 4, "seed": seed}
        elif strategy == "mcts_v1":
            strategy_parameters = {
                "reward_ceiling": 100,
                "reward_floor": 0,
                "seed": seed,
                "simulations": 8,
            }
        else:
            raise DesktopServiceError(
                "unsupported_search_strategy",
                "desktop search strategy is not supported",
                path="$.payload.configuration.strategy",
            )
        strategy_parameters.update(
            {
                "max_frontier_actions": 128,
                "termination": {"stop_on_success": True},
            }
        )
        if pool_size > 1:
            strategy_parameters["parallel"] = {
                "base_seed": seed,
                "max_retries": 1,
                "pool_size": pool_size,
            }
        scenario_preset_id = configuration.get(
            "scenario_preset_id",
            DEFAULT_SCENARIO_PRESET_ID,
        )
        if not isinstance(scenario_preset_id, str):
            raise DesktopServiceError(
                "invalid_scenario_preset",
                "scenario_preset_id must be a string",
                path="$.payload.configuration.scenario_preset_id",
            )
        if scenario_preset_id not in DESKTOP_SCENARIO_PRESETS:
            raise DesktopServiceError(
                "unsupported_scenario_preset",
                "desktop scenario preset is not supported",
                path="$.payload.configuration.scenario_preset_id",
            )
        scenario_preset = json.loads(
            json.dumps(DESKTOP_SCENARIO_PRESETS[scenario_preset_id])
        )
        raw_opening_hand = configuration.get("opening_hand")
        if raw_opening_hand is None:
            opening_hand = {"mode": "random", "seed": seed, "size": 5}
        elif not isinstance(raw_opening_hand, Mapping):
            raise DesktopServiceError(
                "invalid_opening_hand",
                "opening_hand must be an object",
                path="$.payload.configuration.opening_hand",
            )
        else:
            opening_mode = raw_opening_hand.get("mode")
            if opening_mode == "random":
                opening_hand = {
                    "mode": "random",
                    "seed": _integer(
                        raw_opening_hand.get("seed", seed),
                        "opening_hand.seed",
                        minimum=0,
                        maximum=2**63 - 1,
                    ),
                    "size": _integer(
                        raw_opening_hand.get("size", 5),
                        "opening_hand.size",
                        minimum=1,
                        maximum=10,
                    ),
                }
            elif opening_mode == "fixed":
                cards = raw_opening_hand.get("cards")
                if not isinstance(cards, list) or not cards:
                    raise DesktopServiceError(
                        "invalid_opening_hand",
                        "fixed opening_hand.cards must be a non-empty list",
                        path="$.payload.configuration.opening_hand.cards",
                    )
                opening_hand = {
                    "cards": [
                        _integer(
                            card,
                            "opening_hand.cards[]",
                            minimum=1,
                            maximum=2**31 - 1,
                        )
                        for card in cards
                    ],
                    "mode": "fixed",
                }
            elif opening_mode == "conditional":
                conditions = raw_opening_hand.get("conditions")
                if not isinstance(conditions, list) or not conditions:
                    raise DesktopServiceError(
                        "invalid_opening_hand",
                        "conditional opening_hand.conditions must be a non-empty list",
                        path="$.payload.configuration.opening_hand.conditions",
                    )
                opening_hand = {
                    "conditions": to_canonical_data(conditions),
                    "max_attempts": _integer(
                        raw_opening_hand.get("max_attempts", 10_000),
                        "opening_hand.max_attempts",
                        minimum=1,
                        maximum=100_000,
                    ),
                    "mode": "conditional",
                    "seed": _integer(
                        raw_opening_hand.get("seed", seed),
                        "opening_hand.seed",
                        minimum=0,
                        maximum=2**63 - 1,
                    ),
                    "size": _integer(
                        raw_opening_hand.get("size", 5),
                        "opening_hand.size",
                        minimum=1,
                        maximum=10,
                    ),
                }
            else:
                raise DesktopServiceError(
                    "invalid_opening_hand",
                    "opening_hand.mode must be random, fixed, or conditional",
                    path="$.payload.configuration.opening_hand.mode",
                )
        requested_profile_id = configuration.get("preference_profile_id")
        if requested_profile_id is None:
            preference_record = self.preference_catalog.ensure_default()
        elif isinstance(requested_profile_id, str):
            if requested_profile_id.startswith("decktermpref_"):
                deck_profile = self.deck_profile_catalog.require(requested_profile_id)
                if deck_profile.deck_id != record.deck_id:
                    raise DesktopServiceError(
                        "deck_profile_mismatch",
                        "selected terminal evaluation profile belongs to another deck",
                        path="$.payload.configuration.preference_profile_id",
                    )
                if deck_profile.state != "active":
                    raise DesktopServiceError(
                        "deck_profile_archived",
                        "archived terminal evaluation profiles cannot be used for search",
                        path="$.payload.configuration.preference_profile_id",
                    )
                try:
                    preference_record = self.preference_catalog.require(
                        deck_profile.active_profile_id
                    )
                except (KeyError, ValueError) as exc:
                    raise DesktopServiceError(
                        "profile_not_found",
                        "terminal preference profile is not present in the catalog",
                        path="$.payload.configuration.preference_profile_id",
                    ) from exc
            else:
                try:
                    preference_record = self.preference_catalog.require(
                        requested_profile_id
                    )
                except (KeyError, ValueError) as exc:
                    raise DesktopServiceError(
                        "profile_not_found",
                        "terminal preference profile is not present in the catalog",
                        path="$.payload.configuration.preference_profile_id",
                    ) from exc
        else:
            raise DesktopServiceError(
                "invalid_profile_id",
                "preference_profile_id must be null or a string",
                path="$.payload.configuration.preference_profile_id",
            )
        interruption_code = configuration["interruption_card_code"]
        if interruption_code is None:
            interruption = {"definitions": [], "mode": "none"}
        else:
            code = _integer(
                interruption_code,
                "interruption_card_code",
                minimum=1,
                maximum=2**31 - 1,
            )
            interruption = {
                "definitions": [
                    {
                        "id": f"desktop_specified_{code}",
                        "response_roles": [],
                        "source_card_code": code,
                        "source_player": 1,
                        "source_zone": "hand",
                    }
                ],
                "mode": "specified",
            }
        policy = InformationAccessPolicy(
            information_mode="complete_information",
            deck_order="known",
            opening_hand="natural",
        )
        identity = {
            "deck_id": record.deck_id,
            "interruption": interruption,
            "max_depth": max_depth,
            "max_nodes": max_nodes,
            "max_seconds": max_seconds,
            "opening_hand": opening_hand,
            "pool_size": pool_size,
            "preference_profile_id": preference_record.profile.profile_id,
            "scenario_preset_id": scenario_preset_id,
            "seed": seed,
            "strategy": strategy,
        }
        experiment_id = stable_digest(identity, prefix="desktopexperiment_")
        experiment: dict[str, Any] = {
            "deck": {
                "extra": list(record.extra),
                "id": record.deck_id,
                "main": list(record.main),
                "side": list(record.side),
                "source": "inline",
            },
            "evaluate_at": scenario_preset["evaluate_at"],
            "evaluator": scenario_preset["evaluator"],
            "experiment_id": experiment_id,
            "information_mode": "complete_information",
            "information_policy": policy.to_experiment_dict(),
            "interruption": interruption,
            "objective": scenario_preset["objective"],
            "player": {"perspective": 0, "starting_player": 0},
            "replay": {"strict_versions": True},
            "scenario": {
                "opening_hand": opening_hand,
                "schema_version": "scenario-v1",
            },
            "schema_version": "0.4",
            "search": {
                "budget": {
                    "max_depth": max_depth,
                    "max_nodes": max_nodes,
                    "max_replays": max_nodes,
                    "max_seconds": max_seconds,
                },
                "parameters": strategy_parameters,
                "strategy": strategy,
            },
            "success_predicate": scenario_preset["success_predicate"],
            "terminal_preference_profile": preference_record.profile.to_dict(),
            "turn_limit": 2,
        }
        try:
            assert_valid_experiment(experiment)
            strategy_from_experiment(experiment)
        except (TypeError, ValueError) as exc:
            raise DesktopServiceError(
                "invalid_composed_experiment",
                "desktop search configuration did not produce a valid Experiment",
            ) from exc
        return {"experiment": experiment}

    def scenario_preflight(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"deck_id", "experiment"}, "scenario.preflight")
        experiment = self._resolved_experiment(payload)
        result = self.preflight(
            experiment,
            external_root=self.external_root,
        )
        return {"experiment": experiment, "preflight": result.to_dict()}

    def job_enqueue_search(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(
            payload,
            {"deck_id", "experiment", "idempotency_key", "priority"},
            "job.enqueue_search",
        )
        experiment = self._resolved_experiment(payload)
        preflight = self.preflight(experiment, external_root=self.external_root)
        if not preflight.ok:
            raise DesktopServiceError(
                "scenario_preflight_failed",
                "search job was not queued because scenario preflight failed",
                details={"preflight": preflight.to_dict()},
            )
        experiment_digest = stable_digest(experiment, prefix="experiment_")
        experiment_path = self.data_root / "experiments" / f"{experiment_digest}.json"
        experiment_path.parent.mkdir(parents=True, exist_ok=True)
        if not experiment_path.exists():
            temporary = experiment_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(experiment, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            temporary.replace(experiment_path)
        spec = JobSpec(
            kind=JobKind.SEARCH,
            idempotency_key=payload["idempotency_key"],
            input_digest=stable_digest(
                {"experiment_digest": experiment_digest}, prefix="jobinput_"
            ),
            payload={
                "experiment_digest": experiment_digest,
                "experiment_id": experiment["experiment_id"],
            },
            priority=payload["priority"],
            retry_policy=JobRetryPolicy(
                attempt_timeout_seconds=self._attempt_timeout(experiment),
            ),
        )
        job = self.job_catalog.create_job(
            spec,
            created_at=_now(),
            actor="desktop_bridge",
        )
        return {
            "job": job.to_dict(),
            "preflight": preflight.to_dict(),
        }

    def job_enqueue_replay_verification(
        self, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        _exact(
            payload,
            {"idempotency_key", "priority", "search_job_id"},
            "job.enqueue_replay_verification",
        )
        search_job_id = payload["search_job_id"]
        if not isinstance(search_job_id, str):
            raise DesktopServiceError(
                "invalid_job_id",
                "search_job_id must be a string",
                path="$.payload.search_job_id",
            )
        try:
            snapshot = self.job_catalog.status_snapshot(search_job_id)
        except KeyError as exc:
            raise DesktopServiceError(
                "job_not_found",
                "search job ID is not present in the desktop catalog",
                path="$.payload.search_job_id",
            ) from exc
        if (
            snapshot.job.kind != JobKind.SEARCH
            or snapshot.job.state != JobState.SUCCEEDED
        ):
            raise DesktopServiceError(
                "verification_not_available",
                "only a succeeded search job can enqueue fresh Replay verification",
                path="$.payload.search_job_id",
            )
        route_artifact = self._single_artifact(snapshot, "route-dsl")
        try:
            route = yaml.safe_load(
                self._read_job_artifact(route_artifact).decode("utf-8")
            )
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise DesktopServiceError(
                "artifact_decode_failed",
                "committed Route artifact could not be decoded",
            ) from exc
        if not isinstance(route, Mapping):
            raise DesktopServiceError(
                "artifact_schema_mismatch",
                "committed Route artifact must decode to an object",
            )
        route_id = route.get("route_id")
        replay = route.get("replay") if isinstance(route.get("replay"), Mapping) else {}
        manifest = (
            replay.get("manifest")
            if isinstance(replay.get("manifest"), Mapping)
            else {}
        )
        manifest_hash = manifest.get("manifest_hash")
        if not isinstance(route_id, str) or not route_id.startswith("route_"):
            raise DesktopServiceError(
                "artifact_schema_mismatch",
                "committed Route ID is invalid",
            )
        if (
            not isinstance(manifest_hash, str)
            or not manifest_hash.startswith("manifest_")
        ):
            raise DesktopServiceError(
                "artifact_schema_mismatch",
                "committed Route replay manifest hash is invalid",
            )
        spec = JobSpec(
            kind=JobKind.REPLAY,
            idempotency_key=payload["idempotency_key"],
            input_digest=stable_digest(
                {
                    "manifest_hash": manifest_hash,
                    "route_id": route_id,
                    "route_sha256": route_artifact.sha256,
                    "search_job_id": search_job_id,
                },
                prefix="jobinput_",
            ),
            payload={
                "replay_manifest_hash": manifest_hash,
                "route_id": route_id,
            },
            priority=payload["priority"],
            dependency_ids=(search_job_id,),
            retry_policy=JobRetryPolicy(attempt_timeout_seconds=300.0),
        )
        job = self.job_catalog.create_job(
            spec,
            created_at=_now(),
            actor="desktop_bridge",
        )
        return {
            "job": job.to_dict(),
            "source": {
                "route_artifact": route_artifact.to_dict(),
                "search_job_id": search_job_id,
                "verification_state": "queued",
            },
        }

    @staticmethod
    def _attempt_timeout(experiment: Mapping[str, Any]) -> float:
        search = experiment.get("search")
        budget = search.get("budget") if isinstance(search, Mapping) else None
        max_seconds = (
            budget.get("max_seconds", 300) if isinstance(budget, Mapping) else 300
        )
        return float(max_seconds) + 60.0

    def job_status(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"job_id"}, "job.status")
        job_id = payload["job_id"]
        if not isinstance(job_id, str):
            raise DesktopServiceError("invalid_job_id", "job_id must be a string")
        try:
            snapshot = self.job_catalog.status_snapshot(job_id)
        except KeyError as exc:
            raise DesktopServiceError(
                "job_not_found",
                "job ID is not present in the desktop catalog",
                path="$.payload.job_id",
            ) from exc
        return snapshot.to_dict()

    def _read_job_artifact(self, artifact: Any) -> bytes:
        base = (self.data_root / "job-store").resolve()
        relative = Path(artifact.path)
        if relative.is_absolute() or ".." in relative.parts:
            raise DesktopServiceError(
                "artifact_path_forbidden",
                "job artifact path is outside the managed store",
            )
        path = (base / relative).resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise DesktopServiceError(
                "artifact_path_forbidden",
                "job artifact path is outside the managed store",
            ) from exc
        if not path.is_file():
            raise DesktopServiceError(
                "artifact_missing",
                "committed job artifact is missing from the managed store",
            )
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise DesktopServiceError(
                "artifact_hash_mismatch",
                "committed job artifact checksum does not match catalog metadata",
            )
        return content

    @staticmethod
    def _single_artifact(snapshot: Any, kind: str) -> Any:
        matches = [
            artifact for artifact in snapshot.artifacts if artifact.kind == kind
        ]
        if len(matches) != 1:
            raise DesktopServiceError(
                "artifact_set_incomplete",
                f"succeeded search job must contain exactly one {kind} artifact",
            )
        return matches[0]

    @staticmethod
    def _terminal_board_projection_source(
        route: Mapping[str, Any],
        terminal_board: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        embedded_summary = terminal_board.get("board_summary")
        if isinstance(embedded_summary, Mapping):
            return embedded_summary
        if "public_cards" in terminal_board:
            return terminal_board
        checkpoint_step = terminal_board.get("checkpoint_step")
        checkpoints = route.get("checkpoints")
        if isinstance(checkpoint_step, int) and isinstance(checkpoints, list):
            for checkpoint in checkpoints:
                if not isinstance(checkpoint, Mapping):
                    continue
                if checkpoint.get("step") != checkpoint_step:
                    continue
                board_summary = checkpoint.get("board_summary")
                if isinstance(board_summary, Mapping):
                    return board_summary
        raise ValueError(
            "terminal preference evaluation requires terminal board public_cards"
        )

    def _presented_cards(self, codes: Sequence[int]) -> list[dict[str, Any]]:
        return [
            {
                **self._card_presentation_summary(int(code)),
                "card_code": int(code),
            }
            for code in codes
        ]

    def _opening_hand_summary(
        self, route_experiment: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        scenario = (
            route_experiment.get("scenario")
            if isinstance(route_experiment, Mapping)
            else None
        )
        opening = (
            scenario.get("opening_hand")
            if isinstance(scenario, Mapping)
            and isinstance(scenario.get("opening_hand"), Mapping)
            else None
        )
        if not isinstance(opening, Mapping):
            return {
                "cards": [],
                "explainability": "missing",
                "message": "初期手札情報がartifactに含まれていません。",
                "mode": "unknown",
                "seed": None,
                "size": None,
            }
        mode = str(opening.get("mode", "unknown"))
        raw_cards = opening.get("cards")
        cards: list[int] = []
        if isinstance(raw_cards, list):
            cards = [
                int(card)
                for card in raw_cards
                if isinstance(card, int) and not isinstance(card, bool)
            ]
        explainability = "resolved" if cards else "condition_only"
        if mode == "random" and not cards:
            explainability = "seed_only"
        if mode == "conditional" and not cards:
            explainability = "condition_only"
        return {
            "cards": self._presented_cards(cards),
            "conditions": to_canonical_data(opening.get("conditions", [])),
            "explainability": explainability,
            "max_attempts": opening.get("max_attempts"),
            "message": (
                "初期手札カードまで確定しています。"
                if cards
                else "初期手札カードは未解決です。seedまたは条件だけを表示しています。"
            ),
            "mode": mode,
            "seed": opening.get("seed"),
            "size": opening.get("size"),
        }

    def _board_snapshot(
        self,
        *,
        label: str,
        route: Mapping[str, Any],
        board: Mapping[str, Any] | None,
        fallback: Mapping[str, Any],
        score: Any,
    ) -> dict[str, Any]:
        source = board if isinstance(board, Mapping) and board else fallback
        try:
            projection_source = self._terminal_board_projection_source(route, source)
        except (TypeError, ValueError):
            return {
                "available": False,
                "cards": [],
                "label": label,
                "message": "盤面snapshotがartifactから復元できません。",
                "score": score,
                "state_hash": source.get("state_hash") if isinstance(source, Mapping) else None,
            }
        public_cards = projection_source.get("public_cards")
        cards: list[dict[str, Any]] = []
        if isinstance(public_cards, list):
            for card in public_cards:
                if not isinstance(card, Mapping):
                    continue
                code = card.get("code")
                presented = (
                    self._card_presentation_summary(code)
                    if isinstance(code, int) and not isinstance(code, bool)
                    else {
                        "availability": "unavailable",
                        "card_code": code,
                        "name_ja": None,
                        "presentation_id": None,
                        "resolved_locale": None,
                    }
                )
                cards.append({**to_canonical_data(card), **presented})
        return {
            "available": True,
            "cards": cards,
            "label": label,
            "message": "artifact内の公開盤面snapshotです。",
            "score": score,
            "state_hash": projection_source.get("state_hash") or source.get("state_hash"),
        }

    def job_result(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"job_id"}, "job.result")
        job_id = payload["job_id"]
        if not isinstance(job_id, str):
            raise DesktopServiceError("invalid_job_id", "job_id must be a string")
        try:
            snapshot = self.job_catalog.status_snapshot(job_id)
        except KeyError as exc:
            raise DesktopServiceError(
                "job_not_found",
                "job ID is not present in the desktop catalog",
                path="$.payload.job_id",
            ) from exc
        if (
            snapshot.job.kind != JobKind.SEARCH
            or snapshot.job.state != JobState.SUCCEEDED
        ):
            raise DesktopServiceError(
                "result_not_available",
                "only a succeeded search job can expose a result view",
            )
        if snapshot.job.artifact_set_id is None:
            raise DesktopServiceError(
                "artifact_set_incomplete",
                "succeeded search job is missing its artifact set identity",
            )
        route_artifact = self._single_artifact(snapshot, "route-dsl")
        report_artifact = self._single_artifact(snapshot, "search-run-report")
        route_content = self._read_job_artifact(route_artifact)
        report_content = self._read_job_artifact(report_artifact)
        try:
            route = yaml.safe_load(route_content.decode("utf-8"))
            report = json.loads(report_content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
            raise DesktopServiceError(
                "artifact_decode_failed",
                "committed job artifact could not be decoded",
            ) from exc
        if not isinstance(route, Mapping) or not isinstance(report, Mapping):
            raise DesktopServiceError(
                "artifact_schema_mismatch",
                "committed result artifacts must decode to objects",
            )
        route_id = route.get("route_id")
        best_route = report.get("best_route")
        artifact_commit = report.get("artifact_commit")
        if not isinstance(route_id, str) or not route_id.startswith("route_"):
            raise DesktopServiceError("artifact_schema_mismatch", "Route ID is invalid")
        if (
            not isinstance(best_route, Mapping)
            or best_route.get("route_id") != route_id
        ):
            raise DesktopServiceError(
                "artifact_identity_mismatch",
                "search report best Route does not match the committed Route",
            )
        if (
            report.get("report_schema_version") != report_artifact.schema_version
            or report.get("status") != "complete"
            or not isinstance(artifact_commit, Mapping)
            or artifact_commit.get("schema_version") != "search-artifact-commit-v1"
            or artifact_commit.get("status") != "committed"
            or artifact_commit.get("route_id") != route_id
            or artifact_commit.get("route_sha256") != route_artifact.sha256
        ):
            raise DesktopServiceError(
                "artifact_identity_mismatch",
                "search report artifact commit does not match catalog metadata",
            )
        randomness_summary = build_route_randomness_summary(route)
        recorded_randomness = best_route.get("randomness_summary")
        if recorded_randomness is not None and to_canonical_data(
            recorded_randomness
        ) != randomness_summary:
            raise DesktopServiceError(
                "artifact_identity_mismatch",
                "search report randomness summary does not match committed Route",
            )
        route_ranking = report.get("route_ranking")
        if route_ranking is not None:
            raw_routes = report.get("routes")
            if not isinstance(route_ranking, Mapping) or not isinstance(raw_routes, list):
                raise DesktopServiceError(
                    "artifact_schema_mismatch",
                    "search report ranking requires route summaries",
                )
            unique_route_summaries: list[Mapping[str, Any]] = []
            seen_route_ids: set[str] = set()
            for route_summary in raw_routes:
                if not isinstance(route_summary, Mapping):
                    continue
                summary_route_id = route_summary.get("route_id")
                if not isinstance(summary_route_id, str):
                    continue
                if summary_route_id in seen_route_ids:
                    continue
                seen_route_ids.add(summary_route_id)
                unique_route_summaries.append(route_summary)
            committed_summaries = [
                route_summary
                for route_summary in unique_route_summaries
                if route_summary.get("route_id") == route_id
            ]
            if len(committed_summaries) != 1:
                raise DesktopServiceError(
                    "artifact_identity_mismatch",
                    "search report ranking must include the committed best Route",
                )
            committed_summary = committed_summaries[0]
            summary_randomness = committed_summary.get("randomness_summary")
            if (
                route_ranking.get("best_route_id") != route_id
                or committed_summary.get("success") != best_route.get("success")
                or committed_summary.get("terminal_score")
                != best_route.get("terminal_score")
                or committed_summary.get("peak_score") != best_route.get("peak_score")
                or to_canonical_data(summary_randomness) != randomness_summary
            ):
                raise DesktopServiceError(
                    "artifact_identity_mismatch",
                    "search report ranking summary does not match committed best Route",
                )
            try:
                expected_ranking = rank_route_candidates(
                    [
                        {
                            "action_count": route_summary.get("action_count"),
                            "peak_score": route_summary.get("peak_score"),
                            "randomness_summary": route_summary.get(
                                "randomness_summary"
                            ),
                            "route_id": route_summary.get("route_id"),
                            "success": route_summary.get("success"),
                            "terminal_composite_score": route_summary.get(
                                "terminal_score"
                            ),
                        }
                        for route_summary in unique_route_summaries
                    ],
                    policy=RouteRankingPolicy(),
                )
            except ValueError as exc:
                raise DesktopServiceError(
                    "artifact_schema_mismatch",
                    "search report ranking cannot be recomputed",
                ) from exc
            if to_canonical_data(route_ranking) != expected_ranking:
                raise DesktopServiceError(
                    "artifact_identity_mismatch",
                    "search report ranking does not match route summaries",
                )
        result = route.get("result") if isinstance(route.get("result"), Mapping) else {}
        terminal_board = (
            result.get("terminal_board")
            if isinstance(result.get("terminal_board"), Mapping)
            else {}
        )
        peak_board = (
            result.get("peak_board")
            if isinstance(result.get("peak_board"), Mapping)
            else None
        )
        replay = route.get("replay") if isinstance(route.get("replay"), Mapping) else {}
        events = replay.get("events") if isinstance(replay.get("events"), list) else []
        actions = []
        for index, event in enumerate(events[:100], start=1):
            action = event.get("action") if isinstance(event, Mapping) else None
            request = event.get("request") if isinstance(event, Mapping) else None
            actions.append(
                {
                    "index": index,
                    "action_id": (
                        action.get("action_id")
                        if isinstance(action, Mapping)
                        else event.get("action_id")
                        if isinstance(event, Mapping)
                        else None
                    ),
                    "decision_kind": (
                        request.get("kind")
                        if isinstance(request, Mapping)
                        else event.get("decision_kind")
                        if isinstance(event, Mapping)
                        else None
                    ),
                    "state_hash_after": (
                        event.get("state_hash_after")
                        if isinstance(event, Mapping)
                        else None
                    ),
                }
            )
        preference_evaluation = best_route.get("terminal_preference_evaluation")
        if preference_evaluation is not None and not isinstance(
            preference_evaluation, Mapping
        ):
            raise DesktopServiceError(
                "artifact_schema_mismatch",
                "search report terminal preference evaluation must be an object",
            )
        route_experiment = route.get("experiment")
        if isinstance(route_experiment, Mapping) and isinstance(
            route_experiment.get("terminal_preference_profile"), Mapping
        ):
            try:
                profile = TerminalPreferenceProfile.from_mapping(
                    {
                        "name": route_experiment[
                            "terminal_preference_profile"
                        ].get("name"),
                        "rules": route_experiment[
                            "terminal_preference_profile"
                        ].get("rules"),
                        "schema_version": route_experiment[
                            "terminal_preference_profile"
                        ].get("schema_version"),
                    }
                )
                if profile.rules:
                    projection_source = self._terminal_board_projection_source(
                        route,
                        terminal_board,
                    )
                    projection = build_terminal_board_projection(projection_source)
                    expected_preference = evaluate_terminal_preferences(
                        projection,
                        profile,
                        base_score=best_route.get(
                            "score",
                            terminal_board.get("score"),
                        ),
                    )
                    if to_canonical_data(preference_evaluation) != expected_preference:
                        raise DesktopServiceError(
                            "artifact_identity_mismatch",
                            "search report terminal preference evaluation does not match committed Route",
                        )
                    if (
                        best_route.get("terminal_score")
                        != expected_preference.get("terminal_composite_score")
                    ):
                        raise DesktopServiceError(
                            "artifact_identity_mismatch",
                            "search report terminal score does not match terminal preference evaluation",
                        )
                elif preference_evaluation is not None:
                    raise DesktopServiceError(
                        "artifact_identity_mismatch",
                        "empty terminal preference profile must not publish preference evaluation",
                    )
            except DesktopServiceError:
                raise
            except (TypeError, ValueError) as exc:
                raise DesktopServiceError(
                    "artifact_schema_mismatch",
                    "committed Route terminal preference profile cannot be evaluated",
                ) from exc
        score = best_route.get(
            "terminal_score",
            best_route.get("score", terminal_board.get("score")),
        )
        base_score = (
            preference_evaluation.get("base_score")
            if isinstance(preference_evaluation, Mapping)
            else best_route.get("score", terminal_board.get("score"))
        )
        peak_score = best_route.get("peak_score", score)
        route_experiment = (
            route.get("experiment") if isinstance(route.get("experiment"), Mapping) else {}
        )
        search_config = (
            route_experiment.get("search")
            if isinstance(route_experiment.get("search"), Mapping)
            else {}
        )
        search_budget = (
            search_config.get("budget")
            if isinstance(search_config.get("budget"), Mapping)
            else {}
        )
        coverage = (
            report.get("coverage")
            if isinstance(report.get("coverage"), Mapping)
            else {}
        )
        coverage_candidate_counts: dict[str, int] | None = None
        if coverage:
            coverage_identity = {
                key: value for key, value in coverage.items() if key != "coverage_id"
            }
            if coverage.get("coverage_id") != stable_digest(
                coverage_identity,
                prefix="searchcoverage_",
            ):
                raise DesktopServiceError(
                    "artifact_identity_mismatch",
                    "search report coverage certificate content ID is invalid",
                )
            _validate_coverage_certificate(coverage)
            raw_coverage_counts = coverage.get("candidate_counts")
            if isinstance(raw_coverage_counts, Mapping):
                coverage_candidate_counts = _candidate_counts_from_mapping(
                    raw_coverage_counts,
                    "candidate_counts",
                )
        search_evidence = (
            report.get("search_evidence")
            if isinstance(report.get("search_evidence"), Mapping)
            else {}
        )
        search_candidate_counts: dict[str, int] | None = None
        if search_evidence:
            evidence_identity = {
                key: value
                for key, value in search_evidence.items()
                if key != "evidence_id"
            }
            if search_evidence.get("evidence_id") != stable_digest(
                evidence_identity,
                prefix="searchev_",
            ):
                raise DesktopServiceError(
                    "artifact_identity_mismatch",
                    "search report candidate evidence content ID is invalid",
                )
            search_candidate_counts = _validate_candidate_evidence(search_evidence)
        if (
            coverage_candidate_counts is not None
            and search_candidate_counts is not None
            and coverage_candidate_counts != search_candidate_counts
        ):
            raise DesktopServiceError(
                "artifact_identity_mismatch",
                "search report coverage counts do not match candidate evidence",
            )
        candidate_records = (
            search_evidence.get("candidates")
            if isinstance(search_evidence.get("candidates"), list)
            else []
        )
        return to_canonical_data(
            {
                "artifact_set_id": snapshot.job.artifact_set_id,
                "artifacts": {
                    "report": report_artifact.to_dict(),
                    "route": route_artifact.to_dict(),
                },
                "job_id": job_id,
                "result_truth": {
                    "randomness_summary_id": randomness_summary["summary_id"],
                    "ranking_id": (
                        route_ranking.get("ranking_id")
                        if isinstance(route_ranking, Mapping)
                        else None
                    ),
                    "source": "committed_job_artifacts",
                    "synthetic": False,
                    "verification_state": "unverified",
                },
                "route": {
                    "action_count": len(events),
                    "actions": actions,
                    "opening_hand": self._opening_hand_summary(route_experiment),
                    "peak_board": self._board_snapshot(
                        label="peak_board",
                        route=route,
                        board=peak_board,
                        fallback=terminal_board,
                        score=peak_score,
                    ),
                    "randomness_summary": randomness_summary,
                    "route_id": route_id,
                    "success": bool(best_route.get("success", False)),
                    "terminal_board": dict(terminal_board),
                },
                "schema_version": DESKTOP_RESULT_VIEW_VERSION,
                "score": {
                    "base": base_score,
                    "peak": peak_score,
                    "preference": (
                        preference_evaluation.get("components", [])
                        if isinstance(preference_evaluation, Mapping)
                        else []
                    ),
                    "preference_evaluation": (
                        to_canonical_data(preference_evaluation)
                        if isinstance(preference_evaluation, Mapping)
                        else None
                    ),
                    "randomness_penalty": (
                        preference_evaluation.get("randomness_penalty", 0)
                        if isinstance(preference_evaluation, Mapping)
                        else 0
                    ),
                    "terminal_composite": score,
                },
                "search_run": {
                    "best_observed": not bool(coverage.get("frontier_exhausted")),
                    "candidate_evidence": (
                        {
                            "candidate_counts": search_evidence.get(
                                "candidate_counts",
                                {},
                            ),
                            "candidates": candidate_records[:100],
                            "evidence_id": search_evidence.get("evidence_id"),
                            "schema_version": search_evidence.get("schema_version"),
                            "total": len(candidate_records),
                        }
                        if search_evidence
                        else None
                    ),
                    "coverage": (
                        to_canonical_data(coverage) if coverage else None
                    ),
                    "budget": to_canonical_data(search_budget),
                    "nodes": report.get("nodes"),
                    "route_ranking": (
                        to_canonical_data(route_ranking)
                        if isinstance(route_ranking, Mapping)
                        else None
                    ),
                    "replays": report.get("replays"),
                    "run_id": report.get("run_id"),
                    "status": report.get("status"),
                    "termination_reason": report.get("termination_reason"),
                },
            }
        )

    def job_cancel(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"job_id"}, "job.cancel")
        job_id = payload["job_id"]
        if not isinstance(job_id, str):
            raise DesktopServiceError("invalid_job_id", "job_id must be a string")
        existing = self.job_catalog.get_job(job_id)
        if existing is None:
            raise DesktopServiceError("job_not_found", "job ID is not present")
        requested = self.job_catalog.request_cancel(
            job_id,
            actor="desktop_bridge",
            now=_now(),
            reason="renderer_requested_cancel",
        )
        if (
            existing.state == JobState.QUEUED
            and requested.attempt == 0
            and requested.lease_token is None
        ):
            requested = self.job_catalog.finish_cancelled(
                job_id,
                actor="desktop_bridge",
                now=_now(),
                reason="cancelled_before_worker_claim",
            )
        return {"job": requested.to_dict()}

    def analytics_query(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"request"}, "analytics.query")
        request = AnalyticsQueryRequest.from_mapping(payload["request"])
        return self.analytics_service.execute(request).to_dict()

    def analytics_export_enqueue(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(
            payload,
            {"format", "idempotency_key", "priority", "source", "source_kind"},
            "analytics.export.enqueue",
        )
        try:
            export_format = AnalyticsExportFormat(payload["format"])
            source_kind = AnalyticsExportSourceKind(payload["source_kind"])
        except (TypeError, ValueError) as exc:
            raise DesktopServiceError(
                "invalid_export_request",
                "analytics export format or source kind is unsupported",
            ) from exc
        source = payload["source"]
        if not isinstance(source, Mapping):
            raise DesktopServiceError(
                "invalid_export_request",
                "analytics export source must be an object",
            )
        if source_kind == AnalyticsExportSourceKind.QUERY:
            request = AnalyticsExportRequest(
                format=export_format,
                source_kind=source_kind,
                query=AnalyticsQueryRequest.from_mapping(source),
            )
        else:
            if self.comparison_handler is None:
                raise DesktopServiceError(
                    "comparison_source_unavailable",
                    "no validated comparison observation source is configured",
                )
            request = AnalyticsExportRequest(
                format=export_format,
                source_kind=source_kind,
                comparison=self.comparison_handler(source),
            )
        idempotency_key = payload["idempotency_key"]
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not idempotency_key
        ):
            raise DesktopServiceError(
                "invalid_export_request",
                "idempotency_key must be null or a non-empty string",
            )
        priority = payload["priority"]
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise DesktopServiceError(
                "invalid_export_request", "priority must be an integer"
            )
        bound_request = self.analytics_export_service.bind_request(request)
        job = self.analytics_export_queue.enqueue(
            bound_request,
            created_at=_now(),
            idempotency_key=idempotency_key,
            priority=priority,
        )
        return {
            "export_request_id": bound_request.request_id,
            "job": job.to_dict(),
        }

    def analytics_compare(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"request"}, "analytics.compare")
        if self.comparison_handler is None:
            raise DesktopServiceError(
                "comparison_source_unavailable",
                "no validated comparison observation source is configured",
            )
        return self.comparison_handler(payload["request"])

    def card_get(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, {"query"}, "card.get")
        if self.card_provider is None:
            raise DesktopServiceError(
                "card_presentation_source_unavailable",
                "no verified local card-presentation source is configured",
            )
        query = payload["query"]
        if not isinstance(query, Mapping):
            raise DesktopServiceError(
                "invalid_card_query",
                "card query must be an object",
            )
        expected = {
            "card_code",
            "expected_asset_lock_id",
            "expected_provider_version",
            "fallback_locales",
            "redacted",
            "requested_locale",
            "schema_version",
        }
        if set(query) != expected:
            raise DesktopServiceError(
                "invalid_card_query",
                f"card query fields must be exactly {sorted(expected)}",
            )
        presentation = self.card_provider.get_card(
            CardPresentationQuery(
                card_code=query["card_code"],
                requested_locale=query["requested_locale"],
                fallback_locales=tuple(query["fallback_locales"]),
                redacted=query["redacted"],
                expected_asset_lock_id=query["expected_asset_lock_id"],
                expected_provider_version=query["expected_provider_version"],
                schema_version=query["schema_version"],
            )
        )
        return presentation.to_dict()


__all__ = [
    "DESKTOP_DECK_CATALOG_VERSION",
    "DESKTOP_DECK_TERMINAL_PROFILE_CATALOG_VERSION",
    "DESKTOP_RESULT_VIEW_VERSION",
    "DESKTOP_SERVICE_VERSION",
    "DesktopApplicationService",
    "DesktopDeckCatalog",
    "DesktopDeckRecord",
    "DesktopDeckTerminalProfileCatalog",
    "DesktopDeckTerminalProfileRecord",
]
