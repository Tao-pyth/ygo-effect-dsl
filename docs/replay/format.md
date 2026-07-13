# Replay Format

Status: V0.2 specification baseline

Last updated: 2026-07-13

## Purpose

この文書は将来の `ReplayHistory` JSON の最小形式を定義する。V0.2 の目的は、Action 履歴を保存し、読み戻し、同一内容として比較できる deterministic な土台を作ることである。

## ReplayHistory JSON

最小形:

```json
{
  "actions": [
    {
      "action_type": "select_card",
      "created_at": null,
      "payload": {
        "selected": ["card-1"]
      },
      "source": "synthetic",
      "step": 0
    }
  ],
  "deck_identifier": "sample-deck",
  "notes": "synthetic smoke fixture",
  "schema_version": "0.2",
  "seed": 12345,
  "version_metadata": {
    "project_version": "0.1.0"
  }
}
```

必須:

- `schema_version`: Replay JSON の形式バージョン。V0.2 では `"0.2"` とする。
- `seed`: 再現条件の seed。未知の場合は `null` を許容する。
- `deck_identifier`: deck を識別する文字列。V0.2 では deck 内容そのものを保持しない。
- `actions`: `ActionRecord` の順序付き配列。
- `version_metadata`: project、dictionary、core などのバージョン情報を入れる dict。V0.2 では空 dict を許容する。
- `notes`: 人間向けメモ。不要な場合は空文字列とする。

## ActionRecord

最小形:

```json
{
  "step": 0,
  "action_type": "select_card",
  "payload": {
    "selected": ["card-1"]
  },
  "source": "synthetic",
  "created_at": null
}
```

必須:

- `step`: Replay 内の順序。0 から始まる整数とする。
- `action_type`: Action 種別。
- `payload`: Action 固有の情報。空の場合も dict とする。
- `source`: `synthetic`, `bridge`, `search`, `manual` などの発生元。

任意:

- `created_at`: 作成時刻。テスト安定性を壊さないため必須にしない。未使用時は `null` を許容する。

## Deterministic JSON

V0.2 の serializer は人間が読める deterministic output を生成する。

実装時の既定:

- UTF-8
- `ensure_ascii=False`
- `indent=2`
- `sort_keys=True`
- trailing newline あり

配列順序は意味を持つ。特に `actions` の順序は Replay の順序であり、serializer が並べ替えてはならない。

## Invalid Replay JSON

invalid replay JSON は、JSON parse error と replay shape error を区別できるようにする。

V0.2 実装では、次の状態を invalid として扱う。

- JSON として parse できない。
- top-level が object ではない。
- 必須 field がない。
- `actions` が array ではない。
- ActionRecord が必須 field を欠く。
- `payload` または `version_metadata` が object ではない。
- `step` が integer ではない。

invalid replay JSON を読んだ場合、曖昧な `KeyError` や `TypeError` を外へ漏らさず、明確な replay format error として返す。

## Future Extensions

以下は V0.2 の format には含めない。

- binary replay
- snapshot
- clone_duel
- request signature verification
- random choice / shuffle trace の完全仕様
- core / Lua / cards.cdb の厳密な互換性検証
