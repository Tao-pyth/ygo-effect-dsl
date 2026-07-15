# Changelog

All notable package changes are documented here. Package versions follow Semantic Versioning and remain independent from Experiment, Route DSL, Replay, Search, and other functional contract versions.

## Unreleased

### Added

- [v0.4.0] `beam-search-strategy-v1` execution through the shared real-core frontier adapter and `experiment-search` CLI/API path.
- [v0.4.0] `mcts-strategy-v1` selection, expansion, deterministic rollout, reward normalization, and single backpropagation through the shared executor.
- [v0.4.0] PlayerView Route/Replay artifacts with private lineage separation and `information-access-audit-v2` leak detection.
- [v0.4.0] Core-driven multi-interruption timing, going-second board-break, multi-turn lifecycle, and strategy/interruption/recovery cross-validation contracts.
- [v0.5.0] Reproducible SQLite, DuckDB, and Parquet storage-boundary evidence selecting SQLite for operational state and Parquet for derived analytics.
- [v0.5.0] `corpus-manifest-v1` provenance, exact and semantic duplicate identities, idempotent ingest, aggregation eligibility, and structured quarantine diagnostics.
- [v0.5.0] `job-state-machine-v1` with typed search/replay/import/aggregate/export jobs, dependency-aware priority scheduling, leases, heartbeats, retries, cancellation, orphan recovery, transition audit, and atomic artifact commit.
- [v0.5.0] `job-catalog-v2` recovery contracts for job deadlines, deterministic retry backoff, monotonic checkpoints, cooperative cancellation, hard-timeout supervision, crash-safe filesystem publication, orphan reconciliation, fault injection, and `job-inspect` CLI status.
- [v0.5.0] `analytics-query-contract-v1` with typed filters and selected fields, immutable snapshot-bound cursor pagination, explicit missing/redacted/quarantined value states, bounded synchronous scans, and asynchronous export-job fallback.
- [v0.5.0] `analytics-comparison-contract-v1` with validated baseline/interrupted/recovery lineage pairing, fail-closed version and budget compatibility, explicit censored/missing states, paired deltas, provisional confidence metadata, and visible pruning bias.
- [v0.5.0] `parquet-lifecycle-contract-v1` with measured layout policy, manifest-bound immutable snapshots, disk preflight, semantic parity, small-file compaction, explicit migration/backfill, crash-safe pointer activation, and rollback.
- [v0.5.0] Windows desktop shell ADR and same-host evidence selecting pywebview/WebView2, a versioned allowlist bridge, existing isolated search workers, and separate browser/desktop verification boundaries.
- [v0.5.0] `card-presentation-v1` and a verified local BabelCDB read-only provider with explicit locale fallback, PlayerView redaction, structured missing/stale/version diagnostics, metadata projection, and a strict no-Search/Replay dependency boundary.
- [v0.5.0] `desktop-workflow-v1` and a packaged, interactive deck-first research dashboard prototype covering catalog statistics, card detail, search preflight, synthetic job/result flow, comparison, responsive states, and default-deny frontend security.
- [v0.5.0] `desktop-bridge-v1`, an optional pywebview 6.2.1/WebView2 shell, single-instance catalog ownership, native YDK import, typed application-service allowlist, strict payload/path limits, and existing SQLite job/analytics/card-presentation adapters.
- [v0.5.0] `desktop-search-worker-v1` and Windows Job Object containment with real-core Search execution, lease heartbeat, cooperative cancellation, retry/checkpoint restart, atomic Route/SearchRun publication, cold/warm WebView2 evidence, and accessibility/security audits.
- [v0.5.0] `desktop-virtual-table-v1` with immutable 500-row cursor pages, server-side sort/filter integration, bounded viewport DOM rendering, keyboard/ARIA support, column and density controls, and 100,000-row-equivalent Edge evidence.
- [v0.5.0] `analytics-export-contract-v1` with snapshot-bound JSON/CSV/Parquet semantic parity, manifests and checksums, CLI/desktop background-job byte parity, cancel/retry/atomic publication, and formula/path/row/byte/disk safeguards.

### Changed

- [v0.4.0] Search output now uses `search-run-result-v5`, `search-executor-v5`, `search-frontier-v2`, and content-addressed `search-strategy-evidence-v1`.
- [v0.4.0] Interruption execution supports ordered multiple opportunities and explicit turn/phase budgets without changing Python into a rules engine.
- [v0.5.0] The packaged desktop search form now composes Experiment 0.4 in the Python service and uses real preflight, SQLite job status/cancel, and the background worker; only the browser fixture retains synthetic progress.

### Fixed

- [v0.4.0] Treat native `MSG_WIN` as the authoritative duel terminal event even when ocgcore API 11.0 continues to report `AWAITING`; conflicting outcomes fail closed.

### Governance

- [v0.5.0] Added mandatory CHANGELOG maintenance, one-version-label/one-milestone Issue rules, a release work-item form, PR checklist, and a repeatable GitHub governance audit.
- [v0.5.1] Added milestone and Issue scope for reducing verification wall time and agent log/token volume without deleting unique regression coverage.

### Compatibility

- Historical `search-run-result-v4` qualification indexes remain readable.
- Random Search keeps its depth-first expansion and common best-Route ranking semantics.
- Existing Experiment `0.3a`/`0.3b` and Route DSL `0.1` compatibility remains unchanged; package and contract versions continue to advance independently.

## 0.3.0 - 2026-07-15

Status: Real ocgcore / EDOPro Lua qualified source milestone for Python engineers on Windows x64. General distribution and production support remain blocked.

### Added

- Clean, idempotent ocgcore and pinned asset bootstrap qualification with structured failure and recovery evidence.
- Official CardScripts native-load qualification, strict resolver diagnostics, and a fail-closed Decision shape corpus.
- Repeated preflight, Random Search, best Route, and fresh Replay qualification for three external deck profiles.
- 100,000 logical-node evidence, 480 fresh real-core Replay measurements, and self-hosted Windows smoke evidence.
- Fail-closed wheel/sdist content audit and clean-venv wheel smoke in CI.

### Decisions

- Adopted worker pool 4 by default, pool 8 as the calibrated maximum, a 1.5 GiB process-memory preflight, and checked process-local script indexing.
- Kept statistical pruning disabled by default until #110 and kept `resource_consumption_v1` provisional until #108.
- Kept Experiment `0.4`, Route DSL `0.1`, and existing Replay/Search contract versions unchanged because this package release is non-breaking.

### Compatibility

- Experiment `0.3b` remains executable and `0.3a` remains an explicit migration input.
- No ocgcore binary, CardScripts, BabelCDB, or downloaded build tool is bundled.
- Beam Search, MCTS, PlayerView Replay, multi-turn interruption search, corpus UI, and public distribution remain outside this release.

## 0.2.0 - 2026-07-14

Status: General Search MVP candidate for Python engineers using a local asset cache. This source milestone does not authorize redistribution of third-party assets or claim production support.

### Added

- Experiment `0.4` with fixed, inline, and YDK decks; fixed, seeded random, and conditional opening hands; scenario manifest; and fail-closed preflight diagnostics.
- Deterministic `RandomSearchStrategyV1`, real-core frontier Replay, enforced search budgets, stable best-Route ordering, and the `experiment-search` CLI.
- Specified-interruption generation from core-provided activation, cost, target, and option candidates with a machine-readable support taxonomy.
- Three-profile 100,000 logical-node benchmark evidence, cache/worker policy v2, and memory preflight v2.
- Versioned frontier worker attempts, retry/quarantine evidence, structured Search failure reports, and Route-hash artifact commit markers.
- Package `--version` output and a single package-version source used by setuptools.

### Compatibility

- Route DSL remains `0.1`; DecisionRequest, Action, and Replay remain `0.3a`.
- Experiment `0.3b` remains executable and `0.3a` remains readable as explicit migration input.
- Beam Search, MCTS, real-core PlayerView Replay, large-scale statistics UI, and production distribution remain outside this release.
- ocgcore and third-party assets are not bundled.
