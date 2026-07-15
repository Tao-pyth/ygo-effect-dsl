# Package 0.5.0 Windows Desktop UI Requirements

Status: Confirmed product requirements; parent [#164](https://github.com/Tao-pyth/ygo-effect-dsl/issues/164)

Last updated: 2026-07-16

## Product definition

UIは、実ocgcore/EDOPro Luaによる探索を実行し、deck単位の結果を比較・検証するWindows desktop applicationである。主対象はPythonエンジニアと研究・検証利用者であり、game clientやmarketing siteではない。

## Confirmed requirements

| Area | Requirement |
|---|---|
| Primary operations | 探索実行、デッキ統計 |
| First screen | デッキ一覧 |
| Primary navigation | デッキ一覧からdeckを選択し、探索実行フォームへ進む |
| Card presentation | card detailとeffect textを表示する |
| Environment | Windows desktop application |
| Visual direction | 研究・検証dashboard |

## Primary workflow

```text
Application start
  -> asset/catalog readiness
  -> deck catalog
      -> import YDK or register inline deck
      -> select deck
          -> deck detail and statistics
              -> inspect card detail/effect text
              -> open search form
                  -> scenario/search parameters
                  -> preflight
                      -> configuration failure and correction
                      -> enqueue search job
                          -> progress/cancel/failure
                          -> result and best Route
                              -> Route/Event/Decision lineage
```

deckを選ばずに探索を開始できるglobal shortcutは設けてもよいが、最終的にversion付きdeck identityを選択するまでworkerを起動しない。

## Deck catalog

最低表示fieldはdeck name/ID、source kind、main/extra/side count、deck hash短縮表示、preflight status、run count、last run status/timeとする。統計fieldはaggregate versionとsample countを持つ。

必要操作はYDK import、inline deck登録、再検査、検索、filter、sort、選択、探索開始である。deck削除はsource registrationとrun evidenceの扱いを分け、既存evidenceを暗黙削除しない。

状態はloading、empty、asset unavailable、invalid deck、stale asset lock、quarantined、partial statistics、query failureを区別する。

## Deck detail and statistics

deck detailはmain/extra/side、card count、card list、preflight diagnostics、asset/deck identity、過去run、strategy/interruption別aggregateを表示する。

統計は最低限run count、success count/rate、peak/terminal score分布、action/depth/replay/node/time、failure/termination reasonを対象とする。異なるevaluator/search/schemaを暗黙集約せず、比較不能またはfilter必須として表示する。sample sizeとpartial budgetを隠さない。

## Search form

formは既存Experiment/Search contractを編集するpresentationであり、UI独自schemaを作らない。最低fieldはobjective/success predicate、opening hand、strategy/version、seed、node/replay/depth/time budget、interruption、output/catalogである。

- 現行未実装strategyはdisabled stateと理由を表示する。
- field validation後にscenario preflightを実行する。
- DB/Lua/asset/deck failureはcardまたはsettingへ戻れるdiagnostic linkを持つ。
- preflight成功前にreal-core workerを起動しない。
- submitted Experiment identityとUI表示値をjob/resultから再確認できる。

## Card detail and effect text

card detailは利用可能な範囲でcode、localized name、type、attribute、race、level/rank/link、ATK、DEF、scale、setcode、effect text、source/localeを表示する。長文、改行、Unicode、missing fieldでlayoutを壊さない。

effect textはpresentation専用である。合法性、timing、candidate生成、Replay、State、Evaluationの入力にしてはならない。表示用`card-presentation-v1`はreal-core providerから独立して実装し、source/hash/locale/fallback/redactionの詳細を[card presentation contract](16_card_presentation_contract.md)に固定する。非英語sourceの実データqualificationとlabel-map drift検出は[#247](https://github.com/Tao-pyth/ygo-effect-dsl/issues/247)で継続する。

textが取得できない場合はcard code、source、diagnosticを表示し、推測文を生成しない。card text/CDB/imageをlicense review前にrepositoryやinstallerへ同梱しない。card imageは未確定であり、text-onlyを必須fallbackとする。

## Desktop application boundary

v0.5 developer MVPのshellは[ADR 0016](../../adr/0016_v05_windows_desktop_shell.md)に従い、pywebview 6.2.1とWindows Evergreen WebView2を使う。typed Python application serviceはdesktop host内に置き、rendererにはversion付きallowlist bridgeだけを公開する。ocgcore/Search/Replayは既存worker subprocessが所有し、rendererやUI threadで実行しない。

frontendはpackaged local static contentだけを読み、remote content、arbitrary navigation、general local REST APIを禁止する。Playwrightは同じfrontendのbrowser harness、Windows CIはpywebview/WebView2 bridge smokeを担当し、一方を他方の代替にしない。

installer、signing、auto-update、YDK file association、deep linkはdistribution gateまで保留する。WebView2 runtimeは起動前preflightを行い、fixed runtimeを無条件同梱しない。card CDB/text/image、ocgcore binary、CardScriptsはlicense review前にdesktop artifactへ同梱しない。

## Visual and interaction direction

- desktop-firstのdense dashboardとする。
- first viewportでdeck tableと主要操作を確認できる。
- table/filter/search form/statistics/diagnosticsを主役にする。
- compact panel内でhero-scale typeを使わない。
- statusは色だけで表現せず、icon/text/accessible labelを併用する。
- cardをpage sectionの代用にせず、繰り返しitemやframed toolに限定する。
- decorative animation、marketing hero、game client風の過剰演出を避ける。
- keyboard/focus/high contrast/reduced motionをsupportする。

詳細visual systemは[#184](https://github.com/Tao-pyth/ygo-effect-dsl/issues/184)で定義する。

## Window and performance requirements

実装済みfrontendのnavigation、form、visual token、viewport evidenceは[deck dashboard workflow](17_deck_dashboard_workflow.md)を正本とする。v0.5 shell minimumは960×700、主要検証viewportは1440×900とする。実bridgeとdesktop lifecycle/a11yは#244/#245で検証済み、100k virtualizationは#165へ分離する。

主要desktop解像度と最小window sizeを実装Issueで確定し、text、toolbar、table、dialog、detail panelのoverlap/truncationを禁止する。deck/card/run tableはserver-side queryとvirtualizationを使い、dynamic contentでrow/tool dimensionsを変動させない。

10万deck/run相当のworkloadでinput-to-result、sort/filter、selection、detail open、memoryを測定する。測定前に無制限queryや全row client loadを既定にしない。

## Acceptance scenarios

1. 初回起動でasset未取得状態と取得手順を確認できる。
2. YDKをimportし、preflight failureのcard/scriptへ移動できる。
3. valid deckからRandom Searchを開始し、job progressとbest Routeへ移動できる。
4. deck統計をstrategy/interruption/evaluator versionでfilterできる。
5. card detailとeffect textを確認でき、text欠落時も操作を継続できる。
6. worker crash/cancel/retryをUI successとして表示しない。
7. keyboardだけでdeck選択、search form、実行、result確認を完了できる。
8. PlayerView modeでhidden information leak auditを通す。

## Open decisions

| Decision | Owner |
|---|---|
| pywebview shell、versioned bridge実装 | [#244](https://github.com/Tao-pyth/ygo-effect-dsl/issues/244) |
| WebView2 lifecycle、a11y、packaged recovery検証 | [#245](https://github.com/Tao-pyth/ygo-effect-dsl/issues/245) / [desktop lifecycle contract](19_desktop_lifecycle_recovery.md) |
| Installer/update、signing、file association | [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91), [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) |
| Deck catalog/search formのfield・state・navigation詳細 | [#182](https://github.com/Tao-pyth/ygo-effect-dsl/issues/182) |
| Card text source、locale、presentation schema、license/fallback | [#183](https://github.com/Tao-pyth/ygo-effect-dsl/issues/183) |
| Visual tokens、component states、prototype、responsive/a11y | [#184](https://github.com/Tao-pyth/ygo-effect-dsl/issues/184) |
| PlayerView redaction | [#125](https://github.com/Tao-pyth/ygo-effect-dsl/issues/125), [#150](https://github.com/Tao-pyth/ygo-effect-dsl/issues/150), [#151](https://github.com/Tao-pyth/ygo-effect-dsl/issues/151) |
| Distribution license | [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91) |
