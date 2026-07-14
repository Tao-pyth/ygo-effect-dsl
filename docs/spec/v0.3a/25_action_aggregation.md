# Action Aggregation Specification

Status: API 11.0 lifecycle edges real-core validated; cancel is an unreachable raw contract

Last updated: 2026-07-13

Decision basis: [ADR-0006](../../adr/0006_action_granularity.md)

Validation evidence: `examples/prototype/real_core_action_aggregation.route.yaml`, `docs/ocgcore/evidence/action_aggregation_edges.json`

## Responsibility

Action aggregationは、1 DecisionRequestへの応答である原子的Actionを、人間向けログ、UI、Route差分で扱う複合Actionへ変換する表示専用層である。原子的Action、Replay event、探索edge、妨害座標を置き換えない。

## Input And Grouping

入力は順序付き`replay.events`と、任意の`ActionAggregationHint(step, group_key, role)`である。同じ`group_key`を持つ連続イベントだけを1つの複合Actionへまとめる。離れた範囲で同じkeyを再利用した場合はfail-closeする。

roleは`primary`, `cost`, `target`, `option`, `selection`, `resolution`, `control`とする。明示ヒントがない場合、Action kindと明確なprotocol request typeからroleを保守的に分類する。ただしgroupは推測せず、各イベントを単独groupとする。`select_card`がcostかtargetかをカードテキストから推測してはならない。

実コアRouteでは`ACTIVATE_EFFECT`応答をactivation setup groupの開始とし、その応答以降に続くDecisionRequestを、raw core frameの`MSG_CHAINED`またはcancelable requestへの`DECLINE`まで同じgroupへ含める。cancelは`control` roleで記録し、`MSG_CHAINED`を捏造しない。分類根拠は次に限定する。

- `primary`: atomic Action kindが`ACTIVATE_EFFECT`。
- `cost`: 選択したcard refと一致する`MSG_MOVE`が応答後frameにあり、reasonが`REASON_COST` bitを持つ。
- `target`: 要求直前の同一batchに、同じplayer向け`MSG_HINT(HINT_SELECTMSG, HINTMSG_TARGET)`がある。
- `option`: request typeがAPI v11の`select_option`等、protocol上optionと一意に分かる型である。

`HINTMSG_DISCARD`、`HINTMSG_RELEASE`等は操作目的であり、cost callbackを証明しないため単独ではcostにしない。上記根拠がない`select_card`は`selection`とし、group外のhintなしイベントは単独groupとする。effect解決中のselectionはactivation setupと非連続であり、`MSG_CHAIN_SOLVING`を根拠に別groupへ分離する。

`MSG_CHAIN_SOLVING`後、`MSG_CHAIN_SOLVED`または`MSG_CHAIN_END`より前にcoreがDecisionRequestを返した場合は、連続する応答を別のresolution groupへまとめ、roleを`resolution`とする。同一response batch内でsolvingからsolved/endまで完了し、その後に次requestがある場合はresolution groupを作らない。`MSG_CHAIN_DISABLED`、`MSG_CHAIN_NEGATED`、対象消失などで解決時selectionがなければ、後続Actionを直前のactivation groupへ含めない。

## Traceability

各複合Actionは次を持つ。

- `composite_id`: ordered `action_occurrence_ids`から生成する表示group ID
- `comparison_key`: 表示labelを除いた原子的Action、role、選択内容から生成するRoute差分key
- `atomic_steps`, `action_ids`, `action_occurrence_ids`
- ordered `parts`
- role別に展開した`costs`, `targets`, `options`, `selections`

`links`は各Replay stepと`action_occurrence_id`を、`composite_id`とgroup内`part_index`へ対応付ける。すべてのReplay eventはちょうど1つのgroupとlinkに現れなければならない。

## Display Data

各選択は`candidate_id`, candidate `label`, `kind`, `order`, `value`, `card_ref`, `effect_ref`を表示できる。labelは表示専用であり、`comparison_key`と原子的`action_id`へ含めない。cost/target/optionの区分はroleから作り、効果テキスト解析では作らない。

## Route Diff

`diff_action_aggregations`は複合Actionの`comparison_key`列を比較し、`equal`, `replace`, `insert`, `delete`の範囲を返す。1つの効果に属するcost/target/optionの変更は、明示groupがある場合に1つの複合Action差分として現れる。差分結果は表示・分析用であり、Replay同一性判定には使わない。

## Route DSL

派生結果は`presentation.action_aggregation`へ保存できる。`presentation`は`route_id`のidentity inputから除外し、Replayから再生成可能とする。実コアRouteは`action_aggregation_evidence`にroleごとのframe index、message type、reason/hint値、chain lifecycle、group境界、fallback step、canonical evidence IDを保存する。Route DSL validatorはschema version、groupの連続性、Action参照、全イベントcoverage、link整合性に加え、validated表示された集約と証跡をraw Replayから再計算して完全一致を要求する。

API 11.0では`MSG_HINT=10 bytes`、`MSG_MOVE=28 bytes`、`MSG_CHAINING=32 bytes`、`MSG_CHAINED/SOLVING/SOLVED/NEGATED/DISABLED=1 byte`、`MSG_CHAIN_END=0 bytes`を固定する。既知frameの長さ不一致、未知API version、未完了activation/resolution groupはfail-closeする。version別statusは`action_aggregation_compatibility_report()`を真実源とする。

## Acceptance Criteria

- 集約前後の全対応関係を`groups`と`links`で追跡できる。
- cost、target、optionの選択を表示できる。
- 複合Action単位のRoute差分を生成できる。
- 表示集約がReplay、探索、Route IDの意味を変更しない。
- 根拠がない分類は`selection`へfallbackし、cost/targetを推測しない。
- cancel、fizzle/disable、複数selection、resolution-time selectionでもatomic Replayと妨害座標を変更しない。

## Contract Tests

- `test_aggregation_tracks_atomic_mapping_and_display_roles`
- `test_aggregation_is_conservative_without_group_hints`
- `test_composite_action_diff_reports_one_group_replacement`
- `test_aggregation_rejects_non_contiguous_group_key`
- `test_ocgcore_lifecycle_derives_cost_target_and_option_roles`
- `test_ocgcore_lifecycle_does_not_treat_discard_hint_as_cost`
- `test_cancelled_activation_closes_group_and_preserves_atomic_replay`
- `test_fizzled_chain_does_not_absorb_following_action`
- `test_multiple_chain_links_and_negation_keep_separate_boundaries`
- `test_multiple_cost_selection_requests_remain_one_activation_group`
- `test_resolution_time_selections_form_a_separate_group`
- `test_api_and_known_frame_layout_changes_fail_closed`
- `test_fixed_edge_evidence_matches_fresh_recalculation`
- `test_action_aggregation_fixture_derives_core_lifecycle_roles`
