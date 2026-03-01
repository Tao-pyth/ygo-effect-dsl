# 18_dictionary_format.md
# ygoEffectDSL Spec v0.0 — Dictionary File Formats

> Status: Draft (Experimental)  
> 本文書は v0.0 における「辞書（dictionary）」の**データ形式**を定義する。  
> 辞書そのもの（ルールの中身）は実装資産として `resources/dict/` 配下に配置し、
> Docs にはフォーマット仕様（契約）のみを記載する。  
> Last updated: 2026-03-01

---

# 1. 目的

辞書は、正規化済みテキスト（`meta.norm.*`）に対してパターンマッチを行い、
DSL（effects.cost / effects.action / effects.trigger / meta.restrictions.global 等）へ
**部分的に埋め戻す**ためのルール集合である。

v0.0では以下を重視する。

- **決定論的**（同じ入力→同じ結果）
- **部分成功**を許容（当たったところだけ埋める）
- **失敗しても停止しない**
- **優先度**で衝突を制御できる

---

# 2. 配置（推奨）

```text
resources/dict/v0_0/
  00_vocab.yaml
  30_cost_rules.yaml
  31_action_rules.yaml
  32_trigger_rules.yaml
  33_restriction_rules.yaml
```

- `00_vocab.yaml`：語彙（カテゴリ抽出に利用）
- `30_*_rules.yaml`：パターンルール（正規化後テキストに適用）

---

# 3. ルール辞書（rules.yaml）の共通スキーマ

ルール辞書は YAML の配列（list）として定義する。  
各要素が1ルールである。

## 3.1 ルールフィールド一覧

| フィールド | 必須 | 型 | 説明 |
|---|---:|---|---|
| id | ✔ | string | ルール識別子（ユニーク） |
| version | ✔ | string | "0.0" |
| priority | ✔ | int | 大きいほど先に適用（推奨: 0〜1000） |
| language | ✔ | string | "en"（v0.0推奨） |
| applies_to | ✔ | string | "cost" / "action" / "trigger" / "restriction_global" |
| pattern | ✔ | string | 正規化後テキストに当てる正規表現（Python re想定） |
| emit | ✔ | object | DSLへのパッチ（部分埋め） |
| capture |  | object | キャプチャ整形（省略可） |
| on_fail |  | string | "ignore"（既定） |
| note |  | string | ルール意図メモ（運用用） |
| examples |  | list[str] | テスト用の生文例（任意） |

## 3.2 ルール例（cost）

```yaml
- id: "COST_SEND_ST_FROM_HAND_OR_FIELD_TO_GY"
  version: "0.0"
  priority: 100
  language: "en"
  applies_to: "cost"
  pattern: '^you can send 【N】 (?P<thing>spell/trap) from your (?P<from>hand or field) to the gy;$'
  capture:
    n: "N[0]"
    thing: "$thing"
    from: ["hand", "field"]
  emit:
    cost:
      type: "send_to_gy"
      n: "$n"
      thing: "$thing"
      from: "$from"
  on_fail: "ignore"
```

---

# 4. 参照式（v0.0の最小ルール）

辞書内では、以下の参照表現を使用できる（実装側が解釈する）。

## 4.1 正規表現キャプチャ参照
- `$name`：`(?P<name>...)` で取れた文字列

## 4.2 正規化パラメータ参照（推奨）
- `N[0]`：`meta.norm.params.N[0]`
- `CARD_NAME[0]`：`meta.norm.params.CARD_NAME[0]`

## 4.3 値の埋め込み
- `emit` 内で `"$n"` のように書いた場合、captureで生成された変数を参照する。

> v0.0では高度な式評価は行わず、**最小の参照置換**で運用する。

---

# 5. emit（DSLパッチ）の方針

- `emit` は DSL の部分構造を埋める「パッチ」である。
- 未埋めのフィールドは空のまま保持される（キー欠落は禁止）。
- `emit` が書く先は `applies_to` と整合するのが望ましい。

### 5.1 action.target / action.sequence（v0.0許可）
- v0.0では `action.target` と `action.sequence` を許可する（10_grammar.md参照）。

---

# 6. 衝突解決（priority）

- 同一箇所に複数ルールが当たる可能性がある。
- v0.0の原則：
  1) priority 降順で適用  
  2) 既に埋まっている値は上書きしない（推奨）  
  3) 例外として「sequenceに追加」は許可する（推奨）

※ 上書きポリシーは実装側の設定で切替可能にしてよい。

---

# 7. vocab辞書（00_vocab.yaml）のスキーマ

vocabはカテゴリ抽出のための語彙表であり、ルールとは別形式を採用する。

```yaml
zones:
  deck: ["deck"]
  hand: ["hand"]
  GY: ["gy", "graveyard"]
  field: ["field"]
  extra_deck: ["extra deck"]
attributes:
  LIGHT: ["light"]
  DARK: ["dark"]
races:
  Spellcaster: ["spellcaster"]
card_types:
  monster: ["monster"]
  spell: ["spell"]
  trap: ["trap"]
phases:
  Damage Step: ["damage step"]
```

- すべて小文字で登録する（正規化後入力と合わせる）
- 値は同義語の配列（最小でよい、徐々に増やす）

---

# 8. テスト指針（最小）

- 各ルールに `examples` を付けると、辞書回帰テストが作りやすい。
- v0.0では以下を推奨：
  - `resources/dict/v0_0/` の YAML が読み込めること
  - 既知例で少なくとも1件はマッチすること
  - マッチしても DSL が壊れない（キー欠落が起きない）こと
