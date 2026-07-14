# Replay Determinism Specification

Status: Frozen pre-search contract (ADR-0007)

Last updated: 2026-07-13

## Responsibility

Replay は探索結果を再現、比較、監査するための履歴である。
V0.3a での最上位保証は「同じ環境、同じ初期条件、同じ Action 履歴なら、同じ DecisionRequest に戻る」ことである。
Replay は探索アルゴリズムを所有しない。
Route DSLはReplayを内包し、checkpoint、評価、Peak Board、妨害lineageを加える。ReplayのAction履歴が再現性の真実源であり、Route DSLの表示情報や評価値はReplay照合を変更しない。

## Determinism Guarantee

Replay executor は各 step で次を検査する。

1. 初期条件と version metadata が一致する。
2. core が次に返した DecisionRequest の `request_signature` が Replay 記録と一致する。
3. Replay Action の `request_signature` が現在の DecisionRequest と一致する。
4. Action response が candidates と constraints に整合する。
5. Action 適用後、次 step へ進める。

署名が一致しない場合は replay failure とする。
Python は近い candidate を推測して補正しない。

## Seeds

Replay は次の seed を保存する。

- `duel_seed`: core duel random。
- `shuffle_seed`: deck shuffle。
- `search_seed`: search policy random。
- `worker_seed`: 並列 worker 割当。
- `sampling_seed`: 非公開情報 sampling。

V0.3a では seed から初期デッキ順を復元できる場合でも、初期デッキ順 snapshot を保存する。
seed と snapshot が矛盾する場合は Replay を invalid とする。
加えて、全core response、全raw output frame、message化されたshuffle/random select/coin/dice結果を順序付きで保存する。`Duel.GetRandomNumber`の直接Lua乱数は、同じ引数で元関数を1回呼ぶversion固定wrapperでdraw index、inclusive range、resultをtraceへ追加する。計装script hashとtransport設定はReplay manifest identityへ含める。暫定Hint transportの互換性検証は#107で追跡する。

## Initial Snapshot

Replay は最低限次を保存する。

- player config
- main deck order
- extra deck order
- starting player
- opening hand policy
- LP
- rule config
- asset config
- banlist config
- public experiment id

非公開情報を含む snapshot は、視点モードに応じて保存範囲を明示する。
完全情報モードでは全 deck order と hand を保存する。
プレイヤー視点モードでは、公開してよい情報と sampling seed を分離する。

## Event Records

Replay は各 step で次を記録する。

- `step`
- `node_id`
- `request`
- `request_signature`
- `action`
- `action_id`
- `action_occurrence_id`
- `turn` optional
- `turn_action_index` optional
- `chain_index` optional
- `core_input_ref`
- `core_response`
- `core_output`
- `state_hash_before`
- `state_hash_after`
- `timestamp` optional
- `failure` optional

`timestamp` は deterministic 比較の対象にしない。
Replay の canonical JSON では deterministic field と non-deterministic metadata を分離する。
Route DSLへ埋め込む場合も同じ分離を維持する。
`action_id`は選択内容の同一性、`action_occurrence_id`はReplay内の1回の実行を表す。後者は`action_id`, `step`, `state_hash_before`, `turn`, `turn_action_index`, `chain_index`から決定論的に生成し、Route DSL validatorで再計算する。旧Routeとの読み取り互換のため、`action_occurrence_id`がないイベントは受理する。

## Version Metadata

Replay は次を保存する。

- replay schema version
- project version
- Python version
- Python package lock identifier
- ocgcore commit / build id
- EDOPro Lua scripts commit
- cards.cdb hash
- constants hash
- banlist hash
- master rule
- custom patch hash
- direct random instrumentation schema and script hash
- evaluator id and version
- experiment schema version

version metadata が一致しない Replay は既定で strict failure とする。
互換性を明示した migration がある場合のみ warning 付きで読み込める。

## Schema Version

V0.3a Replay schema は `0.3a` とする。
V0.2 の `ReplayHistory` は legacy minimal format として維持する。
V0.3a schema は V0.2 を破壊せず、後続実装で別 loader または migration を用意する。

## Partial And Branch Replay

途中再生は prefix replay として扱う。
prefix の最後で現在の DecisionRequest が Replay 記録と一致することを検査する。

分岐再生は prefix replay 後に別 Action を適用する。
分岐元は `parent_run_id`, `parent_node_id`, `prefix_length` で参照する。

## Corruption Detection

Replay は次を破損または不整合として扱う。

- JSON parse failure
- required field missing
- schema version unsupported
- action step gap
- duplicate action id within same request where impossible
- initial snapshot hash mismatch
- request signature mismatch
- action response invalid
- version metadata mismatch under strict mode

## Acceptance Criteria

- 「同じ履歴なら同じ DecisionRequest に戻る」が最上位保証として明記されている。
- seed と初期デッキ順 snapshot の両方を保存すると定義されている。
- 全response、raw core output、観測可能なランダム結果を順序付きで保存すると定義されている。
- request signature mismatch が replay failure と定義されている。
- V0.2 format を破壊しない方針が明記されている。

## Future Contract Tests

- `test_replay_returns_to_same_decision_request`
- `test_replay_rejects_request_signature_mismatch`
- `test_replay_records_initial_deck_order`
- `test_replay_records_version_metadata`
- `test_replay_prefix_can_branch_from_recorded_request`
