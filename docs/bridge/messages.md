# Bridge Messages

Status: V0.2 specification baseline

Last updated: 2026-07-13

## Purpose

この文書は V0.2 Bridge mock / interface が扱う最小データ形を定義する。目的は、ocgcore の binary message format を完全再現することではなく、後続実装で Message、Action-like object、core input の境界がぶれないようにすることである。

## Message Dict

Message dict は Bridge への入力である。V0.2 では raw binary message ではなく、mock または decoder が作る Python dict として扱う。

最小形:

```json
{
  "message_type": "select_card",
  "payload": {
    "candidates": ["card-1", "card-2"],
    "min": 1,
    "max": 1
  },
  "source": "mock",
  "sequence": 0
}
```

必須:

- `message_type`: Bridge が解釈する message 種別。
- `payload`: message 固有の情報。空の場合も dict とする。

任意:

- `source`: `mock`, `ocgcore`, `fixture` などの発生元。
- `sequence`: 同一 replay / test 内での順序。
- `raw`: 将来 decoder が保持する元データ。V0.2 mock では不要。

## Action-like Dict

Action-like dict は Bridge が Python 側へ渡す中間表現である。Search Engine の正式 Action model ではなく、V0.2 では Replay と test が読める最小形に限定する。

最小形:

```json
{
  "action_type": "select_card",
  "payload": {
    "candidates": ["card-1", "card-2"],
    "min": 1,
    "max": 1
  },
  "source": {
    "kind": "bridge_message",
    "message_type": "select_card",
    "sequence": 0
  }
}
```

必須:

- `action_type`: Python 側で扱う action 種別。
- `payload`: action 固有の情報。Message dict の payload をそのまま使える場合はコピーしてよい。
- `source`: どの Message から生成されたかを追跡する情報。

V0.2 mock の既定変換は、`message_type` を `action_type` に写し、`payload` を保持する。正規化、合法性判定、候補除外は行わない。

## Core Input Dict

Core input dict は Python 側の Action-like dict を ocgcore へ返す入力候補である。V0.2 では実 ocgcore へ送信しない。

最小形:

```json
{
  "input_type": "select_card",
  "payload": {
    "selected": ["card-1"]
  },
  "source_action_type": "select_card"
}
```

必須:

- `input_type`: core 側へ返す入力種別。
- `payload`: core input 固有の情報。
- `source_action_type`: 元になった Python action 種別。

## Unsupported And Invalid Messages

Message dict が `message_type` または `payload` を欠く場合は invalid shape として扱う。

Bridge が `message_type` を認識できない場合は unsupported message として扱う。unsupported message は合法・違法を意味しない。単に V0.2 Bridge が変換仕様を持っていないことを表す。

V0.2 実装では、invalid shape と unsupported message を区別できる例外または診断を返す。どちらの場合も、Python 側でルール判断を補完してはならない。

## Non-Goals

- ocgcore binary message の完全 decode
- 全 selection request type の網羅
- DecisionRequest model の完全仕様化
- invalid response 時の duel 継続方針
- request signature 照合
