# ygoEffectDSL Spec v0.0 (Draft) — Grammar

この文書は **DSLの構文（フィールドと型）** を定義します。  
v0.0 は「初期草案」であり、破壊的変更が起こり得ます。

## 1. ルート構造（案）
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

## 2. 必須フィールド（v0.0）
- `dsl_version`（string）
- `card.cid`（int or string）
- `effects`（list）
- `effects[].id`（string）
- `effects[].order`（int）
- `effects[].trigger / restriction / condition / cost / action`（object）  
  - v0.0では「空オブジェクト」でも必ず存在させる（キー欠落を避ける）

## 3. 欠損・不明の表現ルール
- 文字列：`""`（空文字）
- リスト：`[]`
- オブジェクト：`{}`
- **自動判別できないが後で補完したい**場合：UI側で `???` 表示しても、ファイル上は空値を推奨

## 4. 型の方針（v0.0）
- “柔らかい型” で開始し、v0.1以降に厳格化する
- ただし、破壊的変更の追跡のため、CHANGELOGは必須

## 5. 拡張ポイント（将来）
- `effects[].targets`（複数対象）
- 分岐構文（例：branch_from_draw 等）
- チェーン（stack）表現
