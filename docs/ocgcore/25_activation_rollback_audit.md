# Activation rollback audit

Status: remains unsupported in audited upstream ocgcore API 11.0

Last updated: 2026-07-14

## 結論

`ACTIVATE_EFFECT` setup中のcancelable `MSG_SELECT_CARD`へnative cancel response `ffffffff`を返しても、固定・無改造ocgcore API 11.0は`MSG_CHAINED`を生成する。発動全体をrollbackし、`MSG_CHAINED`を生成しない実コア経路は確認できない。このため分類は`raw_replay_contract_core_unreachable`を維持する。

raw Replayの`cancelled_selection` fixtureはparser/aggregationの保守的契約として残す。実コアで到達不能であることは、raw fixtureを削除する理由にはならない。一方、到達不能なraw fixtureをproduction対応済みのRouteとして表示してはならない。

## Runtime probe

fixture `action_activation_rollback_probe_v1`は、召喚成功時に発動する効果のcost callbackでcancelable `Duel.SelectMatchingCard`を要求する。fresh workerは空の`DECLINE` Actionをnative `ffffffff`へencodeし、次のraw batchを保存する。

- core: API 11.0、source `158aebe758be3c46249c75d602e3f16d63d2ef31`
- custom patches: none
- response: `ffffffff`
- follow-up message types: `[71, 16]` (`MSG_CHAINED`, `MSG_SELECT_CHAIN`)
- next request: `select_chain`
- chain count: `1 -> 1`
- probe evidence: `rollbackprobe_274065e5270b5a216b2f228d743919fa4826e693bb416e236892d79d2cee5833`

manifestはcore lock/binary SHA-256、fixture script SHA-256、card database commit/hashと使用行、seed `[1,2,3,4]`、response bytes、前後State IDを固定する。2つのfresh workerでdocumentとstdout digestが一致する。

## Upstream audit

2026-07-14時点のupstream `edo9300/ygopro-core`を次の範囲で監査した。一次情報は[`v11.0` release](https://github.com/edo9300/ygopro-core/releases/tag/v11.0)、[`master` commit](https://github.com/edo9300/ygopro-core/commit/0764db0c75b3d1d574880d365aa3695ab1f13b43)、[`master` API macros](https://github.com/edo9300/ygopro-core/blob/0764db0c75b3d1d574880d365aa3695ab1f13b43/ocgapi_types.h#L10-L11)である。

| 対象 | commit | API | 検証方法 | 結果 |
| --- | --- | --- | --- | --- |
| release `v11.0` | `158aebe...` | 11.0 | pinned binary runtime probe + source | rollback不可 |
| `master` | `0764db0...` | 11.0 | source auditのみ | 該当contractはreleaseと同じ |

`master`は`v11.0`から74 commits先だが、`AddChain`、`ExecuteCost`、`ExecuteTarget`、response parserの関数bodyは同一である。Lua wrapperの所有権型変更はあるが、cancel flag、Lua `nil`、`SelectCard` processorへの伝播に必要なmarkerは維持されている。未ビルドHEADをruntime検証済みとは扱わない。

audit evidenceは`docs/ocgcore/evidence/activation_rollback_audit.json`に保存する。evidence IDは`rollbackaudit_2476441a3c8ed5acb8c7107acf7a2e3961f1be81bc9ad01a9cb634db44131c98`である。

## Compatibility policy

新しいupstream tag、API version、またはactivation setup制御フロー変更を検出した時だけIssue #117で再監査する。新versionで`MSG_CHAINED`なしのrollback signalが観測されても、直ちに`real_core`へ昇格せず`support_candidate`としてfail-closeする。別versionのreal-core Route、`cancelled_selection` boundary、fresh worker identityを追加してから互換性を昇格する。custom core patchは、ライセンス・再現性・保守責任を別途承認しない限り使用しない。

## 再生成

```bash
python -m ygo_effect_dsl.spikes.activation_rollback_audit --audit-date 2026-07-14
```
