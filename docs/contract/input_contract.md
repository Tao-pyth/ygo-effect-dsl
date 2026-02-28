# Input Contract — ETL → CORE

CORE は ETL が生成した以下の成果物のみを入力として扱う：
- `data/export/cards.jsonl`
- `data/export/manifest.json`

## 必須キー（cards.jsonl）
- cid（Konami ID）
- name_en / card_text_en
- name_ja / card_text_ja（空でもキーは存在）
- card_info_en / card_info_ja
- image_url_* / image_relpath_*（キーは存在、無い場合は空文字）
- fetched_at / source

※ SQLite内部には依存しない。
