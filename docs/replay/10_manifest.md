# Replay reproducibility manifest

Status: V0.3a executable contract

Last updated: 2026-07-13

## Purpose

`ReplayManifestV03a` decides whether a replay contains enough information to attempt deterministic playback. Free-form `version_metadata` remains available for display, but it is not the source of truth for strict replay.

The manifest identity has four versioned sections:

- `environment`: replay/bridge/snapshot schemas, core API/lock/commit/binary hash/custom patches, asset lock/commits/file hashes, and direct-random instrumentation identity.
- `randomness`: the four-word core seed, the I/O trace policy, and whether Python random state was used. A Python seed is required when Python randomness is enabled.
- `rules`: exact duel flags, master-rule identifier, forbidden/limited-list identifier, and unsafe-Lua setting.
- `initial_conditions`: complete initial snapshot hash, information mode, starting player, and proof that deck order is present in the snapshot.

`manifest_hash` is a canonical SHA-256 identity over those sections and the manifest schema version. `reproducible` and `missing_requirements` are derived diagnostics and are not trusted as input.

## Failure policy

Strict replay calls `assert_reproducible()` before playback. A missing required path, unsupported manifest schema, required Python seed omission, or initial snapshot hash mismatch raises `ReplayManifestIncompleteError` or `ReplayFormatError`; the run must not be reported as reproduced.

The verifier constructs a manifest from the current installed environment and compares canonical identity fields before starting the core worker. `ReplayEnvironmentMismatchError` reports the first stable field path and both values, for example `environment.core.binary_sha256`. This separates runtime/assets/rules mismatch from a later DecisionRequest signature mismatch.

The fixed real-core artifact stores the complete initial snapshot, including ordered zones, and a manifest that references its `state_hash`. The worker uses no Python randomness and records this explicitly rather than inventing an unused seed.
`randomness.trace_policy` is fixed to `raw-core-frames-and-script-log-random-events-v3`; missing or different policies fail strict reproducibility validation. Ordered response and random outcome details are defined in [Replay randomness and I/O trace](30_randomness_and_io_trace.md).
