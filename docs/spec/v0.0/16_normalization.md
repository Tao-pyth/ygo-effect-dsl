# ygoEffectDSL Spec v0.0 — Normalization Layer

> Status: Draft (Experimental)  
> 本文書は v0.0 における「正規化（Normalization）」の仕様を定める。  
> 正規化はパターンマッチング（17_pattern_matching_pipeline.md）の前提であり、
> 辞書（trigger/action/cost）適用の安定性を最大化する。  
> Last updated: 2026-03-01

---

# 1. 目的（Goals）

正規化層の目的は以下である。

1. **表記ゆれの吸収**（同義の文を同じ形に寄せる）  
2. **辞書パターン数の削減**（辞書が爆発しないようにする）  
3. **再現性の確保**（同じ入力→同じ正規化結果）  
4. **情報保持**（置換で失う情報は必ず `meta.norm.params` / `meta.norm.categories` に保持）  

v0.0では「意味理解」よりも **決定論的な入力整形** を優先する。

---

# 2. 入力と出力

## 2.1 入力
- `card.text.en`（必須）
- `card.text.ja`（推奨：枠は常に存在）
- `card.info.en`（必須）
- `card.info.ja`（推奨：枠は常に存在）

## 2.2 出力（DSLの共通部へ格納）

正規化結果は DSL の `meta.norm` に格納する。

```yaml
meta:
  norm:
    text_en: ""
    text_ja: ""
    info_en: ""
    info_ja: ""
    params:
      N: []
      CARD_NAME: []
    categories:
      attributes: []
      races: []
      zones: []
      levels: []
      ranks: []
      links: []
      card_types: []
      phases: []
```

- `text_*` / `info_*`：正規化後のテキスト
- `params`：置換で抽出した値（順序を保持）
- `categories`：カテゴリ抽出（置換しない。抽出のみ）

---

# 3. 正規化トークン（置換ルール）

## 3.1 【N】（数値パラメータ）

対象:
- 正規表現 `\b\d+\b` に一致する整数

処理:
- 原文中の数値を出現順に抽出して `meta.norm.params.N` に保存
- テキスト中では `【N】` に置換

例:
- `Draw 2 cards.` → `draw 【N】 cards.`  
  `params.N = [2]`

補足（v0.0）:
- "one/two" 等の英単語数は v0.0 では未対応でもよい（将来拡張）。

---

## 3.2 【CARD_NAME】（引用符付き固有名）

対象:
- ダブルクォートで囲まれた文字列（例: `"Dark Magician"`）

処理:
- 抽出して `meta.norm.params.CARD_NAME` に保存
- テキスト中では `【CARD_NAME】` に置換

例:
- `... each effect of "Silvy of the White Forest" ...`
  → `... each effect of 【CARD_NAME】 ...`  
  `params.CARD_NAME = ["Silvy of the White Forest"]`

注意:
- 引用符は用語強調に使われる場合もあるが、v0.0では割り切って同一扱いとする。
  必要になれば `CARD_NAME_OR_TERM` 等へ拡張する。

---

# 4. カテゴリ抽出（置換しない）

カテゴリ抽出は **置換ではなく抽出** を行う。  
抽出結果は `meta.norm.categories` に格納する。

v0.0で対象とする主なカテゴリ:

- 属性（LIGHT/DARK など）
- 種族（Dragon/Spellcaster など）
- ゾーン（deck/hand/gy/field/extra deck/banished など）
- レベル/ランク/リンク（例: Level 4 / Rank 8 / Link 2）
- カード種別（monster/spell/trap）
- フェーズ（Main Phase / Battle Phase / Damage Step 等）

出力例:

```yaml
meta:
  norm:
    categories:
      attributes: ["LIGHT"]
      races: ["Spellcaster"]
      zones: ["hand", "field", "GY", "deck", "extra deck"]
      levels: [4]
      phases: ["Damage Step"]
```

---

# 5. 正規化順序（決定論）

実装は次の順序で処理する（順序は固定）。

1. Unicode正規化（推奨: NFKC）
2. 小文字化（英語）
3. 空白・改行の統一（連続空白の圧縮、改行→スペース等）
4. 引用符の統一（“” → " など）
5. `"` で囲まれた文字列を抽出 → 【CARD_NAME】置換
6. 数値を抽出 → 【N】置換
7. カテゴリ抽出（attributes/races/zones/phases 等）
8. 最終クリーニング（余計な空白、句読点周り）

---

# 6. 設計原則（v0.0）

- **情報を消さない**：置換で失う情報は params/cat に保持する  
- **置換は最小限**：`【N】` と `【CARD_NAME】` のみ（v0.0）  
- **抽出は増やしてよい**：categories は後から拡張しやすい  
- **失敗しても止めない**：抽出できないカテゴリは空配列でよい  
- **後工程のための安定性**：辞書適用（17）にとって同じ入力は同じ正規化結果になること

---

# 7. 参考：正規化→パターンマッチングの接続

- `meta.norm.text_en` を 17 のパイプラインへ入力する
- cost/action辞書は `meta.norm.params` / `meta.norm.categories` を参照して埋める
