# Package 0.4.0 Work Breakdown and Acceptance

Status: Items 1-13 implemented and included in package 0.5.0; node-level pool/cache #231 tracked in planned package 0.6.0

Last updated: 2026-07-15

## Work items

| Order | Issue | Deliverable | Acceptance evidence |
|---|---|---|---|
| 1 | [#145](https://github.com/Tao-pyth/ygo-effect-dsl/issues/145) | SearchStrategy conformance contract | Random v1 conformance、seed/budget/pool/retry vectors |
| 2 | [#146](https://github.com/Tao-pyth/ygo-effect-dsl/issues/146) | Beam v1 ordering/budget spec | pseudocode、width/tie/terminal test vectors |
| 3 | [#147](https://github.com/Tao-pyth/ygo-effect-dsl/issues/147) | Beam v1 implementation | 3 real deck、pool/cache/retry determinism |
| 4 | [#148](https://github.com/Tao-pyth/ygo-effect-dsl/issues/148) | MCTS v1 statistics spec | UCT/update/reward/parallel test vectors |
| 5 | [#149](https://github.com/Tao-pyth/ygo-effect-dsl/issues/149) | MCTS v1 implementation | replayable statistics、3 real deck determinism |
| 6 | [#125](https://github.com/Tao-pyth/ygo-effect-dsl/issues/125), [#150](https://github.com/Tao-pyth/ygo-effect-dsl/issues/150) | PlayerView real Replayとredaction契約 | actor別golden Replay、unknown shape failure |
| 7 | [#151](https://github.com/Tao-pyth/ygo-effect-dsl/issues/151) | InformationAccessAudit | canary leak scan across all artifacts |
| 8 | [#152](https://github.com/Tao-pyth/ygo-effect-dsl/issues/152) | multi-interruption scenario contract | composition/timing/lineage vectors |
| 9 | [#153](https://github.com/Tao-pyth/ygo-effect-dsl/issues/153) | core-driven interruption timing search | all offered opportunities、cost/target/option corpus |
| 10 | [#154](https://github.com/Tao-pyth/ygo-effect-dsl/issues/154) | going-second board-break scenarios | targeting/targetless/grave-banish fixtures |
| 11 | [#155](https://github.com/Tao-pyth/ygo-effect-dsl/issues/155) | multi-turn lifecycle/budget | 1/2/3 turn deterministic vectors |
| 12 | [#156](https://github.com/Tao-pyth/ygo-effect-dsl/issues/156) | strategy/interruption/recovery cross-validation | 3 deck × 3 strategy × interruption matrix |
| 13 | [#229](https://github.com/Tao-pyth/ygo-effect-dsl/issues/229) | core terminal frontier runtime | LP 0/deck-out MSG_WIN, Action-free terminal frontier, fresh Replay, 3-strategy boundary |

## Gate A: strategy conformance

- Random/Beam/MCTSが同じSearchExecutor/RealCoreFrontierAdapterを使う。
- strategyごとのparameters/result/evidenceにversionがある。
- 同一seed/node/replay/depth budgetでlogical expansionとbest Routeが再現する。
- single-process strategy matrixでsemantic digestが一致し、pool/cache/retryは独立したversion付きcontract regressionを通る。node-level SearchExecutor統合は#231と#258の`0.6.0` gateとする。
- Beam/MCTSの統計またはfrontierをfresh Replayから再構成できる。
- unknown strategy/version/parameterを明示的に拒否する。

## Gate B: PlayerView safety

- own/opponent/public/hidden/derived情報のfield matrixがある。
- complete ReplayからPlayerViewへ変換する各fieldにretain/redact/alias/reject規則がある。
- hidden card、stable ID、deck order、candidate、raw payloadのcanaryが成果物に残らない。
- exception、log、Parquet、exportも同じauditを通る。
- actor switch、shuffle、draw、search、set、random selection、worker crashのfixtureを通す。
- redaction不能または未知shapeではartifactをpublishしない。
- public `player-view-replay-v1`とprivate `player-view-lineage-v1`を分離し、source Route IDとcomplete hashをpublic artifactへ含めない。
- fresh Replay verificationはprivate lineageでsourceへjoinし、再生成したpublic `player_view_id`だけを公開結果として比較する。

## Gate C: scenario breadth

- 複数指定妨害の全core提示機会をPASS/activateへ分岐する。
- cost/target/option組合せをconstraint違反なく生成する。
- candidate消失、source移動、ambiguous mappingをfailureとして保存する。
- going-secondの初期盤面とinformation policyをmanifestに固定する。
- END_TURN、phase、draw、duel end、turn budgetを一意に処理する。
- opponent all-legal-action探索を実装済みと誤って主張しない。

## Gate D: lineage and compatibility

- Random/Beam/MCTS Routeをfresh Replayし、state/request/action identityを照合する。
- baseline/interrupted/recoveryの最初のdivergenceを特定できる。
- Experiment/Route/Replay旧versionを既定policyどおりread/replay/rejectする。
- v0.3.0の3 deck、worker failure、performance gateを回帰させない。

## Release rejection conditions

- strategyがcore以外から合法手を生成する。
- parallel completion orderでMCTS/Beam結果が変わる。
- PlayerView artifactまたはdiagnosticからhidden value/identifierを復元できる。
- unsupported timingやunknown candidateをPASSとして処理する。
- multi-turn停止時にpending chain/mandatory responseを無視する。
