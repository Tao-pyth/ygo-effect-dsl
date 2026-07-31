# Package 0.6.0 Scope: Deterministic Parallel Search

## Current Gate Evidence

`docs/release/evidence/parallel_search_gate.json` is the committed passing `parallel-search-release-gate-v1` result for the current checkout after adopted self-hosted record evidence. The gate now treats 0.6 release scale as a composite claim: self-hosted pool 1/2/4 SearchRun records must still cover at least three representative profiles with the required repeat count, no deadline-censored cells, real-core worker provenance, stable semantic identity, RSS, and 100,000 node/replay budgets; `docs/adr/evidence/0105_general_search_100k.json` supplies the 100,000 logical-node executor/cache/artifact scale witness; `docs/adr/evidence/0128_real_core_replay_pool.json` supplies real-core fresh Replay pool timing, RSS, and semantic invariants; and `docs/search/evidence/real_core_parallel_stress.json` supplies pool-independent scheduling/retry/process-isolation evidence. This avoids claiming that every fresh-process SearchRun must spend days committing 100,000 real-core nodes, while still requiring current self-hosted records before a passing release gate is valid.

`parallel-search-records` writes `parallel-search-release-records-v1` from completed self-hosted `search-run-report-v1` files. It is the handoff between the heavy benchmark runner and `parallel-search-gate`: the normalizer checks committed SearchRun artifacts, artifact-commit schema, best Route/artifact/Route-file ID consistency, optional Route-file SHA-256 consistency, route ranking consistency, pool-size provenance, node/replay counts, elapsed wall time, semantic digest, lineage digest, RSS, and timing-censor metadata before the gate computes profile medians. The record bundle also carries a redacted `input_manifest` with source report/Route SHA-256, filename-only source labels, profile, pool, repeat, budget, RSS, censor, and worker-kind fields; absolute paths are not stored, and persisted bundles are rejected if the manifest is missing, noncanonical, leaks paths, or disagrees with the records. The `parallel-search-gate` CLI accepts only that validated bundle format, plus the explicit empty pending schema used by committed failed evidence; raw JSON lists and ad-hoc `{records: ...}` objects are not release evidence. Persisted gate evidence stores a `record_bundle` witness with the bundle schema, evidence ID, record count, redacted source filename, and input-manifest digest; a passing gate is invalid unless that witness points to a validated `parallel-search-release-records-v1` bundle. Persisted `input_sources` also use filename-only `source_path_name` plus `path_redacted: true`; source summaries and record-bundle witnesses containing local path values or unexpected `*_path` fields are rejected even when the evidence ID has been recomputed. Input node/replay budgets must be at least the measured SearchRun counts, and the gate requires committed nodes plus node/replay budgets to remain invariant across compared pool sizes and at least 100,000 for release evidence. Records are stored in canonical profile/pool/repeat order, duplicate profile/pool/repeat cells are rejected, and each profile/pool repeat sequence must start at `0` and remain contiguous. `parallel-search-gate` validates both the content-addressed record bundle and the persisted gate record ordering before reading records. Persisted gate evidence also recomputes `profile_results`, source-derived rejections, `rejection_reasons`, and `passed` from the stored records and gate thresholds. Complete non-censored repeats must be contiguous from `0`, so reordered, shifted, gapped, undersized, timing-hidden, or tampered self-hosted timing bundles are rejected before release evaluation.

For self-hosted collection, `parallel-search-records` also accepts `parallel-search-record-input-manifest-v1`: a compact grid manifest with `artifact_root`, `defaults`, and `grid.report_pattern`/optional `grid.route_pattern` expanded over profiles, pool sizes, and repeat indexes. This only automates manifest construction; each rendered SearchRun report is still opened, checked for committed artifacts and pool provenance, and converted into the same redacted `parallel-search-release-records-v1` bundle before `parallel-search-gate` can evaluate release readiness.

`parallel-search-collect` is the self-hosted runner entry point for that evidence. It accepts `PROFILE=Experiment` inputs, runs the requested profile/pool/repeat grid through `experiment-search`, writes per-run generated Experiments, committed Routes, and SearchRun reports under an artifact root, records top-level `parallel_policy` provenance in each report, writes a working `parallel-search-record-inputs-v1` manifest, and immediately emits the validated `parallel-search-release-records-v1` bundle. The collector keeps the source strategy seed stable across repeats so the runs measure the same workload; pool size changes are recorded only in `search.parameters.parallel` and the resulting `parallel_policy` witness. A non-zero `experiment-search` status aborts collection with the profile/pool/repeat coordinate, and a SearchRun ending at `termination_reason: max_seconds` is recorded as `timing_censored: true`, so wall-clock deadline-censored cells cannot satisfy the release timing gate. The release workflow calls the collector with `--require-release-grid` and `--max-depth 2`, which rejects missing representative profiles, non-1/2/4 pool grids, repeat counts below five, or node/replay budgets below 100,000 before any heavy Search is started while bounding the live self-hosted SearchRun probe to a reproducible real-core depth. The subsequent `parallel-search-gate` call passes the three supplemental evidence files listed above; they can satisfy release-scale committed-node and speedup claims only when all three summaries pass, and they do not remove the need for a validated positive self-hosted record bundle.

`.github/workflows/release-self-hosted-evidence.yml` is the manual Windows self-hosted workflow for release-scale collection. Before heavy collection it verifies the configured `YGO_EFFECT_DSL_EXTERNAL_ROOT` with `ocgcore-verify` and `ocgcore-assets-verify`, then its `parallel_search` branch runs `parallel-search-collect` on the three representative profiles with `--max-depth 2` and runs `parallel-search-gate`. That live grid proves the current checkout can generate non-censored, positive real-core SearchRun records for pools 1/2/4; route identity, semantic digest invariance, 100,000 logical-node scale, and replay-pool speedup are delegated to the supplemental source evidence summarized by the gate. After finalizing the sanitized summary, the workflow runs `release-self-hosted-evidence-audit` with the current commit, run ID, and selected branch requirements before artifact upload; audit failure rewrites the summary to `failure` and fails the job. The workflow uploads only the redacted records/gate JSON plus the sanitized summary; generated per-run Experiments, Routes, SearchRun reports, record input manifests, and runner-local audit output remain runner-local.

Downloaded workflow artifacts are checked with `release-self-hosted-evidence-audit --require-parallel-search` before replacing committed release evidence. The audit rejects unexpected raw files or directories, validates `parallel_search_records.json` and `parallel_search_gate.json`, and requires the gate's record-bundle witness to match the records bundle evidence ID and record count. Downloaded audit `artifact_files` names only evidence JSON files, while `source_artifact_files` preserves the full workflow artifact file list including `summary.json`. Operators may also supply `--expected-commit` and `--expected-run-id` so downloaded artifacts from the wrong checkout or workflow run are rejected before adoption.

After audit, `release-self-hosted-evidence-adopt --adopt-parallel-search` is the only supported local adoption path for 0.6 workflow artifacts. It reruns the required passing audit, requires `summary.status: success` and `summary.parallel_search: true`, copies only `parallel_search_records.json` and `parallel_search_gate.json` into `docs/release/evidence`, writes a selected-branch `release_self_hosted_evidence_audit.json` beside them, and immediately verifies the copied directory against that saved audit. The adoption log prints both the audit evidence ID and the post-copy verification ID, so CI/operator logs can prove that copied evidence, not only downloaded artifacts, passed validation. That saved audit records the original workflow identity and source artifact list, but `artifact_files` only names the branch evidence actually copied, so 0.6 and 0.7 evidence can be adopted independently from a combined workflow run without pretending that `summary.json` was copied into release evidence. Saved audit file lists must be sorted, unique, and limited to the allowed release evidence filenames; `source_artifact_files` is mandatory for adopted evidence, must include `summary.json`, and must cover every copied `artifact_files` entry. `summary.json` is valid only in `source_artifact_files`, never in adopted `artifact_files`. The parallel-search branch witness is schema-fixed to `gate_evidence_id`, `passed`, `record_count`, and `records_evidence_id` with the expected evidence ID prefixes; a passing branch must have a positive record count, and any parallel-search branch witness must agree with `summary.parallel_search: true`. If another branch from the same workflow identity has already been adopted, the new adoption preserves and merges that existing branch into the saved audit; if the existing branch came from a different workflow identity, the partial merge is rejected before copying files. Failed or pending evidence files for an unadopted branch may remain visible, but unadopted passing branch evidence is rejected before adoption and during adopted-evidence verification. `release-self-hosted-evidence-verify-adopted --require-parallel-search` can be rerun later; it rereads the adopted release-evidence directory, validates the saved audit evidence ID, requires the current records/gate files to reproduce the audit's branch witness, records the requested verification requirements, expected workflow identity, and SHA-256 of every verified file in the verification evidence, and checks that those verified files match the audit's `artifact_files` before the release evidence can be treated as current. Persisted `release-self-hosted-evidence-verification-v1` JSON is itself reloadable validation evidence: the reader recomputes its `releaseevidenceverify_` content ID, validates exact requirement keys and branch witnesses, and can compare recorded SHA-256 values against the adopted files so stale logs or edited verification reports are rejected.

`release-readiness-status-v1` also treats `0.6.0` as ready only when `parallel_search_gate.json` passes and the adopted self-hosted audit/verification proves the copied parallel-search branch. The current committed readiness status passes with `0.5.1`, `0.6.0`, and `0.7.0` in `ready_versions`. This aggregate status is intentionally stricter than reading the gate file alone.

Status: Released; parent [#258](https://github.com/Tao-pyth/ygo-effect-dsl/issues/258)

Last updated: 2026-07-31

Release note: `0.6.0` is now a released source milestone. The `v0.6.0`
milestone is closed, all v0.6.0 work items are closed, and
`release-readiness-status-v1` records `0.6.0` as ready through adopted
self-hosted parallel-search evidence.

## Objective

package `0.6.0`は、実ocgcoreのfresh Replay隔離と既存の探索結果semanticを維持しながら、Random Search、Beam Search、MCTSをsingle-host bounded process poolへ接続し、CLI/API/Windows desktopで探索時間を実測短縮するstageである。並列化そのものではなく、同一workloadをより短時間で処理し、結果の再現性、障害証跡、resource境界を維持することを完了条件とする。

## Current baseline

package `0.5.0`には`parallel-search-policy-v1`等の独立contract、pool 1/2/4/8/16のfresh Replay stress、memory preflight、Random/Beam/MCTSのsingle-process SearchExecutorが存在する。ただし`0.5.0`時点のSearchExecutorは同期`FrontierAdapter.replay()`を順次呼び出しており、独立parallel contractを実探索runtimeへ直接接続していない。既存[#231](https://github.com/Tao-pyth/ygo-effect-dsl/issues/231)はこの統合を追跡し、2026-07-16に`1.0.0`から本stageへ再割当した。

## In scope

1. logical task、physical Replay、attempt、semantic commitを分離するparallel execution contract。
2. cancellable task-oriented frontier protocolとbounded worker-pool coordinator。
3. Experiment、CLI、Python API、desktopで共有するversion付きpool policy。
4. Randomのdeterministic dispatch window、Beamのlayer parallelism、MCTSのordinal batch update。
5. node/replay/depth budgetとwall-clock deadlineの分離。
6. crash、timeout、retry、cancel、late/duplicate completion、atomic publishのhardening。
7. native stateを保存しないverified Replay prefix cache接続。
8. hardware-aware memory preflight、pool上限、parallel execution telemetry。
9. 三つの代表real-core fixtureと100,000 logical-node workloadによる速度、RSS、決定論校正。
10. Windows desktopのpool選択、実効policy、衝突/resource warning、cancel/recovery表示。

## Out of scope

- native duel handle、Lua state、mutable core stateのprocess間共有またはsnapshot/clone。
- distributed worker、remote queue、複数host scheduling。
- 全探索空間の完全列挙または最適性証明。
- 評価weight変更、統計的枝刈りの既定有効化、探索UIの一般最適化。
- third-party assetの成果物同梱、一般公開distribution、production support。
- license、stable compatibility、upgrade/rollback、security、soak。これらは`1.0.0`に残す。

## Performance gate

同一asset-capable Windows host、同一core/asset lock、同一seed、同一node/replay budgetのwarm runを各profile 5回以上測定する。pool 4のmedian wall timeはpool 1に対して、代表fixture中2件以上で25%以上短縮し、どのfixtureでも10%を超えて悪化してはならない。semantic digest、best Route、Route lineageはpool 1/2/4で一致しなければならない。

この閾値は実装前の希望値ではなくrelease判定である。未達の場合はparallel modeを既定にせず、bottleneck evidenceと後続Issueを残す。`0.6.0`を「探索時間を短縮したrelease」として完了扱いにしない。

`parallel-search-release-gate-v1`と`parallel-search-gate` CLIは、外部self-hosted実測recordsからpool 1/2/4、repeat数、real_core証跡、semantic digest、best Route、lineage、RSS、median wall timeを検証する判定contractである。これはgate判定を機械化するが、100,000 logical-node実測evidenceの代替ではない。

## Compatibility

- 現行Experiment `0.4`、Route DSL `0.1`、Replay/Decision `0.3a`を黙って再解釈しない。
- pool policy省略時は`0.5.0`と同じserial-compatible behaviorを維持する。
- pool 1は旧SearchExecutorのsemantic goldenと一致させる。
- 新fieldがcanonical hashや保存semanticへ影響する場合は、対象contractを独立version upする。
- `max_seconds`終了は`timing_censored`として保存し、pool-size independentな探索結果証明に使用しない。

## Uncertainties requiring evidence

| Question | Why unresolved | Owner |
|---|---|---|
| fresh process Replayで25%短縮可能か | startup、resolver、prefix長の支配率がfixtureごとに異なる | [#260](https://github.com/Tao-pyth/ygo-effect-dsl/issues/260), [#273](https://github.com/Tao-pyth/ygo-effect-dsl/issues/273) |
| Randomの投機windowが有効か | depth-first commit前のReplayがwasteになる可能性がある | [#263](https://github.com/Tao-pyth/ygo-effect-dsl/issues/263) |
| deterministic MCTS batchingが品質を変えないか | serial updateとbatch snapshotでselection pathが変わり得る | [#265](https://github.com/Tao-pyth/ygo-effect-dsl/issues/265) |
| pool自動選択の安全上限 | host memory、prefix、strategy、retryでRSSが変動する | [#269](https://github.com/Tao-pyth/ygo-effect-dsl/issues/269) |
| prefix cacheが実時間を短縮するか | fresh Replay verificationとcontentionでhit利得を相殺し得る | [#268](https://github.com/Tao-pyth/ygo-effect-dsl/issues/268) |
| deadline runをどう比較するか | wall clockはpool、host load、完了順に依存する | [#266](https://github.com/Tao-pyth/ygo-effect-dsl/issues/266) |

## Release boundary

`0.5.1`の検証profile再編を先行させる。`0.6.0`完了後は[#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276)の`0.7.0`研究dashboardが実artifact、terminal preference、Route randomness、独立Replayを接続する。license/distribution/production gateの[#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91)、[#127](https://github.com/Tao-pyth/ygo-effect-dsl/issues/127)、[#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134)は閉じない。
