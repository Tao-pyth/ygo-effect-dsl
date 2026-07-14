# Package 0.4.0 Search and PlayerView Contracts

Status: Contract design backlog

Last updated: 2026-07-14

## SearchStrategy conformance

全strategyは次の責任境界を持つversion付きinterfaceへ接続する。

| Operation | Executor responsibility | Strategy responsibility |
|---|---|---|
| initialize | experiment/lock/budget/frontier validation | strategy parameter validation、logical state初期化 |
| expand | fresh Replay、DecisionRequest、legal candidates、State、score | 展開するsemantic node/candidate順を選ぶ |
| observe | failure分類、budget消費、exact identity | strategy固有統計/frontierを決定順で更新する |
| terminate | hard budget、frontier exhausted、fatal worker failure | strategy固有収束または十分条件を提案する |
| rank | success/peak/terminal/action count/Route IDの共通最終順 | strategy固有候補を共通Route集合へ出す |
| evidence | package/schema/lock/worker共通field | parameters、logical update、statisticsを保存する |

strategyはSTOP_LINEを合法候補として扱い、END_TURNと混同しない。exact State identityだけが共通dedup authorityであり、projectionやscore一致でbranchを削除しない。

`SearchFrontier v2`は`state_completeness: exact | query_api_projection`を必須とする。executorは`exact`だけを`seen_states`へ登録する。`query_api_projection`はnode IDと観測値には残すが、同じprojectionの別prefixを展開対象から除外しない。`SearchRun.exact_state_duplicates`はexact identityによる削除件数だけを数える。

## Deterministic RNG and update order

- RNG streamはroot seed、strategy ID/version、semantic node ID、decision purposeから導出する。
- worker ID、process ID、wall clock、completion orderをseedへ含めない。
- parallel resultはexecutorがsemantic commit orderへ並べてからstrategyへ渡す。
- retryは同じlogical attempt identityを維持し、strategy統計を二重更新しない。
- max_secondsは物理的terminationを起こし得るため、同一結果保証の対象workloadではnode/replay/depth budgetを主比較軸とし、time termination差を明示する。

## Beam Search v1 decisions

[#146](https://github.com/Tao-pyth/ygo-effect-dsl/issues/146)で次を固定するまで実装をreleaseしない。

- depth layerとbeam widthの定義
- score/tie-breakと同点nodeのstable ordering
- terminal/STOP_LINE nodeをbeamへ残す規則
- duplicateとfrontier exhaustionの扱い
- budget消費の境界
- width=1とRandom/greedyとの意味差

実装[#147](https://github.com/Tao-pyth/ygo-effect-dsl/issues/147)は共通executor、fresh Replay、共通Route rankを再利用する。

## MCTS v1 decisions

[#148](https://github.com/Tao-pyth/ygo-effect-dsl/issues/148)で次を固定するまで実装をreleaseしない。

- selection/expansion/simulation/backpropagationの一意な順序
- UCT式、exploration定数、reward normalization、未訪問node
- 同点選択、simulation policy、terminal reward
- parallel logical updateとvirtual loss採否
- budget中断時の部分統計とbest Route選択

実装[#149](https://github.com/Tao-pyth/ygo-effect-dsl/issues/149)はstatisticsの全更新をReplay可能なevidenceへ保存し、pool差でvisit/valueが変わらないcontract testを持つ。

## PlayerView Replay

PlayerViewはactorごとのinformation boundaryを永続成果物に適用する。最低限、次を分類する。

| Data | Complete/internal | PlayerView rule |
|---|---|---|
| own hand/public field/grave/banish | retained | actorから可視なら保持 |
| opponent hand/deck order/set identity | retained internally | value、stable ID、ordering hintを除去またはviewer alias化 |
| Decision candidates | complete for acting authority | viewerが知り得ない候補・sourceを保存しない |
| raw message/query/log | audit only | redaction証明なしにPlayerViewへ含めない |
| hash/length/count | internal | side channelにならないか分類し、必要ならbucket/omit |
| diagnostics | internal context可 | private payloadを除きdiagnostic codeとsafe contextだけ保持 |

PlayerView artifactはcomplete Replayと別schema/identityを持ち、complete hashからhidden valueを推測できる参照を公開しない。redaction不能なunknown shapeはPlayerView生成失敗とする。

## InformationAccessAudit

[#151](https://github.com/Tao-pyth/ygo-effect-dsl/issues/151)はReplayだけでなく、exception、worker log、SearchRun、Parquet、export、future UI payloadまでcanary valueを追跡する。false positive allowlistはversion付きで、value/field/path単位の根拠を持つ。漏洩検出時はartifact publishを停止する。

## Multi-interruption scenario

scenarioは指定card code、source制約、最大発動回数、必要ならpriorityを入力する。探索はcoreが提示した各発動機会でPASS/activateへ分岐し、activation/cost/target/option responseをDecisionRequest constraintから生成する。

- 同一chain/別chain、source移動、候補消失、once-per-turn相当の可否はcore結果を使う。
- Pythonがcard textから「最適timing」を推測しない。
- 相手の全合法手を一般探索しない。
- baseline/interrupted/recoveryはprefix、decision signature、candidate、response、state hashで対応付ける。

## Going-second and multi-turn

going-second scenarioは初期公開盤面、turn player、hand、asset/deck identityを明示し、core frontierからだけactionを得る。multi-turn contractはphase、END_TURN、draw、turn counter、duel end、mandatory pending process、legal STOP_LINEを定義する。

node/replay/depth/time/turn budgetの所有者と優先順位を一意にし、turn境界でもcache keyとState completenessを弱めない。
