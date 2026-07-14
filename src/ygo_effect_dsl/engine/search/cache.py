from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.engine.replay import ReplayManifestV03a


PREFIX_CACHE_POLICY_SCHEMA_VERSION = "prefix-cache-policy-v1"
PREFIX_CACHE_KEY_SCHEMA_VERSION = "replay-prefix-cache-key-v1"
PREFIX_CACHE_ENTRY_SCHEMA_VERSION = "replay-prefix-cache-entry-v1"
PREFIX_CACHE_INDEX_SCHEMA_VERSION = "replay-prefix-cache-index-v1"
PREFIX_CACHE_VERIFICATION_SCHEMA_VERSION = "prefix-cache-verification-v1"
PREFIX_CACHE_RUN_METADATA_SCHEMA_VERSION = "prefix-cache-run-metadata-v1"
NATIVE_PREFIX_STATE_REUSE_ALLOWED = False
REJECTED_NATIVE_REUSE_MODES = frozenset({"native_clone", "native_snapshot"})


class CachePersistenceMode(str, Enum):
    DISABLED = "disabled"
    INDEX_ONLY = "index_only"


class PrefixReuseMode(str, Enum):
    VERIFIED_REPLAY_HINT = "verified_replay_hint"


class CacheVerificationStatus(str, Enum):
    VALID = "valid"
    INVALIDATED = "invalidated"


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _positive_integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{path} must be an integer >= 1")
    return value


def _non_negative_integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{path} must be an integer >= 0")
    return value


def build_prefix_cache_run_metadata(
    policy: "PrefixCachePolicy",
    *,
    pool_size: int,
    per_worker_budget_bytes: int,
    main_process_budget_bytes: int = 0,
) -> dict[str, Any]:
    if not isinstance(policy, PrefixCachePolicy):
        raise ValueError("policy must be PrefixCachePolicy")
    pool_size = _positive_integer(pool_size, "pool_size")
    per_worker_budget_bytes = _positive_integer(
        per_worker_budget_bytes, "per_worker_budget_bytes"
    )
    main_process_budget_bytes = _non_negative_integer(
        main_process_budget_bytes, "main_process_budget_bytes"
    )
    identity = to_canonical_data(
        {
            "memory_budget": {
                "cache_bytes": policy.max_bytes,
                "main_process_bytes": main_process_budget_bytes,
                "per_worker_bytes": per_worker_budget_bytes,
                "total_bytes": (
                    main_process_budget_bytes
                    + policy.max_bytes
                    + pool_size * per_worker_budget_bytes
                ),
                "worker_pool_bytes": pool_size * per_worker_budget_bytes,
            },
            "policy": policy.to_dict(),
            "pool_size": pool_size,
            "schema_version": PREFIX_CACHE_RUN_METADATA_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "metadata_id": stable_digest(identity, prefix="prefixrun_"),
    }


@dataclass(frozen=True)
class PrefixCachePolicy:
    max_entries: int = 4096
    max_bytes: int = 16 * 1024 * 1024
    max_entry_bytes: int = 64 * 1024
    persistence_mode: CachePersistenceMode = CachePersistenceMode.INDEX_ONLY
    flush_every_mutations: int = 1000
    schema_version: str = PREFIX_CACHE_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "max_entries",
            "max_bytes",
            "max_entry_bytes",
            "flush_every_mutations",
        ):
            _positive_integer(getattr(self, name), name)
        if self.max_entry_bytes > self.max_bytes:
            raise ValueError("max_entry_bytes must not exceed max_bytes")
        if not isinstance(self.persistence_mode, CachePersistenceMode):
            object.__setattr__(
                self,
                "persistence_mode",
                CachePersistenceMode(self.persistence_mode),
            )
        if self.schema_version != PREFIX_CACHE_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported prefix cache policy schema")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PrefixCachePolicy":
        if not isinstance(value, Mapping):
            raise ValueError("prefix cache policy must be a mapping")
        known = {
            "flush_every_mutations",
            "max_bytes",
            "max_entries",
            "max_entry_bytes",
            "persistence_mode",
        }
        unknown = sorted(set(value) - known)
        if unknown:
            raise ValueError(f"unknown prefix cache policy fields: {unknown}")
        return cls(**dict(value))

    @classmethod
    def from_experiment(cls, experiment: Mapping[str, Any]) -> "PrefixCachePolicy":
        search = experiment.get("search")
        if not isinstance(search, Mapping):
            raise ValueError("experiment.search must be a mapping")
        parameters = search.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise ValueError("search.parameters must be a mapping")
        performance = parameters.get("performance", {})
        if not isinstance(performance, Mapping):
            raise ValueError("search.parameters.performance must be a mapping")
        prefix_cache = performance.get("prefix_cache", {})
        if not isinstance(prefix_cache, Mapping):
            raise ValueError("search.parameters.performance.prefix_cache must be a mapping")
        return cls.from_mapping(prefix_cache)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PrefixCachePolicy":
        raw = dict(value)
        supplied_id = raw.pop("policy_id", None)
        schema_version = raw.pop("schema_version", None)
        if schema_version != PREFIX_CACHE_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported prefix cache policy schema")
        policy = cls.from_mapping(raw)
        if supplied_id != policy.to_dict()["policy_id"]:
            raise ValueError("prefix cache policy_id does not match content")
        return policy

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "flush_every_mutations": self.flush_every_mutations,
                "max_bytes": self.max_bytes,
                "max_entries": self.max_entries,
                "max_entry_bytes": self.max_entry_bytes,
                "persistence_mode": self.persistence_mode.value,
                "schema_version": self.schema_version,
            }
        )
        return {**identity, "policy_id": stable_digest(identity, prefix="prefixpol_")}


@dataclass(frozen=True)
class ReplayPrefixCacheKey:
    manifest_hash: str
    initial_snapshot_hash: str
    replay_schema_version: str
    prefix_length: int
    prefix_digest: str
    schema_version: str = PREFIX_CACHE_KEY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "manifest_hash",
            "initial_snapshot_hash",
            "replay_schema_version",
            "prefix_digest",
        ):
            _string(getattr(self, name), name)
        if (
            not isinstance(self.prefix_length, int)
            or isinstance(self.prefix_length, bool)
            or self.prefix_length < 0
        ):
            raise ValueError("prefix_length must be a non-negative integer")
        if self.schema_version != PREFIX_CACHE_KEY_SCHEMA_VERSION:
            raise ValueError("unsupported prefix cache key schema")

    @classmethod
    def from_replay(
        cls,
        replay: Mapping[str, Any],
        prefix_length: int,
    ) -> "ReplayPrefixCacheKey":
        if not isinstance(replay, Mapping):
            raise ValueError("replay must be a mapping")
        manifest = ReplayManifestV03a.from_dict(
            replay.get("manifest") if isinstance(replay.get("manifest"), Mapping) else {}
        )
        manifest.assert_reproducible()
        events = replay.get("events")
        if not isinstance(events, list):
            raise ValueError("replay.events must be a list")
        if (
            not isinstance(prefix_length, int)
            or isinstance(prefix_length, bool)
            or not 0 <= prefix_length <= len(events)
        ):
            raise ValueError("prefix_length must be between 0 and replay event count")
        initial_snapshot = replay.get("initial_snapshot")
        if not isinstance(initial_snapshot, Mapping):
            raise ValueError("replay.initial_snapshot must be a mapping")
        initial_snapshot_hash = _string(
            initial_snapshot.get("state_hash"), "replay.initial_snapshot.state_hash"
        )
        if manifest.initial_conditions.get("snapshot_hash") != initial_snapshot_hash:
            raise ValueError("Replay manifest snapshot hash does not match initial snapshot")
        prefix: list[dict[str, Any]] = []
        for index, raw_event in enumerate(events[:prefix_length]):
            if not isinstance(raw_event, Mapping):
                raise ValueError(f"replay.events[{index}] must be a mapping")
            if raw_event.get("failure") is not None:
                raise ValueError("failed Replay prefixes must not be cached")
            action = raw_event.get("action")
            if not isinstance(action, Mapping):
                raise ValueError(f"replay.events[{index}].action must be a mapping")
            prefix.append(
                to_canonical_data(
                    {
                        "action_id": _string(
                            action.get("action_id"),
                            f"replay.events[{index}].action.action_id",
                        ),
                        "core_response": raw_event.get("core_response", {}),
                        "request_signature": _string(
                            raw_event.get("request_signature"),
                            f"replay.events[{index}].request_signature",
                        ),
                        "step": index,
                    }
                )
            )
        replay_schema_version = _string(
            replay.get("schema_version"), "replay.schema_version"
        )
        return cls(
            manifest_hash=manifest.manifest_hash,
            initial_snapshot_hash=initial_snapshot_hash,
            replay_schema_version=replay_schema_version,
            prefix_length=prefix_length,
            prefix_digest=stable_digest(
                {
                    "events": prefix,
                    "manifest_hash": manifest.manifest_hash,
                    "replay_schema_version": replay_schema_version,
                },
                prefix="prefix_",
            ),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReplayPrefixCacheKey":
        if not isinstance(value, Mapping):
            raise ValueError("prefix cache key must be a mapping")
        key = cls(
            manifest_hash=value.get("manifest_hash"),
            initial_snapshot_hash=value.get("initial_snapshot_hash"),
            replay_schema_version=value.get("replay_schema_version"),
            prefix_length=value.get("prefix_length"),
            prefix_digest=value.get("prefix_digest"),
            schema_version=value.get("schema_version"),
        )
        if key.to_dict() != to_canonical_data(value):
            raise ValueError("prefix cache key_id does not match content")
        return key

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "initial_snapshot_hash": self.initial_snapshot_hash,
                "manifest_hash": self.manifest_hash,
                "prefix_digest": self.prefix_digest,
                "prefix_length": self.prefix_length,
                "replay_schema_version": self.replay_schema_version,
                "schema_version": self.schema_version,
            }
        )
        return {**identity, "key_id": stable_digest(identity, prefix="prefixkey_")}

    @property
    def key_id(self) -> str:
        return str(self.to_dict()["key_id"])


@dataclass(frozen=True)
class ReplayPrefixCacheEntry:
    key: ReplayPrefixCacheKey
    terminal_state_id: str
    next_request_signature: str | None
    core_trace_digest: str
    artifact_ref: str
    state_completeness: str
    replay_verified: bool = True
    reuse_mode: PrefixReuseMode = PrefixReuseMode.VERIFIED_REPLAY_HINT
    schema_version: str = PREFIX_CACHE_ENTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.key, ReplayPrefixCacheKey):
            raise ValueError("key must be ReplayPrefixCacheKey")
        for name in (
            "terminal_state_id",
            "core_trace_digest",
            "artifact_ref",
            "state_completeness",
        ):
            _string(getattr(self, name), name)
        if self.next_request_signature is not None:
            _string(self.next_request_signature, "next_request_signature")
        if self.state_completeness not in {"exact", "query_api_projection"}:
            raise ValueError(
                "state_completeness must be 'exact' or 'query_api_projection'"
            )
        if self.replay_verified is not True:
            raise ValueError("prefix cache entries require replay_verified=True")
        if not isinstance(self.reuse_mode, PrefixReuseMode):
            if self.reuse_mode in REJECTED_NATIVE_REUSE_MODES:
                raise ValueError(
                    "native snapshot/clone prefix reuse is rejected by ADR-0009; "
                    "use verified_replay_hint"
                )
            object.__setattr__(self, "reuse_mode", PrefixReuseMode(self.reuse_mode))
        if self.reuse_mode != PrefixReuseMode.VERIFIED_REPLAY_HINT:
            raise ValueError("only verified_replay_hint reuse is implemented")
        if self.schema_version != PREFIX_CACHE_ENTRY_SCHEMA_VERSION:
            raise ValueError("unsupported prefix cache entry schema")

    @classmethod
    def from_replay(
        cls,
        replay: Mapping[str, Any],
        prefix_length: int,
        *,
        artifact_ref: str,
        state_completeness: str,
        next_request_signature: str | None = None,
    ) -> "ReplayPrefixCacheEntry":
        key = ReplayPrefixCacheKey.from_replay(replay, prefix_length)
        events = replay.get("events")
        initial_snapshot = replay.get("initial_snapshot")
        terminal_state_id = (
            _string(initial_snapshot.get("state_hash"), "initial_snapshot.state_hash")
            if prefix_length == 0
            else _string(
                events[prefix_length - 1].get("state_hash_after"),
                f"events[{prefix_length - 1}].state_hash_after",
            )
        )
        core_trace = [
            to_canonical_data(event.get("core_output", {}))
            for event in events[:prefix_length]
        ]
        return cls(
            key=key,
            terminal_state_id=terminal_state_id,
            next_request_signature=next_request_signature,
            core_trace_digest=stable_digest(core_trace, prefix="coretrace_"),
            artifact_ref=artifact_ref,
            state_completeness=state_completeness,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReplayPrefixCacheEntry":
        if not isinstance(value, Mapping):
            raise ValueError("prefix cache entry must be a mapping")
        entry = cls(
            key=ReplayPrefixCacheKey.from_dict(value.get("key")),
            terminal_state_id=value.get("terminal_state_id"),
            next_request_signature=value.get("next_request_signature"),
            core_trace_digest=value.get("core_trace_digest"),
            artifact_ref=value.get("artifact_ref"),
            state_completeness=value.get("state_completeness"),
            replay_verified=value.get("replay_verified"),
            reuse_mode=value.get("reuse_mode"),
            schema_version=value.get("schema_version"),
        )
        if entry.to_dict() != to_canonical_data(value):
            raise ValueError("prefix cache entry_id does not match content")
        return entry

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "artifact_ref": self.artifact_ref,
                "core_trace_digest": self.core_trace_digest,
                "key": self.key.to_dict(),
                "next_request_signature": self.next_request_signature,
                "replay_verified": self.replay_verified,
                "reuse_mode": self.reuse_mode.value,
                "schema_version": self.schema_version,
                "state_completeness": self.state_completeness,
                "terminal_state_id": self.terminal_state_id,
            }
        )
        return {**identity, "entry_id": stable_digest(identity, prefix="prefixentry_")}

    @property
    def estimated_bytes(self) -> int:
        return len(canonical_json(self.to_dict()).encode("utf-8"))


@dataclass(frozen=True)
class PrefixCacheVerification:
    key_id: str
    status: CacheVerificationStatus
    expected: Mapping[str, Any]
    actual: Mapping[str, Any]
    schema_version: str = PREFIX_CACHE_VERIFICATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "actual": self.actual,
                "expected": self.expected,
                "key_id": self.key_id,
                "schema_version": self.schema_version,
                "status": self.status.value,
            }
        )
        return {
            **identity,
            "verification_id": stable_digest(identity, prefix="prefixverify_"),
        }


class ReplayPrefixCache:
    def __init__(self, policy: PrefixCachePolicy) -> None:
        self.policy = policy
        self._entries: OrderedDict[str, ReplayPrefixCacheEntry] = OrderedDict()
        self._bytes = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.invalidations = 0
        self.flushes = 0
        self._mutations_since_flush = 0

    def _remove(self, key_id: str) -> ReplayPrefixCacheEntry | None:
        entry = self._entries.pop(key_id, None)
        if entry is not None:
            self._bytes -= entry.estimated_bytes
            self._mutations_since_flush += 1
        return entry

    def put(self, entry: ReplayPrefixCacheEntry) -> tuple[str, ...]:
        if not isinstance(entry, ReplayPrefixCacheEntry):
            raise ValueError("entry must be ReplayPrefixCacheEntry")
        size = entry.estimated_bytes
        if size > self.policy.max_entry_bytes:
            raise ValueError(
                f"prefix cache entry is {size} bytes; max_entry_bytes is "
                f"{self.policy.max_entry_bytes}"
            )
        self._remove(entry.key.key_id)
        self._entries[entry.key.key_id] = entry
        self._bytes += size
        self._mutations_since_flush += 1
        evicted: list[str] = []
        while (
            len(self._entries) > self.policy.max_entries
            or self._bytes > self.policy.max_bytes
        ):
            key_id, oldest = self._entries.popitem(last=False)
            self._bytes -= oldest.estimated_bytes
            self.evictions += 1
            self._mutations_since_flush += 1
            evicted.append(key_id)
        return tuple(evicted)

    def get(
        self, key: ReplayPrefixCacheKey | str
    ) -> ReplayPrefixCacheEntry | None:
        key_id = key.key_id if isinstance(key, ReplayPrefixCacheKey) else str(key)
        entry = self._entries.pop(key_id, None)
        if entry is None:
            self.misses += 1
            return None
        self._entries[key_id] = entry
        self.hits += 1
        return entry

    def verify_replayed_prefix(
        self,
        key: ReplayPrefixCacheKey | str,
        *,
        terminal_state_id: str,
        next_request_signature: str | None,
        core_trace_digest: str,
    ) -> PrefixCacheVerification:
        key_id = key.key_id if isinstance(key, ReplayPrefixCacheKey) else str(key)
        entry = self.get(key_id)
        if entry is None:
            raise KeyError(f"prefix cache key {key_id!r} is not present")
        expected = {
            "core_trace_digest": entry.core_trace_digest,
            "next_request_signature": entry.next_request_signature,
            "terminal_state_id": entry.terminal_state_id,
        }
        actual = {
            "core_trace_digest": _string(core_trace_digest, "core_trace_digest"),
            "next_request_signature": (
                _string(next_request_signature, "next_request_signature")
                if next_request_signature is not None
                else None
            ),
            "terminal_state_id": _string(terminal_state_id, "terminal_state_id"),
        }
        status = (
            CacheVerificationStatus.VALID
            if to_canonical_data(expected) == to_canonical_data(actual)
            else CacheVerificationStatus.INVALIDATED
        )
        if status == CacheVerificationStatus.INVALIDATED:
            self._remove(key_id)
            self.invalidations += 1
        return PrefixCacheVerification(
            key_id=key_id,
            status=status,
            expected=expected,
            actual=actual,
        )

    def retain_manifest(self, manifest_hash: str) -> tuple[str, ...]:
        manifest_hash = _string(manifest_hash, "manifest_hash")
        stale = tuple(
            key_id
            for key_id, entry in self._entries.items()
            if entry.key.manifest_hash != manifest_hash
        )
        for key_id in stale:
            self._remove(key_id)
            self.invalidations += 1
        return stale

    @property
    def should_flush(self) -> bool:
        return (
            self.policy.persistence_mode == CachePersistenceMode.INDEX_ONLY
            and self._mutations_since_flush >= self.policy.flush_every_mutations
        )

    def mark_flushed(self) -> None:
        self._mutations_since_flush = 0
        self.flushes += 1

    def stats(self) -> dict[str, Any]:
        return {
            "bytes": self._bytes,
            "entries": len(self._entries),
            "evictions": self.evictions,
            "flushes": self.flushes,
            "hits": self.hits,
            "invalidations": self.invalidations,
            "misses": self.misses,
            "mutations_since_flush": self._mutations_since_flush,
            "policy_id": self.policy.to_dict()["policy_id"],
        }

    def to_index_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "entries": [entry.to_dict() for entry in self._entries.values()],
                "policy": self.policy.to_dict(),
                "schema_version": PREFIX_CACHE_INDEX_SCHEMA_VERSION,
            }
        )
        return {**identity, "index_id": stable_digest(identity, prefix="prefixindex_")}

    @classmethod
    def from_index_dict(
        cls,
        value: Mapping[str, Any],
        *,
        policy_override: PrefixCachePolicy | None = None,
    ) -> "ReplayPrefixCache":
        if not isinstance(value, Mapping):
            raise ValueError("prefix cache index must be a mapping")
        identity = {
            "entries": value.get("entries"),
            "policy": value.get("policy"),
            "schema_version": value.get("schema_version"),
        }
        if value.get("schema_version") != PREFIX_CACHE_INDEX_SCHEMA_VERSION:
            raise ValueError("unsupported prefix cache index schema")
        if value.get("index_id") != stable_digest(identity, prefix="prefixindex_"):
            raise ValueError("prefix cache index_id does not match content")
        persisted_policy = PrefixCachePolicy.from_dict(
            value.get("policy") if isinstance(value.get("policy"), Mapping) else {}
        )
        cache = cls(policy_override or persisted_policy)
        entries = value.get("entries")
        if not isinstance(entries, list):
            raise ValueError("prefix cache index entries must be a list")
        for raw_entry in entries:
            cache.put(ReplayPrefixCacheEntry.from_dict(raw_entry))
        cache._mutations_since_flush = 0
        return cache


def write_prefix_cache_index(path: str | Path, cache: ReplayPrefixCache) -> None:
    if cache.policy.persistence_mode != CachePersistenceMode.INDEX_ONLY:
        raise ValueError("prefix cache index persistence is disabled")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(canonical_json(cache.to_index_dict()) + "\n", encoding="utf-8")
    temporary.replace(destination)
    cache.mark_flushed()


def read_prefix_cache_index(
    path: str | Path,
    *,
    policy_override: PrefixCachePolicy | None = None,
) -> ReplayPrefixCache:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("prefix cache index is invalid JSON") from exc
    return ReplayPrefixCache.from_index_dict(value, policy_override=policy_override)
