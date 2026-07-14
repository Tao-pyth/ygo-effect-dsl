# ADR-0003: 旧カードテキスト変換を探索実行系から除外する

Status: Accepted

Date: 2026-07-13

## Context

v0.0ではカード効果テキストをYAMLへ変換し、`actions[]`、`targets[]`、diagnostics、analysis metricsを観測していた。しかし、遊戯王OCGのルール、合法手、状態遷移、Lua実行の真実源はocgcore / EDOPro Luaである。

カードテキストから抽出した候補を探索Actionや補助ルールとして使用すると、Python側へカード効果解釈が再侵入し、Lua実装との二重管理と裁定差異が生じる。

## Decision

旧カードテキスト変換は、探索エンジンの前段、補助ルール分析、Action生成元として扱わない。

既存の `ingest / transform / validate / analyze`、辞書、golden testは移行期間の互換確認用として残せるが、その出力は `legacy card-text artifact` と呼ぶ。現在の無修飾のDSLはADR-0004で定義するRoute DSLを意味する。

探索実行系の入力はocgcore / EDOPro Lua由来のMessage / DecisionRequestに限定する。

## Consequences

- Python側のカード効果再実装を本流から排除できる。
- Bridge / Replay / Search / Evaluation / Route DSLは旧変換へ依存しない。
- v0.0 / v0.1仕様は歴史資料として保持する。
- 旧出力をRoute DSLへrenameまたは自動変換しない。
- 削除までコード、CLI help、文書でlegacy状態を明示する必要がある。

## Removal Gate

実ocgcoreからRoute DSLを生成しReplayできる垂直スライスが成立し、現行runtimeが旧変換へ依存しないことをcontract testで確認した後、旧変換コードを削除できる。
