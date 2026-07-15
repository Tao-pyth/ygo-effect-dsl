# Strategy, Interruption, and Recovery Cross-validation

Status: Implemented and qualified locally; node-level pool/cache runtime remains [#231](https://github.com/Tao-pyth/ygo-effect-dsl/issues/231)

Last updated: 2026-07-15

Related issue: [#156](https://github.com/Tao-pyth/ygo-effect-dsl/issues/156)

## Objective

`strategy-interruption-cross-validation-v1`は、Random/Beam/MCTSが同じ実ocgcore Decisionを通ったとき、baseline、指定発動、発動後recoveryのsemantic Routeと最初のdivergenceが一致することを検証するrelease gateである。Route IDはExperimentのstrategy設定を含むためstrategy間比較キーにせず、DecisionRequest、candidate、Action、response、State transition、terminal評価から作るsemantic IDを使用する。

## Matrix

| Axis | Values |
|---|---|
| deck profile | `short`、`long`、`grave_banish` |
| strategy | `random_search_v1`、`beam_search_v1`、`mcts_v1` |
| treatment | `baseline`、`interrupted`、`recovery` |
| stop policy | 最初のcore由来legal stopで`STOP_LINE` |

3 profileはpin済みDB/Luaでpreflightした40枚inline deckであり、正規化deck hashは全て異なる。同じplayer 0の指定source cardをopening handへ置く。baselineとinterruptedは同じExperiment、initial State、core candidate集合を使い、baseline treatmentは指定sourceをPASS、interrupted treatmentは最初のcore提示activationを選ぶ。Pythonは発動可否、timing、responseを生成しない。指定発動後はcore Actionだけを辿り、最初のlegal stopまでをrecovery tailとする。

各strategyはbaseline/interruptedを独立SearchRunとして実行する。legal stop後の追加Action展開だけを停止し、生成Routeは通常の`RealCoreFrontierAdapter`でfilterなしにfresh Replayする。したがってtreatment filterがcoreに存在しないActionや不正responseを作った場合、evidenceはpublishされない。

## Semantic comparison

各Replay eventから次を正規化する。

- request type、player、request signature、candidate ID集合、constraints。
- Action kind、選択candidate ID、request signature。
- encoded responseのcanonical payload。
- step、turn、turn action index、chain index。
- before/after State hash。

Route semantic IDは全event semantics、deck hash、success、terminal turn/phase/score/State/stop reasonから作る。strategy ID、SearchRun ID、Route ID、pool slot、process ID、完了時刻は含めない。

baseline/interrupted lineageは次をfail-closeで照合する。

1. recorded forkより前の全eventが一致する。
2. forkのDecisionRequest、candidate集合、constraints、State beforeが一致する。
3. baseline Actionとinterrupted activation Actionが異なり、activation candidateが共通requestに存在する。
4. traceのresponse stepが連続し、roleごとのcandidateがReplay Actionと一致する。
5. response後に1件以上のrecovery eventがあり、terminal legal stopまでfresh Replayできる。
6. 3 strategyのbaseline semantic ID、interrupted semantic ID、first divergence IDがprofile内でそれぞれ一つになる。

不一致、candidate消失、response欠落、recovery tail欠落、fresh Replay mismatchは`StrategyInterruptionCrossValidationError`となり、atomic writerを呼ばない。既存evidenceは失敗runで上書きしない。

## Evidence boundary

sanitized evidenceはRoute ID、event semantic ID、terminal summary、first divergence、recovery event semantic ID、SearchRun統計だけを保存する。raw Route、snapshot、hand、core response hexは保存しない。content IDは`strategyintmatrix_` prefixで全reportを拘束する。

pool 1/2/4、cache on/off、retry injectionの決定性は、`parallel-search-aggregate-v2`、`prefix-cache-verification-v1`、`parallel-worker-attempt-v1`の既存contract regressionを参照する。現行SearchExecutorはこれらをnode-level runtimeへ直接接続していないため、本matrixをnode-level pool/cache実行済みとは主張しない。実接続と同じ3 deck × 3 strategy再計測は#231のv0.5.0 gateとする。

## Local qualification

2026-07-15にWindows x64のpin済みocgcore/assetsで18 SearchRunと18 fresh Replayを実行した。3 deck、9 strategy cell、baseline/interrupted/recoveryを完走し、profileごとのsemantic Routeとfirst divergenceは3 strategyで一致、path failureは0だった。

Evidence: `docs/ocgcore/evidence/strategy_interruption_cross_validation.json`

Qualification ID: `strategyintmatrix_bae2bcfb6edc2d334c496795fad3089458d06ce16d0a0269b4d9b8bc56b6401f`
