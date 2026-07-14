# Reproducible Parallel Search

Status: V0.3 result schema and failure propagation contract

Last updated: 2026-07-14

## Deterministic planning

parallel schedulerはcandidateを到着順のままworkerへ渡さない。batch内のcandidateを`work_key`でgroup化し、同じReplay prefix keyと次Action IDを持つworkをsingle-flight化する。各groupではcanonical candidate IDが最小の1件を保持し、unique workをsortして0始まりの`task_ordinal`を付ける。

logical worker slotは`task_ordinal % pool_size`で決める。OS process ID、thread ID、完了時刻、queue到着時刻はtask、node、Replay、Routeのidentityへ含めない。1 logical slotは同時に1 duelだけを所有し、worker replacement後も同じslotとして扱う。

Search node IDはExperiment ID、exact State ID、depth、親node ID、遷移Action IDから生成する。rootは親とActionを持たない。同じStateへ別pathで到達したnodeは別node IDを持ち、State dedupは別のexact State keyで行う。

## Seeds

`ParallelSearchPolicy`は明示的な`base_seed`、`pool_size`、`max_retries`を持つ。taskごとの4-word core seedとPython seedはbase seedとsemantic task IDから生成し、worker slot、pool size、attemptを含めない。このためworker割当やretryでtask randomnessは変わらない。

logical worker seedはbase seed、Experiment ID、logical slotから生成する。これはworker内部の非game補助処理用であり、duel結果へ使用しない。workerがcrashした場合はreplacement generationだけを増やし、logical slot、worker seed、task core/Python seedを維持する。

## Retry

`ParallelTaskResult`のschemaは`parallel-search-result-v2`である。成功時は`failure=null`、失敗時はcategory、disposition、recovery、retryable、message、exception type、contextを含む`FailureRecord`全体を`failure`へ保存する。`status`、`failure_category`、`retryable`は独立した入力値ではなく、`failure`の有無と`failure.retryable`から一意に導出する。このため、永続化された状態と再試行判定が食い違うresultは生成できない。

| Stored failure | Derived status | Derived category | Derived retryable |
| --- | --- | --- | --- |
| `null` | `success` | `null` | `false` |
| `FailureRecord(retryable=true)` | `retryable_failure` | `failure.category` | `true` |
| `FailureRecord(retryable=false)` | `permanent_failure` | `failure.category` | `false` |

retry可能failureだけが次attemptへ進み、defaultは初回に加えて1回までとする。attempt列は0から連続していなければならず、successまたはretry不能failure後の追加resultを拒否する。上限最後のretryable failureはretry exhaustedのtask failureとして残し、成功や合法な候補なしへ変換しない。

retryはfresh replacement workerと同じReplay prefixから行う。native duel handle、callback、bufferはprocessまたはattemptを跨いで共有しない。

### v1 reader migration

readerは`parallel-search-result-v1`を明示的にv2へ移行する。v1のsuccessはfailureを持たないsuccessとして保持する。v1のfailureは元の`retryable`に従い、`true`なら`path_failure + replace_worker`、`false`なら`path_failure + stop_path`の`FailureRecord`へ変換する。移行元schemaと、v1ではdisposition/recoveryを保持していなかったために適用した既定値をmigration contextへ残す。推測した値を元から記録されていた値として扱ってはならない。

## Failure boundaries

parallel stressはworkerから受け取る`FailureRecord`のdisposition、recovery、retryableを保持し、次の境界を区別する。

- `path_failure + stop_path`: candidate不一致等の当該pathだけを停止し、sibling taskは継続する。
- `path_failure + replace_worker`: `retryable=true`ならcrash/timeout等のworker run failureをfresh workerでretryし、`retryable=false`または上限超過時はtask failureとして残す。いずれもsibling taskは継続する。
- `experiment_failure + abort_experiment`: 設定・環境契約の破損としてparallel plan全体を中止する。executorは未完了のfutureをbest-effortでcancelし、部分的なaggregateを生成せず`FailureRecordError`を送出する。

futureのcancelは既に実行中のworkerを必ず停止できるという保証ではない。保証する契約は、experiment failureの検出後に新しい集約処理へ進まず、その実行のaggregateを永続化しないことである。

## Aggregation identities

main processは到着順を捨て、task ordinal、attempt、worker内local log sequenceの順でresultとlogを結合する。score合計はtask順の有限値に対して計算し、best resultはscore降順、task ordinal、node IDでtie breakする。

集約には2種類のidentityがある。

- `aggregate_id` / `semantic_result_id`: pool size、logical slot、process IDを除いた意味結果。pool 1/2/4/8で一致しなければならない。
- `execution_id`: plan ID、pool policy、logical slotを含む実行証跡。pool構成ごとに異なる。

duration、PID、completion timestampはraw telemetryへ分離し、semantic identityへ含めない。

aggregate schemaは`parallel-search-aggregate-v2`である。taskごとの`attempt_history`には、初回から最終attemptまでの`status`、`result_id`、`failure`を順に保存する。retry後に成功したtaskも、先行attemptの`FailureRecord`を失わない。これにより、最終結果だけでは見えないworker replacementの理由、retry回数、失敗contextをaggregateから復元できる。

`attempt_history`の最後の要素はtaskの最終resultと一致しなければならず、attempt番号は0から連続する。成功後またはretry不能failure後のattempt、履歴と最終resultの不一致はschema errorとして拒否する。experiment failureではaggregate自体を生成しないため、`parallel-search-aggregate-v2`に中断途中の履歴は含めない。

## Real-core stress evidence

実行コマンド:

```powershell
$env:PYTHONPATH='src'
python -m ygo_effect_dsl prototype-real-stress --out docs/search/evidence/real_core_parallel_stress.json
```

証跡: `docs/search/evidence/real_core_parallel_stress.json`

- report ID: `realcorestress_afe235d35c979058c567ee0ceddb881434fba0c0d8ba46c44b29de40400da0f7`
- 8 unique tasksと8 duplicate submissionsをpool 1/2/4/8で実行
- 全poolのsemantic aggregate ID: `parallelresult_3d4aee75d5da7c4b249142ab8d134e07a3cf1fbb8ef78b93e35a5cbc84f58b97`
- aggregation inputを正順・逆順で切り替えても、semantic result、Route ID、Replay IDは一致
- worker crash、worker timeout、DataReader callback errorは同じtask seedとlogical slotで1回だけretryし、fresh PIDで復旧
- timeoutを2 attempt連続注入したtaskは`failed_retry_exhausted`
- 全processで終了状態を確認し、replacement前後のPIDが異なることを確認

PIDとexecution IDはraw evidenceなので再実行時に変わり得る。semantic report ID、aggregate ID、Route/Replay ID、seed割当、outcomeが再現対象である。

## Experiment extension

Experimentの必須fieldを変えず、検索parameterの拡張点を使う。

```yaml
search:
  parameters:
    parallel:
      pool_size: 4
      base_seed: 42
      max_retries: 1
```

memory/cache予算は`docs/search/30_performance_architecture.md`の校正値を使用する。
