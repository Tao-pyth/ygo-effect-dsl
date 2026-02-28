# Input Contract — ETL → CORE

CORE は ETL が生成した export 成果物のみを入力として扱う：
- `manifest.json`
- `cards.jsonl`

## ingest時の必須検証
- `manifest.json` を先に読み、`export_schema_version` の互換性を検証する
- `manifest.record_count` と `cards.jsonl` 実行行数の一致を検証する
- `manifest.fields` で定義されたキーが、`cards.jsonl` 各行にすべて存在することを検証する

※ ETL の SQLite 内部には依存しない。
