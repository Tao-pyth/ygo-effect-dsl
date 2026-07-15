# Package 0.4.0 Scope: General Strategies and PlayerView

Status: Implemented stage; superseded by cumulative package 0.5.0; production node-level pool/cache remains [#231](https://github.com/Tao-pyth/ygo-effect-dsl/issues/231)

Last updated: 2026-07-15

## Objective

package `0.4.0`は、`0.3.0`でqualificationしたreal-core frontierとfresh Replayを共通実行基盤として、Beam Search、MCTS、PlayerView Replay、複数妨害、後攻盤面、複数turnへ探索範囲を広げるstageである。strategy数だけを増やすのではなく、全strategyの決定性とprivate information非漏洩を同じrelease gateで保証する。

## Entry criteria

- `0.3.0`のclean bootstrap、3 real deck、unknown形状fail-close、worker failure、実worker 10万node gateが完了している。
- RandomSearchStrategyV1を共通strategy conformanceの基準実装にできる。
- asset/core lockを変えずに比較可能なqualified corpusがある。
- PlayerView対象のhidden/visible情報分類に必要なReplay/State provenanceが欠落していない。

## In scope

1. SearchStrategyのversion付き共通適合契約。
2. Beam Search v1のordering、budget、実装、evidence。
3. MCTS v1のselection/statistics、決定性、実装、evidence。
4. PlayerView Replayの永続化、redaction、export境界。
5. InformationAccessAuditによるlog/artifact/UI前段の漏洩検出。
6. 複数指定妨害のscenario compositionと全発動機会探索。
7. 後攻盤面突破scenario。
8. END_TURN、phase、draw、duel endを含む複数turn lifecycle。
9. Random/Beam/MCTSとbaseline/interrupted/recoveryのcross-validation。

## Out of scope

- 任意の相手AIまたは相手の全合法手探索
- distributed MCTS、native snapshot/clone
- 大規模corpus UI、一般利用者向けdashboard
- public distribution、production SLA
- hidden情報を完全情報ReplayからUIだけで隠す方式

## Architectural constraints

- strategyはRealCoreFrontierAdapter以外から合法手を作らない。
- core/native stateをstrategy間またはworker間で共有しない。
- seed、semantic node ID、version付きparametersから探索判断を再現する。
- pool size、completion order、retryはlogical update順を変えない。
- PlayerViewは保存時にredactし、非公開情報を保存後に表示層だけで隠さない。
- unsupported timing、ambiguous candidate、redaction不能shapeはfail-closeする。

## Delivery claim

`0.4.0`完了時に許される主張は「Random/Beam/MCTSを同じreal-core executorから決定論的に実行し、指定した複数妨害や複数turnを探索でき、PlayerView成果物に既知private情報を保存しない」である。探索が最適解であること、相手AIとして完全であること、統計的勝率を示すことは主張しない。

この実装stageは2026-07-16に完了し、独立package tagを作らず累積package `0.5.0`へ収録した。damage step、simultaneous trigger、mandatory trigger、SEGOCは未検証時にfail-closeし、#207-#210で`1.0.0`のproduction qualificationとして継続する。node-level pool/cache統合#231も`1.0.0`へ分離した。
