from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import time
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol

from ygo_effect_dsl.engine.bridge.ocgcore.errors import (
    MissingCardDataError,
    MissingScriptError,
    OcgcoreAssetError,
)
from ygo_effect_dsl.engine.bridge.ocgcore.types import CardRecord


MAX_SCRIPT_BYTES = 1024 * 1024
SCRIPT_RESOLUTION_SCHEMA_VERSION = 1
CARD_SCRIPTS_PROFILE_LEGACY = "card-scripts-legacy-all-v1"
CARD_SCRIPTS_PROFILE_OFFICIAL = "card-scripts-official-v1"
TYPE_LINK = 0x4000000


class CardDataProvider(Protocol):
    def get_card(self, code: int) -> CardRecord: ...


class ScriptProvider(Protocol):
    def get_script(self, name: str) -> bytes: ...


@dataclass(frozen=True)
class ResolvedScript:
    requested_name: str
    resolved_path: str
    source_kind: str
    content: bytes
    size: int
    sha256: str = ""

    def __post_init__(self) -> None:
        content = bytes(self.content)
        _normalise_script_name(self.requested_name)
        resolved_path = _normalise_script_name(self.resolved_path).as_posix()
        if not self.source_kind or any(character.isspace() for character in self.source_kind):
            raise OcgcoreAssetError("script resolution source_kind must be a non-empty token")
        if self.size != len(content):
            raise OcgcoreAssetError("script resolution size does not match its content")
        digest = hashlib.sha256(content).hexdigest()
        if self.sha256 and self.sha256 != digest:
            raise OcgcoreAssetError("script resolution SHA-256 does not match its content")
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "resolved_path", resolved_path)
        object.__setattr__(self, "sha256", digest)

    @classmethod
    def from_bytes(
        cls,
        *,
        requested_name: str,
        resolved_path: str,
        source_kind: str,
        content: bytes,
    ) -> "ResolvedScript":
        value = bytes(content)
        if len(value) > MAX_SCRIPT_BYTES:
            raise OcgcoreAssetError(
                f"Lua script {requested_name!r} exceeds {MAX_SCRIPT_BYTES} bytes"
            )
        return cls(
            requested_name=requested_name,
            resolved_path=resolved_path,
            source_kind=source_kind,
            content=value,
            size=len(value),
        )

    def audit_dict(self) -> dict[str, Any]:
        return {
            "requested_name": self.requested_name,
            "resolved_path": self.resolved_path,
            "source_kind": self.source_kind,
            "size": self.size,
            "sha256": self.sha256,
        }


def resolve_script(provider: ScriptProvider, name: str) -> ResolvedScript:
    _normalise_script_name(name)
    resolver = getattr(provider, "resolve_script", None)
    if callable(resolver):
        result = resolver(name)
        if not isinstance(result, ResolvedScript):
            raise OcgcoreAssetError(
                f"script provider {type(provider).__name__} returned an invalid resolution"
            )
        if result.requested_name != name:
            raise OcgcoreAssetError(
                f"script provider {type(provider).__name__} changed the requested name"
            )
        return result
    result = ResolvedScript.from_bytes(
        requested_name=name,
        resolved_path=name,
        source_kind=f"provider:{type(provider).__module__}.{type(provider).__qualname__}",
        content=provider.get_script(name),
    )
    return result


def _normalise_script_name(name: str) -> PurePosixPath:
    canonical = name.replace("\\", "/")
    relative = PurePosixPath(canonical)
    if (
        not name
        or "\x00" in name
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} or ":" in part for part in relative.parts)
        or relative.as_posix() != canonical
    ):
        raise MissingScriptError(name)
    return relative


class InMemoryCardDataProvider:
    def __init__(self, records: Mapping[int, CardRecord]) -> None:
        self._records = dict(records)

    def get_card(self, code: int) -> CardRecord:
        try:
            record = self._records[code]
        except KeyError as exc:
            raise MissingCardDataError(code) from exc
        record.validate()
        return record


class InMemoryScriptProvider:
    script_resolution_profile_id = "in-memory-script-provider-v1"

    def __init__(self, scripts: Mapping[str, bytes | str]) -> None:
        self._scripts = {
            name: value.encode("utf-8") if isinstance(value, str) else bytes(value)
            for name, value in scripts.items()
        }

    def get_script(self, name: str) -> bytes:
        return self.resolve_script(name).content

    def resolve_script(self, name: str) -> ResolvedScript:
        relative = _normalise_script_name(name)
        try:
            script = self._scripts[name]
        except KeyError as exc:
            raise MissingScriptError(name) from exc
        return ResolvedScript.from_bytes(
            requested_name=name,
            resolved_path=relative.as_posix(),
            source_kind="memory",
            content=script,
        )


class FilesystemScriptProvider:
    script_resolution_profile_id = "filesystem-strict-relative-v1"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise OcgcoreAssetError(f"Lua script root does not exist: {self.root}")
        self._directory_index: dict[
            Path,
            tuple[tuple[int, int, int], dict[str, tuple[Path, ...]]],
        ] = {}
        self._directory_index_builds = 0
        self._directory_index_hits = 0
        self._directory_index_build_seconds = 0.0

    def get_script(self, name: str) -> bytes:
        return self.resolve_script(name).content

    def resolve_script(self, name: str) -> ResolvedScript:
        relative = _normalise_script_name(name)
        candidate = self._resolve_exact(relative, requested_name=name)
        content = self._read_bounded(candidate, requested_name=name)
        return ResolvedScript.from_bytes(
            requested_name=name,
            resolved_path=relative.as_posix(),
            source_kind="filesystem",
            content=content,
        )

    def _resolve_exact(self, relative: PurePosixPath, *, requested_name: str) -> Path:
        current = self.root
        for index, part in enumerate(relative.parts):
            folded = self._indexed_entries(current, requested_name).get(
                part.casefold(), ()
            )
            exact = tuple(entry for entry in folded if entry.name == part)
            if len(folded) > 1:
                choices = ", ".join(sorted(entry.name for entry in folded))
                raise OcgcoreAssetError(
                    f"Lua script {requested_name!r} has a case-colliding path segment: {choices}"
                )
            if not exact:
                if folded:
                    raise OcgcoreAssetError(
                        f"Lua script {requested_name!r} does not match asset path case "
                        f"{folded[0].name!r}"
                    )
                raise MissingScriptError(requested_name)
            candidate = exact[0]
            try:
                candidate_info = candidate.lstat()
            except OSError as exc:
                raise MissingScriptError(requested_name) from exc
            if self._is_reparse(candidate, candidate_info):
                raise OcgcoreAssetError(
                    f"Lua script {requested_name!r} traverses a reparse point or symbolic link"
                )
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise MissingScriptError(requested_name) from exc
            if self.root != resolved and self.root not in resolved.parents:
                raise OcgcoreAssetError(
                    f"Lua script {requested_name!r} resolves outside the allowed root"
                )
            if index < len(relative.parts) - 1:
                if not stat.S_ISDIR(candidate_info.st_mode):
                    raise MissingScriptError(requested_name)
            elif not stat.S_ISREG(candidate_info.st_mode):
                raise MissingScriptError(requested_name)
            current = resolved
        return current

    @staticmethod
    def _file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    @staticmethod
    def _directory_identity(info: os.stat_result) -> tuple[int, int, int]:
        return (info.st_dev, info.st_ino, info.st_mtime_ns)

    @staticmethod
    def _is_reparse(path: Path, info: os.stat_result) -> bool:
        if stat.S_ISLNK(info.st_mode):
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = int(getattr(info, "st_file_attributes", 0))
        reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        return bool(reparse_flag and attributes & reparse_flag)

    def _lstat_regular(self, path: Path, requested_name: str) -> os.stat_result:
        try:
            info = path.lstat()
        except OSError as exc:
            raise MissingScriptError(requested_name) from exc
        if self._is_reparse(path, info):
            raise OcgcoreAssetError(
                f"Lua script {requested_name!r} traverses a reparse point or symbolic link"
            )
        if not stat.S_ISREG(info.st_mode):
            raise MissingScriptError(requested_name)
        return info

    def _lstat_directory(self, path: Path, requested_name: str) -> os.stat_result:
        try:
            info = path.lstat()
        except OSError as exc:
            raise MissingScriptError(requested_name) from exc
        if self._is_reparse(path, info):
            raise OcgcoreAssetError(
                f"Lua script {requested_name!r} traverses a reparse point or symbolic link"
            )
        if not stat.S_ISDIR(info.st_mode):
            raise MissingScriptError(requested_name)
        return info

    def _read_bounded(self, path: Path, *, requested_name: str) -> bytes:
        before = self._lstat_regular(path, requested_name)
        flags = os.O_RDONLY | int(getattr(os, "O_BINARY", 0))
        flags |= int(getattr(os, "O_NOFOLLOW", 0))
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise OcgcoreAssetError(
                f"Lua script {requested_name!r} could not be opened without following links"
            ) from exc
        try:
            try:
                opened_before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened_before.st_mode)
                    or self._file_identity(opened_before) != self._file_identity(before)
                ):
                    raise OcgcoreAssetError(
                        f"Lua script {requested_name!r} changed before it was opened"
                    )
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    content = stream.read(MAX_SCRIPT_BYTES + 1)
                opened_after = os.fstat(descriptor)
            except OSError as exc:
                raise OcgcoreAssetError(
                    f"Lua script {requested_name!r} could not be read safely"
                ) from exc
        finally:
            os.close(descriptor)
        if self._file_identity(opened_before) != self._file_identity(opened_after):
            raise OcgcoreAssetError(
                f"Lua script {requested_name!r} changed while it was read"
            )
        if len(content) > MAX_SCRIPT_BYTES:
            raise OcgcoreAssetError(
                f"Lua script {requested_name!r} exceeds {MAX_SCRIPT_BYTES} bytes"
            )
        after = self._lstat_regular(path, requested_name)
        if self._file_identity(opened_after) != self._file_identity(after):
            raise OcgcoreAssetError(
                f"Lua script {requested_name!r} changed after it was read"
            )
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise OcgcoreAssetError(
                f"Lua script {requested_name!r} disappeared after it was read"
            ) from exc
        if self.root != resolved and self.root not in resolved.parents:
            raise OcgcoreAssetError(
                f"Lua script {requested_name!r} resolves outside the allowed root"
            )
        return content

    def _indexed_entries(
        self, directory: Path, requested_name: str
    ) -> dict[str, tuple[Path, ...]]:
        before = self._lstat_directory(directory, requested_name)
        signature = self._directory_identity(before)
        cached = self._directory_index.get(directory)
        if cached is not None and cached[0] == signature:
            self._directory_index_hits += 1
            return cached[1]
        started = time.perf_counter()
        try:
            entries = tuple(directory.iterdir())
        except OSError as exc:
            raise MissingScriptError(requested_name) from exc
        grouped: dict[str, list[Path]] = {}
        for entry in entries:
            grouped.setdefault(entry.name.casefold(), []).append(entry)
        result = {
            key: tuple(sorted(values, key=lambda item: item.name))
            for key, values in grouped.items()
        }
        after = self._lstat_directory(directory, requested_name)
        if self._directory_identity(after) != signature:
            raise OcgcoreAssetError(
                f"Lua script directory changed while resolving {requested_name!r}"
            )
        self._directory_index[directory] = (signature, result)
        self._directory_index_builds += 1
        self._directory_index_build_seconds += time.perf_counter() - started
        return result

    def directory_index_telemetry(self) -> dict[str, int | float | str]:
        """Return process-local index measurements without exposing asset paths."""

        entry_count = 0
        key_count = 0
        estimated_bytes = 0
        for _signature, index in self._directory_index.values():
            key_count += len(index)
            for folded, entries in index.items():
                estimated_bytes += len(folded.encode("utf-8"))
                entry_count += len(entries)
                estimated_bytes += sum(
                    len(entry.name.encode("utf-8")) for entry in entries
                )
        return {
            "build_seconds": self._directory_index_build_seconds,
            "builds": self._directory_index_builds,
            "directories": len(self._directory_index),
            "entries": entry_count,
            "estimated_name_bytes": estimated_bytes,
            "hits": self._directory_index_hits,
            "keys": key_count,
            "persistence": "process_local_only",
        }


class CardScriptsProvider(FilesystemScriptProvider):
    """Resolve ProjectIgnis/CardScripts root helpers and card subdirectories."""

    CARD_DIRECTORIES = (
        "official",
        "pre-release",
        "pre-errata",
        "goat",
        "skill",
        "rush",
        "unofficial",
    )

    def __init__(
        self,
        root: str | Path,
        *,
        profile_id: str = CARD_SCRIPTS_PROFILE_LEGACY,
        card_directories: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(root)
        if profile_id not in {
            CARD_SCRIPTS_PROFILE_LEGACY,
            CARD_SCRIPTS_PROFILE_OFFICIAL,
        }:
            raise ValueError(f"unsupported CardScripts profile {profile_id!r}")
        if card_directories is None:
            selected = (
                self.CARD_DIRECTORIES
                if profile_id == CARD_SCRIPTS_PROFILE_LEGACY
                else ("official",)
            )
        else:
            selected = card_directories
        if len(set(selected)) != len(selected) or any(
            directory not in self.CARD_DIRECTORIES for directory in selected
        ):
            raise ValueError("card_directories must be a unique subset of CARD_DIRECTORIES")
        self.card_directories = tuple(selected)
        self.script_resolution_profile_id = profile_id
        self._allow_ambiguous_priority = (
            profile_id == CARD_SCRIPTS_PROFILE_LEGACY and card_directories is None
        )

    def resolve_script(self, name: str) -> ResolvedScript:
        if name == "c0.lua":
            return ResolvedScript.from_bytes(
                requested_name=name,
                resolved_path="builtin/c0.lua",
                source_kind="virtual",
                content=b"",
            )
        relative = _normalise_script_name(name)
        basename = relative.name
        is_card_script = (
            basename.startswith("c")
            and basename.endswith(".lua")
            and basename[1:-4].isdigit()
        )
        if "/" in name or "\\" in name:
            if (
                is_card_script
                and not self._allow_ambiguous_priority
                and relative.parts[0] not in self.card_directories
            ):
                raise OcgcoreAssetError(
                    f"Lua script {name!r} is outside CardScripts profile "
                    f"{self.script_resolution_profile_id!r}"
                )
            return super().resolve_script(name)

        matches: list[ResolvedScript] = []
        directories = self.card_directories if is_card_script else self.CARD_DIRECTORIES
        candidates = (name, *(f"{directory}/{name}" for directory in directories))
        for candidate_name in candidates:
            try:
                resolved = super().resolve_script(candidate_name)
            except MissingScriptError:
                continue
            matches.append(replace(resolved, requested_name=name))
        if not matches:
            raise MissingScriptError(name)
        if len(matches) > 1:
            if self._allow_ambiguous_priority:
                return matches[0]
            paths = ", ".join(sorted(item.resolved_path for item in matches))
            raise OcgcoreAssetError(
                f"Lua script {name!r} is ambiguous across allowed roots: {paths}"
            )
        return matches[0]


def card_scripts_profile_for_experiment_schema(schema_version: str) -> str:
    if schema_version in {"0.3a", "0.3b"}:
        return CARD_SCRIPTS_PROFILE_LEGACY
    if schema_version == "0.4":
        return CARD_SCRIPTS_PROFILE_OFFICIAL
    raise OcgcoreAssetError(
        f"no CardScripts resolution profile for Experiment {schema_version!r}"
    )


def _split_setcodes(value: int) -> tuple[int, ...]:
    result: list[int] = []
    unsigned = value & ((1 << 64) - 1)
    for shift in range(0, 64, 16):
        setcode = (unsigned >> shift) & 0xFFFF
        if setcode:
            result.append(setcode)
    return tuple(result)


class SQLiteCardDataProvider:
    """Read the standard YGOPro `datas` table without owning card semantics."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database).expanduser().resolve()
        if not self.database.is_file():
            raise OcgcoreAssetError(f"card database does not exist: {self.database}")
        uri = f"{self.database.as_uri()}?mode=ro"
        try:
            self._connection = sqlite3.connect(uri, uri=True)
        except sqlite3.Error as exc:
            raise OcgcoreAssetError(f"could not open card database: {exc}") from exc

    def get_database_row(self, code: int) -> dict[str, int]:
        try:
            row = self._connection.execute(
                "SELECT id, alias, setcode, type, atk, def, level, race, attribute "
                "FROM datas WHERE id = ?",
                (code,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise OcgcoreAssetError(f"could not read card data for {code}: {exc}") from exc
        if row is None:
            raise MissingCardDataError(code)
        return {
            key: int(value)
            for key, value in zip(
                (
                    "id",
                    "alias",
                    "setcode",
                    "type",
                    "atk",
                    "def",
                    "level",
                    "race",
                    "attribute",
                ),
                row,
                strict=True,
            )
        }

    def get_card(self, code: int) -> CardRecord:
        row = self.get_database_row(code)
        card_id = row["id"]
        alias = row["alias"]
        setcode = row["setcode"]
        card_type = row["type"]
        attack = row["atk"]
        defense = row["def"]
        packed_level = row["level"]
        race = row["race"]
        attribute = row["attribute"]
        packed_level = int(packed_level)
        defense = int(defense)
        record = CardRecord(
            code=int(card_id),
            alias=int(alias),
            setcodes=_split_setcodes(int(setcode)),
            type=int(card_type),
            level=packed_level & 0xFF,
            attribute=int(attribute),
            race=int(race),
            attack=int(attack),
            defense=defense,
            lscale=(packed_level >> 24) & 0xFF,
            rscale=(packed_level >> 16) & 0xFF,
            link_marker=defense if int(card_type) & TYPE_LINK else 0,
        )
        record.validate()
        return record

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteCardDataProvider":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()
