# FAQ

## Q. Wikiと仕様書のどちらが正ですか？

A. 正確な仕様の一次情報は `docs/spec/` です。Wikiは、仕様を読みやすく案内するための日本語ガイドです。

## Q. v0.0とは何ですか？

A. v0.0は研究用の変換ベースラインです。完全な遊戯王ルールエンジンではなく、カード効果テキストを安定したDSL構造へ変換し、検証・分析できる状態にすることを目的にしています。

## Q. v0.0では何を重視していますか？

A. 意味解釈の完全性よりも、構造の安定性と診断可能性を重視しています。未解決の意味は無理に消さず、warningとして可視化します。

## Q. `actions[]` と `action` の違いは何ですか？

A. `actions[]` がv0.0の正規表現です。`action` は古い互換用fallbackです。新しいconsumerやテストは `actions[]` を中心に扱うべきです。

## Q. `validate` の warning は失敗ですか？

A. 失敗ではありません。`warning` はDSL構造としては読めるが、意味が未解決・曖昧・互換用であることを示します。CIや後続処理でまず重視するのは `errors=0` です。

## Q. 代表的な warning code は何ですか？

A. よく見るものは次の4つです。

| Code | 意味 |
| --- | --- |
| `unknown_action` | action type が v0.0 の既知語彙にない |
| `unresolved_target` | target selector が `unknown` のまま |
| `missing_selector` | 対象を必要とするactionに selector 情報がない |
| `legacy_action_fallback` | `actions[]` ではなく互換用 `action` に依存している |

## Q. ETLとはどうつながっていますか？

A. COREはETLが出力する `manifest.json` と `cards.jsonl` を入力として扱います。ETL内部のSQLiteには直接依存しません。

## Q. DSL出力が変わったら何を確認すべきですか？

A. まず `validate` で `errors=0` を確認します。次に `analyze` の action coverage、target解決率、warning件数を確認します。代表カードの出力が変わる場合は golden test の差分も確認します。

## Q. golden fileはいつ更新しますか？

A. DSL出力の変更が意図した仕様変更・辞書改善・transform改善である場合だけ更新します。偶然の差分をそのまま取り込まないように、更新後は `tests/golden/representative_cards/` を確認します。

## Q. v0.1では何が増えますか？

A. 最小限の state/action semantics を導入する予定です。たとえば `Deck`、`Hand`、`Field`、`GY`、`Banished`、`Extra` を読み、`draw`、`add_to_hand`、`send_to_gy`、`destroy`、`special_summon`、`banish`、`negate` などを実行可能な意味へ近づけます。
