from __future__ import annotations

import hashlib
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.bridge.ocgcore import (
    CardScriptsProvider,
    MissingCardDataError,
    MissingScriptError,
    OcgcoreAssetError,
    SQLiteCardDataProvider,
    card_scripts_profile_for_experiment_schema,
)
from ygo_effect_dsl.engine.canonical import canonical_json
from ygo_effect_dsl.experiment.schema import (
    EXPERIMENT_SCHEMA_VERSION,
    SCENARIO_SCHEMA_VERSION,
    assert_valid_experiment,
)
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreAssets,
    OcgcoreBootstrapError,
    resolve_ocgcore_assets,
)


SCENARIO_MANIFEST_SCHEMA_VERSION = "scenario-manifest-v1"
SCENARIO_PREFLIGHT_SCHEMA_VERSION = "scenario-preflight-v1"
DECK_SECTIONS = ("main", "extra", "side")
FixedDeckRegistry = Mapping[str, Mapping[str, Sequence[int]]]


@dataclass(frozen=True)
class ScenarioDiagnostic:
    code: str
    path: str
    message: str
    card_code: int | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class ScenarioManifest:
    experiment_schema_version: str
    deck_id: str
    deck_source: str
    deck_sha256: str
    source_sha256: str | None
    sections: Mapping[str, tuple[int, ...]]
    opening_hand: tuple[int, ...]
    opening_hand_mode: str
    opening_hand_seed: int | None
    interruption_source_codes: tuple[int, ...]
    asset_lock_id: str
    asset_lock_sha256: str | None
    card_database_commit: str | None
    card_scripts_commit: str | None
    schema_version: str = SCENARIO_MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioPreflightResult:
    diagnostics: tuple[ScenarioDiagnostic, ...]
    manifest: ScenarioManifest | None
    schema_version: str = SCENARIO_PREFLIGHT_SCHEMA_VERSION

    @property
    def ok(self) -> bool:
        return self.manifest is not None and not any(
            diagnostic.severity == "error" for diagnostic in self.diagnostics
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "manifest": self.manifest.to_dict() if self.manifest is not None else None,
            "ok": self.ok,
            "schema_version": self.schema_version,
        }


class ScenarioInputError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        super().__init__(message)
        self.diagnostic = ScenarioDiagnostic(code=code, path=path, message=message)


def parse_ydk(path: str | Path) -> tuple[dict[str, tuple[int, ...]], str]:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise ScenarioInputError("ydk_unreadable", "$.deck.path", str(exc)) from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ScenarioInputError(
            "ydk_invalid_encoding", "$.deck.path", "YDK must be UTF-8 text"
        ) from exc
    sections: dict[str, list[int]] = {name: [] for name in DECK_SECTIONS}
    current: str | None = None
    markers = {"#main": "main", "#extra": "extra", "!side": "side"}
    observed: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#created by"):
            continue
        if line in markers:
            current = markers[line]
            observed.add(current)
            continue
        if line.startswith("#") or line.startswith("!"):
            raise ScenarioInputError(
                "ydk_unknown_section",
                f"$.deck.path:{line_number}",
                f"unknown YDK section marker {line!r}",
            )
        if current is None:
            raise ScenarioInputError(
                "ydk_card_before_section",
                f"$.deck.path:{line_number}",
                "card code appears before #main",
            )
        try:
            code = int(line)
        except ValueError as exc:
            raise ScenarioInputError(
                "ydk_invalid_card_code",
                f"$.deck.path:{line_number}",
                f"invalid card code {line!r}",
            ) from exc
        if code <= 0:
            raise ScenarioInputError(
                "ydk_invalid_card_code",
                f"$.deck.path:{line_number}",
                "card code must be positive",
            )
        sections[current].append(code)
    if observed != set(DECK_SECTIONS):
        missing = sorted(set(DECK_SECTIONS) - observed)
        raise ScenarioInputError(
            "ydk_missing_section",
            "$.deck.path",
            f"YDK is missing sections: {', '.join(missing)}",
        )
    return (
        {name: tuple(sections[name]) for name in DECK_SECTIONS},
        hashlib.sha256(raw).hexdigest(),
    )


def _card_tuple(value: Any, path: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ScenarioInputError("invalid_deck_section", path, "must be a card-code list")
    cards: list[int] = []
    for index, raw_code in enumerate(value):
        if not isinstance(raw_code, int) or isinstance(raw_code, bool) or raw_code <= 0:
            raise ScenarioInputError(
                "invalid_card_code", f"{path}[{index}]", "must be a positive integer"
            )
        cards.append(raw_code)
    return tuple(cards)


def normalize_deck(
    experiment: Mapping[str, Any],
    *,
    base_path: str | Path | None = None,
    fixed_decks: FixedDeckRegistry | None = None,
) -> tuple[dict[str, tuple[int, ...]], str | None]:
    deck = experiment["deck"]
    source = str(deck["source"])
    if source == "ydk":
        path = Path(str(deck["path"]))
        if not path.is_absolute():
            path = Path(base_path or Path.cwd()) / path
        return parse_ydk(path)
    if source == "inline":
        return (
            {
                name: _card_tuple(deck[name], f"$.deck.{name}")
                for name in DECK_SECTIONS
            },
            None,
        )
    registry = fixed_decks or {}
    fixed = registry.get(str(deck["id"]))
    if fixed is None:
        raise ScenarioInputError(
            "unknown_fixed_deck",
            "$.deck.id",
            f"fixed deck {deck['id']!r} is not registered",
        )
    return (
        {
            name: _card_tuple(fixed.get(name, ()), f"fixed_decks.{deck['id']}.{name}")
            for name in DECK_SECTIONS
        },
        None,
    )


def _structural_diagnostics(
    sections: Mapping[str, Sequence[int]],
) -> list[ScenarioDiagnostic]:
    diagnostics: list[ScenarioDiagnostic] = []
    sizes = {name: len(sections[name]) for name in DECK_SECTIONS}
    if not 40 <= sizes["main"] <= 60:
        diagnostics.append(
            ScenarioDiagnostic(
                "invalid_main_deck_size",
                "$.deck.main",
                f"main deck must contain 40..60 cards; observed {sizes['main']}",
            )
        )
    for name in ("extra", "side"):
        if sizes[name] > 15:
            diagnostics.append(
                ScenarioDiagnostic(
                    f"invalid_{name}_deck_size",
                    f"$.deck.{name}",
                    f"{name} deck must contain at most 15 cards; observed {sizes[name]}",
                )
            )
    counts = Counter(code for name in DECK_SECTIONS for code in sections[name])
    for code, count in sorted(counts.items()):
        if count > 3:
            diagnostics.append(
                ScenarioDiagnostic(
                    "duplicate_card_limit_exceeded",
                    "$.deck",
                    f"card code {code} occurs {count} times; structural limit is 3",
                    card_code=code,
                )
            )
    return diagnostics


def _opening_hand(
    sections: Mapping[str, tuple[int, ...]], opening: Mapping[str, Any]
) -> tuple[tuple[int, ...], int | None]:
    main = list(sections["main"])
    mode = str(opening["mode"])
    if mode == "fixed":
        hand = _card_tuple(opening["cards"], "$.scenario.opening_hand.cards")
        available = Counter(main)
        requested = Counter(hand)
        missing = {code: count - available[code] for code, count in requested.items() if count > available[code]}
        if missing:
            raise ScenarioInputError(
                "fixed_hand_not_in_deck",
                "$.scenario.opening_hand.cards",
                f"fixed hand exceeds deck copies: {missing}",
            )
        return hand, None
    seed = int(opening["seed"])
    size = int(opening.get("size", 5))
    if size > len(main):
        raise ScenarioInputError(
            "opening_hand_too_large",
            "$.scenario.opening_hand.size",
            "opening hand cannot exceed main deck size",
        )
    generator = random.Random(seed)
    if mode == "random":
        generator.shuffle(main)
        return tuple(main[:size]), seed
    conditions = opening["conditions"]
    max_attempts = int(opening.get("max_attempts", 10_000))
    if max_attempts < 1:
        raise ScenarioInputError(
            "invalid_max_attempts",
            "$.scenario.opening_hand.max_attempts",
            "must be an integer >= 1",
        )
    for _attempt in range(max_attempts):
        candidate = generator.sample(main, size)
        counts = Counter(candidate)
        if all(
            counts[int(condition["code"])] >= int(condition.get("min_count", 0))
            and counts[int(condition["code"])] <= int(condition.get("max_count", size))
            for condition in conditions
        ):
            return tuple(candidate), seed
    raise ScenarioInputError(
        "conditional_hand_unsatisfied",
        "$.scenario.opening_hand.conditions",
        f"no matching hand found in {max_attempts} deterministic attempts",
    )


def _asset_identity(assets: OcgcoreAssets) -> dict[str, str | None]:
    repositories = assets.manifest.get("repositories", {})
    return {
        "asset_lock_id": str(assets.manifest.get("asset_lock_id", "unknown")),
        "asset_lock_sha256": assets.manifest.get("asset_lock_sha256"),
        "card_database_commit": repositories.get("card_database", {}).get("commit"),
        "card_scripts_commit": repositories.get("card_scripts", {}).get("commit"),
    }


def preflight_scenario(
    experiment: Mapping[str, Any],
    *,
    experiment_path: str | Path | None = None,
    external_root: str | Path | None = None,
    assets: OcgcoreAssets | None = None,
    fixed_decks: FixedDeckRegistry | None = None,
) -> ScenarioPreflightResult:
    diagnostics: list[ScenarioDiagnostic] = []
    try:
        assert_valid_experiment(experiment)
    except ValueError as exc:
        return ScenarioPreflightResult(
            diagnostics=(ScenarioDiagnostic("invalid_experiment", "$", str(exc)),),
            manifest=None,
        )
    if experiment.get("schema_version") != EXPERIMENT_SCHEMA_VERSION:
        return ScenarioPreflightResult(
            diagnostics=(
                ScenarioDiagnostic(
                    "scenario_preflight_requires_v04",
                    "$.schema_version",
                    "scenario preflight requires Experiment 0.4",
                ),
            ),
            manifest=None,
        )
    try:
        base_path = Path(experiment_path).resolve().parent if experiment_path else None
        sections, source_sha256 = normalize_deck(
            experiment, base_path=base_path, fixed_decks=fixed_decks
        )
        diagnostics.extend(_structural_diagnostics(sections))
        hand, hand_seed = _opening_hand(
            sections, experiment["scenario"]["opening_hand"]
        )
    except ScenarioInputError as exc:
        diagnostics.append(exc.diagnostic)
        return ScenarioPreflightResult(tuple(diagnostics), None)
    try:
        resolved_assets = assets or resolve_ocgcore_assets(external_root=external_root)
    except (OcgcoreBootstrapError, OSError, ValueError) as exc:
        diagnostics.append(
            ScenarioDiagnostic("asset_lock_unavailable", "$.deck", str(exc))
        )
        return ScenarioPreflightResult(tuple(diagnostics), None)
    scripts = CardScriptsProvider(
        resolved_assets.scripts_root,
        profile_id=card_scripts_profile_for_experiment_schema(
            str(experiment["schema_version"])
        ),
    )
    try:
        with SQLiteCardDataProvider(resolved_assets.database_path) as database:
            interruption_codes = {
                int(definition["source_card_code"])
                for definition in experiment["interruption"]["definitions"]
                if experiment["interruption"]["mode"] == "specified"
            }
            card_codes = {
                code for cards in sections.values() for code in cards
            } | interruption_codes
            for code in sorted(card_codes):
                try:
                    database.get_database_row(code)
                except (MissingCardDataError, OcgcoreAssetError) as exc:
                    diagnostics.append(
                        ScenarioDiagnostic(
                            "missing_card_database_row",
                            "$.deck",
                            str(exc),
                            card_code=code,
                        )
                    )
                try:
                    scripts.get_script(f"c{code}.lua")
                except (MissingScriptError, OcgcoreAssetError) as exc:
                    diagnostics.append(
                        ScenarioDiagnostic(
                            "missing_card_script",
                            "$.deck",
                            str(exc),
                            card_code=code,
                        )
                    )
    except OcgcoreAssetError as exc:
        diagnostics.append(
            ScenarioDiagnostic("card_database_unavailable", "$.deck", str(exc))
        )
    if diagnostics:
        return ScenarioPreflightResult(tuple(diagnostics), None)
    deck_payload = {name: list(sections[name]) for name in DECK_SECTIONS}
    identity = _asset_identity(resolved_assets)
    manifest = ScenarioManifest(
        experiment_schema_version=str(experiment["schema_version"]),
        deck_id=str(experiment["deck"]["id"]),
        deck_source=str(experiment["deck"]["source"]),
        deck_sha256=hashlib.sha256(canonical_json(deck_payload).encode("utf-8")).hexdigest(),
        source_sha256=source_sha256,
        sections=sections,
        opening_hand=hand,
        opening_hand_mode=str(experiment["scenario"]["opening_hand"]["mode"]),
        opening_hand_seed=hand_seed,
        interruption_source_codes=tuple(sorted(interruption_codes)),
        **identity,
    )
    return ScenarioPreflightResult((), manifest)
