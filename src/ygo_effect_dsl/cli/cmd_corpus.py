from __future__ import annotations

from pathlib import Path

from ygo_effect_dsl.engine.bridge.ocgcore.decision_corpus import (
    build_decision_shape_corpus,
    write_decision_shape_corpus,
)
from ygo_effect_dsl.route_dsl import load_route_document


def cmd_ocgcore_decision_corpus(args: object) -> int:
    route_paths = [Path(value) for value in getattr(args, "route")]
    corpus = build_decision_shape_corpus(
        [load_route_document(path) for path in route_paths]
    )
    write_decision_shape_corpus(getattr(args, "out"), corpus)
    coverage = corpus["coverage"]
    print(
        "ocgcore-decision-corpus: "
        f"ok corpus_id={corpus['corpus_id']} "
        f"cases={len(corpus['supported_cases'])} "
        f"coverage={coverage['shape_coverage_status']}"
    )
    return 0


__all__ = ["cmd_ocgcore_decision_corpus"]
