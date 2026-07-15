# Package 0.5.0 Deck Dashboard Workflow

Status: Interactive static prototype verified in Microsoft Edge; parents [#182](https://github.com/Tao-pyth/ygo-effect-dsl/issues/182) and [#184](https://github.com/Tao-pyth/ygo-effect-dsl/issues/184)

Last updated: 2026-07-16

## Product boundary

`desktop-workflow-v1`は、Windows desktop applicationのdeck-first navigation、visual tokens、control statesを固定する。packaged frontendは`src/ygo_effect_dsl/desktop/static/index.html`、`app.css`、`bridge.js`、`analytics.js`、`app.js`の5 assetであり、browser harnessとpywebview/WebView2 shellが同じartifactを読み込む。

browser harnessは明示的なsynthetic fixtureを使い、real workerを起動しない。Windows shellでは[#244](https://github.com/Tao-pyth/ygo-effect-dsl/issues/244)のversioned bridgeがYDK/inline import、preflight、job、analytics、card presentationを実application serviceへ接続する。rendererはExperiment、Search、Replay、State、Decision、Evaluationの権威を持たない。

## Primary workflow

```text
Deck catalog
  -> select deck
      -> overview / cards / recent runs
      -> inspect card presentation
      -> open search form
          -> scenario / strategy / seed / budgets / interruption
          -> run preflight
              -> configuration failure; worker remains stopped
              -> queue job
                  -> progress / cancel
                  -> best Route result / fresh Replay status
```

最初の画面はdeck catalogである。headerのYDK importとinline registration、filter、sort、density、deck table、選択deckのdetail、探索実行をfirst viewportに置く。marketing heroや装飾cardを使わず、比較と反復操作に適したtable、metric band、detail panelを使う。

## Catalog and deck detail

catalog rowはdeck name/hash、全card count、preflight、run count、success rate、best score、updated timeを持つ。filterはname/hash/tag、sortはupdated/runs/success/nameを対象にする。row内のdeck名はbuttonであり、keyboardだけで選択できる。

detailはmain/extra/side count、source kind、success/peak/terminal、strategy別比較、composition、latest preflightを表示する。Cards tabはcard code/name/type/countから`card-presentation-v1` detailへ進み、Runs tabはstrategy/seed/outcome/timeを表示する。prototypeのcard name/effect textは明示的なsynthetic fixtureであり、第三者text/imageではない。

`ready`、`empty`、`asset_unavailable`、`invalid_deck`、`stale_asset_lock`、`quarantined`、`partial_statistics`、`query_failure`をmachine contractに固定する。現行fixtureはready 3件とstale 1件を操作できる。実payloadとserver queryは#244、100,000行相当のrun observation windowは#165で接続済みである。

## Search and preflight

search formはExperiment/Search contractのpresentationであり、独自rules schemaではない。objective、opening hand、Random/Beam/MCTSのversion、seed、max nodes/depth/seconds、指定妨害card codeを扱う。field変更ごとにpreflightをinvalid化し、Validate成功後だけQueue searchを有効にする。

stale asset lock、1から100,000外のnode budget、妨害有効時のcard code欠落はconfiguration failureとして表示し、workerを起動しない。Pythonで効果、合法性、timingを推測しない。synthetic jobはprogress/cancel/resultのinteractionだけを再現し、ログにreal worker未起動を明示する。

## Visual and accessibility system

- 主要viewportは1440×900、v0.5 shell minimumは960×700とする。
- Segoe UI、14px基準、48px compact table row、固定toolbar/control dimensionsを使う。
- paletteはwhite/charcoalを基調にgreen status、blue analytics、amber warning、red failureを役割別に使う。
- deck table、tabs、native dialog、label付きform control、native progress、aria-live status、skip linkを使う。
- `:focus-visible`、`prefers-reduced-motion`、`forced-colors`、`hidden` stateを実装する。
- 960×700ではsearch dialogをscrollableにし、header/footer commandを維持する。
- hash routeはselected deckとsearch/compare viewのbrowser再現に限定する。OS deep linkはdistribution gateまで保留する。

deck画面のbrowser visual evidence単独では、100,000 row virtualizationとdesktop lifecycleを保証しない。virtualizationは[#165](https://github.com/Tao-pyth/ygo-effect-dsl/issues/165)の[専用契約](21_virtualized_analytics_table.md)、screen-reader name/WebView2/renderer・host・worker recoveryは[#245](https://github.com/Tao-pyth/ygo-effect-dsl/issues/245)の[別証跡](19_desktop_lifecycle_recovery.md)で検証する。

## Security and distribution

HTMLはdefault-deny CSPを持ち、remote content、network request、inline script/style、`eval`を使わない。`app.js`はdirect `window.pywebview` accessを持たず、`bridge.js`だけが`desktop-bridge-v1` allowlist facadeを公開する。Windows shellでは実deck catalogとnative YDK importを接続し、browser harnessではfixture search adapterを維持する。CDB、card text/image、ocgcore binary、CardScriptsはstatic artifactとWindows executableへ同梱しない。

## Evidence

`docs/ui/evidence/desktop_frontend.json`はEdgeで実行後DOMに4 deck rowとworkflow versionが存在すること、2 viewport PNGのdimension/hash、security/limitationを保存する。evidence IDは`desktopfrontendevidence_4f259a62bc94cc856c13c8cac5a9534afe0f6c5678050d4062f2ed87711ee04b`である。

- [1440×900 deck dashboard](../../ui/evidence/deck_dashboard_1440x900.png)
- [960×700 search form](../../ui/evidence/deck_search_960x700.png)

```powershell
python -m ygo_effect_dsl.spikes.desktop_frontend_evidence --out docs/ui/evidence/desktop_frontend.json --screenshot-dir docs/ui/evidence
python -m ygo_effect_dsl.spikes.desktop_virtual_table_evidence --out docs/ui/evidence/desktop_virtual_table.json --screenshot-dir docs/ui/evidence
python -m pytest -q tests/test_desktop_frontend.py tests/test_desktop_virtual_table.py
```
