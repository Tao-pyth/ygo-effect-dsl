# Getting Started

現在はRoute DSL 0.1のvalidatorに加え、pin済みocgcoreを使う固定fixture runtimeとGeneral Search MVPを実行できます。General Search MVPは任意YDK/inlineを事前検査し、実core上で決定論的Random Searchを行います。Beam Search / MCTS、PlayerView Replay、一般公開配布は未対応です。

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

## Run General Search

事前に`python -m ygo_effect_dsl ocgcore-bootstrap`と`python -m ygo_effect_dsl ocgcore-assets-bootstrap`で、ライセンス上再配布しない外部assetをローカルcacheへ準備します。

```bash
python -m ygo_effect_dsl experiment-search examples/experiments/general_search_inline.yaml --out data/general-search.route.yaml --search-report data/general-search.report.json
python -m ygo_effect_dsl experiment-replay examples/experiments/general_search_inline.yaml data/general-search.route.yaml
```

探索はocgcoreが提示したcandidateだけを使い、Pythonで効果、合法性、タイミングを推測しません。未検証の妨害categoryはfail-closeします。

## Tests

```bash
python -m pytest
```

旧カードテキスト変換を保守する場合だけ、`docs/spec/v0.0/` とlegacy CLIを参照してください。新しい探索機能は旧変換へ依存しません。
