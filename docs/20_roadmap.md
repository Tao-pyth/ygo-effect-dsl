# Roadmap

Status: Package `0.8.0` Japanese-centered UI and i18n quality source release is current / `1.0.0` production and distribution gate is planned

Last updated: 2026-07-31

## 1. Version model

Package/CLI の現行 release は `0.8.0` であり、正本は `ygo_effect_dsl.version.__version__` である。`0.5.1`、`0.6.0`、`0.7.0`、`0.8.0` は release readiness evidence と GitHub milestone 状態を根拠に、順に source release として昇格した。`0.4.0` は実装 stage として完了したが独立 tag を作らず、累積 `0.5.0` へ収録した。

今後の並びは `1.0.0` production/distribution gate とする。Package version は配布物全体の SemVer、schema/contract version は保存形式と API の互換境界として独立管理する。

| Area | Current version | Position |
|---|---|---|
| Package / CLI | `0.8.0` | 日本語中心 desktop UI と i18n 品質 gate を含む source release |
| Test/release profile | `pytest-profile-*` / `release-readiness-status-v1` | `0.5.1`、`0.6.0`、`0.7.0`、`0.8.0` の ready 状態と昇格根拠を検証 |
| Search | `search-executor-v5` / `parallel-search-release-gate-v1` | `0.6.0` の bounded parallel search と timing witness |
| Windows desktop | `desktop-workflow-v1` / `desktop-bridge-v1` / `desktop-result-view-v1` | committed result dashboard と日本語 UI 品質 stage の対象 |
| Research dashboard | package `0.7.0` | real artifact、terminal preference、opening hand、Replay verification、Top-K/coverage を統合 |
| Desktop UI localization | package `0.8.0` released | 日本語中心 UI、`lang="ja"`、文字化け除去、text catalog 化 |
| Production distribution | package `1.0.0` planned | license、stable compatibility、security、operations、auditable distribution |

Baseline contract index: `0.4`, `0.3b`, `0.3a`, `0.1`, `project-identity-v1`, `scenario-v1`, `ygo-replay-manifest-v1`, `fresh-replay-verification-v1`, `real-deck-qualification-index-v2`, `ocgcore-lua-load-qualification-v1`, `information-policy-v1`, `ygo-state-id-v1`, `evaluation-result-v1`, `search-executor-v5`, `search-frontier-v2`, `search-run-result-v5`, `search-strategy-evidence-v1`, `search-run-report-v1`, `search-run-failure-v2`, `search-artifact-commit-v1`, `random-search-strategy-v1`, `beam-search-strategy-v1`, `mcts-strategy-v1`, `real-core-frontier-v2`, `real-core-frontier-worker-attempt-v1`, `real-core-frontier-worker-failure-v1`, `interruption-support-taxonomy-v1`, `aggregation-v1`, `general-search-benchmark-v1`, `real-core-benchmark-base-routes-v2`, `cache-worker-policy-v2`, `memory-preflight-v2`, `real-core-replay-benchmark-v1`, `real-core-worker-policy-v1`, `real-core-memory-preflight-v1`, `resolver-index-policy-v1`, `ocgcore-platform-contract-v1`, `ocgcore-doctor-v2`.

## 2. Release stages

| Package target | Main purpose | Parent issue | Spec | Completion signal |
|---|---|---|---|---|
| `0.3.0` | real-core/EDOPro Lua qualification | [#131](https://github.com/Tao-pyth/ygo-effect-dsl/issues/131) | [v0.3.0](spec/v0.3.0/00_scope.md) | released source milestone |
| `0.4.0` | Beam/MCTS、PlayerView、interruptions、multiple turns | [#132](https://github.com/Tao-pyth/ygo-effect-dsl/issues/132) | [v0.4.0](spec/v0.4.0/00_scope.md) | `0.5.0` に累積収録済み |
| `0.5.0` | deck-first Windows desktop UI、corpus analytics、job/query/comparison | [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133) | [v0.5.0](spec/v0.5.0/00_scope.md) | released source milestone |
| `0.5.1` | verification profile、test time、CI load、agent output 削減 | [#236](https://github.com/Tao-pyth/ygo-effect-dsl/issues/236) | [v0.5.1](spec/v0.5.1/00_scope.md) | released source milestone |
| `0.6.0` | deterministic node-level parallel search | [#258](https://github.com/Tao-pyth/ygo-effect-dsl/issues/258) | [v0.6.0](spec/v0.6.0/00_scope.md) | released source milestone |
| `0.7.0` | committed result と利用者定義評価を備えた research dashboard | [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276) | [v0.7.0](spec/v0.7.0/00_scope.md) | released source milestone |
| `0.8.0` | 日本人想定ユーザー向け UI/i18n 品質 | [#309](https://github.com/Tao-pyth/ygo-effect-dsl/issues/309) | [v0.8.0](spec/v0.8.0/00_scope.md) | released source milestone |
| `1.0.0` | stable compatibility、license、distribution、security、operations | [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) | [v1.0.0](spec/v1.0.0/00_scope.md) | supported distribution readiness |

## 3. Current release status

`0.8.0` は package/CLI の現行 source release であり、production distribution ではない。一般配布、third-party asset redistribution、long-term artifact retention、security operations は `1.0.0` まで行わない。

`0.5.1`、`0.6.0`、`0.7.0`、`0.8.0` は `docs/release/evidence/release_readiness_status.json` で ready と検証済みであり、対応する GitHub milestone は closed、open issue は 0 件である。`#108` と `#110` は未完の校正・研究課題として `1.0.0` へ移したため、0.5.1 の完了条件には含めない。

`0.8.0` は、`0.7.0` dashboard を日本人想定ユーザーが読める状態へ引き上げる品質 stage として完了した。英語中心 UI、`lang="en"`、fixture や文書の mojibake は利用者品質の阻害要因として release gate で拒否する。

## 4. Release rules

- 新しい strategy や保存形式は専用 contract version を追加する。
- Package version は repository-wide release を示し、schema version は互換境界を示す。
- Real job result は committed artifact だけを正本とし、synthetic/unverified/censored を verified/optimal として表示しない。
- Python 側はカード効果、合法性、timing、chain 処理を推測しない。
- Third-party core/assets は wheel、sdist、executable、CI artifact へ同梱しない。
- Release-facing documentation と UI artifact には、想定ユーザーに合わない言語属性や mojibake を残さない。

## 5. Explicit non-goals

- Python 製カード効果エンジン。
- 任意 deck の完全な最適性証明。
- 完全な対戦 AI。
- 勝率予測。
- 人間向け duel screen。
- General-public binary distribution before `1.0.0`.
