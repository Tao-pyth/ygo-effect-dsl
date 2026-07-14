# External core and search failure policy

Status: executable v2 persistence and executor contract

Last updated: 2026-07-14

## Dispositions

Every failure presented to search is converted to `FailureRecord` with category, disposition, recovery action, retryability, message, exception type, and pointer-free context.

| Disposition | Meaning | Recovery |
| --- | --- | --- |
| `legal_dead_end` | Core request is valid and optional, but exposes no selectable continuation | `none`; preserve as a normal terminal path |
| `path_failure` | This route cannot continue under the supported Bridge contract | `stop_path` or `replace_worker` |
| `experiment_failure` | Environment or replay contract is invalid, so other paths are not trustworthy | `abort_experiment` |

An empty optional request (`min=0`, `required=false`) is a legal dead end. An empty required request is `invalid_message` and a path failure. Exceptions are never converted to a legal dead end.

## FailureRecord invariants

`FailureRecord`はcategory、disposition、recovery、retryableを別々の任意値として受け入れない。永続化と実行制御が同じ意味を持つよう、許可する組合せを次に限定する。

| Disposition | Recovery | Retryable | Executor meaning |
| --- | --- | --- | --- |
| `legal_dead_end` | `none` | `false` | 正常な終端としてpathを終了する |
| `path_failure` | `stop_path` | `false` | 当該pathを停止し、siblingを継続する |
| `path_failure` | `replace_worker` | `true` or `false` | 許可時だけfresh workerでretryし、それ以外は当該pathを停止する |
| `experiment_failure` | `abort_experiment` | `false` | experiment全体を中止する |

上記以外、例えば`legal_dead_end + replace_worker`、`path_failure + abort_experiment`、`experiment_failure + retryable=true`は構築時または読込時に拒否する。`replace_worker + retryable=false`は、workerの隔離は必要だが同じtaskの自動retryは許可しないfailureを表すために有効である。

`ParallelTaskResult`の`parallel-search-result-v2`はこの`FailureRecord`全体を`failure`へ保存する。`status`、`failure_category`、`retryable`は`failure`から導出し、呼出側が重複指定しない。v1 readerによる補完値は`FailureRecord.context`のmigration情報で識別できなければならない。

An `InvalidBridgeResponseError` raised by response validation carries canonical, pointer-free copies of both the original `DecisionRequest` and `DecisionResponse`. `classify_failure()` preserves those values in `FailureRecord.context`; caller context such as `step` is merged into the same record. Replay stores that dictionary in `ReplayEventV03a.failure` and `assert_failure_matches()` reports the first changed field. An invalid response is therefore reproducible as a path failure rather than being confused with a legal no-candidate result.

## Category policy

| Category | Disposition | Recovery |
| --- | --- | --- |
| worker crash, worker timeout, in-core process timeout | path failure | replace worker; one controlled prefix replay may be attempted by a future scheduler |
| worker protocol corruption | path failure | replace worker; no automatic retry |
| invalid/unsupported message or invalid response | path failure | stop path |
| callback/create/state/snapshot core error | path failure | replace worker |
| missing CDB/script, rejected Lua, core/API/architecture mismatch | experiment failure | abort experiment |
| replay manifest/environment/signature/format mismatch | experiment failure | abort replay/experiment |
| unknown Python exception | experiment failure | abort experiment |

`retryable=true`はretryの許可であって成功への変換ではない。parallel executorはpolicy上限内でfresh workerを作成し、検証済みReplay prefixから再実行する。各attemptのfailureは`parallel-search-aggregate-v2`の`attempt_history`へ保存し、retry後に成功しても消去しない。

## Parallel executor boundary

`path_failure`はtask単位のfailureである。`stop_path`は直ちに当該taskを終端し、`replace_worker`はworkerを隔離したうえで`retryable`とretry上限を評価する。他のsibling taskは継続し、完了したtaskと全attempt履歴からaggregateを生成する。

`experiment_failure + abort_experiment`はtask単位へ縮退させない。executorは検出時に未完了のfutureへbest-effort cancelを要求し、`parallel-search-aggregate-v2`を生成せず、元の`FailureRecord`を保持した`FailureRecordError`を送出する。既に実行中のfutureはcancelできない場合があるため、cancel完了ではなく「集約を生成しないこと」を永続化境界の保証とする。

## Worker isolation

The public real-core commands start a child process and apply a 30-second parent deadline. A deadline breach raises `OcgcoreWorkerTimeoutError`; a non-zero exit raises `OcgcoreWorkerCrashError` with return code and copied stderr/stdout; invalid JSON raises `OcgcoreWorkerProtocolError`. No native pointer or partially decoded state crosses the process boundary.

Lua rejection has category `lua_error`, while missing Lua/CDB data has `asset_error`. Unsupported message and version mismatch retain `unsupported_message` and `version_mismatch`, so diagnostics can be aggregated without parsing human text.
