# ADR 0019: v1.0.0 WebView2 runtime policy

Status: Accepted for v1.0.0 runtime gate

## Decision

The v1.0.0 Windows desktop shell uses Microsoft Evergreen WebView2 Runtime as an external prerequisite. The portable ZIP does not bundle WebView2, does not silently download WebView2, and does not launch a WebView2 installer at runtime.

The minimum qualified WebView2 Runtime version is `150.0.4078.65`. The desktop preflight must run before the desktop bridge, worker supervisor, export worker, or application window starts. If the runtime is missing, outdated, or the platform is unsupported, startup must fail with a structured user-facing diagnostic instead of continuing into the bridge or worker path.

## User Guidance

The missing-runtime guidance tells the user to install or repair Microsoft Evergreen WebView2 Runtime from Microsoft or an approved organization software portal, then restart `ygo-effect-dsl-desktop.exe`. The guidance points to the official Microsoft WebView2 page: `https://developer.microsoft.com/microsoft-edge/webview2/`.

The outdated-runtime guidance records the observed version, the required version, and the same explicit install-or-repair action. The unsupported-platform guidance states that the v1.0.0 desktop shell requires Windows.

## Evidence Boundary

The CI executable workflow runs `ygo-effect-dsl-desktop.exe --preflight-only --diagnostics-out` before the bridge smoke command for both the raw executable and the portable ZIP extraction. Unit tests cover installed Evergreen WebView2, missing runtime, outdated runtime, unsupported platform, and pywebview version mismatch.
