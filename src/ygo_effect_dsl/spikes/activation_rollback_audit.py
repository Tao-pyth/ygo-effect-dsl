from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from ygo_effect_dsl.engine.action import (
    ACTIVATION_ROLLBACK_UNREACHABLE,
    assert_valid_activation_rollback_probe,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.external.ocgcore import OcgcoreLayout, load_ocgcore_lock
from ygo_effect_dsl.prototype import invoke_real_core_worker_process


ACTIVATION_ROLLBACK_AUDIT_SCHEMA_VERSION = (
    "ocgcore-activation-rollback-audit-v1"
)
UPSTREAM_REPOSITORY = "https://github.com/edo9300/ygopro-core.git"
DEFAULT_EXPERIMENT = Path(
    "examples/experiments/real_core_activation_rollback_probe.yaml"
)
DEFAULT_OUTPUT = Path(
    "docs/ocgcore/evidence/activation_rollback_audit.json"
)
_FUNCTIONS = {
    "add_chain": (
        "processor.cpp",
        "bool field::process(Processors::AddChain& arg)",
        (),
        True,
    ),
    "execute_cost": (
        "processor.cpp",
        "bool field::process(Processors::ExecuteCost& arg)",
        (),
        True,
    ),
    "execute_target": (
        "processor.cpp",
        "bool field::process(Processors::ExecuteTarget& arg)",
        (),
        True,
    ),
    "parse_response_cards": (
        "playerop.cpp",
        "bool parse_response_cards(",
        (),
        True,
    ),
    "push_return_cards": (
        "scriptlib.cpp",
        "int32_t push_return_cards(",
        ("return_cards.canceled", "lua_pushnil(L)"),
        False,
    ),
    "select_matching_card": (
        "libduel.cpp",
        "LUA_STATIC_FUNCTION(SelectMatchingCard)",
        (
            "bool cancelable = false",
            "lua_isboolean(L, lastarg)",
            "emplace_process<Processors::SelectCard>(playerid, cancelable, min, max)",
            "return push_return_cards(L, cancelable)",
        ),
        False,
    ),
}


def _run(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _extract_function(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise ValueError(f"source function signature not found: {signature}")
    opening = source.find("{", start)
    if opening < 0:
        raise ValueError(f"source function has no body: {signature}")
    depth = 0
    for index in range(opening, len(source)):
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1].replace("\r\n", "\n")
    raise ValueError(f"source function body is unterminated: {signature}")


def _show(source_root: Path, ref: str, path: str) -> str:
    return _run(["git", "show", f"{ref}:{path}"], cwd=source_root)


def _api_version(source_root: Path, ref: str) -> str:
    source = _show(source_root, ref, "ocgapi_types.h")
    major = re.search(r"#define OCG_VERSION_MAJOR (\d+)", source)
    minor = re.search(r"#define OCG_VERSION_MINOR (\d+)", source)
    if major is None or minor is None:
        raise ValueError(f"ocgcore API macros are missing at {ref}")
    return f"{major.group(1)}.{minor.group(1)}"


def _semver_tag(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"v\d+(?:\.\d+)*", value):
        raise ValueError(f"unsupported upstream tag format {value!r}")
    return tuple(int(part) for part in value[1:].split("."))


def _remote_refs() -> tuple[str, list[dict[str, str]]]:
    head_output = _run(["git", "ls-remote", UPSTREAM_REPOSITORY, "HEAD"])
    head = head_output.split()[0]
    tag_output = _run(
        ["git", "ls-remote", "--tags", "--refs", UPSTREAM_REPOSITORY]
    )
    tags = []
    for line in tag_output.splitlines():
        commit, raw_ref = line.split()
        tag = raw_ref.removeprefix("refs/tags/")
        tags.append({"commit": commit, "tag": tag})
    tags.sort(key=lambda item: _semver_tag(item["tag"]))
    return head, tags


def _ensure_object(source_root: Path, ref: str) -> None:
    try:
        _run(["git", "cat-file", "-e", f"{ref}^{{commit}}"], cwd=source_root)
    except subprocess.CalledProcessError:
        _run(
            ["git", "fetch", "--no-tags", "origin", ref],
            cwd=source_root,
        )


def _source_audit(
    source_root: Path, *, pinned_commit: str, upstream_head: str
) -> dict[str, Any]:
    functions = []
    for name, (path, signature, markers, exact_required) in sorted(
        _FUNCTIONS.items()
    ):
        pinned_body = _extract_function(
            _show(source_root, pinned_commit, path), signature
        )
        head_body = _extract_function(
            _show(source_root, upstream_head, path), signature
        )
        pinned_sha256 = hashlib.sha256(pinned_body.encode("utf-8")).hexdigest()
        head_sha256 = hashlib.sha256(head_body.encode("utf-8")).hexdigest()
        same_body = head_sha256 == pinned_sha256
        markers_preserved = all(
            marker in pinned_body and marker in head_body for marker in markers
        )
        functions.append(
            {
                "exact_body_required": exact_required,
                "head_sha256": head_sha256,
                "markers_preserved": markers_preserved,
                "name": name,
                "path": path,
                "pinned_sha256": pinned_sha256,
                "relevant_contract_same": (
                    same_body or (not exact_required and markers_preserved)
                ),
                "same_body": same_body,
                "signature": signature,
            }
        )
    return {
        "functions": functions,
        "observations": {
            "add_chain_emits_msg_chained_after_cost_and_target": True,
            "cancel_response_sets_return_cards_cancelled": True,
            "execute_cost_and_target_do_not_signal_add_chain_rollback": True,
            "lua_receives_nil_for_cancelled_card_selection": True,
        },
        "source_flow_unchanged": all(
            item["relevant_contract_same"] for item in functions
        ),
    }


def build_activation_rollback_audit(
    *,
    audit_date: str,
    experiment_path: str | Path = DEFAULT_EXPERIMENT,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", audit_date):
        raise ValueError("audit_date must use YYYY-MM-DD")
    lock = load_ocgcore_lock()
    layout = OcgcoreLayout.create(lock)
    resolved_source = (
        Path(source_root).resolve() if source_root is not None else layout.source
    )
    upstream_head, tags = _remote_refs()
    if not tags:
        raise ValueError("upstream has no version tags")
    latest_tag = tags[-1]
    _ensure_object(resolved_source, upstream_head)
    experiment = load_experiment_document(experiment_path)
    first = invoke_real_core_worker_process(
        experiment=experiment,
        document_kind="activation_rollback_probe",
    )
    second = invoke_real_core_worker_process(
        experiment=experiment,
        document_kind="activation_rollback_probe",
    )
    if not first.succeeded or first.document is None:
        raise RuntimeError(f"first rollback probe failed: {first.diagnostic}")
    if not second.succeeded or second.document is None:
        raise RuntimeError(f"second rollback probe failed: {second.diagnostic}")
    assert_valid_activation_rollback_probe(first.document)
    assert_valid_activation_rollback_probe(second.document)
    source_audit = _source_audit(
        resolved_source,
        pinned_commit=str(lock.source["commit"]),
        upstream_head=upstream_head,
    )
    latest_release_is_pinned = (
        latest_tag["tag"] == lock.source["ref"]
        and latest_tag["commit"] == lock.source["commit"]
    )
    head_api = _api_version(resolved_source, upstream_head)
    remains_unsupported = (
        first.document["classification"] == ACTIVATION_ROLLBACK_UNREACHABLE
        and first.document == second.document
        and latest_release_is_pinned
        and head_api == "11.0"
        and source_audit["source_flow_unchanged"]
    )
    identity = to_canonical_data(
        {
            "audit_date": audit_date,
            "conclusion": (
                "remains_unsupported"
                if remains_unsupported
                else "requires_new_runtime_probe"
            ),
            "fresh_worker_reproducibility": {
                "documents_identical": first.document == second.document,
                "first_stdout_digest": first.stdout_digest,
                "second_stdout_digest": second.stdout_digest,
            },
            "probe": first.document,
            "raw_replay_contract": {
                "classification": "parser_and_aggregation_contract",
                "preserved": True,
                "real_core_reachability_claim": False,
            },
            "schema_version": ACTIVATION_ROLLBACK_AUDIT_SCHEMA_VERSION,
            "source_audit": source_audit,
            "upstream": {
                "commit_distance_from_release": int(
                    _run(
                        [
                            "git",
                            "rev-list",
                            "--count",
                            f"{lock.source['commit']}..{upstream_head}",
                        ],
                        cwd=resolved_source,
                    )
                ),
                "head": {
                    "api": head_api,
                    "commit": upstream_head,
                    "commit_time": _run(
                        ["git", "show", "-s", "--format=%cI", upstream_head],
                        cwd=resolved_source,
                    ),
                    "runtime_tested": False,
                    "source_flow_matches_pinned_release": source_audit[
                        "source_flow_unchanged"
                    ],
                },
                "latest_release": {
                    "api": _api_version(
                        resolved_source, str(latest_tag["commit"])
                    ),
                    "commit": latest_tag["commit"],
                    "runtime_tested": True,
                    "tag": latest_tag["tag"],
                },
                "release_tags": tags,
                "repository": UPSTREAM_REPOSITORY,
            },
        }
    )
    audit = {
        **identity,
        "evidence_id": stable_digest(identity, prefix="rollbackaudit_"),
    }
    assert_valid_activation_rollback_audit(audit)
    return audit


def assert_valid_activation_rollback_audit(
    document: Mapping[str, Any],
) -> None:
    if document.get("schema_version") != ACTIVATION_ROLLBACK_AUDIT_SCHEMA_VERSION:
        raise ValueError("unsupported activation rollback audit schema")
    identity = {
        key: value for key, value in document.items() if key != "evidence_id"
    }
    if document.get("evidence_id") != stable_digest(
        identity, prefix="rollbackaudit_"
    ):
        raise ValueError("activation rollback audit evidence_id mismatch")
    probe = document.get("probe")
    if not isinstance(probe, Mapping):
        raise ValueError("activation rollback audit probe must be a mapping")
    assert_valid_activation_rollback_probe(probe)
    reproducibility = document.get("fresh_worker_reproducibility")
    if not isinstance(reproducibility, Mapping):
        raise ValueError("fresh worker reproducibility must be a mapping")
    if reproducibility.get("documents_identical") is not True:
        raise ValueError("fresh worker rollback probes are not identical")
    source_audit = document.get("source_audit")
    if not isinstance(source_audit, Mapping):
        raise ValueError("source_audit must be a mapping")
    conclusion = document.get("conclusion")
    if conclusion == "remains_unsupported":
        if probe.get("classification") != ACTIVATION_ROLLBACK_UNREACHABLE:
            raise ValueError("unsupported conclusion conflicts with probe")
        if source_audit.get("source_flow_unchanged") is not True:
            raise ValueError("unsupported conclusion requires unchanged source flow")
    elif conclusion != "requires_new_runtime_probe":
        raise ValueError("unsupported activation rollback audit conclusion")


def dump_activation_rollback_audit(
    document: Mapping[str, Any], path: str | Path
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ygo_effect_dsl.spikes.activation_rollback_audit"
    )
    parser.add_argument("--audit-date", required=True)
    parser.add_argument("--experiment", default=str(DEFAULT_EXPERIMENT))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--source-root")
    args = parser.parse_args()
    audit = build_activation_rollback_audit(
        audit_date=args.audit_date,
        experiment_path=args.experiment,
        source_root=args.source_root,
    )
    path = dump_activation_rollback_audit(audit, args.out)
    print(f"wrote {path.resolve()} evidence_id={audit['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
