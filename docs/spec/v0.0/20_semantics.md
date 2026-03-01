# ygoEffectDSL Spec v0.0 (Draft) — Semantics

> Status: Draft (Experimental)
> 本文書は DSL の**意味論（Semantics）**を定義する。
> Grammar（構文）は 10_grammar.md を参照。

---

# 1. 意味論の目的

本仕様の目的は、カード効果を

> **状態遷移系 (State Transition System)**

として形式化することである。

すなわち、効果は

    State × Effect → State

の写像として定義される。

---

# 2. 基本集合と記法

## 2.1 状態空間

状態の集合を S とする。

    S = { s | s は有効な盤面スナップショット }

各状態 s ∈ S は以下の要素を持つ：

    s = (Deck, Hand, Field, Graveyard, Banished, Extra, Flags)

ここで：

- Deck, Hand, Field, Graveyard, Banished, Extra は有限集合
- Flags はターン制限や一時効果の状態を保持する有限集合

v0.0 では相手プレイヤーの状態は含まない（単一プレイヤーモデル）。

---

## 2.2 効果集合

効果の集合を E とする。

各効果 e ∈ E は以下のタプルで表される：

    e = (trigger, restriction, condition, cost, action)

---

# 3. 適用可能性（Applicability）

ある状態 s において効果 e が適用可能であることを

    applicable(e, s)

と定義する。

v0.0 においては：

    applicable(e, s) =
        trigger_ok(e, s)
    ∧   restriction_ok(e, s)
    ∧   condition_ok(e, s)
    ∧   cost_payable(e, s)

---

# 4. 遷移関数

遷移関数 δ を次のように定義する。

    δ : S × E → S

ただし、

    δ(s, e) = apply_action(pay_cost(s, e), e)

とする。

評価順序は以下：

1. trigger 判定
2. restriction 判定
3. condition 判定
4. cost 処理
5. action 処理

---

# 5. 非決定性（Non-Determinism）

対象選択やランダム性がある場合、遷移は一意ではない。

このとき：

    δ : S × E → P(S)

（P(S) は S の冪集合）

すなわち、

    δ(s, e) = { s1, s2, ... }

となる。

v0.0 ではランダム性は扱わないが、
将来的拡張のために非決定性を許容する構造を前提とする。

---

# 6. 状態遷移系（Transition System）

DSL により定義されるゲーム構造は、

    T = (S, E, δ)

という遷移系として扱う。

探索は以下の形式で行う：

    s0 ∈ S（初期状態）
    Explore(T, s0, depth ≤ k)

---

# 7. 探索モデル（v0.0）

v0.0 の探索は以下の制約を持つ：

- 自ターンのみ
- 相手レスポンス無し
- チェーン未実装
- 深さ制限探索（bounded search）

アルゴリズム例：

- BFS
- DFS
- 深さ優先＋状態ハッシュによる重複除去

---

# 8. 同型状態（State Equivalence）

2つの状態 s1, s2 が同型であることを

    s1 ≈ s2

と定義する。

将来、探索爆発を抑制するため、

    s1 ≈ s2 → 同一状態として扱う

という最適化を導入予定。

---

# 9. 将来的拡張（v0.1+）

## 9.1 チェーン（Stack）

将来は状態を：

    s = (..., Stack)

と拡張する。

この場合、遷移は二段階となる：

1. 効果の積み上げ
2. スタック解決

---

## 9.2 対戦相手の導入

将来は状態を：

    s = (SelfState, OpponentState, TurnInfo)

と拡張する。

このとき遷移は交互遷移系となる：

    δ_self
    δ_opponent

---

## 9.3 制約充足・最適化

将来、以下を導入可能：

- 制約ソルバー
- 最短経路探索
- 到達可能性解析
- 不動点計算

---

# 10. 正しさ（Correctness）

DSL意味論の正しさは以下の観点で評価される：

1. 再現性（同一入力→同一出力）
2. 完全性（テキストの主要意味を落とさない）
3. 拡張可能性（新機能を追加可能）

---

# 11. v0.0 の制限

- チェーンなし
- 相手介入なし
- ランダム性なし
- 優先権処理なし

これらは段階的に拡張予定。

---

# 12. まとめ

ygoEffectDSL v0.0 は、

    「カード効果を状態遷移として形式化する」

ための最小意味論である。

これは将来的に：

- 完全ルール近似
- 探索最適化
- グラフ解析
- 理論的証明

へ発展可能な基盤である。
