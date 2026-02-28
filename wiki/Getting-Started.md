# Getting Started

## 目的
最小の入力データから、DSL生成→検証→（将来）探索までの流れを体験する。

## 前提
- ETLが出力した `data/export/cards.jsonl` を用意する
- 例: `examples/sample_cards.jsonl`

## 最小コマンド例（案）
```bash
python -m ygo_effect_dsl ingest examples/sample_cards.jsonl
python -m ygo_effect_dsl transform --out data/dsl_out/
python -m ygo_effect_dsl validate data/dsl_out/
```
