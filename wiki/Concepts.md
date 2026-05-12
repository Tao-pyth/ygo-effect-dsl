# Concepts

このページでは、`ygo-effect-dsl` を読む上で頻出する概念を説明します。詳細な仕様は `docs/spec/` が一次情報です。

## DSLとは

DSLは Domain Specific Language の略です。このプロジェクトでは、遊戯王カードの自然言語テキストを、機械が読みやすい構造化データへ変換したものを指します。

v0.0 DSLは、完全なルール再現ではなく、変換結果を安定して検証・分析するための研究用フォーマットです。

## Root Object

v0.0 DSLの最小構造は次の形です。

```yaml
dsl_version: "0.0"
card:
  cid: 0
  name:
    en: ""
    ja: ""
  text:
    en: ""
    ja: ""
  props: {}
effects: []
meta: {}
```

`card.info` は v0.0 DSLには含めません。ETL由来の raw info は、必要に応じて compact な `card.props` に正規化します。

## Effect

Effect は、カードテキスト中のひとまとまりの効果を表す単位です。

各 `effects[]` 要素は、主に次のフィールドを持ちます。

| Field | 説明 |
| --- | --- |
| `id` | 効果ID。例: `123456_001` |
| `order` | カード内での効果順 |
| `trigger` | 発動・適用タイミング |
| `restriction` | 1ターンに1度などの制約 |
| `condition` | 適用条件 |
| `cost` | コスト |
| `actions[]` | 効果が行う処理の正規表現 |
| `targets[]` | actionやcostが参照する対象 |

## Action

Action は、効果が実際に行う処理です。v0.0では `actions[]` が canonical、つまり正規の表現です。

代表的な action type は次の通りです。

- `draw`
- `add_to_hand`
- `send_to_gy`
- `destroy`
- `special_summon`
- `banish`
- `negate`

例:

```yaml
actions:
  - type: "destroy"
    target_id: "t1"
```

古い互換用フィールドとして単数の `action` が残る場合がありますが、新しい処理系は `actions[]` を読むべきです。

## Target

Target は、効果が参照するカードや領域を宣言するための構造です。action、cost、conditionから同じ対象を参照できるように、`targets[]` として分離します。

```yaml
targets:
  - id: "t1"
    count: 1
    selector:
      kind: "monster"
      zones: ["field"]
      controller: "opponent"
    raw: "target 1 monster your opponent controls"
```

`selector.kind: "unknown"` は構造としては valid ですが、意味が未解決なので `unresolved_target` warning の対象になります。

## State

State は、ゲーム盤面のスナップショットを表す概念です。将来的には次のような領域を持つモデルへ進む想定です。

- `Deck`
- `Hand`
- `Field`
- `GY`
- `Banished`
- `Extra`
- `Flags`

v0.0では、完全な盤面シミュレーションはまだ目標にしていません。まずはDSLの構造と診断を安定させます。

## State Transition

State Transition は、効果を適用した結果として盤面が変化することです。

概念的には次のように考えます。

```text
State x Effect -> State
```

v0.1以降では、`draw`、`destroy`、`special_summon` などの最小 action を、実行可能な状態遷移へ近づけていく予定です。

## Diagnostics

Diagnostics は、変換結果を改善するための観測点です。

- `error`: DSLの形が壊れており、後続処理が安全に読めない
- `warning`: DSLの形は読めるが、意味が未解決・曖昧・互換用である
- `info`: 失敗ではない補助情報

v0.0では、warningを減らすことが変換品質改善の中心になります。
