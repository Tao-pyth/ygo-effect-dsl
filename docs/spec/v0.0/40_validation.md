# ygoEffectDSL Spec v0.0 (Draft) — Validation

この文書は **DSLが“正しい/受理できる”ための条件** を定義します。

## 1. 最低限の構造検査（v0.0）
- `dsl_version` が存在する
- `card.cid` が存在し、空でない
- `effects` が list である（空でも可）
- 各 effect に `id` と `order` がある
- trigger/restriction/condition/cost/action が存在する（空オブジェクト可）

## 2. 推奨検査（v0.0）
- effect.id が `{cid}_{連番}` 形式に従う（任意）
- order が 1..N の連番（任意）
- 文字コードUTF-8、YAML/JSONとしてパース可能

## 3. エラーの扱い（運用）
- 解析不能箇所は “失敗” ではなく “未確定” として扱えるようにする
- validate は「エラーを列挙」し、後工程で補完可能にする
