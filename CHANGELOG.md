# Changelog

All notable package changes are documented here. Package versions follow Semantic Versioning and remain independent from Experiment, Route DSL, Replay, Search, and other functional contract versions.

## Unreleased

### Added

- `beam-search-strategy-v1` execution through the shared real-core frontier adapter and `experiment-search` CLI/API path.
- `search-run-result-v5` and `search-strategy-evidence-v1` with content-addressed strategy parameters and logical updates.

### Compatibility

- Historical `search-run-result-v4` qualification indexes remain readable.
- Random Search keeps its depth-first expansion and common best-Route ranking semantics.
- MCTS remains explicitly unavailable until its v0.4 implementation issue is complete.

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
