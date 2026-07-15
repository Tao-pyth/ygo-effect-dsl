# Real-core Replay pool calibration

Status: verified local Windows evidence

Last updated: 2026-07-15

## Scope

`real-core-replay-benchmark-v1`は、外部qualification済みshort、long、grave/banish Routeを`experiment-replay`でfresh process再生する。pool `1/2/4/8/16`、persistence `disabled/index_only`、各16 taskを組み合わせ、計480 Replayのthroughput、CLI coordinator RSS、子ocgcore worker RSS、同時process tree RSS、artifact bytesを測る。raw Experiment、Route、deck、opening hand、card code、絶対pathはsanitized evidenceへ保存しない。

```powershell
python -m ygo_effect_dsl.spikes.real_core_replay_benchmark `
  --experiment short_line=<external>/short.yaml `
  --experiment long_line=<external>/long.yaml `
  --experiment grave_banish_or_chain=<external>/grave.yaml `
  --route short_line=<external>/short.route.yaml `
  --route long_line=<external>/long.route.yaml `
  --route grave_banish_or_chain=<external>/grave.route.yaml `
  --base-evidence docs/adr/evidence/0105_real_core_base_routes.json `
  --logical-evidence docs/adr/evidence/0105_general_search_100k.json `
  --failure-evidence docs/search/evidence/real_core_parallel_stress.json `
  --pool-sizes 1,2,4,8,16 --task-count 16 `
  --work-root <external>/replay-work `
  --out docs/adr/evidence/0128_real_core_replay_pool.json `
  --parquet-out docs/adr/evidence/0128_real_core_replay_pool.parquet
```

## Result

Evidence IDは`realreplaybench_0e34c19adba235cd1a1824aa7715b17a22a9692733edb61396a333e7398f2c42`で、480/480 Replayが成功した。全profileでRoute ID、terminal State、semantic digest、best Routeはpool sizeとpersistence modeに依存しない。

| Pool | Maximum main + active process tree RSS | Disabled throughput range |
|---|---:|---:|
| 1 | 209 MiB | 0.127-0.156 Replay/s |
| 2 | 356 MiB | 0.204-0.238 Replay/s |
| 4 | 633 MiB | 0.277-0.330 Replay/s |
| 8 | 1,164 MiB | 0.335-0.388 Replay/s |
| 16 | 2,216 MiB | 0.325-0.406 Replay/s |

1 workerのpeak RSSは約96-100 MiBである。pool 16は完走するが旧`memory-preflight-v2`上限を超え、long/graveではpool 8よりthroughputが低下した。`real-core-worker-policy-v1`はdefault pool 4、max pool 8、native state reuse禁止、verified Replay hintだけを許可する。`real-core-memory-preflight-v1`は1.25倍安全係数を適用し、推奨process memory limitを1.5 GiBとする。

`index_only`は16 taskあたり約27-29 KiB、semantic indexに対して約9.4-9.8倍のwrite amplificationを持つ。長時間corpusで全Replay reportを保存する既定にはせず、aggregate indexと選択Route evidenceへ限定する。

## Resolver and failure boundary

CardScripts checked directory indexは20,963 entry、名称推定558,452 bytes、RSS増分約1.9 MiBである。93 scriptのcold resolutionは0.252秒、同一process warm resolutionは0.120秒で約2.09倍差となった。asset directory identity検査を迂回するpersistent indexは採用せず、process-local checked indexを維持する。永続化またはworker常駐化はasset mutation/trust boundaryを[#212](https://github.com/Tao-pyth/ygo-effect-dsl/issues/212)で検証してから判断する。

この校正は[#128](https://github.com/Tao-pyth/ygo-effect-dsl/issues/128)の実Replay受け入れ条件を満たす。後続の[#212](https://github.com/Tao-pyth/ygo-effect-dsl/issues/212)ではcross-process indexとresident workerを比較し、mutation検査またはnative isolationを弱めずにend-to-end優位を証明できないため、`resolver-index-policy-v1`で測定済み不採用とした。

crash、timeout、callback failure、retry、process cleanupは`real-core-parallel-stress-v2`の`realcorestress_a6868c...`を参照する。480 Replay測定中に一時的な30秒内部timeoutを観測したため、通常既定30秒は維持しつつbenchmarkだけworker timeoutを90秒へ明示設定した。これはtimeoutを成功へ読み替える変更ではなく、高負荷校正の実行上限を分離するものである。

この結果は32 GiB Windows host、固定core/API/assets、現在checkoutのlocal evidenceであり、他host、全deck、production SLAへ一般化しない。
