# Examples Gallery

このページでは、v0.0 DSLの読み方を例で確認します。実装上の正確な契約は [Grammar](../docs/spec/v0.0/10_grammar.md) を参照してください。

## Example 1: Skeleton

最小に近いDSLです。v0.0では、未解決の値があっても構造キーを残します。

```yaml
dsl_version: "0.0"
card:
  cid: 123456
  name:
    en: "Example Card"
    ja: ""
  text:
    en: "Draw 1 card."
    ja: ""
  props: {}
effects:
  - id: "123456_001"
    order: 1
    trigger: {}
    restriction: {}
    condition: {}
    cost: {}
    actions:
      - type: "draw"
        n: 1
    targets: []
meta: {}
```

## Example 2: Targetを参照するAction

対象を選ぶ効果では、`targets[]` に対象を宣言し、`actions[]` から `target_id` で参照します。

```yaml
effects:
  - id: "100001_001"
    order: 1
    trigger: {}
    restriction: {}
    condition: {}
    cost: {}
    targets:
      - id: "t1"
        count: 1
        selector:
          kind: "monster"
          zones: ["field"]
          controller: "opponent"
        raw: "1 monster your opponent controls"
    actions:
      - type: "destroy"
        target_id: "t1"
```

この形にしておくと、同じ対象を cost、condition、複数actionから参照しやすくなります。

## Example 3: Cost + Action

コストと効果処理は分けて表現します。

```yaml
effects:
  - id: "100002_001"
    order: 1
    trigger: {}
    restriction:
      once_per_turn: true
    condition: {}
    cost:
      actions:
        - type: "discard"
          n: 1
    targets: []
    actions:
      - type: "draw"
        n: 2
```

`discard` は研究・互換用のaction typeとして出る場合があります。v0.0の標準語彙に含まれない場合は、validatorが `unknown_action` warningを出すことがあります。

## Example 4: 未解決Target

対象らしい構造は見つかったが種類を確定できない場合は、`selector.kind: "unknown"` として残します。

```yaml
targets:
  - id: "t1"
    count: 1
    selector:
      kind: "unknown"
    raw: "that card"
actions:
  - type: "banish"
    target_id: "t1"
```

これはYAML構造としては valid ですが、変換品質のTODOとして `unresolved_target` warningになります。

## Example 5: legacy action fallback

古い出力では、単数の `action` だけが存在する場合があります。

```yaml
effects:
  - id: "100003_001"
    order: 1
    trigger: {}
    restriction: {}
    condition: {}
    cost: {}
    action:
      type: "draw"
      n: 1
    actions: []
    targets: []
```

v0.0の正規表現は `actions[]` です。この形は互換用として読めますが、`legacy_action_fallback` warningの対象です。

## 例を見る時のチェックリスト

- `effects[]` の各要素に必須キーがあるか
- 新しいconsumerが `actions[]` を読める形か
- 対象を持つactionに `target_id` または inline selector があるか
- `targets[].selector.kind` が `unknown` のまま残っていないか
- warning が変換改善のTODOとして説明できるか
