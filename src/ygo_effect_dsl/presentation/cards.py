from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.resources
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


CARD_PRESENTATION_CONTRACT_VERSION = "card-presentation-v1"
CARD_PRESENTATION_PROVIDER_VERSION = "sqlite-card-presentation-provider-v1"
PRESENTATION_DIAGNOSTIC_VERSION = "presentation-diagnostic-v1"
CARD_TEXT_REGION_VERSION = "card-text-region-v1"
CARD_METADATA_PRESENTATION_VERSION = "card-metadata-presentation-v1"
CARD_PRESENTATION_SOURCE_VERSION = "card-presentation-source-v1"
CARD_PRESENTATION_QUERY_VERSION = "card-presentation-query-v1"

MAX_PRESENTATION_TEXT_CHARS = 1_000_000

TYPE_MONSTER = 0x1
TYPE_XYZ = 0x800000
TYPE_PENDULUM = 0x1000000
TYPE_LINK = 0x4000000

TYPE_LABELS = {
    TYPE_MONSTER: "Monster",
    0x2: "Spell",
    0x4: "Trap",
    0x10: "Normal",
    0x20: "Effect",
    0x40: "Fusion",
    0x80: "Ritual",
    0x100: "Trap Monster",
    0x200: "Spirit",
    0x400: "Union",
    0x800: "Gemini",
    0x1000: "Tuner",
    0x2000: "Synchro",
    0x4000: "Token",
    0x10000: "Quick-Play",
    0x20000: "Continuous",
    0x40000: "Equip",
    0x80000: "Field",
    0x100000: "Counter",
    0x200000: "Flip",
    0x400000: "Toon",
    TYPE_XYZ: "Xyz",
    TYPE_PENDULUM: "Pendulum",
    0x2000000: "Special Summon",
    TYPE_LINK: "Link",
}

ATTRIBUTE_LABELS = {
    0x1: "Earth",
    0x2: "Water",
    0x4: "Fire",
    0x8: "Wind",
    0x10: "Light",
    0x20: "Dark",
    0x40: "Divine",
}

RACE_LABELS = {
    0x1: "Warrior",
    0x2: "Spellcaster",
    0x4: "Fairy",
    0x8: "Fiend",
    0x10: "Zombie",
    0x20: "Machine",
    0x40: "Aqua",
    0x80: "Pyro",
    0x100: "Rock",
    0x200: "Winged Beast",
    0x400: "Plant",
    0x800: "Insect",
    0x1000: "Thunder",
    0x2000: "Dragon",
    0x4000: "Beast",
    0x8000: "Beast-Warrior",
    0x10000: "Dinosaur",
    0x20000: "Fish",
    0x40000: "Sea Serpent",
    0x80000: "Reptile",
    0x100000: "Psychic",
    0x200000: "Divine-Beast",
    0x400000: "Creator-God",
    0x800000: "Wyrm",
    0x1000000: "Cyberse",
    0x2000000: "Illusion",
}

_AVAILABILITY = {
    "available",
    "missing_text",
    "missing_card",
    "redacted",
    "source_unavailable",
    "stale_source",
    "version_mismatch",
}
_LOCALE_STATUS = {"exact", "fallback", "unavailable", "redacted"}
_SEVERITIES = {"info", "warning", "error"}
_DATA_COLUMNS = {
    "id",
    "alias",
    "setcode",
    "type",
    "atk",
    "def",
    "level",
    "race",
    "attribute",
}
_TEXT_COLUMNS = {"id", "name", "desc", *(f"str{i}" for i in range(1, 17))}


class CardPresentationSourceError(ValueError):
    pass


def _non_empty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty trimmed string")
    return value


def _token(value: Any, name: str) -> str:
    parsed = _non_empty(value, name)
    if any(character.isspace() for character in parsed):
        raise ValueError(f"{name} must not contain whitespace")
    return parsed


def _sha256(value: Any, name: str) -> str:
    parsed = _token(value, name)
    if len(parsed) != 64 or any(
        character not in "0123456789abcdef" for character in parsed
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return parsed


def _git_object_id(value: Any, name: str) -> str:
    parsed = _token(value, name)
    if len(parsed) not in {40, 64} or any(
        character not in "0123456789abcdef" for character in parsed
    ):
        raise ValueError(f"{name} must be a lowercase 40- or 64-character Git OID")
    return parsed


def _positive_code(value: Any, name: str = "card_code") -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _labels(value: int, table: Mapping[int, str]) -> tuple[str, ...]:
    return tuple(label for bit, label in table.items() if value & bit)


def _split_setcodes(value: int) -> tuple[int, ...]:
    unsigned = value & ((1 << 64) - 1)
    return tuple(
        setcode
        for shift in range(0, 64, 16)
        if (setcode := (unsigned >> shift) & 0xFFFF)
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_text(value: Any, name: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise CardPresentationSourceError(f"{name} must be TEXT or NULL")
    if len(value) > MAX_PRESENTATION_TEXT_CHARS:
        raise CardPresentationSourceError(
            f"{name} exceeds {MAX_PRESENTATION_TEXT_CHARS} characters"
        )
    return value


@dataclass(frozen=True)
class PresentationDiagnostic:
    code: str
    severity: str
    message: str
    field: str | None = None
    schema_version: str = PRESENTATION_DIAGNOSTIC_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PRESENTATION_DIAGNOSTIC_VERSION:
            raise ValueError("unsupported presentation diagnostic version")
        _token(self.code, "diagnostic.code")
        if self.severity not in _SEVERITIES:
            raise ValueError("unsupported presentation diagnostic severity")
        _non_empty(self.message, "diagnostic.message")
        if self.field is not None:
            _non_empty(self.field, "diagnostic.field")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "schema_version": self.schema_version,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class CardTextRegion:
    key: str
    text: str
    schema_version: str = CARD_TEXT_REGION_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CARD_TEXT_REGION_VERSION:
            raise ValueError("unsupported card text region version")
        _token(self.key, "text_region.key")
        parsed = _optional_text(self.text, "text_region.text")
        if parsed is None:
            raise ValueError("text_region.text must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "schema_version": self.schema_version,
            "text": self.text,
        }


@dataclass(frozen=True)
class CardMetadataPresentation:
    alias: int
    setcodes: tuple[int, ...]
    type_bits: int
    type_labels: tuple[str, ...]
    attack: int | None
    defense: int | None
    level: int | None
    rank: int | None
    link_rating: int | None
    link_markers: int | None
    left_scale: int | None
    right_scale: int | None
    race_bits: int
    race_labels: tuple[str, ...]
    attribute_bits: int
    attribute_labels: tuple[str, ...]
    schema_version: str = CARD_METADATA_PRESENTATION_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CARD_METADATA_PRESENTATION_VERSION:
            raise ValueError("unsupported card metadata presentation version")
        for name in (
            "alias",
            "type_bits",
            "race_bits",
            "attribute_bits",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"metadata.{name} must be an integer")
        for name in (
            "attack",
            "defense",
            "level",
            "rank",
            "link_rating",
            "link_markers",
            "left_scale",
            "right_scale",
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool)
            ):
                raise ValueError(f"metadata.{name} must be an integer or null")
        for name in ("setcodes", "type_labels", "race_labels", "attribute_labels"):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    @classmethod
    def from_database_values(
        cls,
        *,
        alias: int,
        setcode: int,
        type_bits: int,
        attack: int,
        defense_or_link_markers: int,
        packed_level: int,
        race_bits: int,
        attribute_bits: int,
    ) -> "CardMetadataPresentation":
        value = int(packed_level)
        displayed_level = value & 0xFF
        is_monster = bool(type_bits & TYPE_MONSTER)
        is_xyz = bool(type_bits & TYPE_XYZ)
        is_pendulum = bool(type_bits & TYPE_PENDULUM)
        is_link = bool(type_bits & TYPE_LINK)
        return cls(
            alias=int(alias),
            setcodes=_split_setcodes(int(setcode)),
            type_bits=int(type_bits),
            type_labels=_labels(int(type_bits), TYPE_LABELS),
            attack=int(attack) if is_monster else None,
            defense=(
                int(defense_or_link_markers)
                if is_monster and not is_link
                else None
            ),
            level=(
                displayed_level if is_monster and not is_xyz and not is_link else None
            ),
            rank=displayed_level if is_xyz else None,
            link_rating=displayed_level if is_link else None,
            link_markers=int(defense_or_link_markers) if is_link else None,
            left_scale=((value >> 24) & 0xFF) if is_pendulum else None,
            right_scale=((value >> 16) & 0xFF) if is_pendulum else None,
            race_bits=int(race_bits),
            race_labels=_labels(int(race_bits), RACE_LABELS),
            attribute_bits=int(attribute_bits),
            attribute_labels=_labels(int(attribute_bits), ATTRIBUTE_LABELS),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "attack": self.attack,
            "attribute_bits": self.attribute_bits,
            "attribute_labels": list(self.attribute_labels),
            "defense": self.defense,
            "left_scale": self.left_scale,
            "level": self.level,
            "link_markers": self.link_markers,
            "link_rating": self.link_rating,
            "race_bits": self.race_bits,
            "race_labels": list(self.race_labels),
            "rank": self.rank,
            "right_scale": self.right_scale,
            "schema_version": self.schema_version,
            "setcodes": list(self.setcodes),
            "type_bits": self.type_bits,
            "type_labels": list(self.type_labels),
        }


@dataclass(frozen=True)
class CardPresentationSource:
    locale: str
    database_path: Path
    database_sha256: str
    asset_lock_id: str
    source_commit: str
    source_tree: str
    license_status: str
    repository: str
    schema_version: str = CARD_PRESENTATION_SOURCE_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CARD_PRESENTATION_SOURCE_VERSION:
            raise ValueError("unsupported card presentation source version")
        _token(self.locale, "source.locale")
        object.__setattr__(
            self,
            "database_path",
            Path(self.database_path).expanduser().resolve(),
        )
        _sha256(self.database_sha256, "source.database_sha256")
        _token(self.asset_lock_id, "source.asset_lock_id")
        _git_object_id(self.source_commit, "source.source_commit")
        _git_object_id(self.source_tree, "source.source_tree")
        _token(self.license_status, "source.license_status")
        repository = _non_empty(self.repository, "source.repository")
        if not repository.startswith("https://"):
            raise ValueError("source.repository must use https")

    @property
    def source_id(self) -> str:
        return stable_digest(self.identity(), prefix="cardpresentationsource_")

    def identity(self) -> dict[str, Any]:
        return {
            "asset_lock_id": self.asset_lock_id,
            "database_filename": self.database_path.name,
            "database_sha256": self.database_sha256,
            "license_status": self.license_status,
            "locale": self.locale,
            "repository": self.repository,
            "schema_version": self.schema_version,
            "source_commit": self.source_commit,
            "source_tree": self.source_tree,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity(), "source_id": self.source_id}


@dataclass(frozen=True)
class CardPresentationQuery:
    card_code: int | None
    requested_locale: str
    fallback_locales: tuple[str, ...] = ("en",)
    redacted: bool = False
    expected_asset_lock_id: str | None = None
    expected_provider_version: str = CARD_PRESENTATION_PROVIDER_VERSION
    schema_version: str = CARD_PRESENTATION_QUERY_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CARD_PRESENTATION_QUERY_VERSION:
            raise ValueError("unsupported card presentation query version")
        _token(self.requested_locale, "query.requested_locale")
        fallbacks = tuple(self.fallback_locales)
        if len(set(fallbacks)) != len(fallbacks):
            raise ValueError("query.fallback_locales must be unique")
        if self.requested_locale in fallbacks:
            raise ValueError("requested locale must not be repeated as a fallback")
        for locale in fallbacks:
            _token(locale, "query.fallback_locale")
        object.__setattr__(self, "fallback_locales", fallbacks)
        if self.redacted:
            if self.card_code is not None:
                raise ValueError("redacted presentation query must omit card_code")
        else:
            _positive_code(self.card_code)
        if self.expected_asset_lock_id is not None:
            _token(self.expected_asset_lock_id, "query.expected_asset_lock_id")
        _token(self.expected_provider_version, "query.expected_provider_version")


@dataclass(frozen=True)
class CardPresentation:
    card_code: int | None
    availability: str
    requested_locale: str
    resolved_locale: str | None
    locale_status: str
    name: str | None
    effect_text: str | None
    auxiliary_texts: tuple[CardTextRegion, ...]
    metadata: CardMetadataPresentation | None
    source: CardPresentationSource | None
    diagnostics: tuple[PresentationDiagnostic, ...]
    schema_version: str = CARD_PRESENTATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CARD_PRESENTATION_CONTRACT_VERSION:
            raise ValueError("unsupported card presentation contract version")
        if self.availability not in _AVAILABILITY:
            raise ValueError("unsupported card presentation availability")
        if self.locale_status not in _LOCALE_STATUS:
            raise ValueError("unsupported card presentation locale_status")
        _token(self.requested_locale, "presentation.requested_locale")
        if self.card_code is not None:
            _positive_code(self.card_code)
        if self.resolved_locale is not None:
            _token(self.resolved_locale, "presentation.resolved_locale")
        for name in ("name", "effect_text"):
            value = getattr(self, name)
            if value is not None:
                _optional_text(value, f"presentation.{name}")
        object.__setattr__(self, "auxiliary_texts", tuple(self.auxiliary_texts))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if any(
            not isinstance(item, CardTextRegion) for item in self.auxiliary_texts
        ):
            raise ValueError("auxiliary_texts must contain CardTextRegion values")
        if any(
            not isinstance(item, PresentationDiagnostic) for item in self.diagnostics
        ):
            raise ValueError("diagnostics must contain PresentationDiagnostic values")
        if self.availability == "available":
            if (
                self.card_code is None
                or self.metadata is None
                or self.source is None
                or self.resolved_locale is None
                or self.name is None
            ):
                raise ValueError("available presentation requires complete identity")
            if self.locale_status not in {"exact", "fallback"}:
                raise ValueError("available presentation requires a resolved locale")
        if self.source is not None and self.resolved_locale != self.source.locale:
            raise ValueError("resolved locale must match the presentation source")
        payload = (
            self.name,
            self.effect_text,
            self.metadata,
            self.source,
        )
        if self.availability == "redacted":
            if (
                self.card_code is not None
                or self.resolved_locale is not None
                or self.auxiliary_texts
                or any(value is not None for value in payload)
                or self.locale_status != "redacted"
            ):
                raise ValueError("redacted presentation must not expose card data")
        elif self.availability == "missing_text":
            if (
                self.card_code is None
                or self.resolved_locale is None
                or self.metadata is None
                or self.source is None
                or self.name is not None
                or self.effect_text is not None
                or self.auxiliary_texts
                or self.locale_status not in {"exact", "fallback"}
            ):
                raise ValueError("missing_text presentation has invalid payload")
        elif self.availability == "missing_card":
            if (
                self.card_code is None
                or self.resolved_locale is None
                or self.source is None
                or self.name is not None
                or self.effect_text is not None
                or self.metadata is not None
                or self.auxiliary_texts
                or self.locale_status not in {"exact", "fallback"}
            ):
                raise ValueError("missing_card presentation has invalid payload")
        elif self.availability in {
            "source_unavailable",
            "stale_source",
            "version_mismatch",
        }:
            if (
                self.card_code is None
                or self.resolved_locale is not None
                or self.auxiliary_texts
                or any(value is not None for value in payload)
                or self.locale_status != "unavailable"
            ):
                raise ValueError("unavailable presentation must not expose source data")

    @property
    def presentation_id(self) -> str:
        return stable_digest(self.identity(), prefix="cardpresentation_")

    def identity(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "auxiliary_texts": [item.to_dict() for item in self.auxiliary_texts],
                "availability": self.availability,
                "card_code": self.card_code,
                "diagnostics": [item.to_dict() for item in self.diagnostics],
                "effect_text": self.effect_text,
                "locale_status": self.locale_status,
                "metadata": self.metadata.to_dict() if self.metadata else None,
                "name": self.name,
                "requested_locale": self.requested_locale,
                "resolved_locale": self.resolved_locale,
                "schema_version": self.schema_version,
                "source": self.source.to_dict() if self.source else None,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity(), "presentation_id": self.presentation_id}


@dataclass(frozen=True)
class _DatabaseCardRow:
    code: int
    metadata: CardMetadataPresentation
    name: str | None
    effect_text: str | None
    auxiliary_texts: tuple[CardTextRegion, ...]

    @property
    def has_text(self) -> bool:
        return self.name is not None


class LocalizedCardPresentationProvider:
    """Read display-only metadata and text from verified local CDB files."""

    def __init__(self, sources: Iterable[CardPresentationSource]) -> None:
        received = tuple(sources)
        if not received:
            raise CardPresentationSourceError(
                "at least one presentation source is required"
            )
        if any(not isinstance(item, CardPresentationSource) for item in received):
            raise CardPresentationSourceError(
                "presentation sources must be CardPresentationSource values"
            )
        if len({item.locale for item in received}) != len(received):
            raise CardPresentationSourceError(
                "presentation source locales must be unique"
            )
        self._sources = {item.locale: item for item in received}
        self._connections: dict[str, sqlite3.Connection] = {}
        try:
            for source in received:
                self._connections[source.locale] = self._open_source(source)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _open_source(source: CardPresentationSource) -> sqlite3.Connection:
        path = source.database_path
        if not path.is_file():
            raise CardPresentationSourceError(
                f"presentation database does not exist: {path}"
            )
        observed_hash = _file_sha256(path)
        if observed_hash != source.database_sha256:
            raise CardPresentationSourceError(
                "presentation database SHA-256 does not match source manifest"
            )
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{path.as_uri()}?mode=ro&immutable=1",
                uri=True,
            )
            connection.execute("PRAGMA query_only = ON")
            LocalizedCardPresentationProvider._validate_schema(connection)
        except sqlite3.Error as exc:
            if connection is not None:
                connection.close()
            raise CardPresentationSourceError(
                f"could not open presentation database: {exc}"
            ) from exc
        except CardPresentationSourceError:
            if connection is not None:
                connection.close()
            raise
        return connection

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        observed: dict[str, set[str]] = {}
        for table in ("datas", "texts"):
            rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
            observed[table] = {str(row[1]) for row in rows}
        missing_data = sorted(_DATA_COLUMNS - observed["datas"])
        missing_text = sorted(_TEXT_COLUMNS - observed["texts"])
        if missing_data or missing_text:
            raise CardPresentationSourceError(
                "presentation CDB schema is missing required columns: "
                f"datas={missing_data}, texts={missing_text}"
            )

    def _read(self, locale: str, code: int) -> _DatabaseCardRow | None:
        columns = ", ".join(f"t.str{i}" for i in range(1, 17))
        try:
            row = self._connections[locale].execute(
                "SELECT d.id, d.alias, d.setcode, d.type, d.atk, d.def, d.level, "
                "d.race, d.attribute, t.name, t.desc, "
                f"{columns} FROM datas AS d LEFT JOIN texts AS t ON t.id = d.id "
                "WHERE d.id = ?",
                (code,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise CardPresentationSourceError(
                f"could not read card presentation for {code}: {exc}"
            ) from exc
        if row is None:
            return None
        metadata = CardMetadataPresentation.from_database_values(
            alias=int(row[1]),
            setcode=int(row[2]),
            type_bits=int(row[3]),
            attack=int(row[4]),
            defense_or_link_markers=int(row[5]),
            packed_level=int(row[6]),
            race_bits=int(row[7]),
            attribute_bits=int(row[8]),
        )
        name = _optional_text(row[9], f"texts[{code}].name")
        effect_text = _optional_text(row[10], f"texts[{code}].desc")
        auxiliary = tuple(
            CardTextRegion(key=f"string_{index}", text=value)
            for index, raw_value in enumerate(row[11:], start=1)
            if (value := _optional_text(raw_value, f"texts[{code}].str{index}"))
            is not None
        )
        return _DatabaseCardRow(
            code=int(row[0]),
            metadata=metadata,
            name=name,
            effect_text=effect_text,
            auxiliary_texts=auxiliary,
        )

    def get_card(self, query: CardPresentationQuery) -> CardPresentation:
        if not isinstance(query, CardPresentationQuery):
            raise ValueError("query must be CardPresentationQuery")
        if query.redacted:
            return CardPresentation(
                card_code=None,
                availability="redacted",
                requested_locale=query.requested_locale,
                resolved_locale=None,
                locale_status="redacted",
                name=None,
                effect_text=None,
                auxiliary_texts=(),
                metadata=None,
                source=None,
                diagnostics=(
                    PresentationDiagnostic(
                        code="player_view_redacted",
                        severity="info",
                        message="Card presentation is hidden by PlayerView policy.",
                    ),
                ),
            )
        code = _positive_code(query.card_code)
        if query.expected_provider_version != CARD_PRESENTATION_PROVIDER_VERSION:
            return self._unavailable(
                query,
                code,
                availability="version_mismatch",
                diagnostic=PresentationDiagnostic(
                    code="provider_version_mismatch",
                    severity="error",
                    message="Requested presentation provider version is unavailable.",
                    field="expected_provider_version",
                ),
            )
        candidates = tuple(
            source
            for source in self._sources.values()
            if query.expected_asset_lock_id is None
            or source.asset_lock_id == query.expected_asset_lock_id
        )
        if not candidates:
            return self._unavailable(
                query,
                code,
                availability="stale_source",
                diagnostic=PresentationDiagnostic(
                    code="asset_lock_mismatch",
                    severity="error",
                    message=(
                        "No card presentation source matches the expected asset lock."
                    ),
                    field="expected_asset_lock_id",
                ),
            )
        by_locale = {item.locale: item for item in candidates}
        locale_order = (query.requested_locale, *query.fallback_locales)
        configured_order = tuple(
            locale for locale in locale_order if locale in by_locale
        )
        if not configured_order:
            return self._unavailable(
                query,
                code,
                availability="source_unavailable",
                diagnostic=PresentationDiagnostic(
                    code="locale_source_unavailable",
                    severity="error",
                    message=(
                        "No configured source can satisfy the requested locale policy."
                    ),
                    field="requested_locale",
                ),
            )
        metadata_fallback: tuple[
            str, CardPresentationSource, _DatabaseCardRow
        ] | None = None
        for locale in configured_order:
            row = self._read(locale, code)
            if row is None:
                continue
            source = by_locale[locale]
            if metadata_fallback is None:
                metadata_fallback = (locale, source, row)
            if row.has_text:
                diagnostics: tuple[PresentationDiagnostic, ...] = ()
                locale_status = "exact"
                if locale != query.requested_locale:
                    locale_status = "fallback"
                    diagnostics = (
                        PresentationDiagnostic(
                            code="locale_fallback",
                            severity="warning",
                            message=(
                                "Requested locale was unavailable; an explicit "
                                "fallback source was used."
                            ),
                            field="requested_locale",
                        ),
                    )
                return CardPresentation(
                    card_code=code,
                    availability="available",
                    requested_locale=query.requested_locale,
                    resolved_locale=locale,
                    locale_status=locale_status,
                    name=row.name,
                    effect_text=row.effect_text,
                    auxiliary_texts=row.auxiliary_texts,
                    metadata=row.metadata,
                    source=source,
                    diagnostics=diagnostics,
                )
        if metadata_fallback is not None:
            locale, source, row = metadata_fallback
            return CardPresentation(
                card_code=code,
                availability="missing_text",
                requested_locale=query.requested_locale,
                resolved_locale=locale,
                locale_status=(
                    "exact" if locale == query.requested_locale else "fallback"
                ),
                name=None,
                effect_text=None,
                auxiliary_texts=(),
                metadata=row.metadata,
                source=source,
                diagnostics=(
                    PresentationDiagnostic(
                        code="card_text_missing",
                        severity="warning",
                        message=(
                            "Card metadata exists but presentation text is missing."
                        ),
                    ),
                ),
            )
        source = by_locale[configured_order[0]]
        return CardPresentation(
            card_code=code,
            availability="missing_card",
            requested_locale=query.requested_locale,
            resolved_locale=source.locale,
            locale_status=(
                "exact" if source.locale == query.requested_locale else "fallback"
            ),
            name=None,
            effect_text=None,
            auxiliary_texts=(),
            metadata=None,
            source=source,
            diagnostics=(
                PresentationDiagnostic(
                    code="card_data_missing",
                    severity="error",
                    message=(
                        "The verified presentation source has no row for this code."
                    ),
                ),
            ),
        )

    @staticmethod
    def _unavailable(
        query: CardPresentationQuery,
        code: int,
        *,
        availability: str,
        diagnostic: PresentationDiagnostic,
    ) -> CardPresentation:
        return CardPresentation(
            card_code=code,
            availability=availability,
            requested_locale=query.requested_locale,
            resolved_locale=None,
            locale_status="unavailable",
            name=None,
            effect_text=None,
            auxiliary_texts=(),
            metadata=None,
            source=None,
            diagnostics=(diagnostic,),
        )

    def close(self) -> None:
        for connection in self._connections.values():
            connection.close()
        self._connections.clear()

    def __enter__(self) -> "LocalizedCardPresentationProvider":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def card_presentation_contract_document() -> dict[str, Any]:
    resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
        "card-presentation-contract-v1.json"
    )
    document = json.loads(resource.read_text(encoding="utf-8"))
    if document.get("schema_version") != CARD_PRESENTATION_CONTRACT_VERSION:
        raise ValueError("card presentation contract resource version mismatch")
    return document
