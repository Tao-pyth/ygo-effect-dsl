# Additional Card Attribution

Status: v1 frozen / v2 implemented

Last updated: 2026-07-14

## Purpose

additional-card attributionは、妨害後の成功を特定カードへ因果帰属する。単一Routeの盤面差ではなく、同じcore、seed、評価条件で次の4 Routeを比較する。

| 条件 | 追加カードなし | 追加カードあり |
|---|---:|---:|
| control | success | success |
| interrupted | failure | success |

追加カードありcontrolも成功することを確認し、追加カード自体が通常展開を壊していないことを検査する。interrupted Routeは各control Routeのversion付きAction occurrenceから分岐し、別条件のbase Routeを流用しない。

## Versions

v1は`additional-card-attribution-v1`と`card-instance-provenance-v1`である。candidate scope内でcard codeが一意の場合だけ利用し、同一コード複数枚は`reject_ambiguous`で停止する。既存関数、Route、goldenは変更しない。

v2は`additional-card-attribution-v2`と`card-instance-provenance-v2`である。`build_additional_card_attribution_v2()`は初期snapshotの`persistent_instance_id`、Actionの`CardRef.instance_id`、usage evidenceを照合し、同一コード複数枚を個体IDで区別する。matching methodは`ocgcore-card-id-authority-v2`、duplicate policyは`compare_persistent_instance_id`である。

## Minimal Sets

`minimal_required_sets`は、interruptedで成功したcandidate集合のうち、評価済みの全proper subsetが失敗した集合だけを含む。proper subsetのRouteが不足する場合は`insufficient_subset_coverage`とし、最小集合を推測しない。候補は固定手札の末尾へ追加し、既存カードの順序を変えない。

## Provenance

origin taxonomyは`fixed_opening_hand`、`draw`、`search`、`salvage`、`generated_token`、`opponent`である。v2 movement ledgerはdeck→handと同batchの`MSG_DRAW`からdrawを判定し、`MSG_DRAW`なしをsearch、grave→handをsalvageとする。曖昧な移動は分類しない。

v2 reportへ含めるのはcandidate provenanceだけであり、相手hidden card一覧、raw ocgcore `cardid`、instrumentation logは含めない。現行attributionは因果比較のため`complete_information`を要求し、それ以外はfail-closeする。

## Evidence

- v1 golden: `tests/golden/additional_card_attribution_v1.json`
- v2 golden: `tests/golden/additional_card_attribution_v2.json`
- v2 fresh-worker evidence: `docs/ocgcore/evidence/card_instance_route_v2.json`
- v2 movement evidence: `docs/ocgcore/evidence/card_instance_movement_v2.json`

v2 evidenceのattribution IDは生成物内でcanonical検証する。4 Routeを独立processで2回再生成し、Action ID、State hash、Route ID、provenance ID、attribution IDの一致を要求する。
