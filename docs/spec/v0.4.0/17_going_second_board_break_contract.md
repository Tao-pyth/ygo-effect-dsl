# Going-Second Board-Break Contract

Status: Implemented for the package 0.4.0 local corpus; Issue [#154](https://github.com/Tao-pyth/ygo-effect-dsl/issues/154)

Last updated: 2026-07-15

## Boundary

後攻盤面突破は、相手の先攻1ターン目をPythonで模倣する機能ではない。公開済みの相手盤面を`board-break-initial-state-v1`として固定し、native ocgcoreのplayer 0開始状態へ投入するdeterministic snapshotである。現在のadapterは`turn_player: 0`だけを受理し、player 1開始、相手AI、相手の全合法手探索は未対応としてfail-closeする。

snapshotからの召喚、発動、攻撃、cost、target、option、place選択は、すべて`RealCoreFrontierAdapter`が返した`DecisionRequest`とcandidateだけから選ぶ。Python側でカード効果、発動可否、対象、タイミングを推測しない。

## Experiment input

Experiment `0.4`の`scenario.initial_state`は次の形式を使う。

```yaml
initial_state:
  schema_version: board-break-initial-state-v1
  turn_player: 0
  public_cards:
    - card_code: 14558127
      owner: 1
      controller: 1
      location: monster_zone
      sequence: 0
      position: face_up_attack
      visibility: public
```

`public_cards`は1枚以上を要求する。locationは`monster_zone`、`spell_trap_zone`、`graveyard`、`banished`、positionは`face_up_attack`または`face_up_defense`だけを受理する。field sequenceはmonster zoneで0-6、spell/trap zoneで0-7に制限する。同じcontroller/location/sequenceの重複、DB/Lua asset欠落、裏側カード、private identity、未知schemaをpreflightで拒否する。正規化後の内容から`boardbreakstate_` IDを生成し、`ScenarioManifest`へ保存する。

非公開の相手カードは`public_cards`へ書かない。指定妨害として検証する場合は既存のinterruption定義へ分離し、complete Routeだけがprivate source identityを持つ。PlayerView成果物はそのidentityを保存せず、`information-access-audit-v2`を通過しなければpublishしない。

## Evaluation and success

評価器は`real_core_board_break@1`、出力説明schemaは`board-break-evaluation-v1`である。観測値はactorの手札・monster数と、opponentのmonster、spell/trap、graveyard、banished数に限定する。default weightはversionに固定し、Experimentの`weights`で明示的に上書きできる。未知config key、未知metric、非数値weightは拒否する。

成功条件`real_core_board_break@1`は次の閾値をANDで判定する。少なくとも1閾値を必須とし、負数や未知versionを拒否する。

- `max_opponent_monsters`
- `max_opponent_spell_traps`
- `max_opponent_graveyard`
- `min_opponent_banished`

## Qualified corpus

`examples/experiments/board_break_corpus.yaml`は、固定asset lock上の公式カードで次を同一fresh Replay系列から検証する。

| Category | Actor card | Public target/result |
|---|---|---|
| targetless | Raigeki `12580477` | opponent monster count becomes 0 |
| single target | Mystical Space Typhoon `5318639` | Swords of Revealing Light `72302403` |
| grave/banish | Called by the Grave `24224830` | Maxx C `23434538` moves from graveyard to banished |
| hidden interruption | Solemn Judgment `41420027` | Raigeki line diverges and board-break success becomes false |

baselineとinterrupted Routeは、追加された非公開sourceによるpriority PASSの差を許容しつつ、公開actorの3発動を同じsemantic orderで照合する。共通のRaigeki activationをanchorとし、place選択などcoreが要求する中間Decision列を照合した後、chain responseがbaselineではPASS、interruptedでは指定妨害activationになることを確認する。内部Action IDはcomplete Stateを含むため比較キーにしない。両Routeのterminal evaluation、success、Route IDが異なることも確認する。PlayerViewでは`41420027`を復元できず、information auditが`passed`になることをrelease evidenceとする。

既存`ocgcore-query-v1` Stateで`candidate_action_kinds`が`null`のcandidateは、State identityを変更せずPlayerView投影時に`UNSPECIFIED` categoryへ正規化する。これは効果種別の推測ではなく欠落metadataの明示であり、非文字列・空文字・未知fieldは引き続きfail-closeする。

## Known limits

- opponentの全legal action、先攻展開、hidden board identityの自動生成は行わない。
- battle phaseを含む盤面突破の網羅性は、corpusで実際に到達したcore frontierの範囲に限定する。
- damage step、mandatory trigger、simultaneous trigger、SEGOCは既存taxonomyの未検証categoryをfail-closeする。
- snapshotはnative state cloneではない。各prefixをfresh workerでReplayし、cacheは検証済みhintとしてのみ扱う。
