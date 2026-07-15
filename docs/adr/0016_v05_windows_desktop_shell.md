# ADR 0016: Use pywebview and WebView2 for the v0.5 Windows desktop shell

Status: accepted for v0.5 developer MVP

Date: 2026-07-16

## Context

Package 0.5.0 needs a Windows desktop application whose first screen is a deck catalog and whose primary operations are search launch and deck statistics. The authoritative search, Replay, job, and analytics contracts are Python contracts. The shell must not become a second rules engine, expose a broad local API, or force third-party card assets into the package.

Issue #181 requires a same-host comparison of pywebview/WebView2, Tauri, Electron, and Qt. The comparison must cover process ownership, startup and memory, packaging, security, automation, failure recovery, and rollback before production packaging changes.

## Decision

The v0.5 developer MVP uses pywebview 6.2.1 with the Windows Evergreen WebView2 runtime. The dependency remains in an optional desktop group until the desktop release gate. The existing console executable and core worker packaging do not change in this ADR.

The process and authority boundary is:

| Boundary | Owner | Rule |
|---|---|---|
| HTML/CSS/JavaScript renderer | WebView2 in the pywebview host | Presentation and local interaction only |
| JavaScript bridge | Explicit async method allowlist | Version and validate every request/response; no generic Python object exposure |
| Application service | Typed Python facade in the desktop host | Deck, preflight, job, analytics, and presentation-provider orchestration |
| Search and Replay execution | Existing Python worker subprocesses | ocgcore and EDOPro Lua remain outside the renderer and main UI thread |
| Operational authority | Existing SQLite job/run catalogs | Renderer state and UI cache are disposable |
| Analytical authority | Existing immutable Parquet snapshots | UI never mutates analytical evidence |

The renderer loads packaged local static content. No remote content, arbitrary navigation, or general local REST API is allowed. Static serving may use pywebview's loopback-only server, but business operations use the bridge rather than HTTP. The page uses a default-deny CSP. Path inputs are normalized and scope-checked in Python. Card text remains presentation-only and is never sent to Search/Replay as rule evidence.

The Python application service owns worker creation, cancellation, timeout, and cleanup. A worker crash is contained by the existing job state machine and cannot terminate the desktop host. A host crash is recovered from durable job checkpoints after restart; the renderer is never a source of job truth. Windows Job Object ownership and restart behavior remain implementation acceptance items for the packaged desktop executable.

Automation is split deliberately. Playwright tests the same static frontend in a normal browser for layout, keyboard, accessibility, and large-table behavior. A separate Windows smoke starts pywebview/WebView2, checks the versioned bridge, and verifies worker crash containment. Browser success does not replace the desktop smoke.

Evergreen WebView2 is a runtime preflight, not an unreviewed bundled payload. Missing runtime produces a diagnostic before the window is created. Installer, signing, auto-update, YDK file association, deep links, and fixed-version WebView2 remain later distribution decisions. No card CDB, card text, image, ocgcore binary, or CardScripts content is added to the installer before #91.

## Evidence

[`evidence/0181_windows_desktop_shell.json`](evidence/0181_windows_desktop_shell.json) records the same-host probe. The host had Python 3.13.7, Visual Studio 2022 C++ Build Tools, and Evergreen WebView2 150.0.4078.65. Node/npm and Rust/Cargo were not present in the baseline environment.

The checked pywebview live EdgeChromium probe loaded a hidden 800 by 600 window in 1.227 seconds. The Python host and WebView2 family used seven processes and about 410 MB RSS during the minimal probe. Downloaded pywebview and Windows dependencies were about 2.61 MB. The probe venv site-packages tree was about 39.9 MB, but that ceiling includes pip bootstrap and the psutil measurement dependency. These are directional measurements, not release thresholds; WebView2 processes are shared, the pip cache was warm, and the dashboard workload is larger.

The PySide6 6.11.1 package-acquisition probe downloaded four wheels totaling about 248 MB before installation or application assets. Qt remains technically viable but would add a native UI test stack and a much larger dependency surface. Electron was rejected for v0.5 because it adds Node and a bundled Chromium release surface beside Python. Tauri remains the rollback candidate because its capability and sidecar model is stronger, but this host would first need Rust/Cargo and the release would gain a Rust shell plus PyInstaller sidecar boundary.

The primary source constraints used by the decision are:

- pywebview documents a two-way JavaScript/Python bridge and warns that exposed methods execute on separate threads: https://pywebview.flowrl.com/guide/interdomain
- pywebview documents local-server CSRF/token handling: https://pywebview.flowrl.com/guide/security
- Microsoft requires production WebView2 applications to preflight or deploy the runtime and recommends Evergreen for servicing: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution
- Tauri requires Microsoft C++ Build Tools, WebView2, and Rust on Windows and treats a packaged Python executable as a sidecar: https://v2.tauri.app/start/prerequisites/ and https://v2.tauri.app/develop/sidecar/
- Electron documents its Chromium multi-process model and the obligation to maintain Electron, Chromium, Node, dependencies, and application security: https://www.electronjs.org/docs/latest/tutorial/process-model and https://www.electronjs.org/docs/latest/tutorial/security
- Qt for Python recommends its own deployment tooling and records separate freezing considerations: https://doc.qt.io/qtforpython-6/deployment/index.html

## Consequences

The selected path reuses the Python package, worker isolation, PyInstaller knowledge, and web frontend testing without adding Node or Rust to the baseline build. It also keeps the renderer non-authoritative and gives the smallest reversible step toward a usable Windows dashboard.

pywebview is not accepted unconditionally for 1.0. Issue #244 owns the shell and versioned bridge implementation, and #245 owns packaged lifecycle, accessibility, process cleanup, and recovery evidence. The decision must roll back to Tauri or another shell if the v0.5 prototype cannot provide a narrow auditable bridge, reliable WebView2 startup, keyboard/screen-reader behavior, crash containment, or a repeatable signed installer. A rollback changes only the shell adapter because application service requests and responses remain versioned Python contracts.
