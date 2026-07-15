# Multi-interruption Scenario Composition Contract

Status: accepted and machine-validated

Last updated: 2026-07-15

Related issues: [#123](https://github.com/Tao-pyth/ygo-effect-dsl/issues/123), [#152](https://github.com/Tao-pyth/ygo-effect-dsl/issues/152), [#153](https://github.com/Tao-pyth/ygo-effect-dsl/issues/153)

## Boundary

MVPの妨害探索対象は、Experiment `0.4`の`interruption.mode: specified`で利用者が指定したsourceだけとする。相手の全合法手、カードテキストから推測した発動可否、Python側で再実装したtiming ruleは探索しない。activation、cost、target、option、placement、confirmationはocgcoreが提示した`DecisionRequest`だけをauthorityとする。

契約schemaは`multi-interruption-composition-v1`、各発動機会は`multi-interruption-opportunity-v1`、Route間lineageは`multi-interruption-lineage-v1`とする。

## Experiment contract

複数definitionでは各definitionに異なる非負整数`priority`を必須とする。単一定義だけは後方互換のためlist index `0`をdefaultにする。`max_activations`はdefault `1`の正整数で、coreが提示した回数ではなく実際に選択したactivation occurrence数を数える。

```yaml
interruption:
  mode: specified
  composition:
    schema_version: multi-interruption-composition-v1
    opportunity_policy: all_core_offered
    branching_policy: pass_or_one_activation_per_core_request
    priority_policy: ascending_priority_then_definition_id
    opponent_action_scope: specified_sources_only
  definitions:
    - id: first_hand_source
      priority: 10
      max_activations: 1
      source_card_code: 2511
      source_player: 1
      source_zone: hand
      response_roles: []
    - id: second_hand_source
      priority: 20
      max_activations: 1
      source_card_code: 97268402
      source_player: 1
      source_zone: hand
      response_roles: [target]
```

同じ`id`、同じ`priority`、または同じ`source_card_code/source_player/source_zone/core_location/sequence` authorityを複数definitionへ割り当てることは禁止する。異なるpolicyで同一sourceを区別する機能はv1に含めず、`ambiguous_source_authority`としてconfiguration failureにする。

## Opportunity and branch semantics

`select_chain`でcoreが提示したcandidateのうち、指定source authorityと一致し、`max_activations`未到達で、support taxonomyを通過したcandidateを全て独立したactivation opportunityにする。priorityはcandidateのsemantic commit順を決めるだけで、低priorityの枝を削除しない。

1 requestの枝は、coreが提示したPASS/decline Actionを1本と、各supported activation candidateを1本ずつ持つ。definitionごとの重複PASSは作らない。同じsourceから複数effect candidateが提示された場合もcandidateごとに別枝とする。一つのActionへ複数activation candidateを混在させない。

PASSはactivation countを増やさない。`max_activations`到達後はそのdefinitionの新しいactivation枝を抑止するが、他definitionとPASSは残す。once-per-turn、source移動、発動可能性、同一chain/別chainの可否は、次のcore requestにcandidateが存在するかだけで判定する。

## Response ownership

activation Actionを選択した時点で一つのactive response lineageを作る。lineageが要求する`response_roles`を順に消費し終えるまで、別definitionへresponse requestを帰属させない。各responseはrequest type、player、constraints、選択candidateを保存する。

指定candidateがfresh Replayで消失した場合は`candidate_disappeared` path failure、request type/player/constraintsが変わった場合は`response_contract_mismatch` path failure、複数definitionへ一致した場合は`ambiguous_definition_match` configuration failureとする。候補消失や曖昧な対応をPASSまたは成功Routeへ変換しない。

## State machine

| State | Input | Next state | Evidence |
|---|---|---|---|
| `idle` | core activation candidates | `opportunity_offered` | request signature、candidate IDs、definition IDs |
| `opportunity_offered` | PASS | `idle` | shared PASS Action、unchanged activation counts |
| `opportunity_offered` | activate | `responding`または`resolved` | opportunity ID、Action occurrence、fork step |
| `responding` | expected response | `responding`または`resolved` | role index、request、response Action |
| `resolved` | next core request | `idle` | chain index、post-state identity |
| any | candidate/request mismatch | `path_failed` | version付きfailure code、最初の差分 |
| any | unsupported taxonomy | `configuration_failed` | taxonomy category、support registry version |

## Lineage and cross-validation

各opportunityはcomposition ID、definition ID、occurrence index、request signature、candidate ID、prefix Action IDsからcontent IDを作る。interrupted Routeはbaseline Route、fork step、selected opportunity、activation Action、response Actions、post-resolution stateを保持する。recovery Routeは対応するinterrupted Routeをparentにする。

baseline/interrupted/recoveryの比較では、fork前prefix、fork request、提示candidate集合、選択Action、response sequenceをfresh Replayで再計算する。fork前の不一致、candidate消失、response role差、state transition差は最初のdivergenceとして保存し、成功扱いしない。

## Timing support boundary

damage step、mandatory trigger、simultaneous trigger ordering、SEGOC、activation negation、effect negation、missed timingは[#123](https://github.com/Tao-pyth/ygo-effect-dsl/issues/123)の機械可読support taxonomyに従う。未検証categoryはcandidateがcoreから提示されてもproduction-supportedとして扱わずfail-closeする。固定fixtureの成功を任意カード裁定へ一般化しない。

## Acceptance vectors

- 2 definitions、逆list順、異なるpriorityでもcomposition IDとcommit順が一致する。
- priority欠落、重複priority、重複ID、重複source authority、0 activation limitをstructured diagnosticで拒否する。
- 同一requestの共有PASSと全activation candidateを重複なく列挙する。
- targetless、cost、single/multi-target、option、hand/field sourceをcore requestだけから処理する。
- 同一chain、別chain、source移動、once-per-turn候補消失をfresh Replayで検証する。
- candidate消失、response mismatch、unsupported taxonomyでartifactを成功publishしない。
