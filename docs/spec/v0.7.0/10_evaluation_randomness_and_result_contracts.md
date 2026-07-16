# Package 0.7.0 Evaluation, Randomness, and Result Contracts

Status: Planned contract; issues [#277](https://github.com/Tao-pyth/ygo-effect-dsl/issues/277)-[#282](https://github.com/Tao-pyth/ygo-effect-dsl/issues/282)

Last updated: 2026-07-16

## 1. Terminal-board projection

evaluationとdesktopは、同じterminal Stateから一つのcanonical projectionを得なければならない。各card entryはcard instance identity、card code、owner/controller、location、position、sequence、public/private/redacted stateを持つ。locationは少なくとも`HAND`、`MONSTER_ZONE`、`SPELL_TRAP_ZONE`、`FIELD_ZONE`、`GRAVEYARD`、`BANISHED`を区別し、positionは`ANY`、`FACE_UP`、`FACE_DOWN`を使用する。

`set`は独立locationではなく、field locationと`FACE_DOWN`の組合せである。HANDやGRAVEYARDへ`FACE_DOWN`を指定する等の不正組合せはsilent normalizeしない。PlayerViewでcard codeを開示できないentryはredacted identityを維持し、private research viewと同じ評価入力にしない。

## 2. Terminal preference profile

profileはimmutable content-addressed documentとし、少なくともname、rule list、scoring/ranking policy、schema provenance、content digestを持つ。各ruleは次を表す。

- card codeとcontroller。
- locationとposition。
- `min_count`とoptional `max_count`。
- `once`、`per_copy`、`threshold`のscoring mode。
- signed integer weight。
- enabled stateと安定rule identity。

profile編集はclone-on-editとし、既存Experimentが参照するbytesを変更しない。rule列挙順やUI操作順でcontent digestを変えず、同じcard instanceへの重複加点規則をvalidatorとgolden vectorで固定する。浮動小数のplatform差を避けるため、profile weightは整数score unitを正本とする。

## 3. Evaluation breakdown

terminal evaluationはbase evaluator resultを上書きせず、次の再計算可能なcomponentを保存する。

```text
base terminal score
  + matched terminal preference bonuses
  - matched terminal preference penalties
  - configured gameplay-randomness penalty
  = terminal composite score
```

各preference componentはrule ID、matched instance、observed location/position/count、weight、applied valueを持つ。profileなしのlegacy runは旧scoreを維持する。unknown/redacted/unsupported stateへbonusを推測適用しない。

## 4. Randomness domains

次のdomainを混同しない。

| Domain | Example | Route reliabilityへ含めるか |
|---|---|---|
| Experiment sampling | seeded random opening hand、conditional hand試行 | Route eventには含めずscenario provenanceへ保存 |
| Search exploration RNG | Random Search candidate ordering、MCTS rollout selection | 含めない |
| Physical execution | worker slot、completion order、retry | 含めない |
| Gameplay randomness | coin、dice、random card selection、shuffle/draw依存 | 含める |
| Opponent uncertainty | future opponent policy、hidden choice | 本stageでは別のunknown domain。gameplay RNGへ混ぜない |

gameplay eventはRoute step、source card/Action、kind、observed outcome、core/trace evidence、seed/counter provenance、判明する場合だけoutcome space/probabilityを持つ。Pythonはeffect textからeventやprobabilityを生成しない。eventが存在するが確率不明の場合は`probability: null`相当の明示unknownとする。

## 5. Reliability summary

Route summaryは少なくともgameplay event有無、event count、replay determinism、gameplay reliability、evidence completenessを持つ。reliability classは`deterministic`、`stochastic`、`unknown`を区別する。同じseedでevent outcomeが再生できても、実戦でcoin/drawに依存するRouteは`stochastic`である。legacy Routeでfieldがない場合は`unknown`とし、`deterministic`へdefaultしない。

## 6. Ranking policy

新policyの安定rank orderは次を基本とする。

1. success降順。
2. terminal composite score降順。
3. gameplay reliability。defaultは`deterministic`、`stochastic`、`unknown`の順。
4. gameplay random event count昇順。
5. peak score降順。
6. Action count昇順。
7. Route ID辞書順。

randomness penaltyはprofile/policyへ明示した整数だけをcomposite scoreへ適用する。defaultで「非randomならscore差を無視して常に勝つ」とはしない。確率Routeを絶対除外する場合は`require_deterministic`を使用し、除外理由をSearch reportへ保存する。ranking policy IDとdigestをRoute/SearchRunへ保存し、legacy rank keyを黙って変更しない。

## 7. Result truth and verification

real job resultはjob catalogにcommitされたRoute/report artifactだけから生成する。application serviceはjob ownership、path containment、artifact kind、schema、SHA-256、Experiment/Route/SearchRun/profile/randomness identityを再検証し、typed result viewを返す。rendererは任意filesystem pathを読まない。

verificationはSearch jobと別のfresh worker jobであり、状態は`unverified`、`verifying`、`verified`、`mismatch`、`replay_failed`を区別する。Action、request signature、State、score breakdown、randomness eventが一致した場合だけ`verified`とする。browser synthetic previewには別namespaceと明示labelを要求し、real resultとしてexportしない。

## 8. Optimality and coverage

通常のbudget停止、deadline、cancel、resource limit、path failureを含む結果は`best observed`である。`frontier exhausted`を主張するには、pending frontier 0、candidate accounting complete、unknown candidate 0、exact state accounting、termination boundary、coverage certificateが必要である。

logical checkpointはpending frontier、seen exact states、accepted routes、strategy state、budget consumption、semantic commit positionを保存する。jobのprogress checkpointだけではresume可能とは扱わない。resume時はExperiment、deck、asset/core lock、profile、ranking、strategy、contract identityを照合する。adaptive budgetもhard time/RSS/disk/Replay/frontier limitを超えてはならない。

## 9. Compatibility

package stage開始時にschema番号を予約しない。実装でcanonical shapeまたは意味が変わるcontractを特定した後、対象contractだけをversion upする。少なくともRoute、evaluation profile/result、result view、randomness、coverage/checkpointについて、legacy read、replay、migrate、rejectのmatrixを[#278](https://github.com/Tao-pyth/ygo-effect-dsl/issues/278)、[#304](https://github.com/Tao-pyth/ygo-effect-dsl/issues/304)で固定する。
