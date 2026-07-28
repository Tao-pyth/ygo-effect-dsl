# Roadmap

Status: Package `0.5.0` Windows desktop analytics source milestone released / `0.5.1`, `0.6.0`, and `0.7.0` source release evidence ready / `0.8.0` Japanese-centered UI and i18n quality planned

Last updated: 2026-07-28

## 1. Version model

Package/CLI の現行 release は `0.5.0`、対応 tag は `v0.5.0` である。`0.4.0` は Search/PlayerView 実装 stage として完了したが独立 tag を作らず、累積 `0.5.0` へ収録した。`0.5.1`、`0.6.0`、`0.7.0` は source release evidence が ready である。ただし package/tag としての現行 release は `0.5.0` のまま維持する。

今後の並びは `0.5.1` maintenance、`0.6.0` parallel-search、`0.7.0` research-dashboard、`0.8.0` Japanese-centered UI/i18n quality、`1.0.0` production/distribution gate とする。Package version は配布物全体の SemVer、schema/contract version は保存形式と API の互換境界として独立管理する。

| Area | Current version | Position |
|---|---|---|
| Package / CLI | `0.5.0` | real-core search、PlayerView、Windows desktop、corpus analytics を含む source milestone |
| Test/release profile | `pytest-profile-*` / `release-readiness-status-v1` | `0.5.1`、`0.6.0`、`0.7.0` の source release evidence ready 状態を検証 |
| Search | `search-executor-v5` / `parallel-search-release-gate-v1` | `0.6.0` の bounded parallel search と timing witness |
| Windows desktop | `desktop-workflow-v1` / `desktop-bridge-v1` / `desktop-result-view-v1` | `0.7.0` の committed result dashboard と `0.8.0` の日本語 UI 品質 stage の対象 |
| Research dashboard | package `0.7.0` ready | real artifact、terminal preference、opening hand、Replay verification、Top-K/coverage を統合 |
| Desktop UI localization | package `0.8.0` planned | 日本語中心 UI、`lang="ja"`、文字化け除去、text catalog 化 |
| Production distribution | package `1.0.0` planned | license、stable compatibility、security、operations、auditable distribution |

詳細な stage 索引は [release stage index](spec/00_release_stage_index.md) を正本とする。

## 2. Release stages

| Package target | Main purpose | Parent issue | Spec | Completion signal |
|---|---|---|---|---|
| `0.3.0` | real-core/EDOPro Lua qualification | [#131](https://github.com/Tao-pyth/ygo-effect-dsl/issues/131) | [v0.3.0](spec/v0.3.0/00_scope.md) | clean bootstrap、real deck qualification、fail-close |
| `0.4.0` | Beam/MCTS、PlayerView、interruptions、multiple turns | [#132](https://github.com/Tao-pyth/ygo-effect-dsl/issues/132) | [v0.4.0](spec/v0.4.0/00_scope.md) | `0.5.0` に累積収録済み |
| `0.5.0` | deck-first Windows desktop UI、corpus analytics、job/query/comparison | [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133) | [v0.5.0](spec/v0.5.0/00_scope.md) | released source milestone |
| `0.5.1` | verification profile、test time、CI load、agent output 削減 | [#236](https://github.com/Tao-pyth/ygo-effect-dsl/issues/236) | [v0.5.1](spec/v0.5.1/00_scope.md) | source release evidence ready |
| `0.6.0` | deterministic node-level parallel search | [#258](https://github.com/Tao-pyth/ygo-effect-dsl/issues/258) | [v0.6.0](spec/v0.6.0/00_scope.md) | source release evidence ready |
| `0.7.0` | committed result と利用者定義評価を備えた research dashboard | [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276) | [v0.7.0](spec/v0.7.0/00_scope.md) | source release evidence ready |
| `0.8.0` | 日本人想定ユーザー向け UI/i18n 品質 | TBD | [v0.8.0](spec/v0.8.0/00_scope.md) | default UI 日本語化、`lang="ja"`、文字化け不在 |
| `1.0.0` | stable compatibility、license、distribution、security、operations | [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) | [v1.0.0](spec/v1.0.0/00_scope.md) | supported distribution readiness |

## 3. Current release status

`0.5.0` は package/CLI の現行 release であり、production distribution ではない。一般配布、third-party asset redistribution、long-term artifact retention、security operations は `1.0.0` まで行わない。

`0.5.1`、`0.6.0`、`0.7.0` は release readiness evidence 上 ready として扱う。これらは source release evidence の準備完了を意味し、package version が自動的に `0.7.0` へ進んだことは意味しない。

`0.8.0` は、`0.7.0` dashboard が日本人想定ユーザーに読める状態でない問題を扱う。英語中心 UI、`lang="en"`、fixture や文書の mojibake は利用者品質の阻害要因であり、`1.0.0` へ延期しない。

## 4. 0.8.0 planned path

`0.8.0` では desktop UI の表示言語を日本語中心に統一する。HTML は `lang="ja"` を宣言し、静的 copy、aria-label、placeholder、dialog、status、toast、job/result 表示を日本語化する。動的文言は text catalog に集約し、将来 locale switch UI を追加できる形にする。

文字化け除去は UI fixture だけでなく release-facing docs も対象にする。既知の mojibake pattern は tests で拒否し、UTF-8 前提で保存する。英語 locale の完全整備、多言語切替 UI、Card text 翻訳、production distribution は `0.8.0` の範囲に含めない。

## 5. Release rules

- 新しい strategy や保存形式は専用 contract version を追加する。
- Package version は repository-wide release を示し、schema version は互換境界を示す。
- Real job result は committed artifact だけを正本とし、synthetic/unverified/censored を verified/optimal として表示しない。
- Python 側はカード効果、合法性、timing、chain 処理を推測しない。
- Third-party core/assets は wheel、sdist、executable、CI artifact へ同梱しない。
- Release-facing documentation と UI artifact には、想定ユーザーに合わない言語属性や mojibake を残さない。

## 6. Explicit non-goals

- Python 製カード効果エンジン。
- 任意 deck の完全な最適性証明。
- 完全な対戦 AI。
- 勝率予測。
- 人間向け duel screen。
- General-public binary distribution before `1.0.0`.
