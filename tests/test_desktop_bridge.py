from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from ygo_effect_dsl.desktop import desktop_bridge_contract_document
from ygo_effect_dsl.desktop.bridge import (
    DESKTOP_BRIDGE_CONTRACT_VERSION,
    DesktopBridge,
)
from ygo_effect_dsl.desktop.service import DesktopApplicationService
from ygo_effect_dsl.presentation import CARD_PRESENTATION_PROVIDER_VERSION
from ygo_effect_dsl.presentation.cards import CARD_PRESENTATION_QUERY_VERSION
from ygo_effect_dsl.storage.jobs import JobState
from ygo_effect_dsl.storage.query import ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION


def _request(
    method: str, payload: Mapping[str, Any], **overrides: Any
) -> dict[str, Any]:
    return {
        "method": method,
        "payload": dict(payload),
        "request_id": "test-request-1",
        "version": DESKTOP_BRIDGE_CONTRACT_VERSION,
        **overrides,
    }


def _codes() -> list[int]:
    return list(range(10_000, 10_040))


@dataclass(frozen=True)
class _Preflight:
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagnostics": [],
            "manifest": {"schema_version": "scenario-manifest-v1"},
            "ok": self.ok,
            "schema_version": "scenario-preflight-v1",
        }


def _preflight(*_: Any, **__: Any) -> _Preflight:
    return _Preflight()


def test_machine_contract_matches_the_single_method_allowlist(tmp_path: Path) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    contract = desktop_bridge_contract_document()
    bridge = DesktopBridge(service.handlers())

    assert contract["schema_version"] == DESKTOP_BRIDGE_CONTRACT_VERSION
    assert tuple(sorted(contract["methods"])) == bridge.methods
    assert contract["security"] == {
        "generic_python_object": False,
        "local_rest_api": False,
        "public_python_methods": ["invoke"],
        "remote_content": False,
    }
    public_callables = [
        name
        for name in dir(bridge)
        if not name.startswith("_") and callable(getattr(bridge, name))
    ]
    assert public_callables == ["invoke"]


def test_invalid_bridge_requests_fail_before_dispatch() -> None:
    calls: list[Mapping[str, Any]] = []
    bridge = DesktopBridge(
        {"system.describe": lambda payload: calls.append(payload) or {}}
    )

    cases = (
        ({"not": "a request"}, "invalid_request_fields"),
        (_request("system.describe", {}, version="old"), "bridge_version_mismatch"),
        (_request("missing", {}), "unsupported_method"),
        (
            _request("system.describe", {"file_path": "C:/secret"}),
            "renderer_path_forbidden",
        ),
        (_request("system.describe", {"value": float("inf")}), "non_finite_number"),
    )
    for request, code in cases:
        response = bridge.invoke(request)
        assert response["ok"] is False
        assert response["diagnostics"][0]["code"] == code
    assert calls == []


def test_bridge_enforces_request_and_response_byte_limits() -> None:
    request_bridge = DesktopBridge(
        {"echo": lambda payload: payload},
        max_request_bytes=180,
    )
    response = request_bridge.invoke(_request("echo", {"value": "x" * 500}))
    assert response["diagnostics"][0]["code"] == "request_too_large"

    response_bridge = DesktopBridge(
        {"large": lambda _: {"value": "x" * 500}},
        max_response_bytes=200,
    )
    response = response_bridge.invoke(_request("large", {}))
    assert response["diagnostics"][0]["code"] == "response_too_large"


def test_inline_and_native_ydk_registration_are_content_addressed(
    tmp_path: Path,
) -> None:
    ydk = tmp_path / "research.ydk"
    ydk.write_text(
        "#created by test\n#main\n"
        + "\n".join(str(code) for code in _codes())
        + "\n#extra\n!side\n",
        encoding="utf-8",
    )
    service = DesktopApplicationService(
        tmp_path / "state",
        ydk_picker=lambda: ydk,
        preflight=_preflight,
    )
    bridge = DesktopBridge(service.handlers())
    inline = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Inline", "side": []},
        )
    )
    imported = bridge.invoke(_request("deck.import_ydk", {}))
    catalog = bridge.invoke(_request("deck.catalog", {}))

    assert inline["ok"] is True
    assert imported["ok"] is True
    assert imported["result"]["cancelled"] is False
    assert catalog["result"]["total"] == 2
    persisted = json.loads(
        (tmp_path / "state" / "decks.json").read_text(encoding="utf-8")
    )
    assert persisted["schema_version"] == "desktop-deck-catalog-v1"
    assert all("path" not in deck for deck in persisted["decks"])

    persisted["decks"][0]["main"][0] += 1
    (tmp_path / "state" / "decks.json").write_text(
        json.dumps(persisted),
        encoding="utf-8",
    )
    corrupt = bridge.invoke(_request("deck.catalog", {}))
    assert corrupt["ok"] is False
    assert corrupt["diagnostics"][0]["code"] == "deck_catalog_corrupt"


def test_preflight_search_queue_status_and_cancel_use_existing_catalog(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path, preflight=_preflight)
    bridge = DesktopBridge(service.handlers())
    registered = bridge.invoke(
        _request(
            "deck.register_inline",
            {"extra": [], "main": _codes(), "name": "Queue", "side": []},
        )
    )["result"]["deck"]
    experiment = {"experiment_id": "desktop-search", "schema_version": "0.4"}
    checked = bridge.invoke(
        _request(
            "scenario.preflight",
            {"deck_id": registered["deck_id"], "experiment": experiment},
        )
    )
    queued = bridge.invoke(
        _request(
            "job.enqueue_search",
            {
                "deck_id": registered["deck_id"],
                "experiment": experiment,
                "idempotency_key": "desktop-test-search",
                "priority": 0,
            },
        )
    )
    job_id = queued["result"]["job"]["job_id"]
    status = bridge.invoke(_request("job.status", {"job_id": job_id}))
    cancelled = bridge.invoke(_request("job.cancel", {"job_id": job_id}))

    assert checked["result"]["experiment"]["deck"]["source"] == "inline"
    assert queued["result"]["job"]["state"] == "queued"
    assert status["result"]["job"]["state"] == "queued"
    assert cancelled["result"]["job"]["state"] == "cancelled"
    experiment_files = tuple((tmp_path / "experiments").glob("experiment_*.json"))
    assert len(experiment_files) == 1


def test_cancel_does_not_finish_a_job_claimed_during_the_request(
    tmp_path: Path,
) -> None:
    service = DesktopApplicationService(tmp_path)

    class RacingCatalog:
        def get_job(self, _: str) -> Any:
            return SimpleNamespace(state=JobState.QUEUED)

        def request_cancel(self, *_: Any, **__: Any) -> Any:
            return SimpleNamespace(
                attempt=1,
                lease_token="worker-lease",
                to_dict=lambda: {"state": "cancelling"},
            )

        def finish_cancelled(self, *_: Any, **__: Any) -> Any:
            raise AssertionError("a claimed worker must finish its own cancellation")

    service.job_catalog = RacingCatalog()  # type: ignore[assignment]
    result = service.job_cancel({"job_id": "job_race"})

    assert result["job"]["state"] == "cancelling"


def test_analytics_and_card_capabilities_fail_closed_or_use_typed_contracts(
    tmp_path: Path,
) -> None:
    bridge = DesktopBridge(DesktopApplicationService(tmp_path).handlers())
    description = bridge.invoke(_request("system.describe", {}))
    query = bridge.invoke(
        _request(
            "analytics.query",
            {
                "request": {
                    "cursor": None,
                    "fields": ["run", "success"],
                    "filters": [],
                    "limit": 20,
                    "schema_version": ANALYTICS_QUERY_REQUEST_SCHEMA_VERSION,
                    "snapshot_id": None,
                    "sort": [],
                }
            },
        )
    )
    card = bridge.invoke(
        _request(
            "card.get",
            {
                "query": {
                    "card_code": 10000,
                    "expected_asset_lock_id": None,
                    "expected_provider_version": CARD_PRESENTATION_PROVIDER_VERSION,
                    "fallback_locales": ["en"],
                    "redacted": False,
                    "requested_locale": "ja",
                    "schema_version": CARD_PRESENTATION_QUERY_VERSION,
                }
            },
        )
    )

    assert description["result"]["capabilities"]["card_presentation"] is False
    assert query["ok"] is True
    assert query["result"]["rows"] == []
    assert card["ok"] is False
    assert card["diagnostics"][0]["code"] == "card_presentation_source_unavailable"
