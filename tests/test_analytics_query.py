from __future__ import annotations

import importlib.resources
import json

import pytest

from ygo_effect_dsl.storage import (
    ANALYTICS_QUERY_CONTRACT_VERSION,
    ANALYTICS_QUERY_ERROR_SCHEMA_VERSION,
    ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION,
    ANALYTICS_QUERY_RESPONSE_SCHEMA_VERSION,
    AggregationRecord,
    AnalyticsFilter,
    AnalyticsQueryError,
    AnalyticsQueryRequest,
    AnalyticsQueryRow,
    AnalyticsQueryService,
    AnalyticsSnapshot,
    AnalyticsSnapshotStore,
    AnalyticsSort,
    AnalyticsValue,
    AnalyticsValueState,
    analytics_query_contract_document,
    analytics_row_from_aggregation,
)


def _row(
    index: int,
    *,
    score: float | None = None,
    strategy: str = "random-search-v1",
    status: AnalyticsValue | str = "complete",
) -> AnalyticsQueryRow:
    return AnalyticsQueryRow.build(
        {
            "run": f"run_{index // 2}",
            "deck": "deck_alpha" if index < 3 else "deck_beta",
            "card": ["100", str(200 + index)],
            "strategy": strategy,
            "interruption": [] if index == 0 else ["ash_blossom"],
            "success": index % 2 == 0,
            "score": float(index if score is None else score),
            "time": f"2026-07-{10 + index:02d}T00:00:00Z",
            "version": "0.5.0",
            "status": status,
            "route": f"route_{index}",
            "experiment": "experiment_alpha",
            "evaluator": "board-score-v1",
            "target_board": "peak_board",
            "action_count": index + 1,
            "resource_consumption": float(index),
            "state_hash": f"state_{index}",
        },
        row_id=f"analyticsrow_{index}",
    )


def _service(
    rows: tuple[AnalyticsQueryRow, ...], *, max_scan: int = 10_000
) -> tuple[AnalyticsQueryService, AnalyticsSnapshotStore, str]:
    store = AnalyticsSnapshotStore()
    snapshot_id = store.register(AnalyticsSnapshot(rows, ("source_fixture",)))
    return AnalyticsQueryService(store, max_sync_scan_rows=max_scan), store, snapshot_id


def _request(**changes: object) -> AnalyticsQueryRequest:
    values: dict[str, object] = {
        "fields": ("run", "score", "status"),
        "filters": (),
        "sort": (AnalyticsSort("score", "desc"),),
        "limit": 2,
    }
    values.update(changes)
    return AnalyticsQueryRequest(**values)


@pytest.mark.parametrize(
    ("value", "state"),
    (
        (AnalyticsValue.present("x"), "value"),
        (AnalyticsValue.empty(""), "empty"),
        (AnalyticsValue.missing(), "missing"),
        (AnalyticsValue.unknown(), "unknown"),
        (AnalyticsValue.redacted(), "redacted"),
        (AnalyticsValue.not_applicable(), "not_applicable"),
        (AnalyticsValue.quarantined(), "quarantined"),
    ),
)
def test_value_states_remain_distinct_and_round_trip(
    value: AnalyticsValue, state: str
) -> None:
    encoded = value.to_dict()

    assert encoded["state"] == state
    assert AnalyticsValue.from_mapping(encoded) == value


def test_empty_and_missing_are_not_collapsed_to_null() -> None:
    row = AnalyticsQueryRow.build(
        {
            "run": AnalyticsValue.empty(""),
            "card": AnalyticsValue.empty([]),
            "status": AnalyticsValue.quarantined(),
        },
        row_id="analyticsrow_states",
    )

    assert row.values["run"].state == AnalyticsValueState.EMPTY
    assert row.values["deck"].state == AnalyticsValueState.MISSING
    assert row.values["status"].state == AnalyticsValueState.QUARANTINED
    assert row.to_dict()["values"]["card"]["value"] == []


def test_row_rejects_invalid_field_type_and_unknown_field() -> None:
    with pytest.raises(ValueError, match="must be boolean"):
        AnalyticsQueryRow.build({"success": "yes"})
    with pytest.raises(ValueError, match="unknown analytics fields"):
        AnalyticsQueryRow.build({"unsupported": "value"})


def test_snapshot_rows_cannot_be_mutated_after_content_addressing() -> None:
    row = _row(1)
    snapshot = AnalyticsSnapshot((row,))
    snapshot_id = snapshot.snapshot_id

    with pytest.raises(TypeError):
        row.values["run"] = AnalyticsValue.present("changed")  # type: ignore[index]
    with pytest.raises(TypeError):
        row.values["card"].value[0] = "changed"  # type: ignore[index]

    assert snapshot.snapshot_id == snapshot_id


def test_aggregation_adapter_preserves_identity_and_explicit_dimensions() -> None:
    record = AggregationRecord(
        run_id="run_adapter",
        route_id="route_adapter",
        experiment_id="experiment_adapter",
        evaluator_id="evaluator_adapter",
        evaluator_version="7",
        evaluator_config_hash="evaluator_hash",
        run_date="2026-07-15",
        target_board="terminal_board",
        state_hash="state_adapter",
        success=True,
        score=12.5,
        action_count=8,
    )

    row = analytics_row_from_aggregation(
        record,
        dimensions={
            "deck": "deck_adapter",
            "card": ["100", "200"],
            "strategy": "beam-search-v1",
            "interruption": AnalyticsValue.not_applicable(),
            "status": "complete",
        },
    )

    assert row.row_id == record.record_id
    assert row.values["score"].value == 12.5
    assert row.values["version"].value == "7"
    assert row.values["resource_consumption"].state == AnalyticsValueState.MISSING
    assert row.values["interruption"].state == AnalyticsValueState.NOT_APPLICABLE


@pytest.mark.parametrize(
    "item",
    (
        AnalyticsFilter("run", "eq", "run_1"),
        AnalyticsFilter("deck", "eq", "deck_alpha"),
        AnalyticsFilter("card", "contains", "100"),
        AnalyticsFilter("strategy", "eq", "random-search-v1"),
        AnalyticsFilter("interruption", "contains", "ash_blossom"),
        AnalyticsFilter("success", "eq", True),
        AnalyticsFilter("score", "between", [1, 3]),
        AnalyticsFilter("time", "gte", "2026-07-11T00:00:00Z"),
        AnalyticsFilter("version", "eq", "0.5.0"),
        AnalyticsFilter("status", "in", ["complete"]),
    ),
)
def test_required_filter_dimensions_execute(item: AnalyticsFilter) -> None:
    service, _, _ = _service(tuple(_row(index) for index in range(4)))

    result = service.execute(_request(filters=(item,), limit=10))

    assert result.matched_rows >= 1


def test_pagination_uses_stable_sort_and_row_id_tie_breaker() -> None:
    rows = (
        _row(2, score=5),
        _row(0, score=5),
        _row(3, score=4),
        _row(1, score=4),
    )
    service, _, snapshot_id = _service(rows)
    request = _request(fields=("score",), limit=2)

    first = service.execute(request)
    second = service.execute(
        _request(fields=("score",), limit=2, cursor=first.next_cursor)
    )

    assert first.schema_version == ANALYTICS_QUERY_RESPONSE_SCHEMA_VERSION
    assert first.snapshot_id == snapshot_id
    assert [item["row_id"] for item in first.rows] == [
        "analyticsrow_0",
        "analyticsrow_2",
    ]
    assert [item["row_id"] for item in second.rows] == [
        "analyticsrow_1",
        "analyticsrow_3",
    ]
    assert second.next_cursor is None
    assert set(first.rows[0]["values"]) == {"score"}


def test_timestamp_range_and_sort_use_time_semantics_not_string_order() -> None:
    first = _row(0)
    second = AnalyticsQueryRow.build(
        {
            **{
                field: value
                for field, value in first.values.items()
                if field != "time"
            },
            "time": "2026-07-10T00:00:00.5Z",
        },
        row_id="analyticsrow_fractional",
    )
    service, _, _ = _service((first, second))
    request = _request(
        fields=("time",),
        filters=(
            AnalyticsFilter(
                "time",
                "between",
                ["2026-07-10T00:00:00Z", "2026-07-10T00:00:00.9Z"],
            ),
        ),
        sort=(AnalyticsSort("time"),),
        limit=10,
    )

    result = service.execute(request)

    assert [item["row_id"] for item in result.rows] == [
        "analyticsrow_0",
        "analyticsrow_fractional",
    ]


def test_timestamp_with_non_utc_offset_fails_close() -> None:
    with pytest.raises(ValueError, match="UTC"):
        AnalyticsFilter("time", "gte", "2026-07-10T09:00:00+09:00")


def test_cursor_remains_on_old_snapshot_during_concurrent_ingest() -> None:
    service, store, old_snapshot_id = _service(
        tuple(_row(index) for index in range(3))
    )
    first = service.execute(_request(limit=1))
    new_snapshot_id = store.register(
        AnalyticsSnapshot(tuple(_row(index) for index in range(5)), ("source_new",))
    )

    second = service.execute(_request(limit=1, cursor=first.next_cursor))
    current = service.execute(_request(limit=10))

    assert first.snapshot_id == old_snapshot_id
    assert second.snapshot_id == old_snapshot_id
    assert second.matched_rows == 3
    assert current.snapshot_id == new_snapshot_id
    assert current.matched_rows == 5


def test_cursor_reuse_is_idempotent() -> None:
    service, _, _ = _service(tuple(_row(index) for index in range(4)))
    first = service.execute(_request(limit=1))
    request = _request(limit=1, cursor=first.next_cursor)

    assert service.execute(request).to_dict() == service.execute(request).to_dict()


def test_cursor_rejects_query_change_and_tampering() -> None:
    service, _, _ = _service(tuple(_row(index) for index in range(4)))
    first = service.execute(_request(limit=1))
    assert first.next_cursor is not None

    with pytest.raises(AnalyticsQueryError) as changed:
        service.execute(
            _request(
                fields=("run",),
                limit=1,
                cursor=first.next_cursor,
            )
        )
    assert changed.value.code == "cursor_query_mismatch"

    replacement = "A" if first.next_cursor[-1] != "A" else "B"
    tampered = first.next_cursor[:-1] + replacement
    with pytest.raises(AnalyticsQueryError) as invalid:
        service.execute(_request(limit=1, cursor=tampered))
    assert invalid.value.code == "invalid_cursor"


def test_cursor_rejects_explicit_different_snapshot() -> None:
    service, store, _ = _service(tuple(_row(index) for index in range(3)))
    first = service.execute(_request(limit=1))
    new_id = store.register(AnalyticsSnapshot((_row(9),), ("new",)))

    with pytest.raises(AnalyticsQueryError) as error:
        service.execute(
            _request(limit=1, cursor=first.next_cursor, snapshot_id=new_id)
        )

    assert error.value.code == "cursor_snapshot_mismatch"


def test_state_filter_finds_redacted_and_quarantined_values() -> None:
    rows = (
        _row(0, status=AnalyticsValue.redacted()),
        _row(1, status=AnalyticsValue.quarantined()),
        _row(2),
    )
    service, _, _ = _service(rows)

    redacted = service.execute(
        _request(filters=(AnalyticsFilter("status", "state_is", "redacted"),))
    )
    quarantined = service.execute(
        _request(
            filters=(AnalyticsFilter("status", "state_is", "quarantined"),)
        )
    )

    assert [item["row_id"] for item in redacted.rows] == ["analyticsrow_0"]
    assert [item["row_id"] for item in quarantined.rows] == ["analyticsrow_1"]


def test_large_snapshot_is_redirected_to_explicit_async_export_job() -> None:
    service, _, snapshot_id = _service(
        tuple(_row(index) for index in range(3)), max_scan=2
    )

    with pytest.raises(AnalyticsQueryError) as raised:
        service.execute(_request())

    error = raised.value
    assert error.schema_version == ANALYTICS_QUERY_ERROR_SCHEMA_VERSION
    assert error.code == "sync_scan_limit_exceeded"
    assert error.async_job_required is True
    assert error.details["suggested_job_kind"] == "export"
    assert error.details["query_snapshot_id"] == snapshot_id


def test_missing_snapshot_fails_closed() -> None:
    service = AnalyticsQueryService(AnalyticsSnapshotStore())

    with pytest.raises(AnalyticsQueryError) as raised:
        service.execute(_request())

    assert raised.value.code == "snapshot_unavailable"


def test_filter_and_request_limits_are_enforced() -> None:
    with pytest.raises(ValueError, match="1..500"):
        _request(limit=501)
    with pytest.raises(ValueError, match="1..100 items"):
        AnalyticsFilter("run", "in", [])
    with pytest.raises(ValueError, match="not sortable"):
        AnalyticsSort("card")
    with pytest.raises(ValueError, match="not supported"):
        AnalyticsFilter("run", "between", ["a", "b"])


def test_request_and_response_contracts_round_trip_to_canonical_data() -> None:
    request = _request(
        filters=(AnalyticsFilter("score", "gte", 2),),
        snapshot_id="analyticssnapshot_fixture",
    )

    restored = AnalyticsQueryRequest.from_mapping(request.to_dict())

    assert restored == request
    assert restored.schema_version == ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION
    assert restored.fingerprint == request.fingerprint


def test_machine_readable_contract_resource_matches_runtime() -> None:
    resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
        "analytics-query-contract-v1.json"
    )
    stored = json.loads(resource.read_text(encoding="utf-8"))
    runtime = analytics_query_contract_document()

    assert stored == runtime
    assert runtime["version"] == ANALYTICS_QUERY_CONTRACT_VERSION
    assert set(runtime["fields"]) >= {
        "run",
        "deck",
        "card",
        "strategy",
        "interruption",
        "success",
        "score",
        "time",
        "version",
        "status",
    }
    assert runtime["sync_scan_policy"]["fallback_job_kind"] == "export"
