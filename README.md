# ygo-effect-dsl

`ygo-effect-dsl` は、遊戯王 OCG のカード効果テキストを構造化 DSL に変換し、将来的な展開探索、妨害耐性解析、リカバリ解析、デッキ評価につなげるための研究 CORE です。

V0.1 では、単なる DSL 変換ツールではなく「ゲームエンジン + AI 探索」へ進むための方針、責務境界、文書階層を確立します。現時点の実装は ingest / transform / validate / analyze パイプラインが中心ですが、これらは将来の Bridge、Replay、Search、Evaluation を支える前処理基盤として扱います。

## V0.1 の位置付け

V0.1 は完成したゲームエンジンではありません。V0.1 の目的は、以後の破壊的変更を許容できるだけの設計方針を固定し、現在の DSL 変換基盤を次のエンジン設計へ接続することです。

V0.1 で確立するもの:

- `docs/00_project_charter.md` を最上位方針にする。
- プロジェクトを DDD ではなく「ゲームエンジン + AI 探索」として設計する。
- Python は遊戯王のルールを持たず、ルールの真実源を ocgcore / EDOPro Lua に置く。
- Action、Replay、Bridge、Evaluation、Search の責務を分離する。
- Replay 可能性、Peak Board、END_TURN、State Evaluation / Action Evaluation 分離を将来設計の前提にする。
- 既存の DSL 変換、検証、分析機能を V0.1 以降の入力基盤として維持する。

V0.1 でまだ実装しないもの:

- full chain / stack simulation
- full opponent AI
- full ocgcore bridge
- full replay executor
- full MCTS / Beam Search
- all-card rules implemented in Python

特に最後の項目は明確な非目標です。Python にルールを再実装しません。

## 設計文書

このリポジトリでは、実装より上位に文書を置きます。判断順序は次の通りです。

```text
Project Charter
  ▼
Architecture
  ▼
Specifications
  ▼
ADR
  ▼
Implementation
```

主要文書:

- [Project Charter](docs/00_project_charter.md)
- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Glossary](docs/glossary.md)
- [Documentation Policy](docs/documentation_policy.md)
- [ADR: Project Charter](docs/adr/0000_project_charter.md)
- [V0.1 Overview](docs/spec/v0.1/00_overview.md)
- [V0.1 Minimal Semantics](docs/spec/v0.1/10_minimal_semantics.md)
- [V0.1 First 10 One-Step Applications](docs/spec/v0.1/20_first_10_applications.md)
- [Representative Benchmark Policy](docs/spec/v0.0/60_representative_benchmark.md)
- [Versioning And Release Policy](docs/release/versioning.md)
- [Pending Local Commits Checklist](docs/release/pending_local_commits.md)

## 現在の実装範囲

現在のコードは、ETL 出力を受け取り、DSL YAML を生成し、検証と分析を行う研究パイプラインです。

```text
manifest.json / cards.jsonl
  ▼
ingest
  ▼
transform
  ▼
validate
  ▼
analyze
  ▼
reports / metrics
```

この段階で重要なのは、DSL 出力を測定可能かつレビュー可能にすることです。将来の状態遷移や探索は、まず Action と Target を安定して抽出できることに依存します。

## 5 分で動かす

ローカルにインストールします。

```bash
pip install -e .
```

サンプルデータセットを処理します。

```bash
python -m ygo_effect_dsl ingest --dataset examples/sample_dataset
python -m ygo_effect_dsl transform --dataset examples/sample_dataset --out data/dsl_out
python -m ygo_effect_dsl validate data/dsl_out/yaml
python -m ygo_effect_dsl analyze data/dsl_out/yaml --out data/reports
```

主な出力:

- DSL YAML: `data/dsl_out/yaml/*.yaml`
- Transform reports: `data/dsl_out/reports/`
- Analyze report: `data/reports/analysis_report.json`

合成カードによる smoke fixture も利用できます。

```bash
python -m ygo_effect_dsl ingest --dataset examples/synthetic_test_cards
python -m ygo_effect_dsl transform --dataset examples/synthetic_test_cards --out data/synthetic_dsl
python -m ygo_effect_dsl validate data/synthetic_dsl/yaml
```

## 開発ループ

テストを実行します。

```bash
python -m pytest
```

代表カードの golden snapshot を意図的に更新する場合だけ、次を使います。

```powershell
$env:YGO_UPDATE_GOLDEN="1"
python -m pytest tests/test_representative_golden.py
Remove-Item Env:\YGO_UPDATE_GOLDEN
```

Golden 更新は機械的に行わず、Action、Target、Cost、Restriction、Diagnostics、Analyze metrics の変化を確認してからコミットします。

## Windows exe Artifact

Pull request と push では GitHub Actions が pytest を実行し、その後 PyInstaller で Windows x64 executable をビルドします。成果物名は `ygo-effect-dsl-win64` です。

Python をインストールせずに artifact を試す場合の例:

```powershell
.\ygo-effect-dsl.exe ingest --dataset examples/sample_dataset
.\ygo-effect-dsl.exe transform --dataset examples/sample_dataset --out data/dsl_out
.\ygo-effect-dsl.exe validate data/dsl_out/yaml
.\ygo-effect-dsl.exe analyze data/dsl_out/yaml --out data/reports
```

## Analyze Metrics

`analyze` は V0.1 以降も重要な開発フィードバックです。

- `stats.action_type_coverage`: 変換が出力している action type
- `stats.targets_count.resolution_rate`: `target_id` が `targets[]` に解決できている割合
- `stats.unmatched_fragments_top`: 辞書ルールが拾えていない頻出断片
- `quality.empty_block_ratio`: 空の semantic block の比率
- `validation.severity_counts` / `validation.code_counts`: 診断の重大度とコード

これらは、将来の Search Engine の品質以前に、入力 DSL の信頼性を測るための基盤です。

## Scope

Included:

- ETL export artifact の ingest
- DSL YAML への transform
- DSL contract validation
- conversion quality analysis
- representative benchmark と golden regression
- V0.1 state/action semantics の文書化
- 将来の game engine / AI search へ向けた設計基盤

Excluded for now:

- API fetching
- image downloading
- ETL SQLite database への直接依存
- Python による遊戯王ルール再実装
- full ocgcore bridge
- full chain / stack simulation
- full opponent interaction modeling

## Input Contract

CORE は ETL export artifact を入力とします。

- `manifest.json`
- `cards.jsonl`

これらは `ygo-effect-dsl-etl` から生成されます。CORE は ETL SQLite database を直接読みません。

## License

TBD
