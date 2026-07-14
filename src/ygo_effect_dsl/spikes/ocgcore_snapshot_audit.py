from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import OcgcoreLayout, load_ocgcore_lock


SNAPSHOT_AUDIT_SCHEMA_VERSION = "ocgcore-snapshot-audit-v1"
_STATE_TRANSFER_TERMS = ("clone", "copy", "deserialize", "restore", "serialize", "snapshot")
_AUDITED_FILES = (
    "duel.h",
    "effect.cpp",
    "effect.h",
    "field.h",
    "interpreter.cpp",
    "interpreter.h",
    "libeffect.cpp",
    "libgroup.cpp",
    "ocgapi.cpp",
    "ocgapi.h",
    "ocgapi_types.h",
)
_PRIVATE_STATE_PATTERNS = {
    "callback_ownership": re.compile(r"OCG_(?:DataReader|ScriptReader|LogHandler)|payload[1-4]|_callback"),
    "chain_and_effect_usage": re.compile(r"current_chain|effect_count_code"),
    "lua_vm_and_coroutines": re.compile(r"lua_State\*|coroutines|call_depth"),
    "pending_processor_and_selection": re.compile(r"processor_list|reserved|select_cards|select_chains"),
    "raw_pointer_graph": re.compile(r"field\* game_field|interpreter\* lua|unordered_set<(?:card|group|effect)\*>"),
    "rng": re.compile(r"Xoshiro256StarStar random"),
    "transient_buffers_and_messages": re.compile(r"query_buffer|deque<duel_message>|vector<uint8_t> buff"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_c_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*", "", source)


def _line_matches(path: Path, pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if pattern.search(line):
            matches.append(
                {
                    "file": path.name,
                    "line": line_number,
                    "text": line.strip(),
                }
            )
    return matches


def _git_value(source_root: Path, *args: str) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def audit_ocgcore_snapshot_source(
    source_root: str | Path,
    *,
    lock_identity: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(source_root).resolve()
    missing = [name for name in _AUDITED_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError(f"ocgcore snapshot audit missing source files: {missing}")
    public_header = (root / "ocgapi.h").read_text(encoding="utf-8")
    public_functions = re.findall(
        r"\bOCGAPI\s+[^;\n]+?\b(OCG_[A-Za-z0-9_]+)\s*\(",
        _strip_c_comments(public_header),
    )
    transfer_functions = [
        function
        for function in public_functions
        if any(term in function.lower() for term in _STATE_TRANSFER_TERMS)
    ]
    internal_transfer_matches: list[dict[str, Any]] = []
    transfer_pattern = re.compile(
        "|".join(re.escape(term) for term in _STATE_TRANSFER_TERMS),
        re.IGNORECASE,
    )
    for name in _AUDITED_FILES:
        if name.startswith("ocgapi"):
            continue
        internal_transfer_matches.extend(_line_matches(root / name, transfer_pattern))
    private_state: dict[str, list[dict[str, Any]]] = {}
    for category, pattern in _PRIVATE_STATE_PATTERNS.items():
        matches: list[dict[str, Any]] = []
        for name in ("duel.h", "field.h", "interpreter.h", "ocgapi_types.h"):
            matches.extend(_line_matches(root / name, pattern))
        private_state[category] = matches
    source_revision = _git_value(root, "rev-parse", "HEAD")
    source_status = _git_value(root, "status", "--porcelain")
    source_files = {
        name: {"sha256": _sha256(root / name), "size": (root / name).stat().st_size}
        for name in _AUDITED_FILES
    }
    identity = to_canonical_data(
        {
            "decision": {
                "adopt_native_mid_duel_state": False,
                "cache_reuse_mode": "verified_replay_hint",
                "fallback": "fresh_worker_replay_prefix",
                "reason_codes": [
                    "no_public_state_transfer_api",
                    "no_snapshot_format_or_version_contract",
                    "private_lua_rng_processor_pointer_state",
                    "callback_payload_ownership_is_process_local",
                ],
            },
            "internal_transfer_matches": internal_transfer_matches,
            "lock": lock_identity,
            "private_state": private_state,
            "public_api": {
                "functions": public_functions,
                "state_transfer_functions": transfer_functions,
            },
            "schema_version": SNAPSHOT_AUDIT_SCHEMA_VERSION,
            "source": {
                "files": source_files,
                "git_clean": source_status == "",
                "git_revision": source_revision,
            },
        }
    )
    if transfer_functions:
        raise AssertionError(
            f"public ocgcore state-transfer API requires re-evaluation: {transfer_functions}"
        )
    if any(not matches for matches in private_state.values()):
        missing_categories = sorted(
            category for category, matches in private_state.items() if not matches
        )
        raise AssertionError(
            f"private state evidence changed; re-evaluate categories: {missing_categories}"
        )
    return {
        **identity,
        "audit_id": stable_digest(identity, prefix="snapshotaudit_"),
    }


def run_pinned_ocgcore_snapshot_audit(
    *, external_root: str | Path | None = None
) -> dict[str, Any]:
    lock = load_ocgcore_lock()
    layout = OcgcoreLayout.create(lock, external_root)
    return audit_ocgcore_snapshot_source(
        layout.source,
        lock_identity={
            "api": dict(lock.api),
            "commit": lock.source["commit"],
            "lock_id": lock.lock_id,
            "tree": lock.source["tree"],
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="audit pinned ocgcore source for mid-duel snapshot support"
    )
    parser.add_argument("--external-root")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = run_pinned_ocgcore_snapshot_audit(external_root=args.external_root)
    serialized = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"ocgcore-snapshot-audit: wrote {args.out} "
            f"audit_id={evidence['audit_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
