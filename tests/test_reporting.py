from __future__ import annotations

from pathlib import Path

from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.reporting import build_markdown_report
from ygo_effect_dsl.route_dsl import load_route_document


ROOT = Path(__file__).parents[1]


def test_markdown_report_is_deterministic_and_derived_from_route() -> None:
    experiment = load_experiment_document(
        ROOT / "examples" / "experiments" / "real_core_effect_veiler.yaml"
    )
    route = load_route_document(
        ROOT / "examples" / "prototype" / "real_core_effect_veiler.route.yaml"
    )

    first = build_markdown_report(route["experiment"], route)
    second = build_markdown_report(route["experiment"], route)

    assert first == second
    assert f"Route ID: `{route['route_id']}`" in first
    assert "| field_count | 1 | 1 | 10 | 10 | observed |" in first
    assert "## Pending Validation\n\n- None" in first
    assert "not the replay source of truth" in first
