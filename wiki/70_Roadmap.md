# Roadmap

このページは、`ygo-effect-dsl` の現在地と今後の進め方をまとめた補助資料です。最上位方針は [Project Charter](../docs/00_project_charter.md)、正式なロードマップは [docs/20_roadmap.md](../docs/20_roadmap.md)、詳細な仕様変更は [Changelog](../docs/spec/v0.0/50_changelog.md) を参照してください。

## 現在の焦点: V0.1 baseline から V0.2 Bridge / Replay へ

V0.1 で Project Charter、Architecture、README、V0.1 spec を整備し、プロジェクトを「ゲームエンジン + AI 探索」へ進める設計基盤として確立しました。

次の焦点は V0.2 の Bridge / Replay baseline です。

V0.2 の主な作業は次の通りです。

- Replay を基準実装にする ADR を追加する
- Python がルールを持たない方針を ADR として固定する
- Bridge / Replay の仕様書を追加する
- Minimal Replay model を実装する
- Bridge interface / mock adapter を実装する
- Replay round-trip smoke test を追加する

## 廃止対象として残る v0.0 基盤

v0.0 の目的は、transform 出力を測定可能で信頼できる形にすることでした。現在はエンジン入力ではなく、互換維持のため一時的に残る legacy / deprecated / removal target です。

- DSL grammar を現在の transform 出力と同期する
- `actions[]` を legacy DSL 内の canonical action 表現として安定させる
- `targets[]` と `target_id` の関係を検証できるようにする
- validation severity を `error` / `warning` / `info` に分ける
- analyze で action coverage、target 解決率、warning 件数を追えるようにする
- 代表カードの golden test で回帰を検知する

## V0.3 以降の候補

V0.3 以降では、Search と Evaluation の最小垂直スライスへ進みます。

- Random Search
- END_TURN action
- Peak Board tracking
- State Evaluation prototype
- route logging

Beam Search、MCTS、妨害注入、Recovery 探索はさらに後の段階で扱います。

## 当面やらないこと

現時点では次の領域を意図的にスコープ外にしています。

- API fetching
- image downloading
- ETL SQLite への直接依存
- Python による遊戯王ルール再実装
- ocgcore 実接続
- 完全な chain / stack simulation
- 完全な相手ターン・相互作用のモデリング
