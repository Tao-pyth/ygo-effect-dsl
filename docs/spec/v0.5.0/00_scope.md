# Package 0.5.0 Scope: Corpus Analytics and UI

Status: Released source milestone; parent [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133)

Last updated: 2026-07-14

## Objective

package `0.5.0`は、version付きSearch/Replay evidenceを大規模corpusとして取り込み、長時間job、比較API、Route drill-down、統計UIから再現可能に調査できるstageである。新しいルール判断は追加せず、`0.4.0`までのsemantic結果を失わずに保存・集計・比較する。

## Confirmed UI product baseline

- 最重要操作は探索実行とデッキ統計。
- first screenはデッキ一覧。
- primary flowは`デッキ一覧 -> デッキ詳細/統計 -> 探索実行フォーム -> job/result`。
- card detailとeffect textを表示する。
- delivery surfaceはWindows desktop application。
- visual directionはdenseでscan可能な研究・検証dashboard。

詳細契約は[desktop UI requirements](15_desktop_ui_requirements.md)を正本とする。

## Entry criteria

- `0.4.0`のRandom/Beam/MCTS、PlayerView、複数妨害、複数turnがversion付きevidenceを出す。
- private情報のretain/redact/reject規則をserver/export/UIでも再利用できる。
- baseline/interrupted/recovery lineageに機械可読な対応keyがある。
- qualified corpusを生成するcore/asset/deck/search identityがmanifestへ揃っている。

## In scope

1. aggregation catalog/storageとschema evolutionのADR。
2. corpus manifest、provenance、deduplication、quarantine。
3. background job state machine、lease、heartbeat、cancel、retry、checkpoint。
4. pagination/filter付きanalytics query API。
5. Route comparison、missing pair、partial budget、uncertainty semantics。
6. Parquet partition、compaction、migration、atomic snapshot。
7. deck catalog、deck statistics、card detail/effect text、search launch workflow。
8. corpus/run/deck/strategy/interruption comparisonとRoute drill-down UI。
9. Windows desktop shell/Python service境界のADR。
10. large table virtualization、accessibility、desktop window verification。
11. JSON/CSV/Parquet exportとCLI/API/UI parity。
12. 10万run/100万row規模のingest/query/UI/export benchmark。

## Out of scope

- storage engine選定前のproduction data migration
- arbitrary distributed schedulerまたはmulti-region運用
- 勝率、因果、confidenceを証跡なしに自動推論すること
- private情報を集計時に再導出すること
- effect textを合法性、timing、探索candidate、評価の根拠にすること
- card text、CDB、画像をlicense review前にdesktop artifactへ同梱すること
- public distributionまたはproduction SLA

## Principles

- raw evidenceはimmutableとし、derived aggregateからrawを上書きしない。
- source不明、schema不明、hash不一致、partial/corrupt artifactを集計へ混入させない。
- comparison不能を`0`、失敗、欠損なしとして表示しない。
- API、CLI、UI、exportは同じquery/comparison serviceを使う。
- UIは運用・調査用途のため、deck-firstでdenseかつscan可能なtableとlineage中心にする。
- presentation metadata/text providerをreal-core rule data providerと分離する。
- storage/frameworkは[#157](https://github.com/Tao-pyth/ygo-effect-dsl/issues/157)のworkload evidence前に確定しない。
- desktop shellは[#181](https://github.com/Tao-pyth/ygo-effect-dsl/issues/181)、card text境界は[#183](https://github.com/Tao-pyth/ygo-effect-dsl/issues/183)のevidence前に確定しない。

## Delivery claim

`0.5.0`完了時に許される主張は「qualified Search/Replay corpusをprovenance付きで再取込・再集計し、CLI/API/UIから同じ比較結果とRoute lineageを調査でき、測定済み規模でjobをcancel/retry/recoverできる」である。統計結果を勝率や因果推論として一般化しない。

実装、local scale gate、package metadata、source tagは2026-07-16に完了した。固定workloadは10万run、100万Event/Decision row、10万aggregation rowであり、詳細は[production scale calibration](23_production_scale_calibration.md)を正本とする。一般配布、署名、更新、production運用は#91/#134を完了するまで主張しない。
