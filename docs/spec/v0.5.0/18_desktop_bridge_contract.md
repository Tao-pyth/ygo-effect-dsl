# Desktop bridge contract v1

## Status

`desktop-bridge-v1` is the v0.5 Windows developer-MVP boundary between the packaged renderer and the Python application service. It implements ADR 0016 and Issue #244. Issue #245 adds the worker lifecycle and evidence described in [desktop lifecycle contract](19_desktop_lifecycle_recovery.md). Signing/update and distribution approval remain #134/#91 gates.

## Process and authority

| Boundary | Authority |
|---|---|
| `index.html` / CSS / JavaScript | presentation and local interaction only |
| `bridge.js` | versioned request construction and response-envelope verification |
| `DesktopBridge.invoke` | byte limit, exact request shape, method allowlist, path rejection, structured diagnostic |
| `DesktopApplicationService` | deck catalog, preflight, job catalog, analytics and card-provider orchestration |
| existing worker subprocess | ocgcore, EDOPro Lua, Search and Replay execution |
| SQLite / immutable snapshot | job and analytics authority |

The pywebview `js_api` object has one callable public method, `invoke`. The service object, filesystem, subprocess APIs, and a local REST endpoint are not exposed. The renderer cannot submit a path, URI, root, file, or `*_path` field. YDK import starts from the native file picker and persists normalized card-code sections plus hashes; it does not persist or return the selected source path.

## Envelope

Every request has exactly `version`, `request_id`, `method`, and `payload`. `version` is `desktop-bridge-v1`; request IDs are bounded tokens; payloads must be finite JSON values. The request ceiling is 256 KiB and the response ceiling is 4 MiB. Every response uses `desktop-bridge-response-v1` and carries `ok`, `result`, `diagnostics`, and `details`. Validation or configuration failure is returned as `ok=false`; it is never converted into a successful empty result.

The machine-readable source is `src/ygo_effect_dsl/resources/desktop-bridge-v1.json`. Its method allowlist is:

| Method | Operation | Worker start at bridge call |
|---|---|---|
| `system.describe` | service/capability versions | forbidden |
| `deck.catalog` | registered normalized deck summaries | forbidden |
| `deck.import_ydk` | native selection and fail-closed YDK parse | forbidden |
| `deck.register_inline` | inline structural registration | forbidden |
| `scenario.compose_search` | typed UI configuration to validated Experiment 0.4 | forbidden |
| `scenario.preflight` | Experiment 0.4 and real-asset preflight | forbidden |
| `job.enqueue_search` | repeated preflight, immutable Experiment persist, SQLite queue | forbidden |
| `job.status` / `job.cancel` | status snapshot and cooperative cancellation | forbidden |
| `analytics.query` / `analytics.compare` | typed analytics contracts | forbidden |
| `card.get` | read-only `card-presentation-v1` query | forbidden |

`scenario.compose_search` accepts only the visible strategy, seed, budget, and optional specified-interruption card code. The Python service owns the evaluator, success predicate, information policy, opening-hand mode, and Experiment identity; the renderer does not infer rules. `job.enqueue_search` stores a content-addressed Experiment and creates the existing `job-spec-v2` search record only after a successful preflight. It does not run Search in the UI thread. `desktop-search-worker-v1` claims the job and uses the existing real-core frontier process. An unconfigured comparison source or card presentation provider returns a specific capability diagnostic.

## Deck catalog

`desktop-deck-catalog-v1` is a single-writer operational input catalog below `%LOCALAPPDATA%/ygo-effect-dsl/desktop-v1`. Deck IDs are content addressed by normalized sections, name, and source kind. Registration checks 40..60 main cards, at most 15 extra/side cards, positive codes, and the structural three-copy ceiling. It does not infer card effects, legality, format banlists, or card type.

The shell takes an exclusive process lock before opening SQLite or the window. A second writer fails with `desktop_already_running`. Activation of an existing window is not implemented in v0.5; adding it must preserve the same one-writer invariant.

## Shell startup

`ygo-effect-dsl-desktop` is installed only with the optional `desktop` dependency group, which pins `pywebview==6.2.1`. Startup order is Windows check, Evergreen WebView2 discovery, exact pywebview version check, `LOCALAPPDATA` resolution, single-instance lock, application service construction, then window creation. Missing runtime or version mismatch therefore cannot dispatch a worker. The window uses EdgeChromium, private mode, the packaged `file:` frontend, 1440x900 default size, and 960x700 minimum size.

No CDB, card text/image, ocgcore binary, CardScripts checkout, or downloaded WebView2 runtime is package data. External asset identity remains the scenario/card-presentation provider responsibility.

## Verification

Focused verification is:

```powershell
python -m pytest -q tests/test_desktop_bridge.py tests/test_desktop_shell.py tests/test_desktop_frontend.py tests/test_desktop_lifecycle.py
python -m build
```

The browser harness and pywebview shell both load `src/ygo_effect_dsl/desktop/static/index.html`. Browser execution retains the explicit synthetic search adapter. Desktop bridge availability enables the real local deck catalog, native YDK import, Python-owned Experiment composition, preflight, queue/status/cancel, and continuously supervised background Search. Large-table virtualization, signing, update, and distribution remain #165/#134/#91 work.

The same-host hidden WebView2 smoke loaded the packaged frontend, queried the desktop deck catalog, and completed `system.describe` through `DesktopBridge.invoke`. The current evidence is `docs/ui/evidence/desktop_bridge_smoke.json`, ID `desktopbridgesmoke_7666a9fde12209f57b06d8220e695dd736352d3fcafbb0847e68b859ec870068`. Lifecycle and performance measurements are kept separately so a browser/bridge pass cannot substitute for worker recovery evidence.
