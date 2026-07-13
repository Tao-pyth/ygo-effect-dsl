# ygoEffectDSL Spec v0.0 (Draft) - Validation

> Status: Draft / legacy experimental research baseline / removal target
> Last updated: 2026-05-12

この文書は、`validate` が返す diagnostics の読み方と、v0.0 で守るべき severity/code の契約を定義する。

v0.0 の validation は「遊戯王の効果として完全に正しいか」ではなく、「legacy DSL として読める形か」を確認する。新人プログラマーは、まず `error` と `warning` の違いを押さえると追いやすい。

## 1. 基本方針

v0.0 は研究用の変換 baseline であり、意味解釈の完成度よりも安定した構造を優先する。

- 必須の構造キーが欠けている、または型が違う場合は `error` にする。
- 構造は valid だが、語彙や対象解決が未確定の場合は `warning` にする。
- 実装や分析の補助情報で、失敗扱いにしないものは `info` にする。
- `validate` は diagnostics を列挙し、`analyze` が severity/code ごとの件数を集計できるようにする。

## 2. Severity

| Severity | 意味 | DSL shape | validate の出口コード |
| --- | --- | --- | --- |
| `error` | v0.0 DSL として必須構造を満たしていない。legacy処理が安全に読めない。 | invalid | 1 |
| `warning` | 構造上は valid。未解決、曖昧、または互換用 fallback を含む。 | valid | 0 |
| `info` | 失敗ではない補助情報。解析メモや将来の観測用途。 | valid | 0 |

出口コードの方針:

- `error` が 1 件以上あれば `validate` は失敗として `1` を返す。
- `warning` と `info` だけなら構造上 valid とみなし、`validate` は `0` を返す。
- 入力ディレクトリが読めないなど CLI 引数/設定の問題は DSL 診断ではなく、`validate` は `2` を返す。

この方針により、CI やスクリプトは「DSL shape invalid かどうか」を出口コードで判定し、変換品質の改善対象は `warning` として別に追跡できる。

## 3. Code Catalog

v0.0 の代表的な diagnostic code は次の通り。

| Code | Severity | 発生条件 | 読み方 | 典型的な対応 |
| --- | --- | --- | --- | --- |
| `unknown_action` | `warning` | `action.type` / `actions[].type` が v0.0 の既知 action 語彙にない。 | DSL の形は読めるが、action の意味を標準語彙にまだ落とせていない。 | transformer/dictionary に action 語彙を追加するか、既存語彙へ正規化する。 |
| `unresolved_target` | `warning` | `targets[].selector.kind` が `"unknown"`。 | target 構造はあるが、対象種別が未解決。 | selector 抽出を改善し、`monster` / `card` などの kind に解決する。 |
| `missing_selector` | `warning` | 対象を必要とする action に `target_id` も inline selector 相当の情報もない。 | action は存在するが、何を対象にするかが追えない。 | `targets[]` を作って `target_id` で参照するか、最低限の inline selector 情報を出す。 |
| `legacy_action_fallback` | `warning` | `actions[]` がなく、互換用の単数 `action` だけで処理している。 | v0.0 の canonical は `actions[]` だが、古い形を fallback として読んでいる。 | transformer を `actions[]` 出力へ移行する。 |

### 実装上の補足

現在の validator は、必須キー/型の問題に `required` や `type` などの `error` code も返す。これらは一般的な shape error であり、上の catalog は v0.0 stabilization で品質改善の観測対象にする warning code を中心にした一覧である。

`missing_action_type` は `action.type` が空のときに出る warning で、action の意味が未確定であることを示す。v0.0 の主要 catalog ではないが、`unknown_action` と同じく action 語彙改善の入口になる。

## 4. validate CLI 出力の読み方

`validate` は対象ディレクトリ内の YAML を読み、最初に集計、次に個別 diagnostic を出力する。

```text
validate: scanned=20
validate: errors=0 warnings=2 info=0
  data/dsl_out/yaml/9001.yaml: effects[0].actions[0].type [warning:unknown_action] action.type is not in the v0.0 known vocabulary: search
```

読み方:

- `scanned` は読み込んだカード YAML の数。
- `errors` / `warnings` / `info` は severity ごとの合計。
- 個別行の先頭はファイルパス。
- `effects[0].actions[0].type` は DSL 内の場所。0 始まりの配列 index で読む。
- `[warning:unknown_action]` は `severity:code`。
- 最後の文は人間向け message。機械集計では `severity` と `code` を優先する。

新人プログラマー向けの見方:

1. まず `errors` が 0 か確認する。0 でなければ DSL shape が invalid。
2. `warning` は build を止めないが、変換品質の TODO として読む。
3. 同じ code が多い場合は個別カード修正ではなく、dictionary/transformer の規則改善を疑う。
4. `path` をたどって、どの effect/action/target が問題か確認する。

## 5. warning と error の境界

warning は「構造上 valid だが意味が弱い」状態を表す。

例:

```yaml
actions:
  - type: "search_unknown_zone"
```

この action は object であり `type` も string なので DSL shape は読める。ただし v0.0 の既知語彙ではないため `unknown_action` warning になる。

error は「後続処理が前提にしている形が壊れている」状態を表す。

例:

```yaml
effects:
  - id: 123
    actions: "draw"
```

`effect.id` は string であるべきで、`actions` は list であるべきなので shape invalid。これは `error` として出口コード `1` の対象になる。

## 6. v0.0 stabilization で必要な理由

v0.0 stabilization の目的は、transform 出力を「測れる」状態にすること。

severity/code が安定していると、次のことができる。

- golden test で DSL shape の退行を検出できる。
- `analyze` で `warning:unknown_action` の件数を追い、action 語彙の改善を測れる。
- `warning:unresolved_target` や `warning:missing_selector` の件数から、target 抽出の弱点を見つけられる。
- `legacy_action_fallback` を見て、`action` から canonical `actions[]` への移行残りを把握できる。

つまり diagnostics は単なるエラーメッセージではなく、v0.0 の完成度を数値で追うための測定点である。

## 7. v0.1 との関係

v0.1 では、最小限の state/action semantics に進む案を検討していた。現在は ADR-0003 により、この接続案は廃止対象である。

当時 v0.0 の diagnostics が必要とされた理由:

- `error` が残っていると、v0.1 の reader は DSL を安全に読めない。
- `unknown_action` が多いと、v0.1 の候補語彙へ接続できない。
- `unresolved_target` と `missing_selector` が多いと、どの card/zone/player に作用するかを決められない。
- `legacy_action_fallback` が残ると、v0.1 が読むべき canonical 入力が `actions[]` なのか `action` なのか曖昧になる。

したがって v0.0 の validation diagnostics は、過去の v0.1 state/action semantics 検討の前提条件だった。現在の探索エンジン入力の前提条件ではない。
