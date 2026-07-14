from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.interruption import (
    CardOriginKind,
    build_additional_card_attribution,
    classify_card_origin,
)
from ygo_effect_dsl.engine.interruption.attribution import (
    _candidate_instances,
    _classify_minimal_sets,
)
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import verify_real_core_route
from ygo_effect_dsl.route_dsl import load_route_document


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = REPO_ROOT / "examples" / "prototype"
GOLDEN = REPO_ROOT / "tests" / "golden" / "additional_card_attribution_v1.json"
ROUTES = {
    name: PROTOTYPE / f"real_core_recovery_{name}.route.yaml"
    for name in (
        "control_no_card",
        "interrupted_no_card",
        "control_with_card",
        "interrupted_with_card",
    )
}


def _routes() -> dict[str, dict[str, object]]:
    return {name: load_route_document(path) for name, path in ROUTES.items()}


def _report(routes: dict[str, dict[str, object]]) -> dict[str, object]:
    return build_additional_card_attribution(
        routes["control_no_card"],
        routes["interrupted_no_card"],
        [
            {
                "trial_id": "recovery_card_23434538",
                "control_route": routes["control_with_card"],
                "interrupted_route": routes["interrupted_with_card"],
            }
        ],
    )


def test_origin_taxonomy_distinguishes_supported_sources() -> None:
    assert classify_card_origin(
        owner=0, perspective=0, initial_fixed_hand=True
    ) is CardOriginKind.FIXED_OPENING_HAND
    assert classify_card_origin(
        owner=0,
        perspective=0,
        previous_location=0x01,
        current_location=0x02,
        draw_message_present=True,
    ) is CardOriginKind.DRAW
    assert classify_card_origin(
        owner=0,
        perspective=0,
        previous_location=0x01,
        current_location=0x02,
    ) is CardOriginKind.SEARCH
    assert classify_card_origin(
        owner=0,
        perspective=0,
        previous_location=0x10,
        current_location=0x02,
    ) is CardOriginKind.SALVAGE
    assert classify_card_origin(
        owner=0,
        perspective=0,
        previous_location=0,
        current_location=0x04,
        generated_token=True,
    ) is CardOriginKind.GENERATED_TOKEN
    assert classify_card_origin(
        owner=1, perspective=0, initial_fixed_hand=True
    ) is CardOriginKind.OPPONENT

    with pytest.raises(ValueError, match="not distinguishable"):
        classify_card_origin(owner=0, perspective=0, previous_location=0x08)


def test_real_core_counterfactual_matches_versioned_golden_report() -> None:
    routes = _routes()
    report = _report(routes)
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert report == expected
    assert report["status"] == "verified_minimal_required_sets"
    assert report["baseline"]["control_success"] is True
    assert report["baseline"]["interrupted_success"] is False
    assert report["counterfactual"]["trials"][0]["control_effect"] == 0
    assert report["counterfactual"]["trials"][0]["card_effect_under_interruption"] == 1
    assert report["counterfactual"]["trials"][0]["difference_in_differences"] == 1
    assert report["provenance"][0]["card_code"] == 23434538
    assert report["provenance"][0]["origin_kind"] == "fixed_opening_hand"
    assert report["provenance"][0]["usage_evidence"][0]["step"] == 9


def test_attribution_rejects_ambiguous_same_code_instances() -> None:
    with pytest.raises(ValueError, match="same-code card instances"):
        _candidate_instances(
            [14558127],
            [14558127, 23434538, 23434538],
            perspective=0,
            control_route={"route_id": "route_control"},
            interrupted_route={"route_id": "route_interrupted"},
        )


def test_attribution_rejects_manifest_snapshot_identity_mismatch() -> None:
    routes = _routes()
    routes["control_with_card"]["replay"]["manifest"]["initial_conditions"][
        "fixed_hands"
    ]["0"][-1] = 1

    with pytest.raises(ValueError, match="does not match initial_snapshot"):
        _report(routes)


def test_minimal_set_classifier_supports_alternatives_and_coverage_gaps() -> None:
    evaluated = {
        frozenset(): {"control_success": True, "interrupted_success": False},
        frozenset({"a"}): {"control_success": True, "interrupted_success": True},
        frozenset({"b"}): {"control_success": True, "interrupted_success": True},
        frozenset({"a", "b"}): {
            "control_success": True,
            "interrupted_success": True,
        },
        frozenset({"c", "d"}): {
            "control_success": True,
            "interrupted_success": True,
        },
    }
    minimal, incomplete = _classify_minimal_sets(evaluated)

    assert minimal == [frozenset({"a"}), frozenset({"b"})]
    assert incomplete == [frozenset({"c", "d"})]


def test_attribution_fails_closed_outside_complete_information() -> None:
    routes = _routes()
    routes["control_with_card"] = deepcopy(routes["control_with_card"])
    routes["control_with_card"]["experiment"]["information_mode"] = "player_view"

    with pytest.raises(ValueError, match="requires complete_information"):
        _report(routes)


@pytest.mark.parametrize("route_path", ROUTES.values(), ids=ROUTES.keys())
def test_checked_counterfactual_route_matches_fresh_core(route_path: Path) -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")

    route = load_route_document(route_path)
    result = verify_real_core_route(route)

    assert result.route_id == route["route_id"]
