# ADR-0002: Why State-Transition Model?

- Status: Proposed
- Date: YYYY-MM-DD

## Context
遊戯王カード効果は、盤面（状態）を変化させるルールとして捉えられる。
初動や展開の列挙には「状態遷移」モデルが自然である。

## Decision
DSLの意味論（Semantics）は、State → State の遷移として定義し、探索（bounded search）を前提とする。

## Consequences
- 展開列挙や到達可能状態の分析が可能になる
- チェーン/相手介入は段階的拡張として扱える
