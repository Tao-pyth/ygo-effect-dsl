from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sqlite3

import pytest

from ygo_effect_dsl.storage import (
    CORPUS_CATALOG_SCHEMA_VERSION,
    CORPUS_MANIFEST_SCHEMA_VERSION,
    CorpusCatalog,
    CorpusIngestStatus,
    CorpusItemStatus,
    build_corpus_item_manifest,
    validate_corpus_manifest,
)


def _id(prefix: str, character: str) -> str:
    return prefix + character * 64


def _provenance() -> dict[str, object]:
    return {
        "assets": {
            "card_scripts_commit": "a" * 40,
            "database_sha256": "b" * 64,
            "lock_id": "ocgcore-assets-test-v1",
        },
        "core": {
            "api": "11.0",
            "binary_sha256": "c" * 64,
            "lock_id": "ocgcore-test-v1",
            "source_commit": "d" * 40,
        },
        "deck": {
            "id": "deck_alpha",
            "opening_hand_id": _id("hand_", "1"),
            "sha256": "e" * 64,
            "source": "ydk",
        },
        "evaluator": {
            "config_hash": _id("evalcfg_", "2"),
            "id": "board_count",
            "version": "1",
        },
        "experiment": {
            "digest": _id("experiment_", "3"),
            "id": "experiment_alpha",
            "schema_version": "0.4",
        },
        "package_version": "0.5.0-dev",
        "replay": {
            "manifest_hash": _id("manifest_", "4"),
            "manifest_schema_version": "ygo-replay-manifest-v1",
            "terminal_state_id": _id("state_", "5"),
            "verification_id": _id("replayverify_", "6"),
        },
        "route": {
            "document_digest": _id("routedoc_", "7"),
            "id": _id("route_", "8"),
            "schema_version": "0.1",
        },
        "scenario": {
            "manifest_id": _id("scenariomanifest_", "9"),
            "schema_version": "scenario-manifest-v1",
        },
        "search": {
            "executor_schema_version": "search-executor-v5",
            "result_schema_version": "search-run-result-v5",
            "run_id": _id("searchrun_", "a"),
            "strategy_id": "random_search_v1",
            "strategy_schema_version": "random-search-strategy-v1",
        },
    }


def _manifest(
    content: bytes = b'{"route":"alpha"}\n',
    *,
    ingested_at: str = "2026-07-15T12:00:00Z",
    source_uri: str = "routes/alpha.route.yaml",
    status: CorpusItemStatus = CorpusItemStatus.COMPLETE,
):
    return build_corpus_item_manifest(
        content=content,
        artifact_kind="qualified_route_bundle",
        ingested_at=ingested_at,
        source_kind="local_file",
        source_uri=source_uri,
        provenance=_provenance(),
        information_mode="complete_information",
        redaction_policy_id="complete-information-v1",
        status=status,
    )


def test_manifest_round_trip_preserves_full_provenance_and_identity() -> None:
    manifest = _manifest()

    validation = validate_corpus_manifest(manifest.to_dict())

    assert validation.ok is True
    assert validation.aggregate_eligible is True
    assert validation.manifest == manifest
    assert manifest.schema_version == CORPUS_MANIFEST_SCHEMA_VERSION
    assert manifest.corpus_item_id.startswith("corpusitem_")
    assert manifest.semantic_id.startswith("corpussemantic_")
    assert manifest.provenance.deck["sha256"] == "e" * 64
    assert manifest.provenance.search["run_id"].startswith("searchrun_")
    assert manifest.provenance.assets == {
        "card_scripts_commit": "a" * 40,
        "database_sha256": "b" * 64,
        "lock_id": "ocgcore-assets-test-v1",
    }
    assert manifest.source["third_party_assets_included"] is False


def test_source_location_and_ingest_time_do_not_change_content_identity() -> None:
    first = _manifest()
    second = _manifest(
        ingested_at="2026-07-15T12:01:00Z",
        source_uri="import/alpha.route.yaml",
    )

    assert first.semantic_id == second.semantic_id
    assert first.corpus_item_id == second.corpus_item_id


def test_ingest_is_idempotent_for_exact_content(tmp_path: Path) -> None:
    catalog = CorpusCatalog(tmp_path / "corpus.sqlite3")
    first = _manifest()
    second = _manifest(
        ingested_at="2026-07-15T12:01:00Z",
        source_uri="import/alpha.route.yaml",
    )

    created = catalog.ingest(first.to_dict(), received_at=first.ingested_at)
    duplicate = catalog.ingest(second.to_dict(), received_at=second.ingested_at)

    assert created.status == CorpusIngestStatus.INGESTED
    assert duplicate.status == CorpusIngestStatus.EXACT_DUPLICATE
    assert duplicate.corpus_item_id == created.corpus_item_id
    assert catalog.item_count() == 1
    assert catalog.get_item(first.corpus_item_id) == first
    assert catalog.aggregate_eligible_item_ids() == (first.corpus_item_id,)


def test_semantic_duplicate_retains_both_raw_items(tmp_path: Path) -> None:
    catalog = CorpusCatalog(tmp_path / "corpus.sqlite3")
    first = _manifest(b'{"route":"alpha","format":1}\n')
    second = _manifest(
        b'{ "format": 2, "route": "alpha" }\n',
        ingested_at="2026-07-15T12:01:00Z",
    )

    first_result = catalog.ingest(first.to_dict(), received_at=first.ingested_at)
    second_result = catalog.ingest(second.to_dict(), received_at=second.ingested_at)

    assert first.semantic_id == second.semantic_id
    assert first.corpus_item_id != second.corpus_item_id
    assert first_result.status == CorpusIngestStatus.INGESTED
    assert second_result.status == CorpusIngestStatus.SEMANTIC_DUPLICATE
    assert second_result.semantic_duplicate_of == first.corpus_item_id
    assert catalog.item_count() == 2
    assert set(catalog.aggregate_eligible_item_ids()) == {
        first.corpus_item_id,
        second.corpus_item_id,
    }


@pytest.mark.parametrize(
    "status",
    [
        CorpusItemStatus.INCOMPLETE,
        CorpusItemStatus.CORRUPT,
        CorpusItemStatus.QUARANTINED,
    ],
)
def test_non_complete_items_are_never_aggregation_inputs(
    tmp_path: Path,
    status: CorpusItemStatus,
) -> None:
    catalog = CorpusCatalog(tmp_path / f"{status.value}.sqlite3")
    manifest = _manifest(status=status)

    result = catalog.ingest(manifest.to_dict(), received_at=manifest.ingested_at)

    assert result.aggregate_eligible is False
    assert catalog.aggregate_eligible_item_ids() == ()


def test_unknown_source_is_quarantined_with_structured_diagnostic(
    tmp_path: Path,
) -> None:
    catalog = CorpusCatalog(tmp_path / "corpus.sqlite3")
    document = _manifest().to_dict()
    del document["provenance"]["search"]

    first = catalog.ingest(
        document,
        received_at="2026-07-15T12:00:00Z",
        source_uri="unknown-input.json",
    )
    second = catalog.ingest(
        document,
        received_at="2026-07-15T12:02:00Z",
        source_uri="unknown-input.json",
    )

    assert first.status == CorpusIngestStatus.QUARANTINED
    assert first.aggregate_eligible is False
    assert first.corpus_item_id is None
    assert first.quarantine_id == second.quarantine_id
    assert first.diagnostics[0].to_dict() == {
        "code": "invalid_fields",
        "message": (
            "fields must be exactly ['assets', 'core', 'deck', 'evaluator', "
            "'experiment', 'package_version', 'replay', 'route', 'scenario', "
            "'search']; observed ['assets', 'core', 'deck', 'evaluator', "
            "'experiment', 'package_version', 'replay', 'route', 'scenario']"
        ),
        "path": "$.provenance",
        "severity": "error",
    }
    assert catalog.item_count() == 0
    assert catalog.quarantine_count() == 1


def test_embedded_third_party_assets_fail_closed(tmp_path: Path) -> None:
    catalog = CorpusCatalog(tmp_path / "corpus.sqlite3")
    document = _manifest().to_dict()
    document["source"]["third_party_assets_included"] = True

    result = catalog.ingest(
        document,
        received_at="2026-07-15T12:00:00Z",
    )

    assert result.status == CorpusIngestStatus.QUARANTINED
    assert result.diagnostics[0].code == "third_party_asset_embedded"
    assert catalog.item_count() == 0


def test_content_and_semantic_ids_are_revalidated_on_ingest(tmp_path: Path) -> None:
    catalog = CorpusCatalog(tmp_path / "corpus.sqlite3")
    document = _manifest().to_dict()
    document["content_sha256"] = "f" * 64

    result = catalog.ingest(
        document,
        received_at="2026-07-15T12:00:00Z",
    )

    assert result.status == CorpusIngestStatus.QUARANTINED
    assert result.diagnostics[0].code == "corpus_item_id_mismatch"
    assert catalog.aggregate_eligible_item_ids() == ()


def test_conflicting_status_for_same_identity_is_quarantined(tmp_path: Path) -> None:
    catalog = CorpusCatalog(tmp_path / "corpus.sqlite3")
    complete = _manifest()
    corrupt_document = deepcopy(complete.to_dict())
    corrupt_document["status"] = "corrupt"

    catalog.ingest(complete.to_dict(), received_at=complete.ingested_at)
    conflict = catalog.ingest(
        corrupt_document,
        received_at="2026-07-15T12:01:00Z",
    )

    assert conflict.status == CorpusIngestStatus.QUARANTINED
    assert conflict.diagnostics[0].code == "status_conflict"
    assert catalog.item_count() == 1
    assert catalog.quarantine_count() == 1
    assert catalog.aggregate_eligible_item_ids() == (complete.corpus_item_id,)


def test_catalog_requires_explicit_schema_migration_without_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "corpus.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_meta VALUES ('schema_version', 'corpus-catalog-v0')"
        )

    with pytest.raises(ValueError, match="explicit migration"):
        CorpusCatalog(path).initialize()

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        version = connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
    assert tables == {"schema_meta"}
    assert version == "corpus-catalog-v0"
    assert CORPUS_CATALOG_SCHEMA_VERSION == "corpus-catalog-v1"
