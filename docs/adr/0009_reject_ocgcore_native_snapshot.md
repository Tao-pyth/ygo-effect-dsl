# ADR-0009: ocgcore v11のnative mid-duel snapshot/cloneを採用しない

Status: Frozen

Date: 2026-07-13

Decision Issue: #101

Evidence: `docs/adr/evidence/0009_ocgcore_snapshot_audit.json`

## Context

Replay prefix再実行の短縮策として、native duel handleのcopy、mid-duel snapshot、serialize/restoreをcacheする案を検討した。採用にはLua VM、RNG、chain、effect usage、pending processor/request、callback ownership、script stateを含む完全copyと、clone元/先を任意順序でDestroyできる独立所有権が必要である。

対象はlock済みocgcore API 11.0、commit `158aebe758be3c46249c75d602e3f16d63d2ef31`、tree `23915a17e8e0d6b0b64ffc868bf0067a55e00aa0`である。source audit IDは`snapshotaudit_9d5ed8c92bb6b7e11272668b9f152b3aee6575f7998e832d06ac2d81a55d58b1`である。

## Findings

公開`ocgapi.h`には13関数があり、duel lifecycle、process、response、script load、queryを提供する。snapshot、serialize、deserialize、restore、duel clone、duel copyに相当する公開関数は0件である。Queryは観測用bufferを返すAPIであり、Lua VMやpending processorを復元する入力APIではない。

内部の`effect::clone()`と`interpreter::clone_lua_ref()`は同じ`pduel`とLua state上でEffect参照を複製する処理で、duel全体のcopyではない。公開ABIとして利用できず、別duel ownershipも作らない。

`duel`と関連classの状態は次へ分散する。

- `duel.h`: `field*`、`interpreter*`、card/group/effectの生ポインタ集合、private Xoshiro256 RNG、message/query buffer、callback関数、callback payload
- `interpreter.h`: `lua_State*`、current state、coroutine map、call depth
- `field.h`: processor units/subunits/reserved、selection候補、current chain、effect count map

これらのpointer graph、Lua registry/coroutine、callback payloadを完全複製するformat、version、ownership契約は存在しない。C++ objectのmemory copyはdouble free、元/先のalias、stale callback、RNGまたはprocessor欠落を生む。

## Decision

ocgcore v11のnative mid-duel snapshot/cloneは採用しない。Replay prefix cacheは`verified_replay_hint`だけを保持し、cache hitでもfresh workerを作成して初期条件からReplay prefixを再実行する。native duel handle、pointer、Lua state、callback、raw bufferはcache entryまたはprocess間で共有しない。

`ReplayPrefixCacheEntry`は`native_snapshot`と`native_clone`を明示的に拒否する。cache hit後はterminal State ID、next DecisionRequest signature、core trace digestを照合し、不一致entryをinvalidateする。

clone APIが存在しないため、cloneとfresh Replayの大量fixture比較、clone元/先のDestroy順序、clone crash/timeout ownership testは実行不能であり、採用条件へ進まない。これは未検証のまま採用する判断ではなく、公開capability gateでの却下である。

## Snapshot Format Policy

現行版にはsnapshot formatを定義しない。将来再評価して採用する場合は、opaque native bytesだけを保存せず、最低限次のversioned envelopeを必須とする。

- snapshot schema versionとwriter/reader compatibility
- ocgcore API、source commit/tree、binary SHA-256
- card databaseとcard scriptのcommit/lock ID
- rules/duel flags、seed、player config、locale
- Experiment schema、Replay schema、initial snapshot hash、prefix digest
- pending request signature、exact State ID、raw core trace digest

いずれかが不一致ならrestoreせずfresh Replayへfallbackする。readerはunknown field/version、truncated payload、oversize payload、checksum不一致をfail-closeする。

## Re-evaluation Conditions

次をすべて満たした場合だけ再評価する。

1. pin対象ocgcoreに公開かつversionedなduel serialize/restoreまたはclone APIが追加される。
2. API文書または実装契約がLua VM、RNG、processor、chain、effect usage、callback再bindingを対象に含める。
3. auditが公開state-transfer関数を検出してCIをfailさせ、ADR更新を要求する。
4. 多数fixtureの各prefixでfresh ReplayとDecisionRequest、exact State ID、raw trace、最終Route IDが一致する。
5. clone元/先の両Destroy順、片側継続、worker crash/timeout、malformed snapshotをsanitizerまたは同等の検査で通過する。

## Consequences

- correctnessとownershipを公開APIで説明できない最適化を排除できる。
- prefix cacheは検索結果の同値性確認と再実行hintに限定される。
- cache hitでもReplay prefix再実行costは残る。予算と効果測定はIssue #102で扱う。
- 将来公開APIが追加されるとsource auditがfail-closeし、無言で方針が陳腐化しない。
