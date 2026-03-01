dsl_version: "0.0"

card:
  cid: 0
  name:
    en: ""
    ja: ""
  text:
    en: ""   # 必須（キーは必須）
    ja: ""   # 推奨（枠＝キーは作る）
  info:
    en: ""   # 必須（キーは必須）
    ja: ""   # 推奨（枠＝キーは作る）

meta:
  source:
    export_schema_version: 0
    dataset: ""
    exported_at: ""
    endpoint: ""
    misc: true
  raw:
    card_text_en: ""   # 共通部（必須）
    card_text_ja: ""   # 共通部（推奨枠）
    card_info_en: ""   # 共通部（必須）
    card_info_ja: ""   # 共通部（推奨枠）
  transform:
    run_id: ""
    warnings: []

effects:
  - id: "CID_001"
    order: 1
    trigger: {}
    restriction: {}
    condition: {}
    cost: {}
    action: {}