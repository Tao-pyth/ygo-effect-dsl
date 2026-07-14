# Route Normalization and Explanation

Status: V0.1 derived analysis contract

Last updated: 2026-07-13

## Boundary

`route-normalization-v2`は複数の検証済みRoute DSL 0.1文書から生成する派生レポートであり、Replay、Route ID、Action ID、到達Stateを書き換えない。同一盤面の統合keyは選択した`peak_board`または`terminal_board`のexact `state_hash`だけである。board summary、score、Action名、近似State keyだけでは統合しない。

同じexact到達Stateへ至るRouteは、Actionの選択順が異なっていても1 groupへ統合する。ただし元Replayは全件保持し、代表Routeへ破壊的に置換しない。代表Routeはatomic Action数、明示的resource cost、Route IDの順で決定し、表示差分の基準としてのみ使う。

## Essential branches

group内の全Routeが`presentation.action_aggregation`を持つ場合は複合Actionの`comparison_key`列を使う。1件でも欠ける場合は全Routeを原子的Action ID列で比較し、比較粒度を混在させない。代表Routeと各代替Routeをsequence diffし、`replace`、`insert`、`delete`ごとにbranch ID、双方のAction範囲、表示label、atomic step、exact到達Stateへの再合流を記録する。

この差分は本質的な選択箇所を人間向けに示す派生情報であり、Replay同一性や合法性を変更しない。同じAction列を持つ重複Routeは同じgroupに残るが、branch pointは発生しない。

## Rankings

レポート全体と各到達盤面groupは、指標を分離して順位を返す。

- `shortest`: Replayのatomic Action数が最小。
- `minimum_consumption`: Route内のState差分から`resource_consumption_v1`で再計算した有限な非負値が最小。
- `highest_score`: evaluator ID/version/config hash、information mode、評価時点が一致する場合だけ最大。

score評価文脈が異なるRouteを数値だけで比較しない。同じexact Stateと評価文脈でscoreが異なる場合は、古い評価値または改変を疑い分析を停止する。

既定のresource consumptionは初期Stateから対象checkpointまでの正味State差分とAction使用回数から再計算する。Action数や検証済みcost role数をスカラー消費量へ直接読み替えない。cost roleは二重計上を検出する監査証拠である。必要なState入力がないRouteは`unavailable_missing_measurement`と`route_lacks_recalculable_resource_inputs`を返す。互換用の`resource_costs`を明示した場合だけ外部測定モードを使う。詳細は[Resource Consumption v1](../evaluation/20_resource_consumption.md)を参照する。重みの実デッキ校正はIssue #108で追跡する。

## Alternatives

各groupは代表Route以外を代替Routeとして列挙し、atomic Action数差、resource cost差、比較可能な場合だけscore差、Action sequence差分を保持する。これにより「同じ盤面だが短い」「同じ盤面だが消費が少ない」「手順だけ異なる」を別の主張として説明できる。
