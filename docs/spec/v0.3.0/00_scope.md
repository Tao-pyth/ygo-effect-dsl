# Package 0.3.0 Scope: Real-Core Qualification

Status: Planned; parent [#131](https://github.com/Tao-pyth/ygo-effect-dsl/issues/131)

Last updated: 2026-07-15

## Objective

package `0.3.0`は、`0.2.0`で接続済みのocgcore/EDOPro Lua、Experiment `0.4`、Random Searchを、単一fixtureのprototypeから複数の任意YDK/inline deckで検証可能なdeveloper MVPへ昇格させるstageである。新しい探索方式を増やすより先に、取得再現性、入力一般性、unknown形状のfail-close、worker耐障害、実性能を証明する。

## Starting baseline

`0.2.0`には次が実装済みであり、`0.3.0`で作り直さない。

- ocgcore API 11.0のproject-owned bootstrap、runtime resolver、隔離worker
- CardScripts/BabelCDB asset lockとread-only SQLite/Lua provider
- Experiment `0.4`、fixed/inline/YDK、fixed/random/conditional opening hand
- Scenario manifest/preflightとstructured diagnostic
- RealCoreFrontierAdapter、SearchExecutor、RandomSearchStrategyV1
- STOP_LINE/END_TURN分離、全budget、決定論的best Route tie-break
- Route DSL `0.1`出力とfresh Replay
- 指定妨害candidate policyとsupport taxonomyの基礎

2026-07-14のlocal smokeでは、固定inline deckを使う10 node探索とbest Route Replayまで成功した。この結果は接続済みであることだけを示し、任意deckやproduction性能を示さない。

## In scope

1. Windows x64/MSVCを起点としたsupported platform/toolchain契約。
2. 空cacheからのocgcore/CardScripts/BabelCDB取得・build・hash/API検証。
3. BabelCDB `20250419` refと固定commit差異の再現性判断。
4. EDOPro root helper/card scriptのload境界とunsafe Lua無効化。
5. 短展開、長展開、墓地/除外またはchain多発の3 deck qualification。
6. unknown Message/Decision/candidate/Luaのcorpusとfail-close診断。
7. worker crash/timeout/retry/quarantineとatomic artifact commit。
8. 妨害timing taxonomyのproduction許可範囲、未検証category、昇格条件の固定。
9. 10万logical nodeと実worker pool 1/2/4/8/16のthroughput/RSS校正。
10. self-hosted real-core smoke、operator walkthrough、release contract判断。

## Out of scope

- Beam Search、MCTS
- PlayerView Replay
- 複数妨害、後攻盤面、複数turnの一般探索
- 大規模統計API/UI
- third-party assetを含む配布
- Linux/macOSを証跡なしでsupportedと宣言すること
- native duel snapshot/clone、distributed worker

## Dependency order

```text
#135 platform matrix
  -> #136 clean core bootstrap
  -> #137 clean asset bootstrap and BabelCDB decision
      -> #140 Lua loading boundary
      -> #139 three-deck qualification
          -> #141 unknown shape corpus
          -> #123 interruption timing policy
          -> #142 worker failure acceptance
              -> #105/#128 performance and memory calibration
              -> #110 pruning calibration
              -> #108 evaluator calibration
                  -> #138 self-hosted smoke
                  -> #143 operator guide
                      -> #144 release contract decision
```

実際には独立部分を並行実施できるが、asset/coreの取得再現性が確定するまでdeck結果をrelease evidenceとして確定しない。

## Release artifacts

- version付きplatform/toolchain matrix
- clean bootstrap manifestとcore/assets verification evidence
- 3 deckのscenario manifest、SearchRun、best Route、fresh Replay evidence
- unknown/unsupported形状corpusとdiagnostic code一覧
- 妨害timing categoryのproduction許可/fail-close policyと後続fixture Issue
- 10万node JSON/Parquet benchmark evidence
- cache/worker policyとmemory preflightの判断ADR
- self-hosted workflow結果とoperator walkthrough
- contract compatibility/release decision

## Completion statement

`0.3.0`完了時に許される主張は「supported環境と固定asset lockの範囲で、複数の利用者入力deckを事前検査し、実ocgcore/EDOPro Lua上のRandom Search結果を再生可能に生成でき、測定済み上限内で障害を診断できる」である。任意カードの完全対応、全timing、production SLA、一般公開配布は主張しない。
