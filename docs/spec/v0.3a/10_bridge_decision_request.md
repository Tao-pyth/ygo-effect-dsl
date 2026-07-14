# Bridge / DecisionRequest Specification

Status: Frozen pre-search contract (ADR-0007)

Last updated: 2026-07-13

## Responsibility

Bridge は Python と ocgcore / EDOPro Lua の境界である。
Bridge は core message を Python 側の DecisionRequest に変換し、Python 側の Action response を core input に変換する。
Bridge は合法性を判断しない。
合法性、状態遷移、カード効果解決、チェーン処理は ocgcore / EDOPro Lua が所有する。

## Duel Lifecycle

V0.3a で固定する lifecycle は次である。

1. `create_duel(config)` で Duel instance を生成する。
2. `load_assets(asset_config)` で Lua script、card database、constant、banlist、rule config を読み込む。
3. `set_players(players)` で player id、deck、extra deck、initial LP、starting player を設定する。
4. `set_seed(seed_config)` で shuffle、random choice、worker allocation に使う seed を固定する。
5. `start()` で duel を開始する。
6. `process()` を DecisionRequest、terminal、error、timeout のいずれかに到達するまで進める。
7. `respond(request_id, response)` で Python から選択結果を返す。
8. `destroy()` で Duel instance を破棄する。

実装では resource leak を避けるため、`destroy()` は正常終了、エラー、timeout のすべてで呼ばれる必要がある。

## Process Unit

`process()` の進行単位は「Python が判断すべき DecisionRequest まで進める」ことである。
内部のチェーン解決、誘発確認、強制処理、継続処理は core 側で進める。
`process()` は次のいずれかを返す。

- `decision_request`: Python が応答すべき選択要求。
- `terminal`: duel が終了した。
- `idle`: 追加入力なしに進行できないが、DecisionRequest も生成できない異常状態。
- `error`: core error、decode error、asset error、unsupported message。
- `timeout`: 指定時間または step budget を超えた。

## DecisionRequest

DecisionRequest は探索、Replay、ログ、妨害指定の入口である。
文書上の標準型は次で固定する。

```python
@dataclass(frozen=True)
class DecisionRequest:
    request_id: str
    request_type: str
    player: int
    candidates: tuple["Candidate", ...]
    constraints: "DecisionConstraints"
    context: "DecisionContext"
```

必須フィールドの意味は次である。

- `request_id`: 同一 Duel instance 内で一意な要求 ID。
- `request_type`: `activate_effect`, `select_card`, `select_option`, `normal_summon`, `special_summon`, `pass`, `end_turn` などの要求種別。
- `player`: 応答権を持つ player id。原則 `0` または `1`。
- `candidates`: core が合法候補として提示した Candidate の順序付き tuple。
- `constraints`: 選択数、順序要求、重複可否、必須/任意などの制約。
- `context`: phase、chain、turn player、priority player、visible board、request source、version metadata などの補助情報。

`request_signature` は DecisionRequest の canonical JSON から生成する。
署名対象には `request_id` を含めない。
署名対象には `request_type`, `player`, `candidates`, `constraints`, `context` のうち Replay 再現に必要な deterministic field を含める。

## Candidate

Candidate は Action が参照する合法候補である。
Candidate には次を含める。

- `candidate_id`: DecisionRequest 内で一意な ID。
- `kind`: `card`, `effect`, `option`, `position`, `zone`, `pass`, `end_turn` など。
- `label`: UI / report 用の表示名。
- `card_ref`: カード候補の場合の個体参照。
- `effect_ref`: 効果候補の場合の効果参照。
- `payload`: core response 生成に必要な opaque data。

Python は `payload` の意味をルールとして解釈しない。
Bridge は `candidate_id` と `payload` を使って core input を再構成する。

## Response

Python からの応答は DecisionRequest に対する Action response である。
応答は次を満たす。

- `request_id` が一致する。
- `request_signature` が一致する。
- `selected_candidate_ids` が `candidates` に含まれる。
- `constraints` に違反しない形で選択されている。
- core input に必要な payload を復元できる。

制約違反、署名不一致、未知 candidate は Bridge error として扱い、Python 側で補正しない。

## Asset Loading

asset config には次を記録する。

- ocgcore commit / build id
- EDOPro Lua scripts commit
- cards.cdb identifier and hash
- constants identifier and hash
- banlist identifier and hash
- master rule
- custom patch identifier and hash

Replay と Experiment は同じ asset config を参照できる必要がある。

## Error Policy

Bridge は error を分類して返す。

- `invalid_message`: message shape が不正。
- `unsupported_message`: decode はできたが V0.3a 未対応。
- `invalid_response`: Python response が request と整合しない。
- `core_error`: ocgcore が返したエラー。
- `asset_error`: Lua / CDB / constants / banlist の読み込み失敗。
- `timeout`: process / response / destroy が budget を超えた。

未対応 message は合法性判断で代替しない。
未対応 message を受けた run は failed とし、ログと Replay に failure reason を残す。

## Acceptance Criteria

- `DecisionRequest` の必須フィールドと署名対象が文書上で固定されている。
- `process()` が返す状態が列挙されている。
- Python response が `request_id` と `request_signature` に紐づくことが明記されている。
- asset version と error category が Replay / Experiment から参照できる。

## Future Contract Tests

- `test_bridge_decision_request_contract`
- `test_bridge_rejects_invalid_response_signature`
- `test_bridge_distinguishes_invalid_and_unsupported_message`
- `test_bridge_records_asset_version_metadata`
- `test_bridge_process_returns_decision_or_terminal_or_error`
