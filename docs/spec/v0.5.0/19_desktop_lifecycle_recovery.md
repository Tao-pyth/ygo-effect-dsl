# Desktop Lifecycle, Recovery, and Accessibility Contract

## Status

`desktop-search-worker-v1` is the v0.5 Windows developer-MVP process contract implemented by Issue #245. It connects the packaged deck-first frontend to the existing SQLite job catalog and real ocgcore Search without making the renderer authoritative. This contract verifies local lifecycle and recovery behavior. The 100,000-row-equivalent virtualization gate is verified separately by Issue #165; installer signing, update compatibility, and distribution approval remain #134 and #91 gates.

## Process ownership

The pywebview host owns one `DesktopWorkerSupervisor`. The supervisor runs outside the WebView event thread, claims durable `job-spec-v2` records, and starts one fresh `python -m ygo_effect_dsl experiment-search` subprocess for each attempt. The renderer may compose a scenario, enqueue work, poll status, or request cancellation, but it cannot create worker processes, mutate checkpoints, publish artifacts, or decide that a job succeeded.

On Windows, every Search attempt is assigned to a Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. The launcher requests breakaway from an outer Job Object when permitted and otherwise uses the supported nested-job path. All descendants inherit the containment boundary. Closing the attempt terminates the complete process tree. POSIX uses a process group only as a test fallback; it is not the v0.5 supported desktop platform.

## Job lifecycle

1. `scenario.compose_search` builds Experiment 0.4 in Python from the typed UI inputs. Evaluator, success predicate, information policy, and opening-hand semantics are service-owned defaults.
2. `scenario.preflight` validates the deck, asset lock, CDB rows, Lua scripts, and runtime before enqueue.
3. `job.enqueue_search` persists the content-addressed Experiment and immutable job input.
4. The supervisor claims the job, records an attempt checkpoint, starts the contained process, renews the lease, and polls cancel/host-stop controls.
5. A successful process is accepted only when the generated Route and SearchRun both parse, match the immutable input, and can be atomically published through `JobArtifactPublisher`.
6. Crash, timeout, host stop, invalid output, and cancellation terminate the process tree before the job transition is committed.

Checkpoint progress is monotonic metadata, not a native ocgcore snapshot. Retry replays the immutable Experiment in a fresh process. A host crash leaves the durable lease and checkpoint in SQLite; after lease expiry a replacement worker reclaims the same job as a later attempt. No native state handle crosses process boundaries.

## Failure matrix

| Failure | Required state | Artifact rule | Recovery rule |
|---|---|---|---|
| renderer crash/reload | running job remains authoritative in SQLite | no renderer publication | reconnect and poll by job ID |
| Search worker crash | `retrying` or terminal `failed` at retry limit | no partial artifact registration | fresh-process retry from immutable input/checkpoint hint |
| hard timeout | `retrying` or terminal `failed` | no partial artifact registration | terminate complete tree, then retry if allowed |
| user cancel | `cancelled` | no publication from the cancelled attempt | no automatic retry |
| desktop host stop/crash | lease expires and becomes reclaimable | committed artifacts remain; partial files are not registered | next host reclaims as a later attempt |
| invalid/missing output | path failure, never success | reject Route/SearchRun pair | retry policy applies |

## UI and accessibility behavior

The packaged frontend uses the real bridge path for Experiment composition, preflight, enqueue, status, and cancellation. The browser evidence harness retains a synthetic adapter so layout tests remain deterministic and do not claim real-core execution. Search progress comes from durable job/checkpoint fields. Closing a terminal status view does not issue another cancellation.

The static audit requires associated form labels, accessible names for icon-only buttons, a skip link, keyboard-reachable controls, tab arrow navigation, forced-colors rules, reduced-motion rules, and a 960 by 700 minimum window. The audit is a structural baseline, not a substitute for a release screen-reader matrix. Distribution qualification must repeat keyboard and screen-reader checks against the packaged executable.

The bridge remains a single public `invoke` method with a machine-readable allowlist. Renderer-supplied filesystem paths, unknown methods, oversized requests/responses, remote URLs, a local REST surface, and network access are rejected or absent. Card database, Lua, ocgcore, and downloaded assets stay external verified cache content.

## Evidence

The committed lifecycle evidence is [`desktop_lifecycle.json`](../../ui/evidence/desktop_lifecycle.json), ID `desktoplifecycleevidence_e294d061ecb793951cf7933b186dda6ec6031293637c27302b296316dcc3bfd9`. On the measured Windows 11 host it records:

- Windows Job Object parent-plus-child process count `2` before termination and active count `0` after termination.
- host-crash recovery at attempt `2` with checkpoint `search:frontier:17` and immutable input digest parity.
- independent renderer, worker crash, hard timeout, and cancellation outcomes with no partial artifact registration.
- pywebview 6.2.1 and Evergreen WebView2 150.0.4078.65 startup probes: 1.80358 seconds cold and 1.567594 seconds warm, with process-family RSS about 418.3 MB and 421.0 MB.
- missing-runtime and pywebview-version diagnostics, bridge method drift checks, path rejection, CSP, keyboard, label, accessible-name, forced-colors, and reduced-motion checks.

The real-core sidecar is [`desktop_real_core_search.json`](../../ui/evidence/desktop_real_core_search.json), ID `desktoprealcoreprobe_2c1224172be3bfbdb9890f72781c5c732623bc1b3e38aa4212451c81c81e1f44`. It used pinned asset lock `ocgcore-assets-202504-v1`, completed 5 logical nodes under a 10-node budget, returned code 0, and atomically registered one Route plus one SearchRun in 33.728181 seconds. Route syntax, Experiment identity, SearchRun schema/route ID, and commit hash were checked before publication. These are same-host observations, not production thresholds.

## Verification

```powershell
python -m pytest -q tests/test_desktop_bridge.py tests/test_desktop_shell.py tests/test_desktop_frontend.py tests/test_desktop_lifecycle.py tests/test_desktop_lifecycle_evidence.py
python -m ygo_effect_dsl.spikes.desktop_lifecycle_evidence --real-core-probe-out docs/ui/evidence/desktop_real_core_search.json
python -m ygo_effect_dsl.spikes.desktop_lifecycle_evidence --real-core-evidence docs/ui/evidence/desktop_real_core_search.json --out docs/ui/evidence/desktop_lifecycle.json
```

The real-core probe and aggregate evidence are deliberately separate commands. This keeps the durable job result inspectable if the invoking shell is terminated or detached with the contained process tree.

## Residual gates

- #167: real persistent-storage calibration at 100,000 runs / 1,000,000 rows.
- #134: packaged executable compatibility, signing, update, rollback, and runtime support matrix.
- #91: license and third-party asset distribution approval.
