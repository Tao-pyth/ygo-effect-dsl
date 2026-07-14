# ADR-0008: Keep technical names and define the product boundary

Status: Accepted

Date: 2026-07-13

Decision Issue: #62

## Context

`ygo-effect-dsl` はカード効果テキストの構造化から始まったが、現在の主責務はocgcoreが実行した展開ルートの記録、Replay、探索、評価、比較である。名称だけを見るとカード効果をPython DSLで実装するプロジェクトに見える一方、リポジトリ名、Python import、CLI名は既存の文書、fixture、利用手順に定着している。

名称変更、表示名だけの追加、package分割を比較し、現在の実装境界に必要な判断を固定する。

## Decision

技術識別子は変更しない。

- repository/distribution: `ygo-effect-dsl`
- Python import package: `ygo_effect_dsl`
- CLI command: `ygo-effect-dsl`
- product description: `Reproducible Yu-Gi-Oh! route search and Route Information DSL`

現行のDSLは **Route Information DSL（Route DSL）** だけを指す。Route DSLは実行済みルートを保存・交換・比較する出力契約であり、カード効果、合法手、状態遷移を定義する入力言語ではない。

責務境界を次の通り固定する。

- `engine`: Bridge、State、Replay、Search、Evaluation、Interruptionを所有する。
- `route_dsl`: Route成果物のschema、検証、正規化、説明を所有する。
- `dsl` と旧 `ingest / transform / validate / analyze`: `legacy card-text artifact pipeline` の互換用途に限定する。engineから新規依存を追加しない。
- ocgcore / EDOPro Lua: カード挙動、合法性、状態遷移の真実源であり、Python側へ再実装しない。

## Alternatives

### Hard rename

`ygo-route-search` などへrepository、distribution、import、CLIを一括変更する案は、役割を直接表現できる。しかし現時点では互換alias、文書、CI、cache、外部参照の移行コストに対し、探索機能自体の価値を増やさないため採用しない。

### Separate display name

新しい製品名と古い技術名を並存させる案は、canonical nameを二つ作り、検索・Issue・配布時の説明を複雑にするため採用しない。説明文で責務を明示する。

### Split packages or monorepo

Search engineとRoute DSLを別distributionへ分割する案は、現在共有しているReplay、State、Evaluation、Route versionを別々にreleaseする必要が生じる。独立した利用者、release cadence、互換保証がまだ存在しないため採用しない。

## Rename Triggers

次のいずれかが具体化した場合のみ、後続ADRと互換移行計画を作成してrenameまたは分割を再検討する。

1. distribution名の衝突または法務・配布上の制約が発生した。
2. Search engineまたはRoute DSLに独立利用者と独立release cadenceが生じた。
3. 利用者検証により、現行名が導入・利用を継続的に阻害すると確認された。

「探索が主機能になった」という理由だけではrenameしない。

## Consequences

- 既存import、CLI、fixture、文書リンクを壊さず、製品責務を一つの説明へ統一できる。
- `project_identity.py` をpackage、CLI、metadataの名称契約として扱う。
- legacy card-text機能をRoute DSLまたはルール実装として拡張しない。
- 将来分割する場合はversion互換、alias廃止期限、artifact migrationを明示する必要がある。
