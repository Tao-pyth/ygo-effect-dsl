# Interruption Comparison Metrics

Status: V0.1 implementation contract

Last updated: 2026-07-13

## Scope

`interruption-comparison-v1`は妨害なしbase Routeと、そこから妨害時点で分岐したinterrupted/recovery Routeを比較する派生レポートである。勝敗やPeak Scoreだけでなく、評価vector、妨害数、継続力、各zone、手札、LP、Route長、追加カードevidence、exact Stateへの復帰を別々に保存する。Route DSL 0.1自体は変更しない。

## Preconditions

- 両RouteがRoute DSL validatorを通る。
- child `lineage.parent_route_id`がbase Route IDを参照し、`fork_step`が両Replayに存在する。
- initial snapshot、version metadata、seedが一致する。
- fork前のAction、request signature、State遷移が一致する。
- fork Stateが一致する。
- childのfork stepに妨害記録が1件あり、その`interruption-target-v1`がbase Replayの同じstepへ一意解決できる。

これらを満たさないRouteを数値だけで比較しない。targetの合法性と妨害適用結果はocgcoreが所有し、実コア適用はIssue #95で検証する。

## Metrics

各metricはbefore、after、delta、availability statusを持つ。欠損値を暗黙に0へ変換しない。

- `score`: evaluator ID/version/config hash、information mode、評価時点が一致する場合だけ差分を計算。
- `score_breakdown`: 両Routeに`evaluation-result-v1`がある場合、term寄与差まで保存。
- `evaluation`: 全metric名について差分を保存する。`interruptions`、`follow_up`、`resource_balance`などを特別扱いせずEvaluatorのversion付き定義に従う。
- `goal`: success predicate、information mode、評価時点が一致する場合だけretained/recoveredを判定。
- `resources`: Experiment perspectiveのhand、deck、graveyard、banished、extra deck、monster/spell-trap zone、field total、LPをState snapshotから比較。
- `route_length`: atomic Replay event数の増減。
- `additional_cards`: caller supplied evidenceだけを保存する。自動帰属しない。

Evaluatorまたはsuccess predicateの文脈が異なる場合は値を表示してもdeltaを`null`とし、比較不能statusを返す。
同じexact到達Stateとevaluator文脈でscoreまたはevaluation vectorが異なる場合は、staleな再評価結果または改変として比較を拒否する。`evaluation-result-v1`のevaluator ID/version/config hashもExperimentと一致しなければならない。

## Recovery

fork step以降のchild `state_hash_after`をbase Replayの同区間とexact比較する。

- `original_target_reached`: baseの選択board Stateへ到達。
- `original_route_rejoined`: baseの途中Stateへ再合流したが、選択boardは異なる。
- `goal_only`: exact再合流はないが同じsuccess predicateを満たす。
- `not_recovered`: exact再合流もgoal達成もない。
- `goal_incomparable`: success predicateが異なり、exact再合流もない。

再合流はbase step、recovery step、exact State IDをevidenceとして保存する。board summary一致やscore一致だけでは復帰と判定しない。

## Provisional fields

`interruption-comparison-v1.metrics.additional_cards`は後方互換用の暫定fieldであり、未指定時は`unavailable_not_attributed`、指定時も`caller_supplied_provisional`を返す。このfield単体を因果帰属の根拠にしてはならない。

本検証は`additional-card-attribution-v1`で行う。カードなし/ありの各条件について妨害なし/ありを実coreで再実行する2×2比較、card instance provenance、最小必要集合、公開境界を`docs/interruption/30_additional_card_attribution.md`で定義する。
