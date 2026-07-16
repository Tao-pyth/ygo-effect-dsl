# Package 0.7.0 Scope: Evidence-Driven Research Dashboard

Status: Planned; parent [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276)

Last updated: 2026-07-16

## Objective

package `0.7.0`は、Windows desktopを固定profileの探索launcherから、実ocgcore探索の入力、評価、結果、再生、比較を監査できる研究dashboardへ昇格するstageである。`0.6.0`のbounded parallel Searchを前提に、実artifactだけを表示し、カード位置別terminal preferenceとRoute gameplay randomnessをversion付き成果物へ組み込み、最良Routeの意味と探索範囲を利用者が検証できることを完了条件とする。

## Current baseline

package `0.5.0`にはdeck catalog、YDK import、card detail、analytics、実preflight、SQLite job、real-core Search worker、Route/SearchRun atomic publicationが存在する。Experiment `0.4`はfixed/random/conditional hand、starting player、turn limit、version付きevaluator/success predicateを表現できる。ただしdesktop search composerは先攻、seeded random 5枚、turn limit 2、board-count系evaluatorを固定し、inline registration buttonと一部inputは未接続である。

最重要の欠落は、real jobが成功してもresult dialogが`route_fixture_5b7a2c10`等の固定synthetic値を開く点である。`job.status`はcommit済みartifact metadataを返すが、rendererは`best-route.yaml`と`search-report.json`を取得・検証・描画していない。fresh Replay CLIは存在するが、desktopから独立verification jobとして起動・確認できない。

## In scope

1. canonical terminal-board projectionとlocation/position/count predicate。
2. immutable、content-addressed terminal preference profileとlocal catalog。
3. base scoreと分離した位置別signed bonus/penalty、matched-instance score breakdown。
4. profileをExperiment、CLI、API、desktop、Route/SearchRun/Replayへ結ぶidentity。
5. ocgcore/EDOPro由来のgameplay randomness taxonomy、event、reliability、unknown evidence。
6. success、terminal preference、reliabilityを使うversion付きstable ranking。
7. verified job-artifact read serviceと、fixed synthetic値を使わないreal result view。
8. Route Action、terminal board、score、termination、best-observed/coverage表示。
9. conditional hand、認定済みevaluator/success preset、inline deck、指定妨害のdesktop input parity。
10. Search workerから独立したfresh Replay verification jobと差分artifact。
11. Top-K、diversity、candidate別node、unexplored/pruned/failed/censored evidence。
12. conditioned/random/fixed cohortを分離するdeck/run statisticsとexport parity。
13. bounded frontier exhaustion、coverage certificate、logical checkpoint/resume、adaptive budget。
14. Neuron URL/デッキコードの公式access、規約、認証、安定性のresearch decision。
15. real-core end-to-end、migration、security、redaction、accessibility、responsive、resource qualification。

## Product defaults

- UI presetは先攻の最初の盤面構築とする。starting playerとturn countを直近の一般入力にはしない。
- 終了はlegal `STOP_LINE`、`END_TURN`、成功条件、budget、frontier exhaustion、duel terminalを区別する。
- evaluator、success predicate、rankingは認定済みversion付きpresetを使用し、rendererから任意codeを実行しない。
- 結果はcoverage証明がない限り`best observed`と表示する。
- gameplay randomness不明は`unknown`であり、非randomとして優遇しない。
- node上限なしmodeは提供せず、長時間探索にもhard resource limitを課す。

## Out of scope

- 後攻盤面入力、相手盤面editor、相手AI、全合法相手手探索。
- 複数turnリレー、対局完走、勝率予測、online duel client。
- native ocgcore duel handle/Lua state snapshot、process間共有、distributed worker。
- Pythonによるカード効果、合法性、timing、random probabilityの推測。
- 非公式Neuron scraping、credential収集、third-party asset同梱。
- public distribution、stable compatibility、security/operations support。これらは`1.0.0`に残す。

## Dependency order

```text
0.6.0 deterministic bounded parallel Search
  -> #277-#282 contracts
      -> #283-#293 backend and search evidence
          -> #294-#302 desktop and analytics
              -> #303 research decision + #304-#305 qualification
                  -> #306 source release gate
```

result truthfulnessの[#289](https://github.com/Tao-pyth/ygo-effect-dsl/issues/289)、[#294](https://github.com/Tao-pyth/ygo-effect-dsl/issues/294)はUI受入の最優先である。profile実装はterminal projection、randomness rankingはauthoritative event契約、desktop表示はtyped artifact serviceを先行条件とする。parallel executionの実装詳細を本stageで再定義しない。

## Uncertainties requiring evidence

| Question | Policy | Owner |
|---|---|---|
| どのState fieldでset/face-downを安定投影できるか | core queryとcard instance evidenceで検証し、推測しない | [#277](https://github.com/Tao-pyth/ygo-effect-dsl/issues/277), [#305](https://github.com/Tao-pyth/ygo-effect-dsl/issues/305) |
| random selectionと通常drawをどこまで直接検出できるか | direct trace/message/Action evidenceのあるcategoryだけcompleteとする | [#279](https://github.com/Tao-pyth/ygo-effect-dsl/issues/279), [#286](https://github.com/Tao-pyth/ygo-effect-dsl/issues/286) |
| profile scoreと既存Peak優先順位をどう移行するか | policy versionを分け、legacy goldenを保持する | [#280](https://github.com/Tao-pyth/ygo-effect-dsl/issues/280), [#288](https://github.com/Tao-pyth/ygo-effect-dsl/issues/288) |
| frontier exhaustionをどの範囲で証明できるか | exact frontier/candidate accountingがあるsmall fixtureから昇格する | [#282](https://github.com/Tao-pyth/ygo-effect-dsl/issues/282), [#292](https://github.com/Tao-pyth/ygo-effect-dsl/issues/292) |
| Neuronを公式に取り込めるか | scraping実装前に公式access・規約のdecisionを完了する | [#303](https://github.com/Tao-pyth/ygo-effect-dsl/issues/303) |

## Release boundary

`0.7.0`はresearch source milestoneであり、一般利用者向けoptimizer、最適性証明、公開配布を意味しない。parent #276と30 child Issue、[work breakdown](20_work_breakdown_and_acceptance.md)、[ADR-0017](../../adr/0017_v07_research_dashboard_evaluation_and_reliability.md)を正本とし、全childとevidenceが完了するまでpackage versionやtagを先行変更しない。
