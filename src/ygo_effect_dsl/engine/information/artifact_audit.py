from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ygo_effect_dsl.engine.bridge.ocgcore.state import (
    LOCATION_DECK,
    LOCATION_EXTRA,
    LOCATION_HAND,
    LOCATION_MZONE,
    LOCATION_REMOVED,
    LOCATION_SZONE,
    CompleteSnapshot,
)
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data


INFORMATION_ACCESS_AUDIT_V2_SCHEMA_VERSION = "information-access-audit-v2"
INFORMATION_ACCESS_CANARY_REGISTRY_SCHEMA_VERSION = (
    "information-access-canary-registry-v1"
)
INFORMATION_ACCESS_AUDIT_ALLOWLIST_SCHEMA_VERSION = (
    "information-access-audit-allowlist-v1"
)

_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "candidate_id",
        "candidate_ids",
        "core_input_ref",
        "core_output",
        "core_response",
        "core_seed",
        "duel_seed",
        "instance_key",
        "persistent_instance_id",
        "process_id",
        "public_card_id",
        "raw_bytes",
        "raw_frames",
        "raw_hex",
        "replay_digest",
        "request_id",
        "request_signature",
        "route_id",
        "sample_id",
        "sampling_reference",
        "seed",
        "selected_candidate_ids",
        "selected_index",
        "source_replay_digest",
        "source_route_id",
        "state_hash",
        "state_hash_after",
        "state_hash_before",
        "stderr",
        "stderr_digest",
        "stdout",
        "stdout_digest",
        "worker_input_digest",
    }
)
_SIDE_CHANNEL_FIELD_NAMES = frozenset(
    {
        "attempt_count",
        "byte_length",
        "candidate_count",
        "deck_order",
        "elapsed_seconds",
        "filesystem_path",
        "path",
        "pid",
        "raw_byte_count",
        "selected_private_index",
        "slot_list",
        "timestamp",
        "wall_clock",
        "worker_attempt_count",
    }
)
_SENSITIVE_SOURCE_FIELD_FRAGMENTS = (
    "candidate_id",
    "core_input_ref",
    "persistent_instance_id",
    "request_signature",
    "seed",
    "state_hash",
)


def _is_forbidden_field_name(name: str) -> bool:
    return (
        name in _FORBIDDEN_FIELD_NAMES
        or name.startswith("raw_")
        or name.endswith("_request_signature")
        or name.endswith("_state_hash")
        or name.endswith("_worker_input_digest")
    )


def _is_side_channel_field_name(name: str) -> bool:
    return (
        name in _SIDE_CHANNEL_FIELD_NAMES
        or name == "hash"
        or name.endswith("_byte_length")
        or name.endswith("_length")
    )


class InformationArtifactLeakError(ValueError):
    def __init__(self, report: Mapping[str, Any]) -> None:
        self.report = dict(report)
        super().__init__(
            f"information artifact audit failed: audit_id={report.get('audit_id')}"
        )


@dataclass(frozen=True)
class InformationCanary:
    canary_id: str
    classification: str
    matcher_kind: str
    source_path: str
    value: Any

    def __post_init__(self) -> None:
        if self.matcher_kind not in {"exact", "sequence", "substring"}:
            raise ValueError("unsupported canary matcher_kind")
        if not self.canary_id.startswith("canary_"):
            raise ValueError("canary_id must start with 'canary_'")
        if not self.classification or not self.source_path:
            raise ValueError("canary classification and source_path are required")

    def to_private_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "canary_id": self.canary_id,
                "classification": self.classification,
                "matcher_kind": self.matcher_kind,
                "source_path": self.source_path,
                "value": self.value,
            }
        )

    @classmethod
    def from_private_dict(cls, data: Mapping[str, Any]) -> "InformationCanary":
        expected = {
            "canary_id",
            "classification",
            "matcher_kind",
            "source_path",
            "value",
        }
        if set(data) != expected:
            raise ValueError("canary entry has unexpected fields")
        return cls(
            canary_id=str(data["canary_id"]),
            classification=str(data["classification"]),
            matcher_kind=str(data["matcher_kind"]),
            source_path=str(data["source_path"]),
            value=data["value"],
        )


@dataclass(frozen=True)
class InformationCanaryRegistry:
    artifact_kind: str
    viewer: int
    canaries: tuple[InformationCanary, ...]
    schema_version: str = INFORMATION_ACCESS_CANARY_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INFORMATION_ACCESS_CANARY_REGISTRY_SCHEMA_VERSION:
            raise ValueError("unsupported canary registry schema")
        if self.viewer not in (0, 1):
            raise ValueError("canary registry viewer must be 0 or 1")
        if not self.artifact_kind:
            raise ValueError("canary registry artifact_kind is required")
        ids = [canary.canary_id for canary in self.canaries]
        if len(ids) != len(set(ids)):
            raise ValueError("canary registry IDs must be unique")

    @property
    def registry_id(self) -> str:
        return stable_digest(
            {
                "artifact_kind": self.artifact_kind,
                "canaries": [
                    {
                        "canary_id": canary.canary_id,
                        "classification": canary.classification,
                        "matcher_kind": canary.matcher_kind,
                        "source_path": canary.source_path,
                    }
                    for canary in self.canaries
                ],
                "schema_version": self.schema_version,
                "viewer": self.viewer,
            },
            prefix="canaryregistry_",
        )

    def to_private_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "canaries": [canary.to_private_dict() for canary in self.canaries],
            "registry_id": self.registry_id,
            "schema_version": self.schema_version,
            "viewer": self.viewer,
        }

    def for_artifact_kind(self, artifact_kind: str) -> "InformationCanaryRegistry":
        return InformationCanaryRegistry(
            artifact_kind=artifact_kind,
            viewer=self.viewer,
            canaries=self.canaries,
        )

    @classmethod
    def from_private_dict(cls, data: Mapping[str, Any]) -> "InformationCanaryRegistry":
        expected = {
            "artifact_kind",
            "canaries",
            "registry_id",
            "schema_version",
            "viewer",
        }
        if set(data) != expected or not isinstance(data.get("canaries"), list):
            raise ValueError("canary registry has unexpected fields")
        registry = cls(
            artifact_kind=str(data["artifact_kind"]),
            viewer=int(data["viewer"]),
            canaries=tuple(
                InformationCanary.from_private_dict(value)
                for value in data["canaries"]
                if isinstance(value, Mapping)
            ),
            schema_version=str(data["schema_version"]),
        )
        if len(registry.canaries) != len(data["canaries"]):
            raise ValueError("canary registry entries must be mappings")
        if data["registry_id"] != registry.registry_id:
            raise ValueError("canary registry ID mismatch")
        return registry


@dataclass(frozen=True)
class InformationAuditAllowlistEntry:
    artifact_kind: str
    json_path: str
    matcher_kind: str
    reason: str
    review_issue: int

    def __post_init__(self) -> None:
        if not self.artifact_kind or not self.json_path.startswith("$"):
            raise ValueError("allowlist requires exact artifact kind and JSON path")
        if self.matcher_kind not in {"canary", "field_name", "side_channel"}:
            raise ValueError("unsupported allowlist matcher_kind")
        if not self.reason or self.review_issue < 1:
            raise ValueError("allowlist requires reason and review_issue")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "json_path": self.json_path,
            "matcher_kind": self.matcher_kind,
            "reason": self.reason,
            "review_issue": self.review_issue,
        }


@dataclass(frozen=True)
class InformationAuditAllowlist:
    entries: tuple[InformationAuditAllowlistEntry, ...] = ()
    schema_version: str = INFORMATION_ACCESS_AUDIT_ALLOWLIST_SCHEMA_VERSION

    @property
    def allowlist_id(self) -> str:
        return stable_digest(
            {
                "entries": [entry.to_dict() for entry in self.entries],
                "schema_version": self.schema_version,
            },
            prefix="auditallowlist_",
        )

    def matches(self, *, artifact_kind: str, path: str, matcher_kind: str) -> bool:
        return any(
            entry.artifact_kind == artifact_kind
            and entry.json_path == path
            and entry.matcher_kind == matcher_kind
            for entry in self.entries
        )


DEFAULT_INFORMATION_AUDIT_ALLOWLIST = InformationAuditAllowlist()


def _field_value(card: Mapping[str, Any], name: str) -> Any:
    fields = card.get("fields")
    if not isinstance(fields, (list, tuple)):
        return None
    for field in fields:
        if isinstance(field, Mapping) and field.get("name") == name:
            return field.get("value")
    return None


def _snapshot_card_hidden(
    *,
    controller: int,
    location: int,
    viewer: int,
    card: Mapping[str, Any],
) -> bool:
    if location == LOCATION_DECK:
        return True
    if controller != viewer and location in {LOCATION_HAND, LOCATION_EXTRA}:
        return True
    position = _field_value(card, "position")
    face_down = isinstance(position, int) and bool(position & 0x0A)
    return controller != viewer and (
        _field_value(card, "is_hidden") == 1 or face_down
    )


def _walk_source_values(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            yield from _walk_source_values(value[key], f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _walk_source_values(item, f"{path}[{index}]")
        return
    yield path, value


def _walk_source_sequences(value: Any, path: str = "$") -> Iterable[tuple[str, list[Any]]]:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            child_path = f"{path}.{key}"
            child = value[key]
            if isinstance(child, (list, tuple)):
                yield child_path, list(child)
            yield from _walk_source_sequences(child, child_path)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _walk_source_sequences(item, f"{path}[{index}]")


def build_player_view_canary_registry(
    *,
    source_route: Mapping[str, Any],
    snapshots: Sequence[CompleteSnapshot],
    viewer: int,
) -> InformationCanaryRegistry:
    if viewer not in (0, 1):
        raise ValueError("viewer must be 0 or 1")
    raw_canaries: list[tuple[str, str, str, Any]] = []
    visible_codes: set[int] = set()
    hidden_codes: list[tuple[str, int]] = []
    deck_orders: list[tuple[str, list[int]]] = []
    for snapshot_index, snapshot in enumerate(snapshots):
        raw_canaries.append(
            (
                "complete_state_identity",
                "substring",
                f"snapshots[{snapshot_index}].state_hash",
                snapshot.state_hash,
            )
        )
        for zone_index, zone in enumerate(snapshot.zones):
            if not isinstance(zone, Mapping):
                raise ValueError("snapshot zone must be a mapping")
            controller = int(zone["controller"])
            location = int(zone["location"])
            cards = zone.get("cards")
            if not isinstance(cards, (list, tuple)):
                raise ValueError("snapshot zone cards must be a sequence")
            deck_order: list[int] = []
            for card_index, card in enumerate(cards):
                if card is None:
                    continue
                if not isinstance(card, Mapping):
                    raise ValueError("snapshot card must be a mapping")
                source_path = (
                    f"snapshots[{snapshot_index}].zones[{zone_index}]"
                    f".cards[{card_index}]"
                )
                code = _field_value(card, "code")
                hidden = _snapshot_card_hidden(
                    controller=controller,
                    location=location,
                    viewer=viewer,
                    card=card,
                )
                if isinstance(code, int) and code > 0:
                    if hidden:
                        hidden_codes.append((f"{source_path}.code", code))
                    else:
                        visible_codes.add(code)
                    if location == LOCATION_DECK:
                        deck_order.append(code)
                persistent_id = card.get("persistent_instance_id")
                if isinstance(persistent_id, str) and persistent_id:
                    raw_canaries.append(
                        (
                            "persistent_card_identity",
                            "substring",
                            f"{source_path}.persistent_instance_id",
                            persistent_id,
                        )
                    )
            if location == LOCATION_DECK and len(deck_order) > 1:
                deck_orders.append(
                    (
                        f"snapshots[{snapshot_index}].zones[{zone_index}].deck_order",
                        deck_order,
                    )
                )
    for source_path, code in hidden_codes:
        if code not in visible_codes:
            raw_canaries.append(
                ("hidden_card_code", "exact", source_path, code)
            )
    for source_path, order in deck_orders:
        raw_canaries.append(("hidden_deck_order", "sequence", source_path, order))
    for path, value in _walk_source_values(source_route):
        lower_path = path.lower()
        if not any(fragment in lower_path for fragment in _SENSITIVE_SOURCE_FIELD_FRAGMENTS):
            continue
        if isinstance(value, str) and value:
            raw_canaries.append(
                (
                    "complete_route_identity",
                    "substring",
                    path,
                    value,
                )
            )
    for path, sequence in _walk_source_sequences(source_route):
        lower_path = path.lower()
        if "seed" in lower_path and len(sequence) > 1:
            raw_canaries.append(
                ("private_randomness", "sequence", path, sequence)
            )
    route_id = source_route.get("route_id")
    if isinstance(route_id, str) and route_id:
        raw_canaries.append(
            ("complete_route_identity", "substring", "$.route_id", route_id)
        )
    raw_canaries.append(
        (
            "complete_replay_identity",
            "substring",
            "$.replay_digest",
            stable_digest(source_route.get("replay"), prefix="replay_"),
        )
    )
    unique: dict[tuple[str, str], tuple[str, str, str, Any]] = {}
    for item in raw_canaries:
        matcher_kind = item[1]
        value_key = canonical_json(item[3])
        unique.setdefault((matcher_kind, value_key), item)
    canaries = []
    for ordinal, item in enumerate(
        sorted(unique.values(), key=lambda value: (value[0], value[1], value[2], canonical_json(value[3])))
    ):
        classification, matcher_kind, source_path, value = item
        canary_id = stable_digest(
            {
                "classification": classification,
                "matcher_kind": matcher_kind,
                "ordinal": ordinal,
                "source_path": source_path,
            },
            prefix="canary_",
        )
        canaries.append(
            InformationCanary(
                canary_id=canary_id,
                classification=classification,
                matcher_kind=matcher_kind,
                source_path=source_path,
                value=value,
            )
        )
    return InformationCanaryRegistry(
        artifact_kind="player_view_replay",
        viewer=viewer,
        canaries=tuple(canaries),
    )


def _walk_artifact(value: Any, path: str = "$") -> Iterable[tuple[str, str | None, Any]]:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            child_path = f"{path}.{key}"
            yield child_path, str(key), value[key]
            yield from _walk_artifact(value[key], child_path)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]"
            yield child_path, None, item
            yield from _walk_artifact(item, child_path)


def _canary_matches(canary: InformationCanary, value: Any) -> bool:
    if canary.matcher_kind == "exact":
        return value == canary.value
    if canary.matcher_kind == "substring":
        return (
            isinstance(value, str)
            and isinstance(canary.value, str)
            and canary.value in value
        )
    if canary.matcher_kind == "sequence":
        if not isinstance(value, (list, tuple)) or not isinstance(
            canary.value, (list, tuple)
        ):
            return False
        candidate = list(value)
        expected = list(canary.value)
        if not expected or len(candidate) < len(expected):
            return False
        return any(
            candidate[index : index + len(expected)] == expected
            for index in range(len(candidate) - len(expected) + 1)
        )
    raise AssertionError("unreachable canary matcher")


def _canary_matches_field_name(canary: InformationCanary, field_name: str) -> bool:
    if canary.matcher_kind == "sequence":
        return False
    if isinstance(canary.value, str):
        return canary.value in field_name
    if isinstance(canary.value, int) and not isinstance(canary.value, bool):
        return str(canary.value) in field_name
    return False


def _redact_finding_path(
    path: str, canaries: Sequence[InformationCanary]
) -> str:
    redacted = path
    for canary in canaries:
        if canary.matcher_kind == "sequence":
            continue
        raw = str(canary.value)
        if raw and raw in redacted:
            redacted = redacted.replace(raw, "<private-canary>")
    return redacted


def audit_information_artifact(
    artifact: Mapping[str, Any],
    *,
    artifact_kind: str,
    registry: InformationCanaryRegistry,
    allowlist: InformationAuditAllowlist = DEFAULT_INFORMATION_AUDIT_ALLOWLIST,
) -> dict[str, Any]:
    if not isinstance(artifact, Mapping):
        raise TypeError("artifact must be a mapping")
    if artifact_kind != registry.artifact_kind:
        raise ValueError("artifact kind does not match canary registry")
    findings: list[dict[str, Any]] = []
    side_channels: list[dict[str, Any]] = []
    allowlist_applications: list[dict[str, Any]] = []
    scanned_leaf_count = 0
    seen: set[tuple[str, str, str | None]] = set()

    def record(
        *,
        path: str,
        matcher_kind: str,
        rule: str,
        canary_id: str | None = None,
        side_channel: bool = False,
    ) -> None:
        key = (path, matcher_kind, canary_id)
        if key in seen:
            return
        seen.add(key)
        if allowlist.matches(
            artifact_kind=artifact_kind,
            path=path,
            matcher_kind=matcher_kind,
        ):
            allowlist_applications.append(
                {
                    "canary_id": canary_id,
                    "json_path": _redact_finding_path(path, registry.canaries),
                    "matcher_kind": matcher_kind,
                    "rule": rule,
                }
            )
            return
        safe_path = _redact_finding_path(path, registry.canaries)
        finding = {
            "canary_id": canary_id,
            "finding_id": stable_digest(
                {
                    "canary_id": canary_id,
                    "json_path": safe_path,
                    "matcher_kind": matcher_kind,
                    "rule": rule,
                },
                prefix="auditfinding_",
            ),
            "json_path": safe_path,
            "matcher_kind": matcher_kind,
            "rule": rule,
        }
        (side_channels if side_channel else findings).append(finding)

    for path, field_name, value in _walk_artifact(artifact):
        if field_name is not None:
            normalized = field_name.lower()
            if _is_forbidden_field_name(normalized):
                record(
                    path=path,
                    matcher_kind="field_name",
                    rule="forbidden_field_name",
                )
            if _is_side_channel_field_name(normalized):
                record(
                    path=path,
                    matcher_kind="side_channel",
                    rule="forbidden_side_channel",
                    side_channel=True,
                )
            for canary in registry.canaries:
                if _canary_matches_field_name(canary, field_name):
                    record(
                        path=path,
                        matcher_kind="canary",
                        rule="private_canary_in_field_name",
                        canary_id=canary.canary_id,
                    )
        if isinstance(value, (Mapping, list, tuple)):
            if isinstance(value, (list, tuple)):
                for canary in registry.canaries:
                    if canary.matcher_kind == "sequence" and _canary_matches(
                        canary, value
                    ):
                        record(
                            path=path,
                            matcher_kind="canary",
                            rule="private_canary_match",
                            canary_id=canary.canary_id,
                        )
            continue
        scanned_leaf_count += 1
        for canary in registry.canaries:
            if canary.matcher_kind != "sequence" and _canary_matches(canary, value):
                record(
                    path=path,
                    matcher_kind="canary",
                    rule="private_canary_match",
                    canary_id=canary.canary_id,
                )
    findings.sort(key=lambda finding: (finding["json_path"], finding["finding_id"]))
    side_channels.sort(
        key=lambda finding: (finding["json_path"], finding["finding_id"])
    )
    allowlist_applications.sort(
        key=lambda finding: (finding["json_path"], finding["matcher_kind"])
    )
    report_identity = {
        "allowlist_applications": allowlist_applications,
        "allowlist_id": allowlist.allowlist_id,
        "artifact_digest": stable_digest(artifact, prefix="publicartifact_"),
        "artifact_kind": artifact_kind,
        "canary_registry_id": registry.registry_id,
        "findings": findings,
        "scanned_leaf_count": scanned_leaf_count,
        "schema_version": INFORMATION_ACCESS_AUDIT_V2_SCHEMA_VERSION,
        "side_channel_findings": side_channels,
        "status": "failed" if findings or side_channels else "passed",
    }
    return {
        "audit_id": stable_digest(report_identity, prefix="informationaudit_"),
        **report_identity,
    }


def assert_information_artifact_safe(report: Mapping[str, Any]) -> None:
    if (
        report.get("schema_version") != INFORMATION_ACCESS_AUDIT_V2_SCHEMA_VERSION
        or report.get("status") != "passed"
        or report.get("findings") != []
        or report.get("side_channel_findings") != []
    ):
        raise InformationArtifactLeakError(report)
