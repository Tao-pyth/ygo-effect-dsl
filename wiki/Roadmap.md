# Roadmap

このページは、`ygo-effect-dsl` の現在地と今後の進め方をまとめたものです。詳細な仕様変更は [Changelog](../docs/spec/v0.0/50_changelog.md) を参照してください。

## 現在の焦点: v0.0 stabilization

v0.0の目的は、transform出力を測定可能で信頼できる形にすることです。

主な作業は次の通りです。

- DSL grammarを現在のtransform出力と同期する
- `actions[]` をcanonical action表現として安定させる
- `targets[]` と `target_id` の関係を検証できるようにする
- validation severityを `error` / `warning` / `info` に分ける
- analyzeでaction coverage、target解決率、warning件数を追えるようにする
- 代表カードのgolden testで回帰を検知する

## Milestone A: v0.0 spec sync

仕様と実装のずれを減らす段階です。

- `card.info` をDSLから外し、compactな `card.props` に寄せる
- `effects[]` の必須キーを明確にする
- `actions[]`、`targets[]`、diagnosticsの仕様を文書化する
- 仕様変更時に changelog を更新する運用を定着させる

## Milestone B: representative-card benchmark

代表カードを使って、変換品質を継続的に観測できるようにします。

- 代表カードデータセットを整備する
- action type coverageを追う
- target抽出の成功・失敗を見えるようにする
- unmatched fragmentを改善対象としてランキングする

## Milestone C: golden test + diagnostics

出力の意図しない変化を検知し、変化の理由を説明できる状態にします。

- representative-card golden testを維持する
- `unknown_action`、`unresolved_target`、`missing_selector` を改善TODOとして扱う
- `legacy_action_fallback` を減らし、`actions[]` へ移行する
- validate CLIの出力を人間にも機械にも読みやすくする

## Milestone D: analyze coverage dashboard

analyzeのレポートを、変換改善の意思決定に使える形へ育てます。

- action type別の件数を追う
- target reference resolution rateを追う
- validation severity/code countsを追う
- 変換辞書やpattern matchingの改善効果を比較する

## Milestone E: v0.1 minimal state/action semantics

v0.1では、最小限の状態モデルとaction意味論へ進みます。

想定するStateの構成:

- `Deck`
- `Hand`
- `Field`
- `GY`
- `Banished`
- `Extra`
- `Flags`

最初に扱うaction候補:

- `draw`
- `add_to_hand`
- `send_to_gy`
- `destroy`
- `special_summon`
- `banish`
- `negate`

## v0.2以降の候補

v0.2以降では、よりゲームらしい相互作用を段階的に扱う可能性があります。

- chain / stack の導入
- opponent state と response の扱い
- bounded search の改善
- state equivalence と探索最適化
- グラフ解析や検証への応用

## 当面やらないこと

v0.0では次の領域を意図的にスコープ外にしています。

- API fetching
- image downloading
- ETL SQLiteへの直接依存
- 完全なchain/stack simulation
- 完全な相手ターン・相互作用のモデリング
