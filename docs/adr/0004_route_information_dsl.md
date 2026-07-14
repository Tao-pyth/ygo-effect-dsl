# ADR-0004: DSLをルート情報のデータ契約として定義する

Status: Accepted

Date: 2026-07-13

## Context

本プロジェクトの目的は、カードテキスト変換ではなく、展開探索、妨害耐性、リカバリ、デッキ比較を再現可能にすることである。カードごとの効果は既存のEDOPro Luaに実装されており、ocgcoreが合法手判定と状態遷移を実行できる。Python側でカード効果DSLを再構築すると、二重実装と裁定差異が生じる。

一方、探索結果には、人間と機械の双方が扱える安定した交換形式が必要である。Replayだけでは、Peak Board、評価内訳、妨害分岐、親ルート、比較結果を十分に表せない。

## Decision

本プロジェクトで「DSL」はRoute Information DSLを意味する。

Route DSLは、ocgcore / EDOPro Lua由来の実行結果を基に、実験条件、Replay、チェックポイント、Peak Board、Terminal Board、評価、妨害、lineageを記録する。Route DSLはカード効果を記述・実行せず、合法手や状態遷移を判断しない。

旧v0.0カードテキスト変換物は `legacy card-text artifact` と呼び、無修飾のDSLという名称から除外する。既存コマンドは移行期間の互換機能としてのみ扱う。

## Consequences

- EDOPro Luaの既存カード資産を真実源として全カード対応を目指せる。
- Pythonの責務を探索、Replay、評価、比較、集計へ集中できる。
- 同じReplayを異なる成功条件や評価器で再評価できる。
- 妨害なしルートとリカバリルートをlineageで比較できる。
- DSL仕様はカード効果語彙ではなく、Route、Action、State、Evaluation、Experimentの契約変更に応じてversioningする。
- 旧カードテキスト変換コードと文書は、削除まで明確にlegacy名で隔離する必要がある。

## Rejected Alternatives

- カード効果テキストをPython DSLへ変換し、探索エンジンの入力にする。
- EDOPro LuaをRoute DSLへ機械変換してPythonで実行する。
- Replayだけを保存し、評価、Peak Board、妨害分岐を外部の非構造化ログに置く。
- 人間向けMarkdownを唯一のルート保存形式にする。
