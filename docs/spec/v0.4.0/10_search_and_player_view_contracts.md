# Package 0.4.0 Search and PlayerView Contracts

Status: Search and PlayerView safety implemented; scenario contracts in progress

Last updated: 2026-07-15

## SearchStrategy conformance

全strategyは次の責任境界を持つversion付きinterfaceへ接続する。

共通interfaceは`search-strategy-conformance-v1`とする。strategyは`strategy_id`、`schema_version`、`execution_mode`、canonical化可能な`parameters`、candidateを欠落・重複させない決定論的`order_actions`を公開する。`search-strategy-conformance-report-v1`は同じsemantic nodeとcandidate集合を順序違いで渡した結果が一致することをcontent ID付きで証明する。

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

RNGにmutable global stateを使わない。各判断keyは`seed`、strategy ID/schema version、semantic node ID、purpose、candidate IDのcanonical digest `decisionkey_*`とし、purposeは少なくとも`expand_action_order`、`beam_tie_break`、`mcts_selection`、`mcts_rollout`を分離する。同じcandidate集合は入力順に依存せず同じ順序へ正規化される。

## Beam Search v1 decisions

`beam-search-strategy-v1`は`beam_width >= 1`を必須、`seed >= 0`をdefault 0とし、未知parameterを拒否する。depth `d`で採用済みbeam parentをstable順に展開し、生成した全childをfresh Replayで評価してから次layerを選ぶ。hard budgetによりlayer途中で止まった場合、観測済みRouteは保持するが、不完全layerから次layerを作らない。

child順位は`success降順、peak score降順、terminal score降順、Action数昇順、semantic prefix ID辞書順`である。scoreだけでsuccessを逆転させない。同値時にseeded `beam_tie_break`を用いる場合もsemantic prefix IDを最後の全順序にする。上位`beam_width`だけを次depthで展開し、widthがcandidate数以上なら全件を残す。width=1はこの順位のgreedy layer searchであり、Random Searchではない。

legal STOP_LINEはRoute集合へ必ず保存し、そのnodeに別のcore提示Actionがあれば継続候補にもできる。END_TURNは通常Actionとして別prefixを作る。terminal、Actionなし、exact duplicate、max depthのnodeは次layerへ入れない。projection一致では削除しない。frontierが空なら`frontier_exhausted`、hard budgetは共通termination priorityを使う。実装[#147](https://github.com/Tao-pyth/ygo-effect-dsl/issues/147)は共通executor、fresh Replay、共通Route rankを再利用する。

Pseudocode:

```text
beam = [replay(root)]
while beam and budget remains:
  children = replay every core-provided child in semantic commit order
  record every legal STOP_LINE Route and exact duplicate
  if the layer is incomplete because of a hard budget: stop
  beam = best expandable exact/projection children[:beam_width]
```

parameter、width、success優先、同点prefix IDの実行可能vectorは`tests/test_search_strategy_contract.py`を正本とする。

## Beam Search v1 implementation status

2026-07-15時点で`beam-search-strategy-v1`は`SearchExecutor`へ接続済みである。公開結果は`search-run-result-v5`、executorは`search-executor-v5`とし、strategy ID/schema、canonical parameter、層ごとの評価・選択・budget中断を`search-strategy-evidence-v1`へ保存する。層の途中でhard budgetへ到達した場合、その層で観測済みのRouteとfailureは保存するが、部分集合から次層を選択しない。

Random Searchは同じresult/evidence contractへ移行するが、探索順とRoute順位の意味は変更しない。Beam Searchも`RealCoreFrontierAdapter`を共有し、exact Stateのみをdedup authorityとして扱う。`query_api_projection`は同値でも枝を削除しない。

## MCTS v1 decisions

`mcts-strategy-v1`は`simulations >= 1`、有限な`reward_floor < reward_ceiling`を必須とし、`exploration_constant >= 0`はdefault `sqrt(2)`、`seed >= 0`はdefault 0とする。未知parameterと`resume_from`を拒否する。v1はcheckpoint resumeを行わず、version付きlogical update evidenceからfresh Replayで再構築する。

scoreはfloor/ceilingへclampして`normalized = (score - floor) / (ceiling - floor)`とする。failure rewardは`normalized / 3`、success rewardは`(2 + normalized) / 3`とし、任意のsuccessが任意のfailureより高い。未訪問childのUCTは正の無限大、訪問済みchildは`value_sum / visits + c * sqrt(log(parent_visits) / visits)`とする。同点は`mcts_selection` decision key、Action IDの順で一意化する。

各simulationはrootからselectionし、未展開Actionを一つfresh Replayして、`mcts_rollout`順でlegal stop、terminal、exact duplicate、max depth、hard budgetまで進む。その後、選択pathをleafからrootへ一度だけbackpropagateする。retryは同じlogical simulationであり二重更新しない。parallel workerの完了順ではなくsimulation ordinal、semantic node ID、Action IDのcommit順を使い、virtual lossは採用しない。

budget中断時は完了済みsimulationだけをstatisticsへ含め、途中simulationを破棄してfailure/terminationを保存する。最良Routeはvisit数ではなく全strategy共通Route rankで決める。実装[#149](https://github.com/Tao-pyth/ygo-effect-dsl/issues/149)はsimulationごとのselection、expansion、reward、backpropagation後visit/valueを保存し、pool差でstatisticsが変わらないcontract testを持つ。

Pseudocode:

```text
for simulation in range(simulations):
  path = select visited children by deterministic UCT from root
  leaf = fresh Replay of the first deterministic unvisited Action
  leaf = deterministic rollout until a legal reward boundary
  if the simulation completed: backpropagate reward once in reverse(path)
rank all replayable legal-stop Routes with the common Route rank
```

reward、未訪問UCT、平均値、invalid/resume parameterの実行可能vectorは`tests/test_search_strategy_contract.py`を正本とする。

## MCTS v1 implementation status

2026-07-15時点で`mcts-strategy-v1`は`SearchExecutor`へ接続済みである。各simulationはselection、未訪問1枝のfresh Replay、`mcts_rollout`順のrollout、reward正規化、leafからrootへの1回のbackpropagationを`search-strategy-evidence-v1`へ保存する。hard budgetで中断したsimulationとpath failureは`discarded_from_statistics: true`とし、visit/valueへ加えない。

同じAction prefixをrollout後にtree expansionで再訪した場合、prefix cacheは検証済みReplay hintとして利用できる。ただしexact State identityだけを枝の停止根拠とし、`query_api_projection`一致では停止しない。再訪prefixのRouteをartifactへ重複追加せず、別prefixから得たRouteはRoute IDが同じでも個別に保持する。best Routeはvisit数ではなくstrategy共通Route順位で決定する。

## PlayerView Replay

永続化、identifier、field matrix、fail-close、side-channel、leak testの正本は[PlayerView Replay Persistence and Redaction Contract](15_player_view_redaction_contract.md)とする。

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

## PlayerView implementation status

2026-07-15時点で、`player-view-replay-v1`は実ocgcoreのfresh Replay中に各snapshotをallowlist投影して生成する。完全Routeとのcanonical一致をworker内で検証し、公開PlayerView、`player-view-verification-v1`、`information-access-audit-v2`、非公開`player-view-lineage-v1`を分離する。CLIは`experiment-player-view`で4成果物を出力し、audit失敗時は既存の公開artifactを変更しない。

`information-access-audit-v2`はfield name、serialized leaf、sequence canary、side channelを走査する。private canary registry自体は公開せず、公開reportにはcanary IDとJSON pathだけを残す。workerと親processでauditを再計算し、viewer 0/1、actor switch、shuffle、draw、search、set、random selection、worker crash、JSON/Parquet/UI exportの回帰matrixを通す。

## Multi-interruption scenario

scenarioは指定card code、source制約、最大発動回数、必要ならpriorityを入力する。探索はcoreが提示した各発動機会でPASS/activateへ分岐し、activation/cost/target/option responseをDecisionRequest constraintから生成する。

- 同一chain/別chain、source移動、候補消失、once-per-turn相当の可否はcore結果を使う。
- Pythonがcard textから「最適timing」を推測しない。
- 相手の全合法手を一般探索しない。
- baseline/interrupted/recoveryはprefix、decision signature、candidate、response、state hashで対応付ける。

## Going-second and multi-turn

going-second scenarioは初期公開盤面、turn player、hand、asset/deck identityを明示し、core frontierからだけactionを得る。multi-turn contractはphase、END_TURN、draw、turn counter、duel end、mandatory pending process、legal STOP_LINEを定義する。

node/replay/depth/time/turn budgetの所有者と優先順位を一意にし、turn境界でもcache keyとState completenessを弱めない。
