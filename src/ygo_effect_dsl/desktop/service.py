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

from ygo_effect_dsl.desktop.bridge import DesktopHandler, DesktopServiceError
from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.engine.information import InformationAccessPolicy
from ygo_effect_dsl.engine.search import strategy_from_experiment
from ygo_effect_dsl.experiment.schema import assert_valid_experiment
from ygo_effect_dsl.experiment.scenario import parse_ydk, preflight_scenario
from ygo_effect_dsl.presentation import CardPresentationQuery
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
DESKTOP_SERVICE_VERSION = "desktop-application-service-v1"
MAX_CATALOG_DECKS = 10_000
MAX_DESKTOP_SEARCH_NODES = 100_000
MAX_DESKTOP_SEARCH_DEPTH = 256
MAX_DESKTOP_SEARCH_SECONDS = 3_600.0


class YdkPicker(Protocol):
    def __call__(self) -> str | Path | None: ...


class CardProvider(Protocol):
    def get_card(self, query: CardPresentationQuery) -> Any: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    ) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.external_root = (
            Path(external_root).expanduser().resolve()
            if external_root is not None
            else None
        )
        self.deck_catalog = DesktopDeckCatalog(self.data_root / "decks.json")
        self.job_catalog = JobCatalog(self.data_root / "jobs.sqlite3")
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
        if analytics_service is None:
            snapshots = AnalyticsSnapshotStore()
            snapshots.register(AnalyticsSnapshot(rows=()))
            analytics_service = AnalyticsQueryService(snapshots)
        self.analytics_service = analytics_service

    def handlers(self) -> dict[str, DesktopHandler]:
        return {
            "analytics.compare": self.analytics_compare,
            "analytics.query": self.analytics_query,
            "card.get": self.card_get,
            "deck.catalog": self.deck_catalog_list,
            "deck.import_ydk": self.deck_import_ydk,
            "deck.register_inline": self.deck_register_inline,
            "job.cancel": self.job_cancel,
            "job.enqueue_search": self.job_enqueue_search,
            "job.status": self.job_status,
            "scenario.compose_search": self.scenario_compose_search,
            "scenario.preflight": self.scenario_preflight,
            "system.describe": self.system_describe,
        }

    def system_describe(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _exact(payload, set(), "system.describe")
        return {
            "capabilities": {
                "analytics_query": True,
                "card_presentation": self.card_provider is not None,
                "comparison": self.comparison_handler is not None,
                "native_ydk_import": self.ydk_picker is not None,
                "search_job_queue": True,
                "worker_execution": self.worker_execution,
                "worker_health": (
                    self.worker_health()
                    if self.worker_health is not None
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
            "decks": [item.summary() for item in records],
            "schema_version": DESKTOP_DECK_CATALOG_VERSION,
            "total": len(records),
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
        return {"cancelled": False, "deck": record.summary()}

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
        return {"deck": record.summary()}

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
        if set(configuration) != expected:
            raise DesktopServiceError(
                "invalid_search_configuration",
                f"configuration fields must be exactly {sorted(expected)}",
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
            "experiment_id": experiment_id,
            "information_mode": "complete_information",
            "information_policy": policy.to_experiment_dict(),
            "interruption": interruption,
            "objective": "maximize_terminal_board",
            "player": {"perspective": 0, "starting_player": 0},
            "replay": {"strict_versions": True},
            "scenario": {
                "opening_hand": {"mode": "random", "seed": seed, "size": 5},
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
            "success_predicate": {
                "config": {"min_count": 1, "player": 0, "zone": "monster_zone"},
                "id": "real_core_min_monster_count",
                "version": "1",
            },
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
    "DESKTOP_SERVICE_VERSION",
    "DesktopApplicationService",
    "DesktopDeckCatalog",
    "DesktopDeckRecord",
]
