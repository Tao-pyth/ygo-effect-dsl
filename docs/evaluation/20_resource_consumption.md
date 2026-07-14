# Resource Consumption v1

Status: Implemented with provisional weights

Last updated: 2026-07-13

## Purpose

`resource_consumption_v1`は、Routeの初期Stateから選択した`peak_board`または`terminal_board`までに消費した資源を、Route自身から再計算する評価指標である。外部から順位だけを注入せず、入力State、対象checkpoint、設定、evaluator version、計算項をreportへ保存する。

## Truth Source

スカラー値の真実源は、実コアquery由来の初期snapshotと対象checkpointの正味State差分、および対象stepまでのAction使用回数である。Action aggregationの`cost` roleはコスト選択の監査証拠として保存するが、スカラーへ直接加算しない。たとえば手札をコストとして墓地へ送った場合、`hand_net_decrease`と`graveyard_net_increase`と`explicit_cost_cards`が同時に観測されるが、手札減少だけをスカラーへ加算して二重計上を防ぐ。

perspective playerごとのvectorは次を保持する。

- 正味減少: deck、hand、monster zone、spell/trap zone、Extra Deck
- 正味増加: graveyard、banished
- 使用量: normal summon、special summon action
- 損失: Life Point
- 監査値: validated action aggregationから得たexplicit cost cardsと移動元

## Scalar v1

既定値は次の線形和である。

| Dimension | Weight | v1での扱い |
| --- | ---: | --- |
| `hand_net_decrease` | 1 | 加算 |
| `extra_deck_net_decrease` | 1 | 加算 |
| `life_point_loss` | 0.001 | 1,000 LPを1単位として加算 |
| `normal_summon_uses` | 1 | 加算 |

deck減少はdrawとコストを区別できず、graveyard/banished増加は移動元の減少と重複するため、v1 scalarから除外する。field上の正味減少、special summon回数、explicit cost cardsもvectorには残すが、価値モデル未校正のため加算しない。

## Missing Policy

初期snapshotに`zones`と`field_state`がなく、対象checkpointに全zone countとLPがないRouteは推測しない。Route正規化は`unavailable_missing_measurement`と`route_lacks_recalculable_resource_inputs`を返す。通常召喚権残数、once-per-turn残数、公開情報の価値は現行query/APIまたは価値モデルから確定できないため、reportの`unavailable_dimensions`に明示する。

## Versioning and Recalculation

評価器は`route_resource_consumption` version `1`、schemaは`route-resource-consumption-v1`である。重みを含むconfig hashと入力State hashから`resource_report_id`を生成する。重みや意味を変更する場合はevaluator versionを更新し、旧reportを黙って再解釈しない。

固定evidenceは次で再生成する。

```bash
python -m ygo_effect_dsl.spikes.resource_consumption_evidence --out docs/evaluation/evidence/resource_consumption.json
```

evidence IDは`resourceevidence_e9dad86006758d9c2fa6492d8291555b944ef85b5b14d9f860df76f10f64345b`である。

現行重みは代表Routeの算術と二重計上防止を検証した暫定値である。複数デッキ、同一Stateへ至る代替Route、人手によるblind順位との相関校正はIssue #108で検証する。
