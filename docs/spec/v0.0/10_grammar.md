# ygoEffectDSL Spec v0.0 (Draft) — Grammar

> Status: Draft (Experimental)  
> 破壊的変更が起こり得る初期仕様。  
> 本文書は DSL の「構文（構造とフィールド）」のみを定義する。  
> 意味論（評価順序や状態遷移）は 20_semantics.md を参照。  
> Last updated: 2026-03-01

---

# 1. 基本方針（Design Principles）

v0.0 の文法設計は以下の原則に基づく：

1. **常にキーを存在させる**
   - 欠損はキー欠落ではなく空値で表現する
2. **構造優先**
   - 意味の正確性よりも、構造化可能性を優先する
3. **最小十分構造**
   - 将来拡張可能な余白を残す（ただし後方互換を壊しにくい形を優先）
4. **DSLは宣言的**
   - 命令列ではなく、効果の構成要素を分解した宣言型表現とする

---

# 2. ルート構造

```yaml
dsl_version: "0.0"

card:
  cid: 0
  name:
    en: ""
    ja: ""
  text:
    en: ""   # 必須（キーは必須・中身は空でもよい）
    ja: ""   # 推奨（枠は常に作り、空でもよい）
  info:
    en: ""   # 必須（キーは必須・中身は空でもよい）
    ja: ""   # 推奨（枠は常に作り、空でもよい）

effects: []

meta: {}
```

---

# 3. ルートフィールド定義

## 3.1 dsl_version (string) — 必須
- 形式: "0.0"

## 3.2 card (object) — 必須
- `card.cid`：Konami ID（int or string）
- `card.name.en / ja`：文字列（欠損時は空文字）
- `card.text.en`：必須（空文字でもキーは必須）
- `card.info.en`：必須（空文字でもキーは必須）
- `card.text.ja / card.info.ja`：推奨（v0.0運用としてはキーは常に作る）

## 3.3 effects (list) — 必須
- 空配列も許可（未解析など）
- 可能なら最低1件（Level0）を生成する

---

# 4. effect オブジェクト構造

各 effect は以下のフィールドを持つ。

| フィールド | 必須 | 型 | 説明 |
|------------|------|----|------|
| id | ✔ | string | `{cid}_{3桁連番}` 推奨 |
| order | ✔ | integer | 効果の順序 |
| trigger | ✔ | object | 発動契機 |
| restriction | ✔ | object | 制限条件 |
| condition | ✔ | object | 発動条件 |
| cost | ✔ | object | コスト |
| action | ✔ | object | 効果解決（v0.0で target / sequence を許可） |

※ v0.0では trigger/restriction/condition/cost/action のキーは必ず存在させる（空オブジェクト可）。

---

# 5. 構成要素の最小構文（v0.0）

## 5.1 trigger（最小 + 拡張許可）
- v0.0は自由構造（空オブジェクト可）
- ただし **summon等の複数モード** を表現できるよう `modes` を許可する

例:
```yaml
trigger:
  type: "summon"
  modes: ["normal", "special"]
```

## 5.2 restriction
- v0.0は自由構造（空オブジェクト可）
- カード全体制限は `meta.restrictions.global` を推奨（仕様は別紙 17 を参照）

## 5.3 condition
- v0.0は自由構造（空オブジェクト可）

## 5.4 cost
- v0.0は自由構造（空オブジェクト可）

## 5.5 action（最小 + target/sequence許可）
- v0.0は自由構造（空オブジェクト可）
- ただし **対象指定** と **連鎖（成功時続行など）** を表現するため、以下を許可する：
  - `action.target`（対象指定）
  - `action.sequence`（連鎖。配列）

### action.target（例）
```yaml
action:
  target:
    n: 1
    desc: "White Forest Synchro Monster"
    location: ["field", "GY"]
  type: "return_to_extra"
```

### action.sequence（例）
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

# 6. 型と欠損表現

| 種類 | 表現 |
|------|------|
| 文字列 | "" |
| 配列 | [] |
| オブジェクト | {} |

キー欠落は禁止。

---

# 7. 命名規則

- effect.id 形式（推奨）: `{cid}_{3桁連番}`
- effect.order: 1..N

---

# 8. JSON 互換性
DSLは YAML または JSON で表現可能であること。

---

# 9. 互換性ポリシー

v0.0 は Experimental：
- 破壊的変更を許容（ただし可能な限り後方互換を壊しにくい拡張を優先）
- 変更は changelog に記録
