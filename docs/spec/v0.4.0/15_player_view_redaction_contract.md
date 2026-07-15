# PlayerView Replay Persistence and Redaction Contract

Status: accepted for implementation

Last updated: 2026-07-15

Related issues: [#125](https://github.com/Tao-pyth/ygo-effect-dsl/issues/125), [#150](https://github.com/Tao-pyth/ygo-effect-dsl/issues/150), [#151](https://github.com/Tao-pyth/ygo-effect-dsl/issues/151)

## Boundary and claims

PlayerViewは完全情報Routeの表示切替ではなく、保存前にprivate情報を除去した派生成果物とする。公開artifactは`player-view-replay-v1`、各観測は`player-view-observation-v1`、公開verificationは`player-view-verification-v1`とする。完全情報Routeと公開artifactの対応は非公開の`player-view-lineage-v1`だけに保存し、公開artifactへsource Route ID、complete State hash、complete Replay digestを含めない。

PlayerView artifact単体からocgcoreを再実行することは保証しない。fresh verificationは内部Routeをfresh Replayし、同じprojectorで再生成した`player_view_id`との一致を検証する。これにより、完全情報Routeの再生可能性と公開artifactの決定性を両立し、hidden情報を再実行seedやcomplete hashとして公開しない。

## Public artifact

`player-view-replay-v1`は次のtop-level fieldだけを持つ。未知fieldは拒否する。

| Field | Rule |
|---|---|
| `schema_version` | literal `player-view-replay-v1` |
| `player_view_id` | `player_view_id`自身を除くcanonical payloadの`playerview_*` digest |
| `viewer` | `0`または`1` |
| `manifest` | `player-view-manifest-v1`。projector ID/version、公開可能なcore API/asset lock ID、source schema versionだけを保持 |
| `initial_observation` | `player-view-observation-v1` |
| `events` | `player-view-event-v1`の連続した配列 |
| `result` | 公開観測から導出できるsuccess、score、turn、phase、stop reasonだけを保持 |
| `lineage` | public PlayerView同士の`parent_player_view_id`と`fork_step`だけ。完全情報IDは禁止 |

manifestへdeck順、duel seed、process/worker ID、path、timestamp、raw byte数、complete hashを含めない。source schema versionは互換判定であり、source artifactのidentityではない。

非公開`player-view-lineage-v1`は`player_view_id`、source Route ID、source Replay digest、viewer、projector version、生成時のaudit IDを保持できる。このdocumentはpublic export、UI payload、Parquet、例外、logへ渡してはならない。

## Observation projection

各観測は`viewer`、`observation_id`、turn/phase、process category、公開field state、zone配列、viewerが応答権限を持つ場合だけのsafe requestを持つ。`observation_id`は公開payloadだけから導出し、complete State hashを参照しない。

| Source data | Viewer rule | Persisted representation |
|---|---|---|
| viewer hand identity | retain | card code/public propertiesとviewer-scoped instance alias |
| viewer deck | redact order and identity | rules上観測可能なcountだけ |
| viewer private extra deck | retain unordered identity | card codeとviewer-scoped alias。source slot/orderは除去 |
| public field/grave/banish | retain | public card dataとviewer-scoped alias |
| opponent hand/deck/private extra | redact | rules上観測可能なzone countだけ |
| opponent facedown field card | redact identity | public controller/location/sequenceとobservation-scoped hidden marker |
| opponent public card | retain | public card dataとviewer-scoped alias |
| chain/LP/phase/turn | retain typed public fields | allowlist済みfieldだけ |
| complete `state_hash` / persistent ID | reject | 保存しない |
| sampling reference/result | reject | 保存しない |

`persistent_instance_id`、`public_card_id`、complete request signatureはownerに関係なく公開artifactへ保存しない。公開cardの連続性が必要な場合はcard instance v2が発行するviewer-scoped aliasを使う。aliasがないshapeはraw IDを代用せずfail-closeする。

hand/deck/private extraは順序なしzoneとして保存する。hidden zoneのcard配列、slot列、candidate数、raw payload長は保存しない。facedown fieldのsequenceは盤面上公開される位置なので保持できるが、hidden markerは観測をまたぐstable identityにしてはならない。

## Event and request projection

`player-view-event-v1`は連続`step`、turn/phase/chain index、公開可能なactor/action category、before/after observation ID、safe request/responseだけを持つ。次を必須とする。

- viewerがDecisionRequestのacting authorityでない場合、request、candidate、responseを全て`null`にする。candidate数も保存しない。
- viewerのrequestはknown request typeごとのallowlist projectorを通し、candidate IDをviewer-scoped aliasまたは公開zone coordinateへ変換する。
- opponent actionは公開snapshotでsource/targetが公開されたと証明できるcategoryだけを保持する。証明できないselectionはcategoryだけへ縮退し、category自体もhidden情報を表す場合はevent生成を拒否する。
- `core_input_ref`、`core_response`、raw frame/message/query、random event、complete request signature、complete state hashは常に除去する。
- unknown request type、unknown candidate payload、alias欠落、前後観測と矛盾するvisibilityは`unprojectable_shape`としてfail-closeする。

specified interruptionはactivation後にcore観測で公開されたsource/targetだけを保持する。hand source code、未選択candidate、PASSとactivateの内部branch集合を先に公開しない。sampled private stateをsourceに使う場合、sampling policy ID、selected index、sampled hand、seedを全て除去し、同じvisible projectionを生成できる場合だけ対応する。

## Diagnostics, logs, and exports

公開diagnosticはversion付きcode allowlistを使い、`code`、`severity`、safe numeric contextだけを保持する。自由文message、exception text、worker stderr/stdout、path、PID、attempt input digest、candidate payloadは公開しない。unknown diagnosticはmessageをredactして続行せずPlayerView生成を失敗させる。

JSON、Parquet、UI API、CLI reportは同じprojected documentを入力とし、complete Routeから個別に再変換しない。これによりexportごとのredaction差を禁止する。artifact publishはtemporary fileへ生成後、schema validationと`information-access-audit-v2`を通過した場合だけatomic replaceする。失敗時は既存artifactを変更せず、公開可能なfailure codeだけを別reportへ保存する。

## Side-channel policy

| Channel | Decision |
|---|---|
| opponent hand/deck count | retain。rules上観測可能 |
| hidden zone ordering/slot list | omit |
| complete hash、Route ID、Replay digest | private lineage only |
| raw byte length、candidate count、worker attempt count | omit |
| public event count、turn、phase | retain |
| wall-clock、PID、filesystem path | omit |
| viewer-scoped alias | retain only after canary audit |
| observation-scoped hidden marker | retain。観測間でjoin不能であることをtest |

hash化はredactionではない。small-domain card code、candidate ID、deck list、slot列をhashへ置換して公開することを禁止する。

## InformationAccessAudit v2

`information-access-audit-v2`はartifact kindごとにserialized leafを走査し、field nameとvalueの両方を検査する。入力はcanary registry、artifact集合、`information-access-audit-allowlist-v1`とし、出力はaudit ID、artifact digest、検査leaf数、leak、side-channel finding、allowlist適用結果を持つ。

allowlist entryはexact artifact kind、JSON path、matcher kind、根拠、期限またはreview issueを必須とする。hidden valueそのもの、汎用substring、top-level wildcardをallowlistへ登録してはならない。未知artifact kind/field shape、期限切れallowlist、canary衝突はaudit failureとする。

## Leak test matrix

| Fixture | Canary | Required assertion |
|---|---|---|
| initial opponent hand | card code、persistent ID | 全public artifactから不在 |
| opponent deck and shuffle | full order、top/bottom code、slot列 | order、hash、ordering hintが不在。countだけ一致 |
| draw | before/after hidden ID | draw前後をhidden aliasでjoin不能 |
| search | non-selected candidate/card code | viewer権限外candidateとcandidate数が不在 |
| set card | code、stable instance ID | public sequence以外が不在 |
| random selection | seed、selected private index | seed/index/hashが不在 |
| actor switch | 両playerのprivate canary | 各viewerで相手canaryだけ不在、own handは保持 |
| specified interruption | hand source、unused target candidate | activation前は不在、公開後のsource/targetだけ保持 |
| sampled private state | sample ID、candidate hands、selected index | public artifactから不在、visible IDは反復一致 |
| worker crash | stderr、path、PID、input digest | safe failure code以外が不在、artifact未publish |
| unknown native/query shape | unknown field canary | fail-closeしartifact未publish |
| JSON/Parquet/UI export | 全canary | canonical PlayerView payloadと同じleak結果 |

各fixtureはviewer 0/1、初期観測、全frontier、terminal観測で実行する。検出されたleakが1件でもあればPlayerView、verification、exportのpublishを停止する。

## Acceptance

1. 同一complete Routeとviewerから生成したPlayerView IDがprocess、retry、export形式に依存せず一致する。
2. fresh Replayから再生成したPlayerView IDとevent/observation IDが一致する。
3. source Route/Replayは従来どおり完全情報で再生可能だが、public artifactだけからhidden stateを復元できない。
4. matrix内の既知canaryとunknown shapeはfail-closeし、atomic publish前に停止する。
5. PlayerView artifact、audit、verification、failure reportの全schemaとprojector versionを固定する。
