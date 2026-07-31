# Changelog

All notable package changes are documented here. Package versions follow Semantic Versioning and remain independent from Experiment, Route DSL, Replay, Search, and other functional contract versions.

## Unreleased

### Added

- [v0.9.0] Added deck-scoped terminal evaluation profile management for the desktop UI, including the `[P] プロファイル` page, deck-card selection, archive deletion, and `deck.profile.*` bridge contracts.
- [v0.9.0] Added desktop deck metadata management for display names and tags without changing `deck_id`, `deck_sha256`, existing jobs, or evidence.
- [v0.9.0] Added result-view explainability for Help icons, conservative termination explanations, opening hand conditions, and peak-score board snapshots.

### Changed

- [v0.9.0] The desktop catalog now uses Japanese card presentation when available and does not treat card codes as card names. The deprecated visible inline deck creation entry point is hidden while retaining `deck.register_inline` compatibility.

### Governance

- [v0.9.0] Planned and started the terminal preference and card selection UX release. The stage keeps `card_code` as the internal identifier while moving desktop editing to deck-scoped profiles, deck-card selection, archive deletion, and fail-closed handling when Japanese card presentation is unavailable.

## 0.8.0 - 2026-07-31

Status: Japanese-centered desktop UI and i18n quality source release. It promotes the research dashboard UI to Japanese defaults, rejects mojibake in release-facing assets, and adds a dedicated release gate for localization quality.

### Added

- [v0.8.0] Added `japanese-i18n-release-gate-v1` and the `japanese-i18n-gate` CLI command so `lang="ja"`, Japanese desktop copy, dynamic text catalogs, fixture copy, release-facing docs, and known mojibake markers are checked as release readiness evidence.
- [v0.8.0] Added `ANALYTICS_TEXT` and `ANALYTICS_LOCALE` to the desktop analytics module so virtual table labels, status text, export messages, and fail-closed diagnostics are centralized in Japanese for future locale switching.

### Changed

- [v0.8.0] Promoted desktop UI copy to Japanese-centered defaults across the packaged static HTML, dynamic deck/search/result text, analytics table labels, fixture deck names, fixture tags, card metadata, recent runs, aria labels, placeholders, dialog labels, and status regions.
- [v0.8.0] Updated release governance, roadmap, versioning documentation, and release readiness aggregation so `0.8.0` is tracked as a released source milestone and `1.0.0` remains the production/distribution gate.

### Fixed

- [v0.8.0] Removed known mojibake patterns such as halfwidth U+FF82 separators and corrupted arrow/close/check glyphs from desktop static assets and release-facing 0.8.0 documentation, with regression tests covering the packaged UI and docs.

## 0.7.0 - 2026-07-31

Status: Evidence-driven research dashboard source release. It promotes committed result hydration, preference-aware ranking, fresh Replay verification, Top-K/coverage drill-down, conditioned cohort analytics, and adopted dashboard qualification evidence.

### Added

- [v0.7.0] Added `desktop-result-view-v1` and the `job.result` bridge method so the desktop result dialog can hydrate only committed `route-dsl` and `search-run-report` job artifacts after path containment, checksum, schema, Route ID, and artifact-commit verification. Browser preview remains explicitly synthetic and real desktop jobs now fail closed instead of falling back to a fixed Route fixture.
- [v0.7.0] Added `terminal-board-projection-v1`, immutable `terminal-preference-profile-v1`, and `terminal-preference-evaluation-v1` so terminal scoring can explain matched card instances by controller, location, position, count predicate, scoring mode, and redacted/unknown status.
- [v0.7.0] Added `route-randomness-summary-v1` and `route-ranking-v1` with a content-addressed ranking policy for success, terminal composite score, gameplay reliability, random event count, peak score, action count, and stable Route ID tie-breaking.
- [v0.7.0] Persisted Route randomness summaries and explicit research ranking identities in `search-run-result-v5` output while preserving the legacy `best_route` ordering, and extended `job.result` to verify and expose ranking/randomness identities from committed artifacts.
- [v0.7.0] Hardened committed result hydration so `route_ranking` and Top-K route summaries must include and agree with the committed `best_route` Route ID, score, peak score, success flag, and recomputed randomness summary. Recomputed ranking IDs alone are no longer enough when the Top-K summary diverges from the committed Route artifact.
- [v0.7.0] Added a local terminal preference profile catalog with content-addressed atomic JSON records, clone-on-edit semantics, desktop bridge list/get/clone methods, and Experiment 0.4 profile document binding.
- [v0.7.0] Connected Experiment terminal preference profiles to Search route summaries, terminal composite scoring, research ranking, and desktop result score breakdowns when committed Route artifacts expose terminal board projections.
- [v0.7.0] Hardened committed result hydration so `best_route.terminal_score` must match the recomputed `terminal-preference-evaluation-v1` composite score. Terminal preference evaluation mismatches now preserve their identity-mismatch diagnostics instead of being wrapped as generic schema failures.
- [v0.7.0] Added `job.enqueue_replay_verification` and Replay worker execution so the desktop bridge can create an independent verification job only from succeeded search jobs with committed Route artifacts, then publish a checksum-tracked `fresh-replay-verification-v1` artifact after Route ID, replay manifest, and report validation.
- [v0.7.0] Added `search-candidate-evidence-v1` and `search-coverage-v1` to SearchRun output so desktop result views can expose bounded candidate/path counts, censored budget stops, and conservative `frontier_exhausted` versus `best_observed` coverage certificates from committed artifacts.
- [v0.7.0] Hardened desktop result hydration so committed coverage certificates are not accepted by content ID alone: `frontier_exhausted` now requires matching status, complete candidate accounting, frontier-exhausted termination, zero pending/unknown candidates, and zero unexplored/censored/pruned counts before the UI can drop the conservative `best_observed` label.
- [v0.7.0] Hardened committed candidate evidence hydration so `search-candidate-evidence-v1` counts are recomputed from candidate records and compared with the coverage certificate before result rendering. Rehashed reports with inconsistent candidate totals or coverage/candidate count drift now fail closed instead of showing contradictory drill-down data.
- [v0.7.0] Connected committed result coverage and candidate evidence to the desktop Result dialog with bounded candidate preview, coverage status, explored count, and censored count while synthetic browser preview and fail-closed artifact errors keep evidence hidden.
- [v0.7.0] Connected the desktop Result dialog to `job.enqueue_replay_verification` so committed Search results can queue an independent Replay verification job and surface queued, running, verified, or terminal failure states without substituting browser preview data.
- [v0.7.0] Added bounded Result dialog drill-down tables for committed Top-K route ranking and candidate/path evidence, with local tab switching over verified `job.result` payloads and no extra browser-side data source.
- [v0.7.0] Extended `analytics-query-contract-v1` rows and desktop Run observations with opening-hand cohort, terminal preference profile, success predicate, ranking policy, termination, censor state, core lock, and asset lock fields so conditioned, fixed, random, censored, and profile-distinct runs can be filtered/exported without silent cohort merging.
- [v0.7.0] Connected the desktop Search dialog to the terminal preference profile catalog so real desktop searches send the selected immutable profile ID through `scenario.compose_search` instead of always binding the default profile.
- [v0.7.0] Added a desktop terminal preference clone editor for card code, terminal location, position, and signed weight rules, using `profile.get` plus `profile.clone` so UI edits create a new immutable profile instead of mutating prior SearchRun scoring inputs.
- [v0.7.0] Connected desktop Search opening-hand controls for seeded random, fixed cards, and conditional draw predicates to typed `scenario.compose_search` payloads so conditioned research cohorts no longer require hand-written Experiment JSON.
- [v0.7.0] Connected the desktop inline deck dialog to the typed `deck.register_inline` bridge path with comma/space/newline card-code parsing, local shape checks, service diagnostics, catalog refresh, and registered-deck selection.
- [v0.7.0] Connected desktop Objective selection to a service-owned `scenario_preset_id` allowlist so evaluator and success predicate selection remains qualified and renderer-defined expressions fail closed.
- [v0.7.0] Added `research-dashboard-release-gate-v1` and the `research-dashboard-gate` CLI to bundle Gate A-E static contract checks for committed result artifacts, independent Replay verification, terminal preference, route randomness/ranking, coverage/drill-down, typed scenario inputs, cohort analytics, and the Neuron import rejection ADR. Early committed evidence remained failed until later real-core dashboard qualification evidence was adopted.
- [v0.7.0] Added content-addressed validation and the `research-dashboard-qualification` CLI for `research-dashboard-qualification-v1`, so the release gate no longer accepts a minimal `passed: true` JSON as real-core dashboard qualification. The initial pending qualification recorded failed checks for committed artifact E2E, fresh Replay E2E, desktop screenshot/a11y, security/redaction, and resource-budget evidence; adopted qualification evidence now supplies the passing release witness.
- [v0.7.0] Added `research-dashboard-qualification-bundle` and connected it to the manual `release-self-hosted-evidence.yml` workflow so runner-local dashboard artifacts can be converted into the exact five required qualification checks and redacted qualification/gate evidence without uploading raw screenshots, Routes, SearchRun reports, or fresh Replay reports.
- [v0.7.0] Added `research-dashboard-qualification-manifest-template` to write a runner-local artifact manifest starter with required artifact paths, identity placeholders, and `null` pass-critical booleans that must be replaced by measured witnesses before the bundle can pass.
- [v0.7.0] Hardened `research-dashboard-qualification-bundle` so pass-critical manifest booleans for committed artifact verification, fresh-worker Replay, screenshot/a11y, security/redaction, censor recording, and resource budget pass state are required explicit witnesses instead of defaulting to a passing value when omitted.
- [v0.7.0] Hardened `research-dashboard-qualification-bundle` to read and validate committed result view, SearchRun report, and Route DSL artifacts before qualification generation, rejecting invalid schemas, non-committed SearchRun artifacts, and Route ID mismatches instead of trusting manifest booleans alone.
- [v0.7.0] Hardened `research-dashboard-qualification-bundle` to validate the fresh Replay report with the existing `fresh-replay-verification-v1` reader, require readable security/resource JSON reports, and reject security/resource report values that contradict the manifest witness.
- [v0.7.0] Hardened `research-dashboard-qualification-bundle` to reject non-PNG desktop screenshots and viewport-dimension mismatches before emitting dashboard qualification evidence.
- [v0.7.0] Hardened the manual `release-self-hosted-evidence.yml` workflow so the runner-local dashboard manifest input is passed to PowerShell through a step environment variable rather than direct string interpolation in the script body.
- [v0.7.0] Extended the release self-hosted workflow's pre-upload audit to cover the research-dashboard branch, requiring finalized summary identity, dashboard qualification/gate agreement, and the selected workflow inputs before sanitized dashboard evidence is published.
- [v0.7.0] Extended `release-self-hosted-evidence-audit` to validate dashboard qualification imports, requiring the release gate manual witness to match the qualification evidence ID and pass state before committed 0.7 evidence is replaced.
- [v0.7.0] Adopted passing research-dashboard qualification and gate evidence from local browser/self-hosted artifacts, then refreshed `release-readiness-status-v1` so 0.7.0 is ready alongside 0.5.1 and 0.6.0.
- [v0.7.0] Added `release-self-hosted-evidence-adopt --adopt-research-dashboard` to rerun the required passing audit, require a successful workflow summary with the research-dashboard branch marked as run, and copy only redacted dashboard qualification/gate evidence plus the audit report into `docs/release/evidence`.
- [v0.7.0] Extended adopted self-hosted evidence verification with `--require-research-dashboard`, validating the saved audit and requiring the current dashboard qualification/gate files to reproduce the audited branch witness.
- [v0.7.0] Hardened passing `research-dashboard-qualification-v1` checks to require structured witness fields for committed artifact identity and checksums, independent fresh Replay verification, desktop screenshot/a11y results, security/redaction review, and resource-budget measurements. A content-addressed qualification with `passed: true` and only a placeholder artifact path is now rejected before it can satisfy the manual release gate.
- [v0.7.0] Extended passing `research-dashboard-qualification-v1` evidence with a common redacted artifact manifest requirement. Passing checks must now include filename-only evidence artifact labels plus SHA-256 fingerprints and `path_redacted: true`; persisted qualification evidence with path leaks, missing artifact manifests, duplicate or reordered artifact labels, or invalid artifact hashes is rejected before the dashboard release gate can pass.
- [v0.7.0] Hardened `research-dashboard-qualification-v1` to require exactly the five release qualification checks in canonical order, and hardened `research-dashboard-release-gate-v1` so persisted check pass states, `passed`, and `rejection_reasons` must agree. Generation normalizes input ordering, while inconsistent persisted evidence is rejected instead of silently widening or weakening the manual dashboard gate.
- [v0.7.0] Hardened `research-dashboard-release-gate-v1` to require the exact static/manual release check set and reject duplicate static/manual `gate:check_id` entries in persisted gate evidence.
- [v0.7.0] Extended the research dashboard static gate evidence to record and require the pinned `desktop-bridge-v1` and `analytics-query-contract-v1` contract versions, source/test/bridge witness flags, and the `job.result`, inline deck registration, and scenario composition renderer-path rejections. Persisted gate validation now recomputes each static check's pass state from those witnesses, including scenario composition's renderer-side rule-inference rejection, before the real-core dashboard qualification can pass.

### Governance

- [v0.7.0] Added the planned evidence-driven research-dashboard milestone, ADRs, evaluation/randomness/result contracts, and 30 fine-grained implementation and qualification work items. ADR-0018 rejects representative-card substitution and user-facing cost-card modes, and keeps user burden versus concrete-scenario qualification volume as a measured design constraint. This planning update does not change runtime behavior, package version, Route ranking, or desktop defaults.
- [v0.7.0] Added ADR-0019 for #303, rejecting NEURON direct import without an official third-party API and keeping YDK/inline/manual local deck input as the supported path.

## 0.6.0 - 2026-07-31

Status: Deterministic parallel-search source release. It promotes bounded pool execution, semantic determinism, self-hosted timing evidence, and adopted parallel-search release evidence.

### Added

- [v0.6.0] Connected explicit `search.parameters.parallel` policies to Random Search bounded child prefetch, Beam Search layer replay dispatch, and MCTS untried-expansion prefetch so child nodes can be fetched through a bounded pool while SearchRun commits, logical updates, route ordering, and pool-size-independent semantics remain canonical. Desktop scenario composition now exposes bounded pool selection through the typed bridge, with policy omission and `pool_size=1` preserving the existing serial behavior.
- [v0.6.0] Added `parallel-search-release-gate-v1` and the `parallel-search-gate` CLI, a content-addressed release-gate evaluator that rejects synthetic evidence, timing-censored cells, semantic drift, insufficient repeats, pool 4 regressions, and speedups below the planned 3-fixture threshold. Early committed evidence was intentionally incomplete until the later adopted self-hosted 100,000-node real-core performance evidence satisfied the release gate.
- [v0.6.0] Extended the parallel-search release gate with source-evidence summaries and committed `docs/release/evidence/parallel_search_gate.json` as an intentionally failed gate. The evidence records that `real_core_parallel_stress.json` validates scheduling/retry semantics and `0105_general_search_100k.json` validates logical executor/cache/artifact behavior, but neither is a real-core per-profile timing record source; later adopted self-hosted pool 1/2/4 benchmark records complete the 0.6.0 release witness.
- [v0.6.0] Added `parallel-search-release-records-v1` and the `parallel-search-records` CLI to normalize completed self-hosted `search-run-report-v1` artifacts into release-gate timing records. The normalizer verifies committed SearchRun artifacts, artifact-commit schema, best Route/artifact/Route-file ID consistency, optional Route-file SHA-256 consistency, route ranking consistency, pool-size provenance, elapsed wall time, node/replay counts, semantic digest, lineage digest, and RSS input before records can be evaluated by `parallel-search-gate`; the gate also rejects compared pools whose committed node count or node/replay budgets drift and record bundles with duplicate profile/pool/repeat cells.
- [v0.6.0] Extended `parallel-search-release-records-v1` with a redacted `input_manifest` that content-addresses each source report/Route file by SHA-256 and records the profile, pool, repeat, budget, RSS, censor, and worker-kind handoff without storing absolute paths. Persisted record bundles now reject missing manifests, path leaks, noncanonical manifest order, and manifest/record mismatches before the release timing gate can run.
- [v0.6.0] Hardened the `parallel-search-gate` CLI to accept only validated `parallel-search-release-records-v1` bundles produced by `parallel-search-records`, plus the explicit empty pending schema used by committed failed evidence. Raw JSON lists or ad-hoc `{records: ...}` objects can still be evaluated in unit tests through the Python API, but no longer satisfy the release CLI path.
- [v0.6.0] Hardened persisted `parallel-search-release-gate-v1` evidence to retain a `record_bundle` witness with the source bundle schema, evidence ID, redacted source filename, record count, and input-manifest digest. A content-addressed passing gate built from inline/raw records is rejected unless it references a validated `parallel-search-release-records-v1` bundle.
- [v0.6.0] Redacted `parallel-search-gate` source-evidence summaries so persisted `input_sources` keep filename-only `source_path_name` plus `path_redacted: true` instead of local paths. Persisted gate validation now rejects legacy or tampered source summaries that include a `path` field.
- [v0.6.0] Hardened `parallel-search-gate` so `parallel-search-release-records-v1` bundles and persisted gate records are stored in canonical profile/pool/repeat order, require zero-origin contiguous repeat-index sequences per profile/pool, require at least 100,000 committed nodes plus node/replay budgets for release-scale records, recompute persisted profile results/rejections/pass state from records and source summaries, and are content-address verified before records are evaluated. Reordered, shifted, gapped, undersized, timing-hidden, or tampered self-hosted timing evidence now fails before median speedup or semantic-invariant checks run.
- [v0.6.0] Added the manual Windows self-hosted `release-self-hosted-evidence.yml` workflow for release-scale parallel-search collection. It runs `parallel-search-collect` and `parallel-search-gate` on the representative profile set, then uploads only redacted records/gate evidence and a sanitized summary while leaving generated Routes, SearchRun reports, and working manifests on the runner.
- [v0.6.0] Hardened `parallel-search-collect` so a non-zero `experiment-search` status aborts collection with the profile/pool/repeat coordinate, and SearchRun reports ending at `termination_reason: max_seconds` are marked `timing_censored: true` in the release record manifest before gate evaluation.
- [v0.6.0] Added `parallel-search-collect --require-release-grid` and wired the self-hosted release workflow to it, so missing representative profiles, non-1/2/4 pool grids, repeat counts below five, or node/replay budgets below 100,000 fail before heavy release Search starts.
- [v0.6.0] Added explicit `ocgcore-verify` and `ocgcore-assets-verify` steps to the release self-hosted workflow and pass `--external-root` through the release collection command, making real-core prerequisite failures visible before the 100,000-node timing grid begins.
- [v0.6.0] Updated the release self-hosted parallel-search workflow to use the Experiment 0.4 `cross_validation_short`, `cross_validation_long`, and `cross_validation_grave_banish` representative profiles, preventing the release collector from failing preflight on legacy 0.3b prototype fixtures.
- [v0.6.0] Hardened the release self-hosted workflow to run `release-self-hosted-evidence-audit` after summary finalization and before artifact upload, with expected commit/run-id and selected branch requirements, so mismatched redacted records/gates fail the workflow instead of being discovered only during local adoption.
- [v0.6.0] Added `release-self-hosted-evidence-audit` so downloaded workflow artifacts are checked before replacing committed release evidence. The audit rejects unexpected raw files and verifies that `parallel_search_gate.json` references the same records bundle evidence ID and record count as `parallel_search_records.json`.
- [v0.6.0] Added optional `--expected-commit` and `--expected-run-id` checks to `release-self-hosted-evidence-audit` and `release-self-hosted-evidence-adopt` so downloaded workflow artifacts from the wrong checkout or GitHub run are rejected before committed evidence is replaced.
- [v0.6.0] Added `release-self-hosted-evidence-adopt --adopt-parallel-search` to rerun the required passing audit, require a successful workflow summary with the parallel-search branch marked as run, and copy only redacted 0.6 records/gate evidence plus the audit report into `docs/release/evidence`.
- [v0.6.0] Added `release-self-hosted-evidence-verify-adopted --require-parallel-search` so adopted `docs/release/evidence` records/gate files are reread and compared with the saved self-hosted audit before 0.6 release evidence is treated as current.
- [v0.6.0] Hardened self-hosted evidence adoption so the saved audit references only the selected copied branch, allowing 0.6 and 0.7 evidence to be adopted independently from one combined workflow run without leaving dangling audit references.
- [v0.6.0] Clarified adopted self-hosted audit identity by separating copied `artifact_files` from original workflow `source_artifact_files`, so adopted release evidence no longer claims that `summary.json` was copied into `docs/release/evidence`.
- [v0.6.0] Hardened `release-self-hosted-evidence-verify-adopted` so the files actually revalidated from `docs/release/evidence` must match the saved audit's copied `artifact_files` list.
- [v0.6.0] Hardened the release self-hosted workflow summary writer to emit BOM-free UTF-8 JSON from Windows PowerShell so the Python audit/adoption CLIs can read `summary.json` consistently.

### Governance

- [v0.6.0] Added the planned deterministic node-level parallel-search milestone, detailed implementation work items, and a measured search-latency release gate. No runtime default or package version changes in this planning update.

## 0.5.1 - 2026-07-31

Status: Compatible maintenance source release. It promotes verification profile planning, quieter profile evidence, and release-readiness status verification without weakening regression coverage.

### Added

- [v0.5.1] Added `pytest-profile-plan-v1`, `pytest-profile-measurement-v1`, `pytest-profile-suite-v1`, `pytest-profile-summary-v1`, and the `test-profile-plan` / `test-profile-run` / `test-profile-suite` / `test-profile-summary` CLIs, content-addressed verification contracts that assign every `tests/test_*.py` file to one primary `unit`, `integration`, `real_core`, `evidence`, `packaging`, or `release` profile, record per-profile wall time, pytest counts, stdout/stderr bytes, return code, and process peak RSS where available, label baseline/current cold/warm suite cells, then aggregate measurements against a baseline reduction gate. The committed suite covers all six profiles for both `baseline` and `current` cold/warm runs, and the committed summary is passing for the documented release-profile selection comparison.
- [v0.5.1] Connected `test-profile-summary` to `pytest-profile-suite-v1` so summary evidence can be derived from labelled `phase` and `temperature` cells, including optional baseline suite extraction, instead of only accepting loose measurement files.
- [v0.5.1] Added `pytest-profile-release-gate-v1` and the `test-profile-gate` CLI to bind plan, suite, and summary evidence into one release decision. The gate rejects incomplete suite coverage, failed summary reduction, summary measurements not sourced from the suite, `--collect-only` cells, and skipped real-core measurements, while persisted gate validation recomputes rejections/pass state from suite/summary measurement IDs, suite profile plan IDs, and cell rejection witnesses.
- [v0.5.1] Added `release-readiness-status` and `release-readiness-status-v1` evidence so the staged 0.5.1/0.6.0/0.7.0 release state can be audited from committed gate files plus adopted self-hosted evidence. The current status records 0.5.1, 0.6.0, and 0.7.0 as ready after combined self-hosted artifact adoption.
- [v0.5.1] Updated `release-self-hosted-evidence-adopt` to regenerate `release_readiness_status.json` after copying audited artifacts, so adopting 0.6.0 or 0.7.0 self-hosted evidence also refreshes the aggregate staged release state.
- [v0.5.1] Hardened persisted `release-readiness-status-v1` validation so each stage's `ready` flag is recomputed from its gate witness and, for 0.6.0/0.7.0, its adopted self-hosted verification witness. Rehashed status JSON with contradictory stage readiness is now rejected.
- [v0.5.1] Added current-directory verification for persisted `release-readiness-status-v1`, allowing stale readiness reports to be rejected after any gate or adopted self-hosted evidence file changes.
- [v0.5.1] Added the `release-readiness-verify` CLI to validate a saved `release_readiness_status.json` against the current release evidence directory without regenerating it; incomplete staged releases still exit successfully when the saved status is current.
- [v0.5.1] Added `release-readiness-verify --require-passed` so final release checks can fail when the saved readiness status is current but 0.6.0 or 0.7.0 remains incomplete.
- [v0.5.1] Extended `release-readiness-verify` with optional `--expected-commit` and `--expected-run-id` checks, so staged release verification revalidates any adopted Windows self-hosted branch identity, and final `--require-passed` checks no longer trust readiness freshness alone.
- [v0.5.1] Added incremental `test-profile-suite --existing-suite` merging so remaining cold/warm profile cells can be measured one at a time without losing prior evidence. The committed suite now contains real `baseline/warm`, `baseline/cold`, `current/warm`, and `current/cold` measurements for all six profiles, including `real_core` with 207 passed and 0 skipped tests in each cell, reducing missing cells to 0.
- [v0.5.1] Marked pytest profile measurement subprocesses with `YGO_EFFECT_DSL_PYTEST_PROFILE_MEASUREMENT=1` and skipped only committed release-evidence self-check tests under that environment, avoiding a circular dependency while regenerating `pytest_profile_suite.json`; normal pytest and CI still run those committed evidence checks.
- [v0.5.1] Added `--suppress-success-output` to `test-profile-run` and `test-profile-suite`. Successful measurements disable pytest's terminal reporter and recover pytest counts from JUnit XML, while failing measurements rerun with normal terminal output to preserve actionable failure evidence. The committed `current/warm` summary now records stdout/stderr ratios of 0.0 and passes the release gate through the documented release-profile selection comparison, while keeping per-profile wall-time misses visible and marking that selected release profile evidence is not a substitute for full regression.
## 0.5.0 - 2026-07-16

Status: Cumulative Windows desktop analytics source milestone for Python engineers. Package stage 0.4.0 was not tagged separately. General distribution and production support remain blocked.

### Added

- [v0.5.0] `beam-search-strategy-v1` execution through the shared real-core frontier adapter and `experiment-search` CLI/API path.
- [v0.5.0] `mcts-strategy-v1` selection, expansion, deterministic rollout, reward normalization, and single backpropagation through the shared executor.
- [v0.5.0] PlayerView Route/Replay artifacts with private lineage separation and `information-access-audit-v2` leak detection.
- [v0.5.0] Core-driven multi-interruption timing, going-second board-break, multi-turn lifecycle, and strategy/interruption/recovery cross-validation contracts.
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
- [v0.5.0] `analytics-scale-calibration-v1` with 100,000 catalog runs, 1,000,000 raw Event/Decision rows, 100,000 persistent analytics rows, operation-level Parquet samples, crash/migration/concurrency recovery, and a manual Windows self-hosted workflow.

### Changed

- [v0.5.0] Search output now uses `search-run-result-v5`, `search-executor-v5`, `search-frontier-v2`, and content-addressed `search-strategy-evidence-v1`.
- [v0.5.0] Interruption execution supports ordered multiple opportunities and explicit turn/phase budgets without changing Python into a rules engine.
- [v0.5.0] The packaged desktop search form now composes Experiment 0.4 in the Python service and uses real preflight, SQLite job status/cancel, and the background worker; only the browser fixture retains synthetic progress.
- [v0.5.0] Analytics export scan/output hard caps are 100,000 rows after measured three-format exports reached approximately 2.48 GB peak RSS; the unverified one-million-row export path now fails closed.

### Fixed

- [v0.5.0] Treat native `MSG_WIN` as the authoritative duel terminal event even when ocgcore API 11.0 continues to report `AWAITING`; conflicting outcomes fail closed.

### Governance

- [v0.5.0] Added mandatory CHANGELOG maintenance, one-version-label/one-milestone Issue rules, a release work-item form, PR checklist, and a repeatable GitHub governance audit.
- [v0.5.0] Recorded untagged package stage 0.4.0 as superseded by this cumulative source milestone and retargeted incomplete production qualification without closing it as complete.

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
