from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.bridge.ocgcore import FilesystemScriptProvider, OcgcoreAssetError
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.resolver_index_policy import (
    RESOLVER_INDEX_POLICY_SCHEMA_VERSION,
    build_resolver_index_policy,
)


ROOT = Path(__file__).parents[1]


def test_checked_index_rejects_mutation_and_keeps_concurrent_reads_identical(
    tmp_path: Path,
) -> None:
    script = tmp_path / "Case.lua"
    script.write_bytes(b"return 1\n")
    provider = FilesystemScriptProvider(tmp_path)
    assert provider.get_script("Case.lua") == b"return 1\n"

    with ThreadPoolExecutor(max_workers=8) as executor:
        contents = list(executor.map(lambda _: provider.get_script("Case.lua"), range(32)))
    assert contents == [b"return 1\n"] * 32

    script.write_bytes(b"return 2\n")
    assert provider.get_script("Case.lua") == b"return 2\n"
    collision = tmp_path / "case.lua"
    collision.write_bytes(b"return 3\n")
    if len(tuple(tmp_path.iterdir())) == 2:
        with pytest.raises(OcgcoreAssetError, match="case-colliding"):
            provider.get_script("Case.lua")


def test_checked_resolver_policy_is_content_addressed_and_rejects_reuse() -> None:
    benchmark = json.loads(
        (ROOT / "docs/adr/evidence/0128_real_core_replay_pool.json").read_text(
            encoding="utf-8"
        )
    )
    policy = build_resolver_index_policy(benchmark)
    checked = json.loads(
        (ROOT / "docs/adr/evidence/0212_resolver_index_policy.json").read_text(
            encoding="utf-8"
        )
    )
    assert checked == policy
    policy_id = policy.pop("policy_id")

    assert policy["schema_version"] == RESOLVER_INDEX_POLICY_SCHEMA_VERSION
    assert policy["selected_mode"] == "checked_process_local"
    assert {candidate["decision"] for candidate in policy["candidates"]} == {
        "rejected",
        "rejected_for_v0.3",
    }
    assert policy_id == stable_digest(policy, prefix="resolverpolicy_")
