from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.evaluation.terminal import (
    TERMINAL_PREFERENCE_PROFILE_SCHEMA_VERSION,
    TerminalPreferenceProfile,
    TerminalPreferenceRule,
)
from ygo_effect_dsl.io_atomic import atomic_write_text, sha256_file


TERMINAL_PREFERENCE_CATALOG_SCHEMA_VERSION = "terminal-preference-catalog-v1"
TERMINAL_PREFERENCE_DEFAULT_PROFILE_NAME = "Default terminal preference"


def _profile_from_payload(value: Mapping[str, Any]) -> TerminalPreferenceProfile:
    profile = TerminalPreferenceProfile.from_mapping(
        {
            "name": value.get("name"),
            "rules": value.get("rules"),
            "schema_version": value.get("schema_version"),
        }
    )
    profile_id = value.get("profile_id")
    if profile_id is not None and profile_id != profile.profile_id:
        raise ValueError("terminal preference profile_id does not match content")
    return profile


@dataclass(frozen=True)
class TerminalPreferenceCatalogRecord:
    profile: TerminalPreferenceProfile
    path: str
    sha256: str
    catalog_schema_version: str = TERMINAL_PREFERENCE_CATALOG_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "catalog_schema_version": self.catalog_schema_version,
                "path": self.path,
                "profile": self.profile.to_dict(),
                "profile_id": self.profile.profile_id,
                "sha256": self.sha256,
            }
        )


class TerminalPreferenceProfileCatalog:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def default_profile(self) -> TerminalPreferenceProfile:
        return TerminalPreferenceProfile(
            name=TERMINAL_PREFERENCE_DEFAULT_PROFILE_NAME,
            rules=(),
            schema_version=TERMINAL_PREFERENCE_PROFILE_SCHEMA_VERSION,
        )

    def path_for(self, profile_id: str) -> Path:
        if not isinstance(profile_id, str) or not profile_id.startswith("termpref_"):
            raise ValueError("profile_id must be a terminal preference content ID")
        return self.root / f"{profile_id}.json"

    def put(
        self,
        profile: TerminalPreferenceProfile | Mapping[str, Any],
    ) -> TerminalPreferenceCatalogRecord:
        resolved = (
            profile
            if isinstance(profile, TerminalPreferenceProfile)
            else _profile_from_payload(profile)
        )
        path = self.path_for(resolved.profile_id)
        payload = resolved.to_dict()
        atomic_write_text(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")
        return TerminalPreferenceCatalogRecord(
            profile=resolved,
            path=path.name,
            sha256=sha256_file(path),
        )

    def ensure_default(self) -> TerminalPreferenceCatalogRecord:
        existing = self.get(self.default_profile.profile_id)
        return existing if existing is not None else self.put(self.default_profile)

    def get(self, profile_id: str) -> TerminalPreferenceCatalogRecord | None:
        path = self.path_for(profile_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("terminal preference profile file must contain an object")
        profile = _profile_from_payload(payload)
        if profile.profile_id != profile_id:
            raise ValueError("terminal preference profile path/content mismatch")
        return TerminalPreferenceCatalogRecord(
            profile=profile,
            path=path.name,
            sha256=sha256_file(path),
        )

    def require(self, profile_id: str) -> TerminalPreferenceCatalogRecord:
        record = self.get(profile_id)
        if record is None:
            raise KeyError(profile_id)
        return record

    def list(self) -> tuple[TerminalPreferenceCatalogRecord, ...]:
        records: list[TerminalPreferenceCatalogRecord] = []
        for path in sorted(self.root.glob("termpref_*.json")):
            records.append(self.require(path.stem))
        return tuple(sorted(records, key=lambda record: record.profile.name))

    def clone(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        rules: Sequence[Mapping[str, Any] | TerminalPreferenceRule] | None = None,
    ) -> TerminalPreferenceCatalogRecord:
        source = self.require(profile_id)
        return self.put(source.profile.clone_with(name=name, rules=rules))

    def catalog_digest(self) -> str:
        identity = [record.to_dict() for record in self.list()]
        return stable_digest(identity, prefix="termprefcatalog_")
