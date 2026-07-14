# Getting Started

現在はRoute DSL 0.1の契約とvalidatorを確認できます。実ocgcoreからルートを生成するruntimeは未実装です。

## Setup

```bash
pip install -e .
```

## Validate a Route

```bash
python -m ygo_effect_dsl validate-route examples/route_dsl/minimal_route.yaml
```

成功時は次を表示します。

```text
validate-route: ok route_id=route_example_normal_summon
```

validatorは次の整合性を確認します。

- Route DSL名とschema version
- Replay eventの連番
- eventとActionのrequest署名一致
- checkpointからReplay stepへの参照
- Peak Board / Terminal Boardとcheckpointのstate hash一致
- 妨害位置からReplay stepへの参照

Actionが遊戯王ルール上合法か、state hashが実際のocgcore状態かは検査しません。実行上の正しさは将来のBridge / Replay executorがocgcoreで検証します。

## Tests

```bash
python -m pytest
```

旧カードテキスト変換を保守する場合だけ、`docs/spec/v0.0/` とlegacy CLIを参照してください。新しい探索機能は旧変換へ依存させません。
