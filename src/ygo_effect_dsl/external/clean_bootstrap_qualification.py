from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import re
import time
from typing import Any, Mapping
from uuid import uuid4

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreLayout,
    bootstrap_ocgcore,
    doctor_ocgcore,
    load_ocgcore_lock,
    verify_ocgcore,
)
from ygo_effect_dsl.io_atomic import atomic_write_text


CLEAN_BOOTSTRAP_QUALIFICATION_SCHEMA_VERSION = (
    "ocgcore-clean-bootstrap-qualification-v1"
)
_BUILD_CASES = (
    ("clean_primary", "primary", "none"),
    ("repeat_primary", "primary", "idempotent-repeat"),
    ("stale_build_recovery", "primary", "build-and-runtime-partials"),
    ("clean_independent", "independent", "none"),
    ("stale_download_recovery", "download_recovery", "download-partial"),
)
_NETWORK_IMPORTS = frozenset(
    {"aiohttp", "http.client", "httpx", "requests", "urllib.request"}
)
_NETWORK_OWNER = "ygo_effect_dsl.external.ocgcore"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\|/)")


class CleanBootstrapQualificationError(ValueError):
    """The clean ocgcore bootstrap could not be qualified unambiguously."""


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CleanBootstrapQualificationError(f"{path} must be a mapping")
    return value


def _non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise CleanBootstrapQualificationError(f"{path} must be a non-empty string")
    return value


def _sha256(value: Any, path: str) -> str:
    text = _non_empty_string(value, path)
    if _SHA256.fullmatch(text) is None:
        raise CleanBootstrapQualificationError(f"{path} must be a lowercase SHA-256")
    return text


def _reject_absolute_paths(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_absolute_paths(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_absolute_paths(item, f"{path}[{index}]")
    elif isinstance(value, str) and _ABSOLUTE_PATH.match(value):
        raise CleanBootstrapQualificationError(
            f"{path} contains an absolute path in sanitized evidence"
        )


def _module_name(package_root: Path, source: Path) -> str:
    relative = source.relative_to(package_root.parent).with_suffix("")
    return ".".join(relative.parts)


def _network_import_names(tree: ast.AST) -> set[str]:
    observed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _NETWORK_IMPORTS:
                    observed.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                candidate = f"{node.module}.{alias.name}"
                if node.module in _NETWORK_IMPORTS:
                    observed.add(node.module)
                elif candidate in _NETWORK_IMPORTS:
                    observed.add(candidate)
    return observed


def audit_bootstrap_network_boundary(
    package_root: str | Path | None = None,
) -> dict[str, Any]:
    root = (
        Path(package_root).resolve()
        if package_root is not None
        else Path(__file__).resolve().parents[1]
    )
    imports: list[dict[str, str]] = []
    for source in sorted(root.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=source.name)
        module = _module_name(root, source)
        for import_name in sorted(_network_import_names(tree)):
            imports.append({"import": import_name, "module": module})
    owners = sorted({entry["module"] for entry in imports})
    if not imports:
        raise CleanBootstrapQualificationError(
            "network ownership audit did not find the bootstrap transport"
        )
    if owners != [_NETWORK_OWNER]:
        raise CleanBootstrapQualificationError(
            "network-capable imports exist outside the ocgcore bootstrap owner: "
            + ", ".join(owners)
        )
    return {
        "audit_kind": "static-import-ownership",
        "bootstrap_network_modules": owners,
        "imports": imports,
        "non_bootstrap_network_import_count": 0,
        "runtime_network_access": False,
    }


def _ensure_repository_external(
    work_root: str | Path,
    *,
    repository_root: str | Path | None = None,
) -> Path:
    root = Path(work_root).expanduser().resolve()
    repository = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[3]
    )
    if root == repository or repository in root.parents:
        raise CleanBootstrapQualificationError(
            "clean bootstrap work root must be outside the repository"
        )
    root.mkdir(parents=True, exist_ok=True)
    return root


def prepare_stale_build_partials(external_root: str | Path) -> tuple[Path, Path]:
    lock = load_ocgcore_lock()
    layout = OcgcoreLayout.create(lock, external_root)
    build_partial = layout.install_root / ".build.partial"
    runtime_partial = layout.install_root / ".runtime.partial"
    for partial in (build_partial, runtime_partial):
        partial.mkdir(parents=True, exist_ok=False)
        (partial / "interrupted.marker").write_text("qualification probe\n", encoding="utf-8")
    return build_partial, runtime_partial


def prepare_stale_download_partial(external_root: str | Path) -> Path:
    lock = load_ocgcore_lock()
    layout = OcgcoreLayout.create(lock, external_root)
    archive = layout.tools / "downloads" / str(lock.tool["archive"])
    partial = archive.with_suffix(archive.suffix + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.write_bytes(b"interrupted qualification download")
    return partial


def _source_identity(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "commit": source.get("commit"),
        "submodules": [
            {"commit": item.get("commit"), "path": item.get("path")}
            for item in source.get("submodules", [])
        ],
        "tree": source.get("tree"),
    }


def _build_observation(verified: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source = _mapping(verified.get("source"), "verified.source")
    build = _mapping(verified.get("build"), "verified.build")
    binary = _mapping(build.get("binary"), "verified.build.binary")
    api = _mapping(build.get("api"), "verified.build.api")
    premake = _mapping(build.get("premake"), "verified.build.premake")
    input_identity = {
        "api": {"major": api.get("major"), "minor": api.get("minor")},
        "compiler": {
            "family": build.get("compiler_family"),
            "version": build.get("compiler_version"),
        },
        "premake": {"sha256": premake.get("sha256"), "version": premake.get("version")},
        "source": _source_identity(source),
    }
    runtime_binary = {"sha256": binary.get("sha256"), "size": binary.get("size")}
    return input_identity, runtime_binary


def _run_build(
    *,
    label: str,
    root_slot: str,
    external_root: Path,
    recovery_probe: str,
    stale_paths: tuple[Path, ...] = (),
) -> dict[str, Any]:
    started = time.perf_counter()
    bootstrap_ocgcore(external_root=external_root)
    verified = verify_ocgcore(external_root=external_root)
    elapsed = round(time.perf_counter() - started, 6)
    if stale_paths and any(path.exists() for path in stale_paths):
        raise CleanBootstrapQualificationError(
            f"{label} left a harness-owned interruption partial behind"
        )
    input_identity, runtime_binary = _build_observation(verified)
    return {
        "elapsed_seconds": elapsed,
        "input_identity": input_identity,
        "input_identity_digest": stable_digest(input_identity, prefix="coreinput_"),
        "label": label,
        "recovery_observed": True,
        "recovery_probe": recovery_probe,
        "root_slot": root_slot,
        "runtime_binary": runtime_binary,
        "verify_ok": verified.get("ok") is True,
    }


def run_clean_bootstrap_qualification(
    *,
    work_root: str | Path,
) -> dict[str, Any]:
    owned_root = _ensure_repository_external(work_root)
    session_id = f"clean-bootstrap-{uuid4().hex}"
    session = owned_root / session_id
    session.mkdir()
    primary = session / "primary"
    independent = session / "independent"
    download_recovery = session / "download-recovery"

    lock = load_ocgcore_lock()
    network = audit_bootstrap_network_boundary()
    doctor = doctor_ocgcore(external_root=primary)
    if doctor.get("ok") is not True:
        raise CleanBootstrapQualificationError(
            "ocgcore doctor rejected the clean-bootstrap environment"
        )

    builds = [
        _run_build(
            label="clean_primary",
            root_slot="primary",
            external_root=primary,
            recovery_probe="none",
        ),
        _run_build(
            label="repeat_primary",
            root_slot="primary",
            external_root=primary,
            recovery_probe="idempotent-repeat",
        ),
    ]
    stale_build_paths = prepare_stale_build_partials(primary)
    builds.append(
        _run_build(
            label="stale_build_recovery",
            root_slot="primary",
            external_root=primary,
            recovery_probe="build-and-runtime-partials",
            stale_paths=stale_build_paths,
        )
    )
    builds.append(
        _run_build(
            label="clean_independent",
            root_slot="independent",
            external_root=independent,
            recovery_probe="none",
        )
    )
    stale_download = prepare_stale_download_partial(download_recovery)
    builds.append(
        _run_build(
            label="stale_download_recovery",
            root_slot="download_recovery",
            external_root=download_recovery,
            recovery_probe="download-partial",
            stale_paths=(stale_download,),
        )
    )

    input_identities = [entry["input_identity_digest"] for entry in builds]
    if len(set(input_identities)) != 1:
        raise CleanBootstrapQualificationError(
            "clean bootstrap inputs differ across builds"
        )
    binary_hashes = sorted({entry["runtime_binary"]["sha256"] for entry in builds})
    binary_sizes = {entry["runtime_binary"]["size"] for entry in builds}
    if len(binary_sizes) != 1:
        raise CleanBootstrapQualificationError(
            "clean bootstrap runtime binary sizes differ across builds"
        )
    source = lock.source
    report: dict[str, Any] = {
        "builds": builds,
        "doctor": {
            "git_available": bool(doctor.get("git")),
            "machine": doctor.get("machine"),
            "ok": True,
            "platform": doctor.get("platform"),
            "virtual_build_drive": doctor.get("virtual_build_drive"),
            "virtual_build_drive_available": doctor.get("virtual_build_drive_available"),
            "visual_studio_available": doctor.get("visual_studio") is not None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "machine": platform.machine(),
            "operating_system": platform.system(),
            "python": platform.python_version(),
        },
        "binary_reproducibility": {
            "distinct_sha256": binary_hashes,
            "distinct_sha256_count": len(binary_hashes),
            "follow_up_issue": "#171",
            "required_for_clean_bootstrap": False,
            "scope": "single-session-same-host",
            "status": (
                "session_bit_identical"
                if len(binary_hashes) == 1
                else "session_variant_observed"
            ),
        },
        "invariants": {
            "all_inputs_identical": True,
            "all_runtime_sizes_identical": True,
            "all_verifications_succeeded": True,
            "download_interruption_recovered": True,
            "idempotent_repeat": True,
            "same_host_only": True,
            "stale_build_interruption_recovered": True,
        },
        "lock": {
            "api": {"major": lock.api["major"], "minor": lock.api["minor"]},
            "lock_id": lock.lock_id,
            "lock_sha256": lock.sha256,
            "runtime_network_access": lock.data["policy"]["runtime_network_access"],
            "source": {
                "commit": source["commit"],
                "submodules": [
                    {"commit": item["commit"], "path": item["path"]}
                    for item in source["submodules"]
                ],
                "tree": source["tree"],
            },
        },
        "network_boundary": network,
        "package_version": __version__,
        "qualification_id": "",
        "raw_artifact_policy": "retained-outside-repository",
        "schema_version": CLEAN_BOOTSTRAP_QUALIFICATION_SCHEMA_VERSION,
        "status": "qualified_local",
        "work_session_id": session_id,
    }
    report["qualification_id"] = stable_digest(
        {key: value for key, value in report.items() if key != "qualification_id"},
        prefix="corebootstrap_",
    )
    return validate_clean_bootstrap_qualification(report)


def validate_clean_bootstrap_qualification(value: Any) -> dict[str, Any]:
    document = dict(_mapping(value, "$"))
    if document.get("schema_version") != CLEAN_BOOTSTRAP_QUALIFICATION_SCHEMA_VERSION:
        raise CleanBootstrapQualificationError(
            "unsupported clean bootstrap qualification schema"
        )
    if document.get("status") != "qualified_local":
        raise CleanBootstrapQualificationError(
            "clean bootstrap qualification status must be qualified_local"
        )
    if document.get("raw_artifact_policy") != "retained-outside-repository":
        raise CleanBootstrapQualificationError("raw artifacts must remain external")
    _reject_absolute_paths(document)
    required_top_level = {
        "binary_reproducibility",
        "builds",
        "doctor",
        "generated_at",
        "host",
        "invariants",
        "lock",
        "network_boundary",
        "package_version",
        "qualification_id",
        "raw_artifact_policy",
        "schema_version",
        "status",
        "work_session_id",
    }
    if set(document) != required_top_level:
        raise CleanBootstrapQualificationError(
            "clean bootstrap qualification fields are not canonical"
        )
    if not _non_empty_string(document.get("work_session_id"), "$.work_session_id").startswith(
        "clean-bootstrap-"
    ):
        raise CleanBootstrapQualificationError("work session ID is invalid")
    _non_empty_string(document.get("package_version"), "$.package_version")

    try:
        datetime.fromisoformat(_non_empty_string(document.get("generated_at"), "$.generated_at"))
    except ValueError as exc:
        raise CleanBootstrapQualificationError("$.generated_at is invalid") from exc

    lock = _mapping(document.get("lock"), "$.lock")
    _sha256(lock.get("lock_sha256"), "$.lock.lock_sha256")
    if lock.get("runtime_network_access") is not False:
        raise CleanBootstrapQualificationError("runtime network access must be disabled")
    lock_api = _mapping(lock.get("api"), "$.lock.api")
    lock_source = _mapping(lock.get("source"), "$.lock.source")
    _non_empty_string(lock.get("lock_id"), "$.lock.lock_id")
    for field in ("major", "minor"):
        if not isinstance(lock_api.get(field), int) or isinstance(lock_api.get(field), bool):
            raise CleanBootstrapQualificationError(f"lock API {field} must be an integer")
    for field in ("commit", "tree"):
        text = _non_empty_string(lock_source.get(field), f"$.lock.source.{field}")
        if re.fullmatch(r"[0-9a-f]{40}", text) is None:
            raise CleanBootstrapQualificationError(f"lock source {field} is invalid")

    doctor = _mapping(document.get("doctor"), "$.doctor")
    for field in (
        "git_available",
        "ok",
        "virtual_build_drive_available",
        "visual_studio_available",
    ):
        if doctor.get(field) is not True:
            raise CleanBootstrapQualificationError(f"doctor field {field} must be true")

    network = _mapping(document.get("network_boundary"), "$.network_boundary")
    if network.get("runtime_network_access") is not False:
        raise CleanBootstrapQualificationError("network audit permits runtime access")
    if network.get("non_bootstrap_network_import_count") != 0:
        raise CleanBootstrapQualificationError("network imports escaped bootstrap ownership")
    if network.get("bootstrap_network_modules") != [_NETWORK_OWNER]:
        raise CleanBootstrapQualificationError("network bootstrap owner is inconsistent")
    if network.get("imports") != [
        {"import": "urllib.request", "module": _NETWORK_OWNER}
    ]:
        raise CleanBootstrapQualificationError("network import audit is inconsistent")

    builds = document.get("builds")
    if not isinstance(builds, list) or len(builds) != len(_BUILD_CASES):
        raise CleanBootstrapQualificationError("qualification requires five ordered builds")
    build_values = [
        _mapping(raw_build, f"$.builds[{index}]")
        for index, raw_build in enumerate(builds)
    ]
    observed_cases = [
        (build.get("label"), build.get("root_slot"), build.get("recovery_probe"))
        for build in build_values
    ]
    if observed_cases != list(_BUILD_CASES):
        raise CleanBootstrapQualificationError(
            "qualification build cases are not canonical"
        )
    input_identities: list[Mapping[str, Any]] = []
    input_digests: list[str] = []
    binary_hashes: list[str] = []
    binary_sizes: list[int] = []
    for index, build in enumerate(build_values):
        elapsed = build.get("elapsed_seconds")
        if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed <= 0:
            raise CleanBootstrapQualificationError("build elapsed time must be positive")
        if build.get("verify_ok") is not True or build.get("recovery_observed") is not True:
            raise CleanBootstrapQualificationError("every build and recovery must verify")
        identity = _mapping(build.get("input_identity"), "input_identity")
        if _mapping(identity.get("api"), "input_identity.api") != lock_api:
            raise CleanBootstrapQualificationError("build API differs from the lock")
        if _mapping(identity.get("source"), "input_identity.source") != lock_source:
            raise CleanBootstrapQualificationError("build source differs from the lock")
        compiler = _mapping(identity.get("compiler"), "input_identity.compiler")
        _non_empty_string(compiler.get("family"), "input_identity.compiler.family")
        _non_empty_string(compiler.get("version"), "input_identity.compiler.version")
        premake = _mapping(identity.get("premake"), "input_identity.premake")
        _sha256(premake.get("sha256"), "input_identity.premake.sha256")
        _non_empty_string(premake.get("version"), "input_identity.premake.version")
        binary = _mapping(build.get("runtime_binary"), "runtime_binary")
        binary_hash = _sha256(binary.get("sha256"), "runtime_binary.sha256")
        if not isinstance(binary.get("size"), int) or binary["size"] < 1:
            raise CleanBootstrapQualificationError("runtime binary size must be positive")
        digest = _non_empty_string(
            build.get("input_identity_digest"), "input_identity_digest"
        )
        expected = stable_digest(identity, prefix="coreinput_")
        if digest != expected:
            raise CleanBootstrapQualificationError("input identity digest is inconsistent")
        input_identities.append(identity)
        input_digests.append(digest)
        binary_hashes.append(binary_hash)
        binary_sizes.append(binary["size"])
    if len(set(input_digests)) != 1 or any(
        identity != input_identities[0] for identity in input_identities[1:]
    ):
        raise CleanBootstrapQualificationError("build input identities differ")
    if len(set(binary_sizes)) != 1:
        raise CleanBootstrapQualificationError("runtime binary sizes differ")

    reproducibility = _mapping(
        document.get("binary_reproducibility"), "$.binary_reproducibility"
    )
    observed_hashes = sorted(set(binary_hashes))
    expected_status = (
        "session_bit_identical"
        if len(observed_hashes) == 1
        else "session_variant_observed"
    )
    if reproducibility.get("distinct_sha256") != observed_hashes:
        raise CleanBootstrapQualificationError("binary hash set is inconsistent")
    if reproducibility.get("distinct_sha256_count") != len(observed_hashes):
        raise CleanBootstrapQualificationError("binary hash count is inconsistent")
    if reproducibility.get("status") != expected_status:
        raise CleanBootstrapQualificationError("binary reproducibility status is inconsistent")
    if reproducibility.get("scope") != "single-session-same-host":
        raise CleanBootstrapQualificationError("binary reproducibility scope is inconsistent")
    if reproducibility.get("required_for_clean_bootstrap") is not False:
        raise CleanBootstrapQualificationError(
            "bit reproducibility must remain a separate release gate"
        )
    if reproducibility.get("follow_up_issue") != "#171":
        raise CleanBootstrapQualificationError("binary reproducibility follow-up is missing")

    invariants = _mapping(document.get("invariants"), "$.invariants")
    required_invariants = {
        "all_inputs_identical",
        "all_runtime_sizes_identical",
        "all_verifications_succeeded",
        "download_interruption_recovered",
        "idempotent_repeat",
        "same_host_only",
        "stale_build_interruption_recovered",
    }
    if set(invariants) != required_invariants or not all(
        value is True for value in invariants.values()
    ):
        raise CleanBootstrapQualificationError("qualification invariants are incomplete")

    qualification_id = document.pop("qualification_id", None)
    if qualification_id != stable_digest(document, prefix="corebootstrap_"):
        raise CleanBootstrapQualificationError("qualification ID is not canonical")
    return {**to_canonical_data(document), "qualification_id": qualification_id}


def write_clean_bootstrap_qualification(
    path: str | Path,
    qualification: Mapping[str, Any],
) -> None:
    validated = validate_clean_bootstrap_qualification(qualification)
    atomic_write_text(path, canonical_json(validated) + "\n")


def read_clean_bootstrap_qualification(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CleanBootstrapQualificationError(
            "clean bootstrap qualification is invalid JSON"
        ) from exc
    return validate_clean_bootstrap_qualification(value)


__all__ = [
    "CLEAN_BOOTSTRAP_QUALIFICATION_SCHEMA_VERSION",
    "CleanBootstrapQualificationError",
    "audit_bootstrap_network_boundary",
    "prepare_stale_build_partials",
    "prepare_stale_download_partial",
    "read_clean_bootstrap_qualification",
    "run_clean_bootstrap_qualification",
    "validate_clean_bootstrap_qualification",
    "write_clean_bootstrap_qualification",
]
