from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ygo_effect_dsl.engine.bridge.ocgcore.decision_corpus import (
    DECISION_SHAPE_CORPUS_SCHEMA_VERSION,
    DecisionShapeCorpusError,
    build_decision_shape_corpus,
    write_decision_shape_corpus,
)
from ygo_effect_dsl.engine.canonical import canonical_json
from ygo_effect_dsl.route_dsl import load_route_document


REPO_ROOT = Path(__file__).parents[1]
ROUTE = REPO_ROOT / "examples" / "prototype" / "real_core_action_aggregation.route.yaml"
EVIDENCE = REPO_ROOT / "docs" / "ocgcore" / "evidence" / "decision_shape_corpus.json"


def test_route_decisions_round_trip_into_sanitized_machine_readable_corpus(
    tmp_path: Path,
) -> None:
    route = load_route_document(ROUTE)
    corpus = build_decision_shape_corpus([route])
    repeated = build_decision_shape_corpus([route])

    assert corpus == repeated
    assert corpus["schema_version"] == DECISION_SHAPE_CORPUS_SCHEMA_VERSION
    assert corpus["corpus_id"].startswith("decisioncorpus_")
    assert len(corpus["supported_cases"]) == len(route["replay"]["events"])
    assert {case["round_trip"] for case in corpus["supported_cases"]} == {
        "verified"
    }
    assert {case["role"] for case in corpus["supported_cases"]} >= {
        "cost",
        "option",
        "target",
    }
    assert set(corpus["coverage"]["categories"]) >= {
        "cost",
        "field_source",
        "option",
        "single_target",
    }
    assert corpus["coverage"]["shape_coverage_status"] == "incomplete"
    assert {case["case_id"] for case in corpus["negative_cases"]} >= {
        "unknown_message_id",
        "unknown_candidate_shape",
        "candidate_disappeared",
        "ambiguous_response_mapping",
    }
    serialized = canonical_json(corpus)
    assert "payload_hex" not in serialized
    assert "response_hex" not in serialized

    destination = tmp_path / "decision-corpus.json"
    write_decision_shape_corpus(destination, corpus)
    assert json.loads(destination.read_text(encoding="utf-8")) == corpus


def test_corpus_rejects_tampered_frame_request_response_and_identity() -> None:
    route = load_route_document(ROUTE)

    bad_frame = deepcopy(route)
    bad_frame["replay"]["initial_core_output"]["frames"][-1][
        "payload_sha256"
    ] = "0" * 64
    with pytest.raises(DecisionShapeCorpusError, match="payload hash"):
        build_decision_shape_corpus([bad_frame])

    bad_request = deepcopy(route)
    bad_request["replay"]["events"][0]["request"]["candidates"][0][
        "payload"
    ]["response_value"] = 99
    with pytest.raises(DecisionShapeCorpusError, match="binary decoder output"):
        build_decision_shape_corpus([bad_request])

    bad_response = deepcopy(route)
    bad_response["replay"]["events"][0]["core_response"][
        "response_sha256"
    ] = "f" * 64
    with pytest.raises(DecisionShapeCorpusError, match="response hash"):
        build_decision_shape_corpus([bad_response])

    corpus = build_decision_shape_corpus([route])
    corpus["corpus_id"] = "decisioncorpus_tampered"
    with pytest.raises(DecisionShapeCorpusError, match="not canonical"):
        write_decision_shape_corpus(Path(os.devnull), corpus)

    unsafe = build_decision_shape_corpus([route])
    unsafe["payload_hex"] = "00"
    with pytest.raises(DecisionShapeCorpusError, match="forbidden"):
        write_decision_shape_corpus(Path(os.devnull), unsafe)

    with pytest.raises(DecisionShapeCorpusError, match="duplicate Route ID"):
        build_decision_shape_corpus([route, route])


def test_decision_corpus_cli_writes_verified_json(tmp_path: Path) -> None:
    destination = tmp_path / "cli-corpus.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ygo_effect_dsl",
            "ocgcore-decision-corpus",
            "--route",
            str(ROUTE),
            "--out",
            str(destination),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "ocgcore-decision-corpus: ok corpus_id=decisioncorpus_" in completed.stdout
    assert json.loads(destination.read_text(encoding="utf-8"))[
        "schema_version"
    ] == DECISION_SHAPE_CORPUS_SCHEMA_VERSION


def test_committed_fixture_corpus_is_complete_sanitized_and_canonical(
    tmp_path: Path,
) -> None:
    corpus = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert corpus["corpus_id"] == (
        "decisioncorpus_4320f03495f29e9eb79c7489321ddd5c4529c1a812b2ae425f10de010fea9103"
    )
    assert len(corpus["routes"]) == 5
    assert len(corpus["supported_cases"]) == 63
    assert corpus["coverage"]["shape_coverage_status"] == "complete"
    assert corpus["coverage"]["missing_required_categories"] == []
    serialized = canonical_json(corpus)
    assert "payload_hex" not in serialized
    assert "response_hex" not in serialized
    write_decision_shape_corpus(tmp_path / "verified.json", corpus)
