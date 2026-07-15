from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)


CORPUS_MANIFEST_SCHEMA_VERSION = "corpus-manifest-v1"
CORPUS_CATALOG_SCHEMA_VERSION = "corpus-catalog-v1"
CORPUS_VALIDATION_SCHEMA_VERSION = "corpus-manifest-validation-v1"
CORPUS_INGEST_RESULT_SCHEMA_VERSION = "corpus-ingest-result-v1"

_ARTIFACT_KINDS = {
    "qualified_route_bundle",
    "replay_verification",
    "route",
    "search_run",
}
_SOURCE_KINDS = {"generated_artifact", "import_bundle", "local_file"}
_INFORMATION_MODES = {"complete_information", "player_view"}


class CorpusItemStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    CORRUPT = "corrupt"
    QUARANTINED = "quarantined"


class CorpusIngestStatus(str, Enum):
    INGESTED = "ingested"
    EXACT_DUPLICATE = "exact_duplicate"
    SEMANTIC_DUPLICATE = "semantic_duplicate"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class CorpusDiagnostic:
    code: str
    path: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "severity": self.severity,
        }


class _CorpusValidationError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        super().__init__(message)
        self.diagnostic = CorpusDiagnostic(code, path, message)


def _fail(code: str, path: str, message: str) -> None:
    raise _CorpusValidationError(code, path, message)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("invalid_type", path, "must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    observed = set(value)
    if observed != expected:
        _fail(
            "invalid_fields",
            path,
            f"fields must be exactly {sorted(expected)}; observed {sorted(observed)}",
        )


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("invalid_string", path, "must be a non-empty string")
    return value


def _choice(value: Any, path: str, choices: set[str]) -> str:
    observed = _string(value, path)
    if observed not in choices:
        _fail(
            "unsupported_value",
            path,
            f"must be one of {sorted(choices)}",
        )
    return observed


def _sha256(value: Any, path: str) -> str:
    observed = _string(value, path)
    if len(observed) != 64 or any(
        character not in "0123456789abcdef" for character in observed
    ):
        _fail("invalid_sha256", path, "must be 64 lowercase hexadecimal characters")
    return observed


def _commit(value: Any, path: str) -> str:
    observed = _string(value, path)
    if len(observed) != 40 or any(
        character not in "0123456789abcdef" for character in observed
    ):
        _fail("invalid_commit", path, "must be 40 lowercase hexadecimal characters")
    return observed


def _content_id(value: Any, path: str, prefix: str) -> str:
    observed = _string(value, path)
    if not observed.startswith(prefix):
        _fail("invalid_content_id", path, f"must start with {prefix!r}")
    _sha256(observed[len(prefix) :], path)
    return observed


def _timestamp(value: Any, path: str) -> str:
    observed = _string(value, path)
    if not observed.endswith("Z"):
        _fail(
            "invalid_timestamp",
            path,
            "must be an ISO-8601 UTC timestamp ending in Z",
        )
    try:
        parsed = datetime.fromisoformat(observed[:-1] + "+00:00")
    except ValueError:
        _fail(
            "invalid_timestamp",
            path,
            "must be an ISO-8601 UTC timestamp ending in Z",
        )
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        _fail("invalid_timestamp", path, "must use UTC")
    return observed


def _id_sequence(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("invalid_type", path, "must be a sequence")
    result = tuple(
        _content_id(item, f"{path}[{index}]", "corpusitem_")
        for index, item in enumerate(value)
    )
    if len(result) != len(set(result)):
        _fail("duplicate_parent", path, "must not contain duplicate item IDs")
    return result


@dataclass(frozen=True)
class CorpusProvenance:
    package_version: str
    experiment: Mapping[str, Any]
    scenario: Mapping[str, Any]
    deck: Mapping[str, Any]
    search: Mapping[str, Any]
    replay: Mapping[str, Any]
    route: Mapping[str, Any]
    evaluator: Mapping[str, Any]
    core: Mapping[str, Any]
    assets: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "assets": self.assets,
                "core": self.core,
                "deck": self.deck,
                "evaluator": self.evaluator,
                "experiment": self.experiment,
                "package_version": self.package_version,
                "replay": self.replay,
                "route": self.route,
                "scenario": self.scenario,
                "search": self.search,
            }
        )

    @classmethod
    def from_mapping(cls, value: Any, path: str = "$.provenance") -> "CorpusProvenance":
        document = _mapping(value, path)
        _exact_keys(
            document,
            {
                "assets",
                "core",
                "deck",
                "evaluator",
                "experiment",
                "package_version",
                "replay",
                "route",
                "scenario",
                "search",
            },
            path,
        )
        package_version = _string(
            document.get("package_version"), f"{path}.package_version"
        )

        experiment = _mapping(document.get("experiment"), f"{path}.experiment")
        _exact_keys(
            experiment,
            {"digest", "id", "schema_version"},
            f"{path}.experiment",
        )
        _string(experiment.get("id"), f"{path}.experiment.id")
        _content_id(
            experiment.get("digest"),
            f"{path}.experiment.digest",
            "experiment_",
        )
        _string(experiment.get("schema_version"), f"{path}.experiment.schema_version")

        scenario = _mapping(document.get("scenario"), f"{path}.scenario")
        _exact_keys(scenario, {"manifest_id", "schema_version"}, f"{path}.scenario")
        _content_id(
            scenario.get("manifest_id"),
            f"{path}.scenario.manifest_id",
            "scenariomanifest_",
        )
        _string(scenario.get("schema_version"), f"{path}.scenario.schema_version")

        deck = _mapping(document.get("deck"), f"{path}.deck")
        _exact_keys(deck, {"id", "opening_hand_id", "sha256", "source"}, f"{path}.deck")
        _string(deck.get("id"), f"{path}.deck.id")
        _sha256(deck.get("sha256"), f"{path}.deck.sha256")
        _choice(deck.get("source"), f"{path}.deck.source", {"fixed", "inline", "ydk"})
        _content_id(
            deck.get("opening_hand_id"),
            f"{path}.deck.opening_hand_id",
            "hand_",
        )

        search = _mapping(document.get("search"), f"{path}.search")
        _exact_keys(
            search,
            {
                "executor_schema_version",
                "result_schema_version",
                "run_id",
                "strategy_id",
                "strategy_schema_version",
            },
            f"{path}.search",
        )
        _content_id(search.get("run_id"), f"{path}.search.run_id", "searchrun_")
        for field in (
            "executor_schema_version",
            "result_schema_version",
            "strategy_id",
            "strategy_schema_version",
        ):
            _string(search.get(field), f"{path}.search.{field}")

        replay = _mapping(document.get("replay"), f"{path}.replay")
        _exact_keys(
            replay,
            {
                "manifest_hash",
                "manifest_schema_version",
                "terminal_state_id",
                "verification_id",
            },
            f"{path}.replay",
        )
        _content_id(
            replay.get("verification_id"),
            f"{path}.replay.verification_id",
            "replayverify_",
        )
        _content_id(
            replay.get("manifest_hash"),
            f"{path}.replay.manifest_hash",
            "manifest_",
        )
        _string(
            replay.get("manifest_schema_version"),
            f"{path}.replay.manifest_schema_version",
        )
        _content_id(
            replay.get("terminal_state_id"),
            f"{path}.replay.terminal_state_id",
            "state_",
        )

        route = _mapping(document.get("route"), f"{path}.route")
        _exact_keys(route, {"document_digest", "id", "schema_version"}, f"{path}.route")
        _content_id(route.get("id"), f"{path}.route.id", "route_")
        _content_id(
            route.get("document_digest"),
            f"{path}.route.document_digest",
            "routedoc_",
        )
        _string(route.get("schema_version"), f"{path}.route.schema_version")

        evaluator = _mapping(document.get("evaluator"), f"{path}.evaluator")
        _exact_keys(evaluator, {"config_hash", "id", "version"}, f"{path}.evaluator")
        _string(evaluator.get("id"), f"{path}.evaluator.id")
        _string(evaluator.get("version"), f"{path}.evaluator.version")
        _content_id(
            evaluator.get("config_hash"),
            f"{path}.evaluator.config_hash",
            "evalcfg_",
        )

        core = _mapping(document.get("core"), f"{path}.core")
        _exact_keys(
            core,
            {"api", "binary_sha256", "lock_id", "source_commit"},
            f"{path}.core",
        )
        _string(core.get("api"), f"{path}.core.api")
        _sha256(core.get("binary_sha256"), f"{path}.core.binary_sha256")
        _string(core.get("lock_id"), f"{path}.core.lock_id")
        _commit(core.get("source_commit"), f"{path}.core.source_commit")

        assets = _mapping(document.get("assets"), f"{path}.assets")
        _exact_keys(
            assets,
            {"card_scripts_commit", "database_sha256", "lock_id"},
            f"{path}.assets",
        )
        _string(assets.get("lock_id"), f"{path}.assets.lock_id")
        _sha256(assets.get("database_sha256"), f"{path}.assets.database_sha256")
        _commit(
            assets.get("card_scripts_commit"),
            f"{path}.assets.card_scripts_commit",
        )

        return cls(
            package_version=package_version,
            experiment=to_canonical_data(experiment),
            scenario=to_canonical_data(scenario),
            deck=to_canonical_data(deck),
            search=to_canonical_data(search),
            replay=to_canonical_data(replay),
            route=to_canonical_data(route),
            evaluator=to_canonical_data(evaluator),
            core=to_canonical_data(core),
            assets=to_canonical_data(assets),
        )


@dataclass(frozen=True)
class CorpusItemManifest:
    content_sha256: str
    artifact_kind: str
    ingested_at: str
    source: Mapping[str, Any]
    provenance: CorpusProvenance
    information: Mapping[str, Any]
    status: CorpusItemStatus
    parent_item_ids: tuple[str, ...] = ()
    schema_version: str = CORPUS_MANIFEST_SCHEMA_VERSION

    @property
    def semantic_id(self) -> str:
        return stable_digest(
            {
                "artifact_kind": self.artifact_kind,
                "information": self.information,
                "parent_item_ids": list(self.parent_item_ids),
                "provenance": self.provenance.to_dict(),
            },
            prefix="corpussemantic_",
        )

    @property
    def corpus_item_id(self) -> str:
        return stable_digest(
            {
                "artifact_kind": self.artifact_kind,
                "content_sha256": self.content_sha256,
                "semantic_id": self.semantic_id,
            },
            prefix="corpusitem_",
        )

    @property
    def aggregate_eligible(self) -> bool:
        return self.status == CorpusItemStatus.COMPLETE

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "artifact_kind": self.artifact_kind,
                "content_sha256": self.content_sha256,
                "corpus_item_id": self.corpus_item_id,
                "information": self.information,
                "ingested_at": self.ingested_at,
                "parent_item_ids": list(self.parent_item_ids),
                "provenance": self.provenance.to_dict(),
                "schema_version": self.schema_version,
                "semantic_id": self.semantic_id,
                "source": self.source,
                "status": self.status.value,
            }
        )

    @classmethod
    def from_mapping(cls, value: Any) -> "CorpusItemManifest":
        document = _mapping(value, "$")
        _exact_keys(
            document,
            {
                "artifact_kind",
                "content_sha256",
                "corpus_item_id",
                "information",
                "ingested_at",
                "parent_item_ids",
                "provenance",
                "schema_version",
                "semantic_id",
                "source",
                "status",
            },
            "$",
        )
        if document.get("schema_version") != CORPUS_MANIFEST_SCHEMA_VERSION:
            _fail(
                "unsupported_schema",
                "$.schema_version",
                f"must be {CORPUS_MANIFEST_SCHEMA_VERSION!r}",
            )

        source = _mapping(document.get("source"), "$.source")
        _exact_keys(
            source,
            {"kind", "third_party_assets_included", "uri"},
            "$.source",
        )
        _choice(source.get("kind"), "$.source.kind", _SOURCE_KINDS)
        _string(source.get("uri"), "$.source.uri")
        if source.get("third_party_assets_included") is not False:
            _fail(
                "third_party_asset_embedded",
                "$.source.third_party_assets_included",
                "corpus manifests may store asset locks but not third-party assets",
            )

        information = _mapping(document.get("information"), "$.information")
        _exact_keys(information, {"mode", "redaction_policy_id"}, "$.information")
        _choice(information.get("mode"), "$.information.mode", _INFORMATION_MODES)
        _string(
            information.get("redaction_policy_id"),
            "$.information.redaction_policy_id",
        )

        try:
            status = CorpusItemStatus(document.get("status"))
        except (TypeError, ValueError):
            _fail(
                "unsupported_status",
                "$.status",
                f"must be one of {[item.value for item in CorpusItemStatus]}",
            )

        manifest = cls(
            content_sha256=_sha256(document.get("content_sha256"), "$.content_sha256"),
            artifact_kind=_choice(
                document.get("artifact_kind"), "$.artifact_kind", _ARTIFACT_KINDS
            ),
            ingested_at=_timestamp(document.get("ingested_at"), "$.ingested_at"),
            source=to_canonical_data(source),
            provenance=CorpusProvenance.from_mapping(document.get("provenance")),
            information=to_canonical_data(information),
            status=status,
            parent_item_ids=_id_sequence(
                document.get("parent_item_ids"), "$.parent_item_ids"
            ),
        )
        if document.get("semantic_id") != manifest.semantic_id:
            _fail(
                "semantic_id_mismatch",
                "$.semantic_id",
                "does not match the manifest semantic identity",
            )
        if document.get("corpus_item_id") != manifest.corpus_item_id:
            _fail(
                "corpus_item_id_mismatch",
                "$.corpus_item_id",
                "does not match the content and semantic identity",
            )
        return manifest


def build_corpus_item_manifest(
    *,
    content: bytes,
    artifact_kind: str,
    ingested_at: str,
    source_kind: str,
    source_uri: str,
    provenance: CorpusProvenance | Mapping[str, Any],
    information_mode: str,
    redaction_policy_id: str,
    status: CorpusItemStatus | str = CorpusItemStatus.COMPLETE,
    parent_item_ids: Sequence[str] = (),
) -> CorpusItemManifest:
    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    parsed_provenance = (
        provenance
        if isinstance(provenance, CorpusProvenance)
        else CorpusProvenance.from_mapping(provenance)
    )
    parsed_status = (
        status if isinstance(status, CorpusItemStatus) else CorpusItemStatus(status)
    )
    provisional = CorpusItemManifest(
        content_sha256=hashlib.sha256(content).hexdigest(),
        artifact_kind=artifact_kind,
        ingested_at=ingested_at,
        source={
            "kind": source_kind,
            "third_party_assets_included": False,
            "uri": source_uri,
        },
        provenance=parsed_provenance,
        information={
            "mode": information_mode,
            "redaction_policy_id": redaction_policy_id,
        },
        status=parsed_status,
        parent_item_ids=tuple(parent_item_ids),
    )
    return CorpusItemManifest.from_mapping(provisional.to_dict())


@dataclass(frozen=True)
class CorpusManifestValidationResult:
    manifest: CorpusItemManifest | None
    diagnostics: tuple[CorpusDiagnostic, ...]
    schema_version: str = CORPUS_VALIDATION_SCHEMA_VERSION

    @property
    def ok(self) -> bool:
        return self.manifest is not None and not self.diagnostics

    @property
    def aggregate_eligible(self) -> bool:
        return (
            self.ok
            and self.manifest is not None
            and self.manifest.aggregate_eligible
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "aggregate_eligible": self.aggregate_eligible,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "manifest": self.manifest.to_dict() if self.manifest is not None else None,
            "ok": self.ok,
            "schema_version": self.schema_version,
        }


def validate_corpus_manifest(value: Any) -> CorpusManifestValidationResult:
    try:
        manifest = CorpusItemManifest.from_mapping(value)
    except _CorpusValidationError as exc:
        return CorpusManifestValidationResult(None, (exc.diagnostic,))
    except (TypeError, ValueError) as exc:
        diagnostic = CorpusDiagnostic(
            "invalid_manifest", "$", str(exc) or exc.__class__.__name__
        )
        return CorpusManifestValidationResult(None, (diagnostic,))
    return CorpusManifestValidationResult(manifest, ())


@dataclass(frozen=True)
class CorpusIngestResult:
    status: CorpusIngestStatus
    corpus_item_id: str | None
    aggregate_eligible: bool
    semantic_duplicate_of: str | None = None
    quarantine_id: str | None = None
    diagnostics: tuple[CorpusDiagnostic, ...] = ()
    schema_version: str = CORPUS_INGEST_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "aggregate_eligible": self.aggregate_eligible,
            "corpus_item_id": self.corpus_item_id,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "quarantine_id": self.quarantine_id,
            "schema_version": self.schema_version,
            "semantic_duplicate_of": self.semantic_duplicate_of,
            "status": self.status.value,
        }


class CorpusCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            has_schema_meta = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
            ).fetchone() is not None
            if has_schema_meta:
                row = connection.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()
                if row is None or row[0] != CORPUS_CATALOG_SCHEMA_VERSION:
                    observed = None if row is None else row[0]
                    raise ValueError(
                        f"corpus catalog schema {observed!r} requires explicit "
                        "migration "
                        f"to {CORPUS_CATALOG_SCHEMA_VERSION!r}"
                    )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS corpus_items (
                    corpus_item_id TEXT PRIMARY KEY,
                    semantic_id TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    artifact_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    aggregate_eligible INTEGER NOT NULL
                        CHECK(aggregate_eligible IN (0, 1)),
                    first_ingested_at TEXT NOT NULL,
                    manifest_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS corpus_items_semantic
                    ON corpus_items(semantic_id, corpus_item_id);
                CREATE TABLE IF NOT EXISTS corpus_sources (
                    corpus_item_id TEXT NOT NULL
                        REFERENCES corpus_items(corpus_item_id),
                    source_uri TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    PRIMARY KEY(corpus_item_id, source_uri)
                );
                CREATE TABLE IF NOT EXISTS corpus_quarantine (
                    quarantine_id TEXT PRIMARY KEY,
                    source_uri TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    raw_content_sha256 TEXT NOT NULL,
                    diagnostic_json TEXT NOT NULL,
                    manifest_json TEXT NOT NULL
                );
                """
            )
            if not has_schema_meta:
                connection.execute(
                    "INSERT INTO schema_meta VALUES ('schema_version', ?)",
                    (CORPUS_CATALOG_SCHEMA_VERSION,),
                )

    def ingest(
        self,
        value: Any,
        *,
        received_at: str,
        source_uri: str | None = None,
    ) -> CorpusIngestResult:
        observed_at = _timestamp(received_at, "received_at")
        validation = validate_corpus_manifest(value)
        if not validation.ok or validation.manifest is None:
            return self._quarantine(
                value,
                diagnostics=validation.diagnostics,
                received_at=observed_at,
                source_uri=source_uri,
            )
        manifest = validation.manifest
        self.initialize()
        manifest_json = canonical_json(manifest.to_dict())
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT status FROM corpus_items WHERE corpus_item_id = ?",
                (manifest.corpus_item_id,),
            ).fetchone()
            if existing is not None:
                if existing["status"] != manifest.status.value:
                    connection.rollback()
                    diagnostic = CorpusDiagnostic(
                        "status_conflict",
                        "$.status",
                        "the same content identity was already ingested with "
                        "another status",
                    )
                    return self._quarantine(
                        value,
                        diagnostics=(diagnostic,),
                        received_at=observed_at,
                        source_uri=source_uri or manifest.source["uri"],
                    )
                connection.execute(
                    "INSERT OR IGNORE INTO corpus_sources VALUES (?, ?, ?, ?)",
                    (
                        manifest.corpus_item_id,
                        manifest.source["uri"],
                        manifest.source["kind"],
                        manifest.ingested_at,
                    ),
                )
                connection.commit()
                return CorpusIngestResult(
                    CorpusIngestStatus.EXACT_DUPLICATE,
                    manifest.corpus_item_id,
                    manifest.aggregate_eligible,
                )

            duplicate = connection.execute(
                """
                SELECT corpus_item_id FROM corpus_items
                WHERE semantic_id = ?
                ORDER BY first_ingested_at, corpus_item_id LIMIT 1
                """,
                (manifest.semantic_id,),
            ).fetchone()
            connection.execute(
                "INSERT INTO corpus_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    manifest.corpus_item_id,
                    manifest.semantic_id,
                    manifest.content_sha256,
                    manifest.artifact_kind,
                    manifest.status.value,
                    int(manifest.aggregate_eligible),
                    manifest.ingested_at,
                    manifest_json,
                ),
            )
            connection.execute(
                "INSERT INTO corpus_sources VALUES (?, ?, ?, ?)",
                (
                    manifest.corpus_item_id,
                    manifest.source["uri"],
                    manifest.source["kind"],
                    manifest.ingested_at,
                ),
            )
            connection.commit()
        if manifest.status == CorpusItemStatus.QUARANTINED:
            ingest_status = CorpusIngestStatus.QUARANTINED
        elif duplicate is not None:
            ingest_status = CorpusIngestStatus.SEMANTIC_DUPLICATE
        else:
            ingest_status = CorpusIngestStatus.INGESTED
        return CorpusIngestResult(
            ingest_status,
            manifest.corpus_item_id,
            manifest.aggregate_eligible,
            semantic_duplicate_of=(duplicate["corpus_item_id"] if duplicate else None),
        )

    def _quarantine(
        self,
        value: Any,
        *,
        diagnostics: tuple[CorpusDiagnostic, ...],
        received_at: str,
        source_uri: str | None,
    ) -> CorpusIngestResult:
        self.initialize()
        try:
            manifest_json = canonical_json(value)
        except (TypeError, ValueError):
            manifest_json = json.dumps(repr(value), ensure_ascii=False)
        raw_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
        diagnostic_payload = [item.to_dict() for item in diagnostics]
        quarantine_id = stable_digest(
            {
                "diagnostics": diagnostic_payload,
                "raw_content_sha256": raw_hash,
                "source_uri": source_uri or "unknown",
            },
            prefix="quarantine_",
        )
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO corpus_quarantine VALUES (?, ?, ?, ?, ?, ?)",
                (
                    quarantine_id,
                    source_uri or "unknown",
                    received_at,
                    raw_hash,
                    canonical_json(diagnostic_payload),
                    manifest_json,
                ),
            )
        return CorpusIngestResult(
            CorpusIngestStatus.QUARANTINED,
            None,
            False,
            quarantine_id=quarantine_id,
            diagnostics=diagnostics,
        )

    def get_item(self, corpus_item_id: str) -> CorpusItemManifest | None:
        self.initialize()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT manifest_json FROM corpus_items WHERE corpus_item_id = ?",
                (corpus_item_id,),
            ).fetchone()
        if row is None:
            return None
        return CorpusItemManifest.from_mapping(json.loads(row["manifest_json"]))

    def aggregate_eligible_item_ids(self) -> tuple[str, ...]:
        self.initialize()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT corpus_item_id FROM corpus_items
                WHERE aggregate_eligible = 1
                ORDER BY corpus_item_id
                """
            ).fetchall()
        return tuple(row["corpus_item_id"] for row in rows)

    def item_count(self) -> int:
        return self._count("corpus_items")

    def quarantine_count(self) -> int:
        return self._count("corpus_quarantine")

    def _count(self, table: str) -> int:
        if table not in {"corpus_items", "corpus_quarantine"}:
            raise ValueError("unsupported corpus catalog table")
        self.initialize()
        with closing(self._connect()) as connection:
            row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(row[0])
