# ygo-effect-dsl

`ygo-effect-dsl` は、Yu-Gi-Oh! の展開ルート探索を再現可能に記録し、ocgcore / EDOPro Lua が実行した Action 履歴、途中盤面、Peak Board、評価、妨害分岐を Route Information DSL として保存・比較するための Python プロジェクトです。

## Name And Scope

Repository / distribution name は `ygo-effect-dsl`、Python import は `ygo_effect_dsl`、CLI は `ygo-effect-dsl` です。製品説明は **Reproducible Yu-Gi-Oh! route search and Route Information DSL** です。

現行 DSL は **Route Information DSL (Route DSL)** です。Route DSL はカード効果を記述する言語ではなく、ocgcore / EDOPro Lua が実行したルート、Action 履歴、評価、証跡を保存・交換するデータ契約です。旧 `dsl` package と `ingest / transform / validate / analyze` は legacy card-text artifact pipeline であり、Search engine と Route DSL の入力正本ではありません。

## Version And Compatibility

現在の package / CLI release は **`0.7.0`** です。`0.5.1`、`0.6.0`、`0.7.0` は release readiness evidence と GitHub milestone 状態を根拠に、順に source release として昇格しました。`0.8.0` は日本人想定ユーザー向け UI/i18n 品質 stage、`1.0.0` は production/distribution gate です。

Package version と機能契約の schema / contract version は独立管理します。Package version は配布物全体の SemVer、schema version は保存形式または API の互換境界です。たとえば Experiment `0.4` と package `0.7.0` は別の軸です。

| Area | Current version | Position |
|---|---|---|
| Package / CLI | `0.7.0` | parallel search と evidence-driven research dashboard を含む source release |
| Project identity | `project-identity-v1` | repository、import、CLI、製品説明の安定名 |
| Historical baseline | `0.3.0` | real-core / EDOPro Lua qualified source milestone |
| Experiment / scenario | `0.4` / `scenario-v1` | 現行 scenario/search 入力。`0.3b` は実行互換、`0.3a` は読み取り・migration 入力 |
| Decision / Action / Replay | `0.3a` / `ygo-replay-manifest-v1` / `fresh-replay-verification-v1` | request、選択、再生の基礎契約 |
| Route DSL | `0.1` | 最良 Route の交換形式。正規化出力は `route-normalization-v2` |
| Search executor | `search-executor-v5` / `search-frontier-v2` / `search-run-result-v5` / `search-strategy-evidence-v1` / `search-run-report-v1` / `search-run-failure-v2` / `search-artifact-commit-v1` | Random、Beam、MCTS、parallel search の共通実行契約 |
| Search strategies | `random-search-strategy-v1` / `beam-search-strategy-v1` / `mcts-strategy-v1` | strategy 別の互換境界 |
| Parallel search | `parallel-search-release-records-v1` / `parallel-search-release-gate-v1` | `0.6.0` の bounded pool 実行と self-hosted timing evidence |
| Evaluation | `evaluation-result-v1` / `terminal-board-projection-v1` / `terminal-preference-profile-v1` / `terminal-preference-evaluation-v1` | terminal board と user preference を分離した評価契約 |
| Information boundary | `information-policy-v1` | 探索・評価が参照できる情報と access 証跡 |
| State identity | `ygo-state-id-v1` | exact dedup と状態互換境界 |
| Real-core frontier | `real-core-frontier-v2` / `real-core-frontier-worker-attempt-v1` / `real-core-frontier-worker-failure-v1` | fresh worker Replay、retry、quarantine evidence |
| Qualification | `real-deck-qualification-index-v2` / `ocgcore-lua-load-qualification-v1` / `ocgcore-platform-contract-v1` / `ocgcore-doctor-v2` | real deck、Lua load、platform doctor の source milestone evidence |
| Interruption | `interruption-support-taxonomy-v1` | core 提示 candidate だけを使う妨害分類 |
| Storage / analytics | `aggregation-v1` / `analytics-query-contract-v1` / `analytics-comparison-contract-v1` / `parquet-lifecycle-contract-v1` / `analytics-export-contract-v1` | snapshot query、cohort、export parity、Parquet lifecycle |
| Corpus / jobs | `corpus-manifest-v1` / `job-state-machine-v1` / `job-catalog-v2` | provenance、dedup、lease、cancel、retry、atomic artifact commit |
| Windows desktop | `desktop-workflow-v1` / `desktop-bridge-v1` / `desktop-search-worker-v1` / `desktop-virtual-table-v1` / `desktop-result-view-v1` | deck-first dashboard、real-core job、committed result hydration、Replay verification、Top-K/candidate drill-down |
| Research dashboard | `research-dashboard-release-gate-v1` / `research-dashboard-qualification-v1` | `0.7.0` の committed artifact、preference profile、opening hand、coverage、fresh Replay、cohort analytics の gate |
| Benchmark / policy | `general-search-benchmark-v1` / `real-core-benchmark-base-routes-v2` / `cache-worker-policy-v2` / `memory-preflight-v2` | representative benchmark と memory/cache policy |
| Real Replay policy | `real-core-replay-benchmark-v1` / `real-core-worker-policy-v1` / `real-core-memory-preflight-v1` | fresh Replay throughput/RSS と worker policy |
| Resolver index policy | `resolver-index-policy-v1` | checked process-local script index policy |

## Release Status

`0.7.0` は package / CLI の現行 source release ですが、production distribution ではありません。一般配布、third-party asset redistribution、long-term artifact retention、security operations は `1.0.0` まで行いません。

`0.5.1`、`0.6.0`、`0.7.0` の ready 状態は `docs/release/evidence/release_readiness_status.json` で検証します。`#108` と `#110` は未完の校正・研究課題として `1.0.0` へ移しており、`0.5.1` の完了条件には含めません。

## Principles

- EDOPro Lua と ocgcore をカード効果・合法性・chain 処理の真実源にする。
- Python は Bridge、Replay、Search、Evaluation、実験、統計を担当する。
- Python 側でカード効果、合法性、timing を推測しない。
- Replay できないルートを正式な探索結果として扱わない。
- Real job result は committed artifact だけを正本にする。
- Third-party core/assets は wheel、sdist、executable、CI artifact へ同梱しない。

```text
EDOPro Lua + card data
  -> ocgcore
  -> Bridge / DecisionRequest
  -> Action / Replay
  -> Search / Evaluation
  -> Route DSL
  -> compare / aggregate / report / re-evaluate
```

## Setup

```bash
pip install -e .
python -m ygo_effect_dsl --version
python -c "import ygo_effect_dsl; print(ygo_effect_dsl.__file__)"
```

Parquet analytics を使う場合:

```bash
pip install -e ".[analytics]"
```

## Common Commands

```bash
python -m ygo_effect_dsl prototype-run examples/prototype/fixed_hand_normal_summon.yaml --out data/prototype/route.yaml
python -m ygo_effect_dsl prototype-verify examples/prototype/fixed_hand_normal_summon.yaml data/prototype/route.yaml
python -m ygo_effect_dsl experiment-search examples/experiments/general_search_inline.yaml --out data/prototype/general-search.route.yaml --search-report data/prototype/general-search.report.json
python -m ygo_effect_dsl experiment-replay examples/experiments/general_search_inline.yaml data/prototype/general-search.route.yaml --verification-report data/prototype/general-search.replay-verification.json
```

Release evidence:

```bash
python -m ygo_effect_dsl test-profile-plan --repo-root . --out docs/release/evidence/pytest_profile_plan.json
python -m ygo_effect_dsl test-profile-gate --plan docs/release/evidence/pytest_profile_plan.json --suite docs/release/evidence/pytest_profile_suite.json --summary docs/release/evidence/pytest_profile_summary.json --out docs/release/evidence/pytest_profile_gate.json
python -m ygo_effect_dsl parallel-search-gate --records docs/release/evidence/parallel_search_records_pending.json --source-evidence docs/search/evidence/real_core_parallel_stress.json --source-evidence docs/adr/evidence/0105_general_search_100k.json --out docs/release/evidence/parallel_search_gate.json
python -m ygo_effect_dsl research-dashboard-gate --repo-root . --qualification docs/release/evidence/research_dashboard_qualification.json --out docs/release/evidence/research_dashboard_gate.json
python -m ygo_effect_dsl release-readiness-status --evidence-dir docs/release/evidence --out docs/release/evidence/release_readiness_status.json
python -m ygo_effect_dsl release-readiness-verify --evidence-dir docs/release/evidence --status docs/release/evidence/release_readiness_status.json --require-passed
python -m ygo_effect_dsl release-self-hosted-evidence-audit --artifact-dir D:/qualification/release-self-hosted-evidence --expected-commit <commit-sha> --expected-run-id <github-run-id> --require-parallel-search --require-research-dashboard --out D:/qualification/release-self-hosted-evidence/audit.json
python -m ygo_effect_dsl release-self-hosted-evidence-adopt --artifact-dir D:/qualification/release-self-hosted-evidence --expected-commit <commit-sha> --expected-run-id <github-run-id> --adopt-parallel-search --adopt-research-dashboard
python -m ygo_effect_dsl.release_governance --check
```

## Current And Next Stages

`0.5.1` reduced verification cost without weakening release confidence. `0.6.0` connected deterministic node-level parallel search and adopted self-hosted timing evidence. `0.7.0` replaced synthetic result views with committed artifacts, terminal preferences, Route randomness/ranking, fresh Replay verification, Top-K/coverage, and conditioned cohort analytics.

`0.8.0` makes the desktop UI Japanese-centered: visible copy defaults to Japanese, HTML declares `lang="ja"`, UI/documentation mojibake is rejected, and strings are centralized for future locale switching. `1.0.0` remains the stable compatibility, licensing, distribution, security, and operations gate.

## References

- [Roadmap](docs/20_roadmap.md)
- [Release stage index](docs/spec/00_release_stage_index.md)
- [Versioning and release policy](docs/release/00_versioning.md)
- [0.5.1 verification efficiency scope](docs/spec/v0.5.1/00_scope.md)
- [0.6.0 deterministic parallel search scope](docs/spec/v0.6.0/00_scope.md)
- [0.7.0 evidence-driven research dashboard scope](docs/spec/v0.7.0/00_scope.md)
- [0.8.0 Japanese UI and i18n quality scope](docs/spec/v0.8.0/00_scope.md)
- [1.0.0 production distribution scope](docs/spec/v1.0.0/00_scope.md)
