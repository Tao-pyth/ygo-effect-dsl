# ygoEffectDSL Spec v0.0 (Draft) — Grammar

> Status: Draft (Experimental)
> 破壊的変更が起こり得る初期仕様。
> 本文書は DSL の「構文（構造とフィールド）」のみを定義する。
> 意味論（評価順序や状態遷移）は 20_semantics.md を参照。

---

# 1. 基本方針（Design Principles）

v0.0 の文法設計は以下の原則に基づく：

1. **常にキーを存在させる**
   - 欠損はキー欠落ではなく空値で表現する
2. **構造優先**
   - 意味の正確性よりも、構造化可能性を優先する
3. **最小十分構造**
   - 将来拡張可能な余白を残す
4. **DSLは宣言的**
   - 命令列ではなく、効果の構成要素を分解した宣言型表現とする

---

# 2. ルート構造

v0.0 における DSL 文書のルートは以下とする。

```yaml
dsl_version: "0.0"
card:
  cid: 0
  name:
    en: ""
    ja: ""
effects:
  - id: "CID_001"
    order: 1
    trigger: {}
    restriction: {}
    condition: {}
    cost: {}
    action: {}
meta:
  source:
    dataset: ""
    exported_at: ""
```
---

# 3. ルートフィールド定義

## 3.1 dsl_version (string) — 必須

- 形式: "0.0"
- 意味: DSL仕様バージョン
- 将来は "0.1", "1.0" などへ更新

---

## 3.2 card (object) — 必須

```yaml
card:
  cid: 123456
  name:
    en: "Example"
    ja: "例"
```
### card.cid
- 型: string または integer
- 意味: Konami ID
- ETL契約と一致すること

### card.name.en / ja
- 型: string
- 欠損時は空文字

---

## 3.3 effects (list) — 必須

カードが持つ効果の配列。

```yaml
effects:
  - id: "123456_001"
    order: 1
    trigger: {}
    restriction: {}
    condition: {}
    cost: {}
    action: {}
```
空配列も許可する（効果未解析など）。

---

# 4. effect オブジェクト構造

各 effect は以下のフィールドを持つ。

| フィールド | 必須 | 型 | 説明 |
|------------|------|----|------|
| id | ✔ | string | `{cid}_{連番}` 推奨 |
| order | ✔ | integer | 効果の順序 |
| trigger | ✔ | object | 発動契機 |
| restriction | ✔ | object | 制限条件 |
| condition | ✔ | object | 発動条件 |
| cost | ✔ | object | コスト |
| action | ✔ | object | 効果解決 |

---

# 5. 各構成要素の構文（v0.0 最小定義）

## 5.1 trigger
```yaml
trigger: {}
```
v0.0では自由構造。将来は列挙型を導入予定。

## 5.2 restriction
```yaml
restriction: {}
```

## 5.3 condition
```yaml
condition: {}
```

## 5.4 cost
```yaml
cost: {}
```

## 5.5 action
```yaml
action: {}
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

effect.id 形式:
{cid}_{3桁連番}

---

# 8. 将来拡張のための留保事項

- 複数対象選択
- 分岐構文
- チェーン（stack）表現
- 優先権

---

# 9. JSON 互換性

```json
{
  "dsl_version": "0.0",
  "card": { "cid": 123456, "name": { "en": "", "ja": "" } },
  "effects": { 
    "id": "CID_001",
    "order": 1,
    "trigger": {},
    "restriction": {},
    "condition": {},
    "cost": {},
    "action": {} }
  "meta": {}
}
```

---

# 10. 互換性ポリシー

v0.0 は Experimental であり：
- 破壊的変更を許容
- 変更は 50_changelog.md に記録
