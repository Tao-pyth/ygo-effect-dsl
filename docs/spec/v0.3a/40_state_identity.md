# State Identity Specification

Status: Frozen pre-search contract (ADR-0007)

Last updated: 2026-07-13

## Responsibility

State は探索、評価、枝刈り、Replay 検査で参照するゲーム状態表現である。
State は Python が状態遷移を実装するためのものではない。
State は ocgcore / EDOPro Lua から観測された状態を正規化し、同値判定と評価に使うための表現である。

## Standard Shape

State ID schema versionは`ygo-state-id-v1`とし、canonical inputを次で固定する。

```python
@dataclass(frozen=True)
class CanonicalState:
    public_state: Mapping[str, Any]
    private_state: Mapping[str, Any]
    constraints: Mapping[str, Any]
    history: Mapping[str, Any]
    pending_request: Mapping[str, Any] | None
    engine_state: Mapping[str, Any]
    information_mode: InformationMode
    completeness: StateIdentityCompleteness
    viewer: int | None
    sampling_reference: Mapping[str, Any] | None
    missing_fields: tuple[str, ...]
    schema_version: str
```

- `public_state`: turn、turn player、priority、phase、chain、LP、公開zoneなど。
- `private_state`: information modeで許可された手札、deck順、非公開カードなど。
- `constraints`: 通常召喚権、特殊召喚制限、locks、pledges、期限付き制約など。
- `history`: 使用済み効果key、残存効果、公開済み情報、過去依存のルール状態など。
- `pending_request`: 現在のDecisionRequestを再同定する情報。
- `engine_state`: core/runtime identity、乱数状態参照、snapshot schemaなど。
- `information_mode`, `viewer`, `sampling_reference`: 非公開情報の観測条件。
- `completeness`, `missing_fields`: exact identityを構成できるかと、取得不能な項目。

`state_id`は上記canonical inputのSHA-256へ`state_` prefixを付ける。`state_id`自身、表示metadata、timestamp、Python object identityはhash inputに含めない。

## State Scope

State は visible board だけでは不十分である。
最低限、次の情報を含める。

- turn number
- turn player
- priority player
- phase
- chain state
- player LP
- field zones
- hand count and known hand cards
- graveyard
- banished
- deck count and known deck order
- extra deck count and known extra cards
- normal summon availability
- special summon constraints
- used once-per-turn keys
- lingering effects
- locks and pledges
- remaining mandatory effects
- public counters and flags
- information mode

同じ場と手札でも、通常召喚権、ターン1効果使用済み、制約、残存効果が異なる場合は別 State である。
これらの実装schema、期限、visibility制約は[Rule history, constraints, and visibility state](../../state/10_rule_and_visibility_state.md)に定義する。

## Complete Identity

complete state identity は Replay 整合性に使う完全同値である。
complete canonical hash は、同じ情報モードで観測可能かつ再現に必要な全 field から生成する。
complete hash は枝刈りのために情報を落としてはならない。

complete hash の対象には次を含める。

- public and private zone contents allowed by information mode
- card instance identity
- zone and sequence
- effect usage keys
- summon rights
- locks and pledges
- lingering effects
- chain and pending effects
- phase and priority
- deck order when known or sampled
- random state reference when required by replay

`completeness: exact`では`missing_fields`を許可しない。現在のocgcore Query API snapshotは`query_api_projection`であり、未取得項目を明示したState IDとして扱う。これにより不完全なprojectionを完全同値と誤認しない。

## Search Approximate Identity

search approximate identity は探索爆発対策のための近似同値である。
これは完全同値ではない。
search hash は評価cache、探索順序、exact比較を行うtransposition候補抽出に使えるが、Replayの正当性検査、合法性cache、直接枝刈りには使ってはならない。

search hash で落としてよい情報は Experiment が明示する。
例として、非公開 deck order、同値とみなす hand permutation、評価に影響しない表示 metadata は落とせる。
ただし、召喚権、ターン1使用済み、phase、chain、priority、locks、pledges は既定では落とさない。
実装上の利用制限、policy versioning、cache・pruning規則は[Exact and approximate State equivalence](../../state/20_equivalence_and_keys.md)に定義する。近似keyはReplay、合法性cache、直接枝刈りへ使用できず、常にexact確認を必要とする。

## Canonicalization

canonical hash は canonical JSON から生成する。
canonical JSON は次を満たす。

- deterministic key order
- deterministic list order
- explicit schema version
- explicit information mode
- no timestamp
- no display label dependency
- no object memory address dependency

hash algorithm は `sha256` を既定とする。
hash input の schema version が変わる場合、過去 cache は無効化する。
`CanonicalState.from_dict`は未知schema version、必須section欠落、`state_id`改ざんをfail-closeする。setとして扱う`missing_fields`はsort・deduplicateし、zone、chain、選択など意味のあるlist順序は維持する。

## Hidden Information

State は情報モードを必ず持つ。

- `complete_information`: 全プレイヤーの非公開情報を含む。
- `player_view`: 指定プレイヤーから見える情報のみ含む。
- `sampled_private_state`: sampling seed で補完した非公開情報を含む。

情報モードが異なる State hash は比較してはならない。
情報リークを避けるため、player view の評価器は相手の未知手札や未知 deck order を直接参照しない。

## Dominance

支配関係による枝刈りは complete identity とは別の判定である。
V0.3a では支配関係を必須実装にしない。
導入する場合は Experiment が dominance rule id と version を記録し、Replay の正当性とは分離する。

## Acceptance Criteria

- visible board だけでは State として不十分だと明記されている。
- complete hash と search hash が別用途として定義されている。
- 召喚権、ターン1使用済み、制約、chain、phase、priority が State identity に含まれる。
- information mode が hash 比較の前提として定義されている。
- public/private state、constraints、history、pending request、engine stateがversioned schemaとして実装されている。
- 不完全なQuery API projectionがexact identityと区別されている。
- 召喚権、使用済み効果、制約期限、情報モード別private stateをcanonical sectionへ保存できる。
- exact比較の必要十分条件と、approximate keyを直接枝刈りへ使わない規則がAPIで強制されている。

## Future Contract Tests

- `test_state_canonical_hash_is_stable`
- `test_minimal_canonical_state_fixture_is_stable_and_round_trips`
- `test_state_id_is_canonical_and_changes_with_identity_sections`
- `test_state_hash_changes_when_normal_summon_right_changes`
- `test_state_hash_changes_when_once_per_turn_key_changes`
- `test_state_search_hash_is_declared_approximate`
- `test_state_hash_rejects_cross_information_mode_comparison`
