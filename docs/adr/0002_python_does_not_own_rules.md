# ADR-0002: Python はルールを持たない

Status: Accepted

Date: 2026-07-13

## Context

Project Charter は、遊戯王 OCG のルール、合法手判定、状態遷移、Lua 実行の真実源を ocgcore / EDOPro Lua に置くと定めている。

Python 側にルールを増やすと、短期的には動く検証コードを作りやすい。しかし、カードごとの例外、タイミング、チェーン、優先権、置換効果、裁定差分を Python に再実装し始めると、ocgcore と異なる独自ルールエンジンになり、長期的な正当性を失う。

## Decision

Python は遊戯王ルールを所有しない。

Python が担当してよいのは、Replay、探索制御、評価、統計、実験制御である。既存の DSL 変換、Action / Target 抽出は legacy 互換機能であり、探索エンジンの入力や Action 生成元として扱わない。

Bridge は ocgcore Message と Python Action の変換を担当するが、合法性や状態遷移を判断しない。

V0.1 の state/action semantics は過去の候補表現であり、現在の engine boundary ではない。V0.2 以降は ocgcore / EDOPro Lua 由来の Bridge 入力を優先する。

## Consequences

採用する結果:

- ルール正当性の基準を ocgcore / EDOPro Lua に集中できる。
- Python 実装は探索、評価、再現性、分析に集中できる。
- v0.0 / v0.1 の DSL を engine 入力から外し、ocgcore / EDOPro Lua 由来の Bridge 入力に集中できる。
- 状態遷移の説明は可能だが、Python-only executor を正式ルールとして扱わない。

採用しない選択:

- Python 側にカード処理や合法手判定を実装する。
- v0.0 semantics を State -> State の実行仕様として扱う。
- Bridge にルール判断を持たせる。

## Notes

Python で許容される「rule」は、既存 legacy DSL CORE 内の変換辞書や pattern matching rule に限る。これらはゲームルールとは明確に区別し、新規探索エンジン設計の根拠にしない。
