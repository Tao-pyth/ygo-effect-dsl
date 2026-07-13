# ADR-0003: DSL CORE を探索エンジンから除外し廃止対象にする

Status: Accepted

Date: 2026-07-13

## Context

このリポジトリは、v0.0 までカード効果テキストを DSL 化し、`actions[]`、`targets[]`、diagnostics、analyze metrics を観測する研究基盤として進んできた。

しかし Project Charter は、遊戯王 OCG のルール、合法手判定、状態遷移、Lua 実行の真実源を ocgcore / EDOPro Lua に置くと定めている。DSL 由来の Action / Target 抽出を探索エンジンの入力、補助分析、または Action 生成の根拠として残すと、Python 側にカード効果解釈が再侵入する。

## Decision

DSL CORE は探索エンジンの前段、補助分析基盤、Action 生成元として扱わない。

既存の DSL CLI / transform / validate / analyze / golden tests は互換維持のため一時的に残すが、位置付けは legacy / deprecated / removal target とする。

探索エンジンの実行系入力は、ocgcore / EDOPro Lua 由来の Message / DecisionRequest を Bridge が変換したものに限定する。

## Consequences

採用する結果:

- Python 側でカード効果テキストを実行意味へ変換する経路を本流から排除できる。
- Bridge / Replay / Search / Evaluation の実装は DSL CORE に依存しない。
- DSL 関連コードを削除する破壊的変更の理由を明確に追跡できる。
- v0.0 / v0.1 の DSL 仕様は過去の実験記録として扱い、新規設計判断の根拠にはしない。

採用しない選択:

- DSL CORE を engine の入力基盤として維持する。
- DSL CORE を補助分析モジュールとして推奨する。
- DSL `actions[]` / `targets[]` から探索用 Action を生成する。
- DSL の minimal semantics を Bridge / DecisionRequest の仕様根拠にする。

## Notes

今回の判断は物理削除ではない。削除は V0.2 Bridge / Replay baseline が安定した後の破壊的変更で実施する。

削除までの間も、DSL CORE は実行系、合法手判定、Action 生成の真実源として使ってはならない。
