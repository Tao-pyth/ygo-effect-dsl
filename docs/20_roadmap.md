# Roadmap

Status: Package `0.2.0` released / `0.3.0` real-core qualification in progress

Last updated: 2026-07-14

## 1. Version model

package/CLIの現行releaseは`0.2.0`、対応tagは`v0.2.0`である。`0.3.0`から`1.0.0`は将来のpackage milestoneであり、実装済みversionではない。package versionは配布物全体のSemVer、schema/contract versionは保存形式とAPIの互換境界として独立管理する。Experiment `0.4`をpackage `0.4.0`へ機械的に揃えない。

| 領域 | 現行version | 現在の位置付け |
|---|---|---|
| Package / CLI | `0.2.0` | Pythonエンジニア向けsource milestone |
| Project identity | `project-identity-v1` | repository、Python import、CLI、製品説明の安定名 |
| Experiment | `0.4` | 現行scenario/search入力。`0.3b`は実行互換、`0.3a`は読み取り・migration入力 |
| Scenario | `scenario-v1` / `scenario-manifest-v1` / `scenario-preflight-v1` | fixed/inline/YDK、初手、asset/card/script事前検査 |
| Decision / Action / Replay | `0.3a` / `ygo-replay-manifest-v1` / `fresh-replay-verification-v1` | core request、選択、fresh Replayと成功証跡の基礎契約 |
| Route DSL | `0.1` / `route-normalization-v2` | 探索Routeの交換・再生形式 |
| Information boundary | `information-policy-v1` / `information-audit-v1` | 探索・評価の参照可能情報とaccess証跡 |
| State identity | `ygo-state-id-v1` / `ygo-rule-state-v1` / `ygo-visibility-state-v1` | exact dedup、ルール状態、可視性状態 |
| Evaluation | `evaluation-result-v1` / `score-breakdown-v1` / `route-resource-consumption-v1` | 成功、盤面score、資源消費 |
| Search | `search-executor-v4` / `search-frontier-v2` / `search-run-result-v4` / `search-run-report-v1` / `search-run-failure-v2` / `search-artifact-commit-v1` / `random-search-strategy-v1` | state completeness、structured failure、atomic commit付きRandom Searchのみ実動。Beam/MCTSは未実装 |
| Real core | `real-core-frontier-v2` / `real-core-worker-failure-v1` / `real-core-frontier-worker-attempt-v1` / `real-core-frontier-worker-failure-v1` | ocgcore API 11.0のfresh worker Replay、state completeness、retry/quarantine evidence |
| Core bootstrap qualification | `ocgcore-clean-bootstrap-qualification-v1` | 空root・再実行・build/download中断復旧の5 build local evidence。再現buildは#171 |
| Real-deck qualification | `real-deck-qualification-index-v1` | 外部short/long/grave-banish deckの反復証跡とsanitized index |
| Lua load qualification | `ocgcore-lua-load-qualification-v1` | official 12,702 scriptのresolver/native load証跡。CDB欠落120件はfail-close |
| Specified interruption | `core-interruption-candidate-policy-v1` / `interruption-support-taxonomy-v1` | core提示candidateだけを使う妨害分岐 |
| Storage / aggregation | `raw-event-log-v1` / `run-catalog-v2` / `aggregation-v1` | JSONL、run catalog、optional Parquet集計 |
| Runtime lock | `ocgcore-v11.0-win-x64-msvc-v1` | commit/tree/API/build入力を固定 |
| Asset lock | `ocgcore-assets-202504-v1` | CardScripts/BabelCDBのcommit/tree/file hashを固定 |
| Benchmark policy | `general-search-benchmark-v1` / `cache-worker-policy-v2` / `memory-preflight-v2` | logical workload基準。実worker校正は未完了 |

versionの詳細正本は[release stage index](spec/00_release_stage_index.md)、未確定事項は[validation register](spec/00_validation_register.md)とする。

## 2. Implemented baseline

`0.2.0`には次が存在する。

- project-owned ocgcore/CardScripts/BabelCDB bootstrap、hash検証、runtime network禁止
- official CardScripts 12,702件のfresh-worker native load、helper順序、resolver cache同値性のlocal qualification
- ocgcore API 11.0のlifecycle、callback、Message decode、Action response、State query
- Experiment `0.4`のinline/YDK、fixed/random/conditional hand、manifest、preflight
- `RealCoreFrontierAdapter`、決定論的Random Search、budget、STOP_LINE、best Route tie-break
- 指定妨害候補とsupport taxonomyの基礎契約
- Route DSL出力とfresh Replay、JSONL/catalog/optional Parquet evidence

2026-07-14に既存lock済みassetで10 nodeの`experiment-search`とbest Routeの`experiment-replay`を実行し、実ocgcore/EDOPro Luaのend-to-end動作を確認した。同日に空root、再実行、build/runtime partial、独立root、download partialの5 build clean-bootstrap qualificationも完了した。ただしSearch/Replayは単一inline fixtureのlocal smokeであり、任意deck一般性、未知Message形状、10万node実worker性能を保証しない。single-sessionのDLL hash一致をcross-host再現buildへ一般化せず、#171を維持する。

## 3. Release stages

依存順は`0.3.0 → 0.4.0 → 0.5.0 → 1.0.0`とする。後続stageは前段のrelease gateを弱めてはならない。

| Package目標 | 主目的 | 親Issue | 詳細spec | 完了判定の要点 |
|---|---|---|---|---|
| `0.3.0` | 実ocgcore/EDOPro Lua統合と任意deck・性能のqualification | [#131](https://github.com/Tao-pyth/ygo-effect-dsl/issues/131) | [v0.3.0](spec/v0.3.0/00_scope.md) | clean bootstrap、3 real deck、fail-close、実worker 10万node、決定性 |
| `0.4.0` | Beam/MCTS、PlayerView、複数妨害、後攻・複数turn | [#132](https://github.com/Tao-pyth/ygo-effect-dsl/issues/132) | [v0.4.0](spec/v0.4.0/00_scope.md) | strategy適合、private情報非漏洩、lineage相互検証 |
| `0.5.0` | deck-first Windows desktop UI、大規模corpus、比較API、統計、長時間job | [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133) | [v0.5.0](spec/v0.5.0/00_scope.md) | deckから探索実行、card detail、job復旧、10万run/100万row、CLI/API/UI一致 |
| `1.0.0` | stable compatibility、license、配布、security、運用 | [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) | [v1.0.0](spec/v1.0.0/00_scope.md) | 法務承認、再現build、upgrade/rollback、soak、release provenance |

## 4. Immediate priority: real ocgcore / EDOPro Lua

次の作業順を`0.3.0`のcritical pathとする。

1. [#135](https://github.com/Tao-pyth/ygo-effect-dsl/issues/135)でsupported platform/toolchainを確定する。
2. [#136](https://github.com/Tao-pyth/ygo-effect-dsl/issues/136)で空cacheからocgcoreを取得・build・verifyし、5 build local qualificationを完了した。
3. [#137](https://github.com/Tao-pyth/ygo-effect-dsl/issues/137)でBabelCDBのtag/固定commit差異を解決し、asset clean bootstrapを証明する。
4. [#140](https://github.com/Tao-pyth/ygo-effect-dsl/issues/140)と[#141](https://github.com/Tao-pyth/ygo-effect-dsl/issues/141)でLua/Message/Decision境界をfail-close検証する。
5. [#139](https://github.com/Tao-pyth/ygo-effect-dsl/issues/139)で短展開・長展開・墓地/除外またはchain多発の3 deckをpreflightからReplayまで通す。
6. [#142](https://github.com/Tao-pyth/ygo-effect-dsl/issues/142)、[#105](https://github.com/Tao-pyth/ygo-effect-dsl/issues/105)、[#128](https://github.com/Tao-pyth/ygo-effect-dsl/issues/128)でworker障害と10万node実測を完了する。
7. [#138](https://github.com/Tao-pyth/ygo-effect-dsl/issues/138)と[#143](https://github.com/Tao-pyth/ygo-effect-dsl/issues/143)でself-hosted smokeと利用手順を固定する。
8. [#144](https://github.com/Tao-pyth/ygo-effect-dsl/issues/144)で測定結果からcontract versionとdefault policyを決める。

asset lock、第三者asset、default performance policyは、対応する検証Issueとreviewを経ずに変更しない。upstream version変更時だけ再実行する[#117](https://github.com/Tao-pyth/ygo-effect-dsl/issues/117)は関連監査であり、通常の`0.3.0`完了条件には含めない。

## 5. Release rules

- 新しいstrategyは専用contract versionを追加する。既存schemaの必須fieldや意味を変える場合だけschemaをversion upする。
- Pythonはカード効果、合法性、timing、chain処理を推測しない。真実源は固定したocgcore/EDOPro Luaとする。
- unknown Message、candidate、Lua、asset不一致、Replay divergenceはfail-closeする。
- native duel handle/Lua stateをcacheやprocess間で共有しない。cache hitでもfresh Replayする。
- third-party core/assetsをwheel、sdist、executable、CI artifactへ同梱しない。
- `#91`完了前に一般公開distributionを行わない。
- 各releaseは全test、必要なmanual/self-hosted evidence、commit、push、PR、CI、merge、`main`同期、tag/changelog整合を完了してから宣言する。

## 6. Explicit non-goals

- Python製カード効果エンジン
- 全ルート完全列挙または完全な相手AI
- 勝率予測
- オンライン対戦クライアント
- third-party assetの無審査配布
- 実測根拠のないnative snapshot/cloneまたはdistributed worker導入
