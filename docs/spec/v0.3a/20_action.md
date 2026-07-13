# Action Specification

Status: V0.3a specification baseline

Last updated: 2026-07-13

## Responsibility

Action は DecisionRequest に対する Python 側の選択結果である。
探索木、Replay、ログ、妨害指定、レポートは Action を共通言語として扱う。
Action は合法候補の選択結果を表すが、合法性そのものは core が DecisionRequest として提示した候補に依存する。

## Standard Shape

文書上の標準型は次で固定する。

```python
@dataclass(frozen=True)
class Action:
    action_id: str
    kind: "ActionKind"
    player: int
    source: "CardRef | None"
    effect_ref: "EffectRef | None"
    selections: tuple["Selection", ...]
    request_signature: str
```

必須フィールドの意味は次である。

- `action_id`: Replay、ログ、妨害指定で使う安定 ID。
- `kind`: `ACTIVATE_EFFECT`, `SELECT_CARD`, `SELECT_OPTION`, `NORMAL_SUMMON`, `SPECIAL_SUMMON`, `PASS`, `DECLINE`, `STOP_LINE`, `END_TURN` など。
- `player`: Action を選んだ player id。
- `source`: Action の発生源カード。カードに紐づかない Action では `None`。
- `effect_ref`: 効果発動に紐づく場合の効果参照。
- `selections`: Candidate に対する選択列。
- `request_signature`: 元 DecisionRequest の署名。

## Granularity

Action の粒度は「1つの DecisionRequest への応答」とする。
効果発動、対象選択、コスト選択、解決時選択は、core が別 DecisionRequest として提示する場合は別 Action として記録する。
core が同一 DecisionRequest 内に複数選択を含める場合は、1 Action の `selections` に順序付きで記録する。

この方針により、Python はカードごとの処理手順を推測しない。
Action 境界は core から見える要求境界に従う。

## Selection

Selection は Candidate の選択結果である。

- `candidate_id`: DecisionRequest 内の Candidate ID。
- `order`: 順序選択の場合の 0 始まり index。
- `card_ref`: 選択対象カードの個体参照。
- `effect_ref`: 選択対象効果の参照。
- `value`: option、number、position、zone などの値。
- `payload_ref`: core response 復元に使う opaque payload への参照。

複数選択は `selections` の順序で表す。
順序が意味を持たない選択でも deterministic output のため canonical order を保存する。

## CardRef

同名、同IDカードを区別するため、Action はカード名や card id だけでカードを識別しない。
CardRef は次を持つ。

- `controller`: 現在の controller。
- `owner`: 所有者。
- `location`: hand, deck, extra, field, graveyard, banished など。
- `sequence`: location 内の位置。
- `public_card_id`: 公開済みの場合の card id。
- `instance_id`: Duel instance 内で core が提供できる場合の個体 ID。

非公開カードでは `public_card_id` を必須にしない。
Replay 用の照合では `instance_id` を優先し、提供できない場合は location snapshot と request candidate の組で照合する。

## EffectRef

EffectRef は効果候補を識別する。

- `card_ref`: 効果を持つカード。
- `effect_index`: core / Lua から得られる効果 index。
- `effect_label`: 表示用 label。
- `once_per_turn_key`: 使用済み判定に関わる key。取得できない場合は `None`。

Python は effect text を解析して効果番号を推測しない。
Bridge は core / Lua 由来の識別情報を優先する。

## Stable Action ID

`action_id` は次の canonical input から生成する。

- `schema_version`
- `request_signature`
- `kind`
- `player`
- `source`
- `effect_ref`
- `selections`

`action_id` は表示名、ログ時刻、探索 node id、run id に依存しない。
同じ DecisionRequest に同じ選択を返す Action は同じ `action_id` になる。

## Control Actions

`PASS` は任意発動や任意応答をしない選択である。
`DECLINE` は提示された任意効果、任意処理、任意継続を明示的に拒否する選択である。
`STOP_LINE` は探索上の停止宣言であり、core へ送る turn 終了入力ではない。
`END_TURN` は core に送るターン終了入力である。

`STOP_LINE` は Peak Board 判定でのみ使う。
`END_TURN` は Replay と core progression に記録する。

## Display Action And Replay Action

表示用 Action は report / UI のために label、card name、effect text summary を持ってよい。
Replay 用 Action は deterministic replay のために `action_id`, `request_signature`, `kind`, `selections`, `payload_ref` を持つ。
Replay 用 Action は表示文字列に依存してはならない。

## Acceptance Criteria

- Action は 1 DecisionRequest への応答として定義されている。
- 効果発動、対象選択、コスト選択の分割規則が core request 境界に従うと明記されている。
- `action_id` が表示名、run id、node id に依存しない。
- `STOP_LINE` と `END_TURN` が別概念として定義されている。

## Future Contract Tests

- `test_action_round_trip`
- `test_action_id_is_stable_for_same_request_and_selection`
- `test_action_id_ignores_display_label`
- `test_action_distinguishes_stop_line_and_end_turn`
- `test_action_supports_ordered_multi_selection`
