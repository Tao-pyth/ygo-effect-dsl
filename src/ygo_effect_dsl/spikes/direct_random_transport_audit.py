from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from ygo_effect_dsl.engine.bridge.ocgcore import (
    DIRECT_RANDOM_TRACE_TRANSPORT,
    direct_random_trace_metadata,
)
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import (
    load_ocgcore_lock,
    resolve_ocgcore_runtime,
)


DIRECT_RANDOM_TRANSPORT_AUDIT_SCHEMA_VERSION = (
    "ocgcore-direct-random-transport-audit-v1"
)
SUPPORTED_EDOPRO_COMMIT = "650ec7b2273f60733b178d238cf6fec46722d8b4"
LEGACY_HINT_TYPE = 199
_DEFINE_PATTERN = re.compile(r"^#define\s+(HINT_[A-Z0-9_]+)\s+([0-9]+)\s*$", re.MULTILINE)


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise ValueError(f"required source file is missing: {path}")
    return path.read_text(encoding="utf-8")


def _file_evidence(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    content = path.read_bytes()
    return {
        "path": relative,
        "sha256": sha256(content).hexdigest(),
        "size": len(content),
    }


def _git_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _core_audit(root: Path, *, expected_commit: str | None) -> dict[str, Any]:
    commit = _git_commit(root)
    if expected_commit is not None and commit != expected_commit:
        raise ValueError(
            f"core source commit must be {expected_commit}, got {commit}"
        )
    api_types = _read(root, "ocgapi_types.h")
    libdebug = _read(root, "libdebug.cpp")
    libduel = _read(root, "libduel.cpp")
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in root.rglob("*.h")
    )
    source_text += "\n" + "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in root.rglob("*.cpp")
    )
    dedicated_random_hook = bool(
        re.search(
            r"OCGAPI[^\n]*OCG_[A-Za-z0-9_]*(Random|Rng)|"
            r"typedef[^\n]*(random|rng)[A-Za-z0-9_]*(callback|handler)",
            source_text,
            re.IGNORECASE,
        )
    )
    checks = {
        "debug_message_uses_from_script_log_type": (
            "OCG_LOG_TYPE_FROM_SCRIPT" in libdebug
            and "handle_message" in libdebug
        ),
        "duel_options_expose_log_handler": (
            "typedef void (*OCG_LogHandler)" in api_types
            and "OCG_LogHandler logHandler" in api_types
        ),
        "get_random_number_uses_internal_rng": (
            "LUA_STATIC_FUNCTION(GetRandomNumber)" in libduel
            and "get_next_integer(min, max)" in libduel
        ),
    }
    return {
        "checks": checks,
        "commit": commit,
        "dedicated_random_hook_found": dedicated_random_hook,
        "files": [
            _file_evidence(root, relative)
            for relative in ("libdebug.cpp", "libduel.cpp", "ocgapi_types.h")
        ],
        "status": "compatible" if all(checks.values()) else "incompatible",
    }


def _edopro_audit(root: Path) -> dict[str, Any]:
    commit = _git_commit(root)
    if commit != SUPPORTED_EDOPRO_COMMIT:
        raise ValueError(
            f"EDOPro source commit must be {SUPPORTED_EDOPRO_COMMIT}, got {commit}"
        )
    constants = _read(root, "gframe/ocgapi_constants.h") + "\n" + _read(
        root, "gframe/core_utils.h"
    )
    generic_duel = _read(root, "gframe/generic_duel.cpp")
    single_mode = _read(root, "gframe/single_mode.cpp")
    duel_client = _read(root, "gframe/duelclient.cpp")
    hint_values = {
        name: int(value) for name, value in _DEFINE_PATTERN.findall(constants)
    }
    legacy_defined = LEGACY_HINT_TYPE in hint_values.values()
    checks = {
        "legacy_hint_199_has_no_named_constant": not legacy_defined,
        "legacy_hint_199_not_routed_by_online_server": (
            "case 199" not in generic_duel
        ),
        "legacy_hint_199_not_analyzed_by_single_mode": (
            "case 199" not in single_mode
        ),
        "legacy_hint_199_not_handled_by_duel_client_switch": (
            "case 199" not in duel_client
        ),
        "unknown_hint_can_confirm_queued_panel_if_directly_injected": (
            "if(type != HINT_SELECTMSG)" in duel_client
            and "PerformQueuedPanelConfirm();" in duel_client
        ),
    }
    return {
        "checks": checks,
        "commit": commit,
        "files": [
            _file_evidence(root, relative)
            for relative in (
                "gframe/core_utils.h",
                "gframe/duelclient.cpp",
                "gframe/generic_duel.cpp",
                "gframe/ocgapi_constants.h",
                "gframe/single_mode.cpp",
            )
        ],
        "hint_constants": hint_values,
        "legacy_transport_assessment": {
            "direct_injection": "no display case but queued panel confirmation can run",
            "online_server": "unknown hint is not sent",
            "single_mode": "unknown hint is not analyzed",
        },
        "status": "legacy_not_collision_free_for_arbitrary_delivery",
    }


def build_direct_random_transport_audit(
    *,
    edopro_source_root: str | Path,
    upstream_core_source_root: str | Path,
    external_root: str | Path | None = None,
) -> dict[str, Any]:
    core_lock = load_ocgcore_lock()
    runtime = resolve_ocgcore_runtime(external_root=external_root)
    pinned_core_root = runtime.parent.parent / "source"
    edopro = _edopro_audit(Path(edopro_source_root).resolve())
    pinned_core = _core_audit(
        pinned_core_root,
        expected_commit=core_lock.source["commit"],
    )
    upstream_core = _core_audit(
        Path(upstream_core_source_root).resolve(),
        expected_commit=None,
    )
    checks = {
        "client_receives_no_trace_message": True,
        "legacy_hint_transport_deprecated": True,
        "pinned_core_log_transport_compatible": (
            pinned_core["status"] == "compatible"
        ),
        "supported_edopro_source_audited": all(edopro["checks"].values()),
        "upstream_dedicated_random_hook_absent": (
            not upstream_core["dedicated_random_hook_found"]
        ),
        "upstream_log_transport_still_compatible": (
            upstream_core["status"] == "compatible"
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError("direct random transport audit failed: " + ", ".join(failed))
    identity = to_canonical_data(
        {
            "checks": checks,
            "instrumentation": direct_random_trace_metadata(enabled=True),
            "legacy_hint_type": LEGACY_HINT_TYPE,
            "pinned_core": pinned_core,
            "schema_version": DIRECT_RANDOM_TRANSPORT_AUDIT_SCHEMA_VERSION,
            "supported_edopro": edopro,
            "transport": DIRECT_RANDOM_TRACE_TRANSPORT,
            "transport_decision": (
                "use script log callback; emit no duel/client message"
            ),
            "upstream_core_observation": upstream_core,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="rngtransportev_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="audit direct RNG transport against pinned client/core source"
    )
    parser.add_argument("--edopro-source-root", type=Path, required=True)
    parser.add_argument("--upstream-core-source-root", type=Path, required=True)
    parser.add_argument("--external-root")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = build_direct_random_transport_audit(
        edopro_source_root=args.edopro_source_root,
        upstream_core_source_root=args.upstream_core_source_root,
        external_root=args.external_root,
    )
    serialized = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"direct-random-transport-audit: wrote {args.out} "
            f"evidence_id={evidence['evidence_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
