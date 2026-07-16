# Package 0.6.0 Scope: Deterministic Parallel Search

Status: Planned; parent [#258](https://github.com/Tao-pyth/ygo-effect-dsl/issues/258)

Last updated: 2026-07-16

## Objective

package `0.6.0`は、実ocgcoreのfresh Replay隔離と既存の探索結果semanticを維持しながら、Random Search、Beam Search、MCTSをsingle-host bounded process poolへ接続し、CLI/API/Windows desktopで探索時間を実測短縮するstageである。並列化そのものではなく、同一workloadをより短時間で処理し、結果の再現性と障害証跡を維持することを完了条件とする。

## Current baseline

package `0.5.0`には`parallel-search-policy-v1`等の独立contract、pool 1/2/4/8/16のfresh Replay stress、memory preflight、Random/Beam/MCTSのsingle-process SearchExecutorが存在する。ただし`SearchExecutor`のnode-level runtimeは同期`FrontierAdapter.replay()`を順次呼び出しており、独立contractを実探索へ接続していない。既存[#231](https://github.com/Tao-pyth/ygo-effect-dsl/issues/231)はこの統合を追跡し、2026-07-16に`1.0.0`から本stageへ再割当した。

## In scope

1. logical task、physical Replay、attempt、semantic commitを分離するparallel execution contract。
2. cancellable task-oriented frontier protocolとbounded worker-pool coordinator。
3. Experiment、CLI、Python API、desktopで共有するversion付きpool policy。
4. Randomのdeterministic dispatch window、Beamのlayer parallelism、MCTSのordinal batch update。
5. node/replay/depth budgetとwall-clock deadlineの分離。
6. crash、timeout、retry、cancel、late/duplicate completion、atomic publishのhardening。
7. native stateを保存しないverified Replay prefix cache接続。
8. hardware-aware memory preflight、pool上限、parallel execution telemetry。
9. 3 real-deck fixtureと100,000 logical-node workloadによる速度・RSS・決定論校正。
10. Windows desktopのpool選択、実効policy、進捗、resource warning、cancel/recovery表示。

## Out of scope

- native duel handle、Lua state、mutable core stateのprocess間共有またはsnapshot/clone。
- distributed worker、remote queue、複数host scheduling。
- 全探索空間の完全列挙または最適性証明。
- 評価weight変更、統計的枝刈りの既定有効化、相手AIの一般化。
- third-party assetの成果物同梱、一般公開distribution、production support。
- license、stable compatibility、upgrade/rollback、security、soak。これらは`1.0.0`に残す。

## Performance gate

同一asset-capable Windows host、同一core/asset lock、同一seed、同一node/replay budgetのwarm runを各5回以上測定する。pool 4のmedian wall timeはpool 1に対して、3代表fixture中2件以上で25%以上短縮し、いずれのfixtureでも10%を超えて悪化してはならない。semantic digest、best Route、Route lineageはpool 1/2/4で一致しなければならない。

この閾値は実装前の希望値ではなくrelease判定である。未達の場合はparallel modeを既定にせず、bottleneck evidenceと後続Issueを残す。`0.6.0`を「探索時間を短縮したrelease」として完了扱いにしない。

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
| prefix cacheが実時間を短縮するか | fresh Replay verificationとcontentionがhit利得を相殺し得る | [#268](https://github.com/Tao-pyth/ygo-effect-dsl/issues/268) |
| deadline runをどう比較するか | wall clockはpool、host load、完了順に依存する | [#266](https://github.com/Tao-pyth/ygo-effect-dsl/issues/266) |

## Release boundary

`0.5.1`の検証profile再編を先行させる。`0.6.0`完了後は[#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276)の`0.7.0`研究dashboardが実artifact、terminal preference、Route randomness、独立Replayを接続する。license/distribution/production gateの[#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91)、[#127](https://github.com/Tao-pyth/ygo-effect-dsl/issues/127)、[#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134)は閉じない。
