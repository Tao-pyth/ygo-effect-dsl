# Package 0.3.0 Platform Matrix

Status: qualified contract

Last updated: 2026-07-15

| Boundary | Classification | Contract |
|---|---|---|
| Windows 10/11 x64, Python 3.10+, Visual Studio 2022 MSVC x64 | supported | ocgcore API 11.0、Release x64、Premake 5.0.0-beta2、isolated subprocess worker |
| Windows ARM64/x86 | unsupported | x64 DLL ABIと一致しないためnative load前に拒否 |
| Linux/macOS | unsupported | lock済みbinary/build/worker evidenceがなく、Wineや互換layerへfallbackしない |
| Python 3.9以下 | unsupported | package/runtime契約外 |

`ocgcore-platform-contract-v1`がOS、machine、Pythonを判定し、`ocgcore-doctor-v2`がGit、MSVC、virtual build driveを加えて検査する。未対応環境は`unsupported_operating_system`、`unsupported_architecture`、`unsupported_python_version`を返す。Git、MSVC、build driveは`git_not_found`、`msvc_not_found`、`virtual_build_drive_in_use`で区別する。

`YGO_EFFECT_DSL_EXTERNAL_ROOT`または`--external-root`はproject-owned cacheだけを選択する。rootはwrite可能なlocal pathを推奨し、network share、junction/reparse point、管理者権限依存をsupportしない。non-ASCII/long pathはPython側で許容するが、MSVC/Premakeを含むrelease qualification evidenceがないため、self-hosted gateでは短いASCII pathを使う。runtimeはlock、manifest、DLL hash、APIを検証し、別installやPATH上のDLLへfallbackしない。

support解除条件は、対象OS/architectureごとの固定build lock、clean bootstrap、API/ABI、Lua corpus、3 deck Replay、worker failure、pool/RSS evidenceを現行Windows x64と同じgateで取得することである。

`.github/workflows/real-core-self-hosted-smoke.yml`は手動起動だけを許可し、`self-hosted/Windows/X64/ygo-real-core` labelとrunner-local `YGO_EFFECT_DSL_EXTERNAL_ROOT`を要求する。raw Lua、CDB、Route、deckはartifact化せず、lock、Route ID、terminal Stateを相互検証した`self-hosted-real-core-smoke-v1` summaryだけを14日保持する。2026-07-15の同一Windows host local command sequenceは`realcoresmoke_621138...`で成功済みであり、GitHub workflow run自体は#138で別途確認する。
