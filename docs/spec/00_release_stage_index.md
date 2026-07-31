# Release Stage Index: 0.3.0 to 1.0.0

Status: Package `0.8.0` released; `0.9.0` planned; `1.0.0` planned

Last updated: 2026-07-31

## Purpose

本書は package `0.3.0` から `1.0.0` までの stage、依存関係、責任境界、親 Issue を一つの索引にする。現行の package/CLI version は `0.8.0` であり、正本は `ygo_effect_dsl.version.__version__` である。`0.5.1`、`0.6.0`、`0.7.0`、`0.8.0` は release readiness evidence と GitHub milestone 状態を根拠に、順に released とする。

`0.8.0` は日本人想定ユーザー向けの desktop UI/i18n 品質 stage として完了した。`0.9.0` は終端評価ルールとカード選択 UX の planned stage であり、`1.0.0` は production/distribution gate である。

## Stage dependency

```text
0.3.0 real-core and EDOPro Lua qualified baseline
  -> 0.4.0 search breadth and private-view safety
      -> 0.5.0 corpus analytics and desktop UI
          -> 0.5.1 verification efficiency and compatible maintenance
              -> 0.6.0 deterministic parallel search and measured latency reduction
                  -> 0.7.0 evidence-driven research dashboard and preference-aware results
                      -> 0.8.0 Japanese-centered desktop UI and localization quality
                          -> 0.9.0 terminal preference and card selection UX
                              -> 1.0.0 stable distribution and operations
```

| Stage | Parent | Input | Main responsibility | Exit condition |
|---|---|---|---|---|
| `0.3.0` | [#131](https://github.com/Tao-pyth/ygo-effect-dsl/issues/131) | Random Search, real-core frontier, asset lock | real-core/EDOPro Lua qualification | released source milestone |
| `0.4.0` | [#132](https://github.com/Tao-pyth/ygo-effect-dsl/issues/132) | `0.3.0` qualified core baseline | Beam/MCTS, PlayerView, interruptions, multiple turns | superseded implementation stage included in `0.5.0` |
| `0.5.0` | [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133) | `0.4.0` implementation evidence | corpus, jobs, query/comparison, desktop UI | released source milestone |
| `0.5.1` | [#236](https://github.com/Tao-pyth/ygo-effect-dsl/issues/236) | released `0.5.0` plus verification profile | test profile, fixture consolidation, quieter evidence | released source milestone without weakening regression coverage |
| `0.6.0` | [#258](https://github.com/Tao-pyth/ygo-effect-dsl/issues/258) | serial SearchExecutor and `0.5.1` verification profile | bounded process pool and parallel strategy execution | released source milestone with semantic determinism and timing witnesses |
| `0.7.0` | [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276) | bounded Search and desktop artifact publication | real result hydration, terminal preferences, Route randomness, Replay verification, Top-K/coverage | released source milestone with truthful committed artifacts |
| `0.8.0` | [#309](https://github.com/Tao-pyth/ygo-effect-dsl/issues/309) | `0.7.0` research dashboard | Japanese-centered UI/i18n quality, `lang="ja"`, mojibake removal | released source milestone with `japanese-i18n-release-gate-v1` evidence |
| `0.9.0` | [#324](https://github.com/Tao-pyth/ygo-effect-dsl/issues/324) | `0.8.0` localized desktop UI | deck-scoped terminal evaluation profiles, deck-card picker, deck metadata, result explainability, fail-closed presentation source handling | planned source milestone with issue-backed UX scope |
| `1.0.0` | [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) | qualified runtime, analytics, and localized desktop UI | stable compatibility, license, distribution, security, operations | auditable supported distribution and operations readiness |

## Version allocation rules

1. Package version は利用者へ提示する repository-wide release を表す。
2. Schema/contract version は保存形式、API、semantic boundary を表す。
3. Package milestone 開始時に schema 番号を自動的には上げない。
4. UI 文言、言語属性、fixture 表示、文書文字化けが利用者体験を変える場合は package milestone に割り当てる。
5. `0.8.0` の既定 UI は日本語中心とするが、英語 locale の完全提供や locale switch UI は必須にしない。
6. `0.9.0` は終端評価ルールの分かりやすさ、デッキ別プロファイル管理、デッキ内カード選択、デッキ metadata、結果説明性 UX を扱う minor UX release とし、内部 `card_code` と hash identity 契約は維持する。
7. `1.0.0` は production/distribution gate であり、日本語化や終端評価 UI 改善をそこまで延期しない。

## Cross-stage mandatory gates

- Python 側でカード効果、合法性、タイミングを推測しない。
- Runtime resolver は実行時に network install を行わない。
- Asset/core mismatch は worker 起動前に fail-close する。
- Node/replay/depth budget の semantic 結果は pool size、worker completion order、retry に依存させない。
- Real job result は committed artifact だけを表示し、synthetic/unverified/censored/unknown を verified/optimal として扱わない。
- UI は想定ユーザーに合わせた言語属性と文言を持ち、文字化けを release-facing artifact に残さない。
- Third-party core/assets は監査なしに wheel、sdist、executable、CI artifact へ同梱しない。

## Detailed specifications

- [0.3.0 scope](v0.3.0/00_scope.md)
- [0.3.0 real-core integration](v0.3.0/10_real_core_integration.md)
- [0.3.0 work breakdown](v0.3.0/20_work_breakdown.md)
- [0.3.0 acceptance](v0.3.0/30_acceptance.md)
- [0.4.0 scope](v0.4.0/00_scope.md)
- [0.4.0 contracts](v0.4.0/10_search_and_player_view_contracts.md)
- [0.4.0 work breakdown and acceptance](v0.4.0/20_work_breakdown_and_acceptance.md)
- [0.5.0 scope](v0.5.0/00_scope.md)
- [0.5.0 analytics contracts](v0.5.0/10_analytics_contracts.md)
- [0.5.0 desktop UI requirements](v0.5.0/15_desktop_ui_requirements.md)
- [0.5.0 work breakdown and acceptance](v0.5.0/20_work_breakdown_and_acceptance.md)
- [0.5.1 verification efficiency scope](v0.5.1/00_scope.md)
- [0.6.0 deterministic parallel search scope](v0.6.0/00_scope.md)
- [0.6.0 parallel execution contracts](v0.6.0/10_parallel_execution_contracts.md)
- [0.6.0 work breakdown and acceptance](v0.6.0/20_work_breakdown_and_acceptance.md)
- [0.7.0 evidence-driven research dashboard scope](v0.7.0/00_scope.md)
- [0.7.0 evaluation, randomness, and result contracts](v0.7.0/10_evaluation_randomness_and_result_contracts.md)
- [0.7.0 research dashboard workflow](v0.7.0/15_research_dashboard_workflow.md)
- [0.7.0 work breakdown and acceptance](v0.7.0/20_work_breakdown_and_acceptance.md)
- [0.8.0 Japanese UI and i18n quality scope](v0.8.0/00_scope.md)
- [0.9.0 terminal preference and card selection UX scope](v0.9.0/00_scope.md)
- [1.0.0 scope](v1.0.0/00_scope.md)
- [1.0.0 production contracts](v1.0.0/10_production_distribution_contracts.md)
- [1.0.0 work breakdown and acceptance](v1.0.0/20_work_breakdown_and_acceptance.md)
- [1.0.0 support matrix](v1.0.0/30_support_matrix.md)
- [Validation register](00_validation_register.md)
