from __future__ import annotations

import sqlite3
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol

from ygo_effect_dsl.engine.bridge.ocgcore.errors import (
    MissingCardDataError,
    MissingScriptError,
    OcgcoreAssetError,
)
from ygo_effect_dsl.engine.bridge.ocgcore.types import CardRecord


MAX_SCRIPT_BYTES = 1024 * 1024
TYPE_LINK = 0x4000000


class CardDataProvider(Protocol):
    def get_card(self, code: int) -> CardRecord: ...


class ScriptProvider(Protocol):
    def get_script(self, name: str) -> bytes: ...


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
    def __init__(self, scripts: Mapping[str, bytes | str]) -> None:
        self._scripts = {
            name: value.encode("utf-8") if isinstance(value, str) else bytes(value)
            for name, value in scripts.items()
        }

    def get_script(self, name: str) -> bytes:
        try:
            script = self._scripts[name]
        except KeyError as exc:
            raise MissingScriptError(name) from exc
        if len(script) > MAX_SCRIPT_BYTES:
            raise OcgcoreAssetError(f"Lua script {name!r} exceeds {MAX_SCRIPT_BYTES} bytes")
        return script


class FilesystemScriptProvider:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def get_script(self, name: str) -> bytes:
        relative = PurePosixPath(name.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise MissingScriptError(name)
        candidate = self.root.joinpath(*relative.parts).resolve()
        if self.root != candidate and self.root not in candidate.parents:
            raise MissingScriptError(name)
        try:
            size = candidate.stat().st_size
        except OSError as exc:
            raise MissingScriptError(name) from exc
        if size > MAX_SCRIPT_BYTES:
            raise OcgcoreAssetError(f"Lua script {name!r} exceeds {MAX_SCRIPT_BYTES} bytes")
        try:
            return candidate.read_bytes()
        except OSError as exc:
            raise MissingScriptError(name) from exc


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

    def get_script(self, name: str) -> bytes:
        if name == "c0.lua":
            return b""
        try:
            return super().get_script(name)
        except MissingScriptError as root_error:
            if "/" in name or "\\" in name:
                raise root_error
            for directory in self.CARD_DIRECTORIES:
                try:
                    return super().get_script(f"{directory}/{name}")
                except MissingScriptError:
                    continue
            raise root_error


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
