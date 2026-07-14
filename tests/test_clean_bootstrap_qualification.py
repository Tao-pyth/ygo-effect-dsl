from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ygo_effect_dsl.external import clean_bootstrap_qualification as qualification
from ygo_effect_dsl.external.clean_bootstrap_qualification import (
    CLEAN_BOOTSTRAP_QUALIFICATION_SCHEMA_VERSION,
    CleanBootstrapQualificationError,
    audit_bootstrap_network_boundary,
    prepare_stale_build_partials,
    prepare_stale_download_partial,
    read_clean_bootstrap_qualification,
    validate_clean_bootstrap_qualification,
)
from ygo_effect_dsl.external.ocgcore import OcgcoreLayout, load_ocgcore_lock


REPO_ROOT = Path(__file__).parents[1]
EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "ocgcore"
    / "evidence"
    / "clean_bootstrap_qualification.json"
)


def test_network_capable_imports_are_owned_by_bootstrap_module() -> None:
    result = audit_bootstrap_network_boundary(REPO_ROOT / "src" / "ygo_effect_dsl")

    assert result["runtime_network_access"] is False
    assert result["non_bootstrap_network_import_count"] == 0
    assert result["bootstrap_network_modules"] == [
        "ygo_effect_dsl.external.ocgcore"
    ]
    assert result["imports"] == [
        {
            "import": "urllib.request",
            "module": "ygo_effect_dsl.external.ocgcore",
        }
    ]


def test_interrupted_partial_probes_are_harness_owned(tmp_path: Path) -> None:
    lock = load_ocgcore_lock()
    layout = OcgcoreLayout.create(lock, tmp_path / "external")

    build_partial, runtime_partial = prepare_stale_build_partials(
        layout.external_root
    )
    download_partial = prepare_stale_download_partial(layout.external_root)

    assert build_partial == layout.install_root / ".build.partial"
    assert runtime_partial == layout.install_root / ".runtime.partial"
    assert download_partial == (
        layout.tools
        / "downloads"
        / f"{lock.tool['archive']}.partial"
    )
    assert build_partial.is_dir()
    assert runtime_partial.is_dir()
    assert download_partial.read_bytes() == b"interrupted qualification download"


def test_qualification_work_root_must_be_repository_external() -> None:
    with pytest.raises(CleanBootstrapQualificationError, match="outside the repository"):
        qualification._ensure_repository_external(
            REPO_ROOT / "raw-qualification",
            repository_root=REPO_ROOT,
        )


def test_committed_clean_bootstrap_qualification_is_canonical() -> None:
    if not EVIDENCE.is_file():
        pytest.skip("clean bootstrap qualification evidence has not been generated yet")
    report = read_clean_bootstrap_qualification(EVIDENCE)

    assert report["schema_version"] == CLEAN_BOOTSTRAP_QUALIFICATION_SCHEMA_VERSION
    assert report["status"] == "qualified_local"
    assert len(report["builds"]) == 5
    assert report["invariants"] == {
        "all_inputs_identical": True,
        "all_runtime_sizes_identical": True,
        "all_verifications_succeeded": True,
        "download_interruption_recovered": True,
        "idempotent_repeat": True,
        "same_host_only": True,
        "stale_build_interruption_recovered": True,
    }
    assert len({build["input_identity_digest"] for build in report["builds"]}) == 1
    assert report["binary_reproducibility"]["distinct_sha256_count"] >= 1
    assert json.loads(EVIDENCE.read_text(encoding="utf-8")) == report

    tampered = deepcopy(report)
    tampered["builds"][1]["input_identity"]["api"]["major"] = 10
    with pytest.raises(CleanBootstrapQualificationError, match="build API differs"):
        validate_clean_bootstrap_qualification(tampered)

    leaked = deepcopy(report)
    leaked["raw_artifact_path"] = r"C:\qualification\raw"
    with pytest.raises(CleanBootstrapQualificationError, match="absolute path"):
        validate_clean_bootstrap_qualification(leaked)
