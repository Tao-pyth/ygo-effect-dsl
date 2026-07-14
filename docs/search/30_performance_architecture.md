# Replay-based Search Performance Architecture

Status: V0.2 prototype cache budget calibrated

Last updated: 2026-07-13

Evidence: `docs/search/evidence/prefix_cache_benchmark.json`

## Correctness baseline

任意の探索prefixはfresh isolated workerでReplay prefixを再実行できなければならない。cache、pool、並列完了順はAction、DecisionRequest、Replay、State、Evaluation、Routeのidentityを変更しない。cache miss、破損、予算超過、worker置換ではfresh Replayへ戻る。

`verified_replay_hint` cacheはnative duel handleやLua VMを保存しない。完全なReplay manifest、初期snapshot hash、Replay schema、ordered Action ID、request signature、core responseからprefix keyを作り、既存immutable Replay/Route artifactへの参照だけを保持する。

cache hitでもfresh workerでprefixを再実行し、terminal State ID、次request signature、core trace digestを照合する。不一致entryは即時削除する。このため現行modeではhitとmissのどちらもfresh Replayを1回必要とし、hit率をcore実行削減率として扱わない。

## Native state decision

ADR-0009によりocgcore v11のnative snapshot/cloneは不採用である。公開state-transfer API、完全copy format、Lua/RNG/processor/callback ownership契約がないため、`native_snapshot`と`native_clone`はruntimeで拒否する。

将来公開APIが追加された場合はsource auditがfail-closeし、fresh ReplayとのDecisionRequest、exact State、raw trace一致を確認するまで採用しない。

## Invalidation

prefix keyはReplay manifest全体のhashを含む。core API/lock/commit/binary、asset lock/commit/hash、rule flags、seed/random policy、初期snapshot、Replay/Bridge/State schemaの変更は別keyになる。Actionまたはcore response prefixの変更はprefix digestを変える。

Evaluatorのweight変更はReplay prefixを変えないためprefix cacheを無効化しない。evaluation cacheはState ID、Evaluator ID/version/config、information mode、vector schemaを別keyとして管理する。

timestamp、表示label、Python object identity、worker番号、PID、完了順はkeyに含めない。

## Calibrated policy

```yaml
search:
  parameters:
    performance:
      prefix_cache:
        max_entries: 4096
        max_bytes: 16777216
        max_entry_bytes: 65536
        persistence_mode: index_only
        flush_every_mutations: 1000
```

policy schemaは`prefix-cache-policy-v1`、推奨policy IDは`prefixpol_b603c5ccc70d52adc420f718bfe4baa16b3a442cbbb6b5b35647c530e81102f8`である。Experimentが上書きしない場合も、run metadataには解決後のpolicy全体とpolicy IDを保存する。

上限超過時の挙動:

- 1 entryが64 KiBを超える場合は保存せず、明示的なerrorにする。
- entry数または総byte上限を超える場合はdeterministic LRUで最古entryを削除する。
- eviction、破損、manifest変更はfresh Replay fallbackへ進み、探索失敗にはしない。
- persistence失敗またはindex破損ではindexを信頼せず、空cacheから再構築する。

## Benchmark

実行コマンド:

```powershell
$env:PYTHONPATH='src'
python -m ygo_effect_dsl.spikes.prefix_cache_benchmark --out docs/search/evidence/prefix_cache_benchmark.json
```

benchmark ID: `prefixbench_5fbc99d4cfa63d523881bd0e5f0a45372feba5e264d52b1350fcb4296c2334fe`

対象は実コアEffect Veilerのbase/interrupted Route全23 prefixと、同じentry shapeを使う4,096 deterministic branch、20,000 lookupである。access分布は80%を上位20%のhot set、20%を全体へ割り当てた。

実Route entry size:

| Metric | Bytes |
| --- | ---: |
| min | 1,099 |
| median | 1,099 |
| p95 | 1,101 |
| max | 1,101 |

capacity比較:

| Entries | Hit rate | Eviction rate per miss | Python cache heap peak | Fresh Replay count |
| ---: | ---: | ---: | ---: | ---: |
| 64 | 0.05520 | 0.996613 | 19,074 B | 20,000 |
| 256 | 0.21490 | 0.983696 | 74,127 B | 20,000 |
| 1,024 | 0.70350 | 0.827319 | 289,415 B | 20,000 |
| 4,096 | 0.79895 | 0 | 935,151 B | 20,000 |

16 MiB totalは実測1.1 KiB entryを4,096件保持する約4.5 MiBのserialized payloadに対して3倍以上のheadroomを持つ。64 KiB/entryは現行p95の約59倍で、異常に大きいentryを1 MiBまで許していた旧defaultを縮小する。

## Persistence

index-onlyはcache key、terminal照合値、completeness、immutable artifact refだけをatomic replaceで保存する。Replay event、initial snapshot本文、hand、deck order、card data、core response、native handle、response bufferは保存しない。構造化key監査は全禁止keyが0件で通過した。

2,048 entryのfinal indexは約2.14 MBだった。

| Flush interval | Flushes | Write amplification | Recovery startup |
| ---: | ---: | ---: | ---: |
| 100 | 21 | 11.252851x | 549.256 ms |
| 1,000 | 3 | 2.464670x | 491.101 ms |

flush 100はfull index書換え回数が多く、final sizeの11倍以上を書き込むため不採用とする。flush 1,000をdefaultとし、process crash時は最大999 mutations分のhintを失うが、Replay/Route artifactは失わず空cacheから再構築できる。`disabled`はwrite/startup cost 0で、毎run空cacheから始める。

## Worker pool memory

実コアworker 3回のpeak RSSは40,325,120、40,505,344、40,546,304 bytesだった。最大値へ25% marginを加え、1 workerのbudgetを49 MiBとする。

main processの既存RSSを除くcache + worker追加予算:

| Pool size | Additional budget |
| ---: | ---: |
| 1 | 65 MiB |
| 2 | 114 MiB |
| 4 | 212 MiB |
| 8 | 408 MiB |

計算式は`cache.max_bytes + pool_size * 49 MiB`である。main process、Route artifact、dataset、reporting bufferは別予算として加算する。poolを増やす前にこの上限をrun metadataへ記録し、利用可能memoryを超える構成を起動前に拒否する。

## Scope

この校正は現行prototypeのEffect Veiler fixtureとdeterministic branch workloadに対するdefaultであり、任意デッキ、長いcombo、数十万nodeのproduction tuningではない。複数デッキ・長prefix・実探索frontierでの再校正はIssue #105で追跡する。
