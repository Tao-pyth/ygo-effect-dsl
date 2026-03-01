# ygoEffectDSL Spec v0.0 — Pattern Matching Pipeline

> Status: Draft (Experimental)  
> 本文書は v0.0 における **正規化後テキスト** から DSL へ埋めるための、
> パターンマッチング手順と優先順位を定める。  
> Last updated: 2026-03-01

---

# 1. 解析順序（確定）

v0.0では以下の順序でパターンマッチを実行する。

① Global restriction 抽出（カード全体制限）  
② `;` と `:` による骨格判定（cost→action / condition→action）  
③ cost辞書 → action辞書（actionは target/sequence を許可）  
④ trigger / condition辞書（最後に当てる。埋まらなければ空）  

---

# 2. Global Restriction（カード全体制限）

カード全体に掛かる制限（例: once per turn / once per duel）は、
effects には入れず `meta.restrictions.global` に集約することを推奨する。

例:
`You can only use each effect of "X" once per turn.`

出力例:
```yaml
meta:
  restrictions:
    global:
      once_per_turn:
        scope: "each_effect"
        key: "each_effect_of_card"
        card_name: "X"
```

---

# 3. 骨格判定（Structure Inference）

## 3.1 `A ; B`（コスト→解決）
- A → cost候補（cost辞書の入力）
- B → action候補（action辞書の入力）

## 3.2 `if A : B`（条件→解決）
- A → trigger/condition候補（④で解析）
- B → action候補（③で解析）

---

# 4. cost辞書

入力: 文字列断片（骨格判定で cost 側と判断された部分）  
出力: costオブジェクト（任意の自由構造、空オブジェクト可）

原則:
- 未解析でも `{}` を保持（失敗しても停止しない）
- 抽出した数値や固有名は、正規化パラメータ（meta.norm.params）と整合させる

---

# 5. action辞書（target / sequence 許可）

入力: 文字列断片（骨格判定で action 側と判断された部分）  
出力: actionオブジェクト。v0.0では次を許可する：

- `action.target`：対象選択を表す
- `action.sequence`：複数アクションの連鎖を表す（配列）
  - `condition: "if_previous_success"` など、連鎖条件の最小表現を許可

出力例（target）:
```yaml
action:
  target:
    n: 1
    desc: "White Forest Synchro Monster"
    location: ["field", "GY"]
  type: "return_to_extra"
```

出力例（sequence）:
```yaml
action:
  sequence:
    - type: "return_to_extra"
      target:
        n: 1
        desc: "White Forest Synchro Monster"
        location: ["field", "GY"]
    - type: "special_summon"
      who: "self"
      condition: "if_previous_success"
    - type: "negate_effects"
      target: "self"
```

---

# 6. trigger / condition辞書

最後に適用する。
- if/when/while/during などの節を解析対象とする
- 未解析の場合は `{}` のまま保持する（停止しない）

trigger最小拡張（modes許可）例:
```yaml
trigger:
  type: "summon"
  modes: ["normal", "special"]
```

---

# 7. 設計原則

- 失敗しても DSL 生成は止めない（部分成功を許容）
- キー欠落を発生させない（空値で保持）
- 解析結果・警告は meta に残す（再現性・改善に必須）
