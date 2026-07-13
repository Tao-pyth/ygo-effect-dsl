# ygo-effect-dsl

`ygo-effect-dsl` は、遊戯王 OCG の展開探索、妨害耐性解析、リカバリ解析、デッキ評価を再現可能にするためのゲーム木探索エンジン基盤です。

カード効果とルールの真実源は ocgcore / EDOPro Lua です。既存の DSL CORE は過去の実験由来の legacy / deprecated / removal target であり、探索エンジンの前段、補助分析基盤、Action 生成元として扱いません。

## V0.1 の位置付け

V0.1 は完成したゲームエンジンではありません。V0.1 の目的は、以後の破壊的変更を許容できるだけの設計方針を固定し、実行系を ocgcore / EDOPro Lua 中心へ移すことです。

V0.1 で確立するもの:

- `docs/00_project_charter.md` を最上位方針にする。
- プロジェクトを DDD ではなく「ゲームエンジン + AI 探索」として設計する。
- Python は遊戯王のルールを持たず、ルールの真実源を ocgcore / EDOPro Lua に置く。
- Action、Replay、Bridge、Evaluation、Search の責務を分離する。
- Replay 可能性、Peak Board、END_TURN、State Evaluation / Action Evaluation 分離を将来設計の前提にする。
- 既存の DSL 変換、検証、分析機能は互換維持のため一時残置し、廃止対象として隔離する。

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
- [ADR: Replay Baseline](docs/adr/0001_replay_baseline.md)
- [ADR: Python Does Not Own Rules](docs/adr/0002_python_does_not_own_rules.md)
- [ADR: Deprecate DSL CORE](docs/adr/0003_deprecate_dsl_core.md)
- [V0.1 Overview](docs/spec/v0.1/00_overview.md)
- [V0.1 Minimal Semantics](docs/spec/v0.1/10_minimal_semantics.md)
- [V0.1 First 10 One-Step Applications](docs/spec/v0.1/20_first_10_applications.md)
- [Bridge Overview](docs/bridge/overview.md)
- [Bridge Messages](docs/bridge/messages.md)
- [Replay Overview](docs/replay/overview.md)
- [Replay Format](docs/replay/format.md)
- [Representative Benchmark Policy](docs/spec/v0.0/60_representative_benchmark.md)
- [Versioning And Release Policy](docs/release/versioning.md)
- [Pending Local Commits Checklist](docs/release/pending_local_commits.md)

## 現在の実装範囲

現在のコードには、ETL 出力を受け取り、DSL YAML を生成し、検証と分析を行う legacy パイプラインが残っています。

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

このパイプラインは既存テストと互換維持のため一時的に残します。探索エンジンの実行系入力、合法手判定、Action 生成元として使ってはいけません。

Primary Runtime Path:

```text
ocgcore / EDOPro Lua
  ▼
Bridge
  ▼
Replay / Search / Evaluation
```

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

`analyze` は legacy DSL CORE の互換確認用フィードバックです。

- `stats.action_type_coverage`: 変換が出力している action type
- `stats.targets_count.resolution_rate`: `target_id` が `targets[]` に解決できている割合
- `stats.unmatched_fragments_top`: 辞書ルールが拾えていない頻出断片
- `quality.empty_block_ratio`: 空の semantic block の比率
- `validation.severity_counts` / `validation.code_counts`: 診断の重大度とコード

これらは既存DSL機能の互換確認に限って利用します。Search Engine の品質や入力妥当性の根拠にはしません。

## Scope

Included:

- ETL export artifact の ingest
- DSL YAML への transform
- DSL contract validation
- conversion quality analysis
- representative benchmark と golden regression
- legacy DSL CORE の廃止方針の明文化
- game engine / AI search へ向けた Bridge / Replay 設計基盤

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
