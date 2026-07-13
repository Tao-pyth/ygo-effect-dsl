# State Identity Specification

Status: V0.3a specification baseline

Last updated: 2026-07-13

## Responsibility

State は探索、評価、枝刈り、Replay 検査で参照するゲーム状態表現である。
State は Python が状態遷移を実装するためのものではない。
State は ocgcore / EDOPro Lua から観測された状態を正規化し、同値判定と評価に使うための表現である。

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

## Search Approximate Identity

search approximate identity は探索爆発対策のための近似同値である。
これは完全同値ではない。
search hash は評価・枝刈り・transposition table に使えるが、Replay の正当性検査には使ってはならない。

search hash で落としてよい情報は Experiment が明示する。
例として、非公開 deck order、同値とみなす hand permutation、評価に影響しない表示 metadata は落とせる。
ただし、召喚権、ターン1使用済み、phase、chain、priority、locks、pledges は既定では落とさない。

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

## Future Contract Tests

- `test_state_canonical_hash_is_stable`
- `test_state_hash_changes_when_normal_summon_right_changes`
- `test_state_hash_changes_when_once_per_turn_key_changes`
- `test_state_search_hash_is_declared_approximate`
- `test_state_hash_rejects_cross_information_mode_comparison`
