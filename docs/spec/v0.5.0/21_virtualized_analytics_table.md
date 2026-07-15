# Virtualized Analytics Table Contract

Status: Implemented and locally verified for Issue #165

Last updated: 2026-07-16

## Scope

`desktop-virtual-table-v1`はWindows desktopのrun observation tableを対象とする。Python application serviceの`analytics.query`をauthorityとし、rendererはcard effect、合法性、missing row、snapshot変更を推測しない。browser harnessだけは同じrequest/response schemaを返す決定論的100,000行fixtureを使う。

このgateはUI query接続、cursor pagination、DOM virtualization、keyboard/focus、screen-reader metadata、狭幅layoutを検証する。実SQLite/Parquetの10万run・100万row、process RSS、disk、p50/p95/p99は#167のscale gateであり、このfixture結果で代替しない。

## Query and rendering

- request/responseは`analytics-query-request-v1` / `analytics-query-response-v1`、cursorは`analytics-cursor-v1`を使う。
- page sizeは500行とし、sort/filter変更時はsnapshotとloaded rowを破棄して先頭からqueryする。
- 継続pageは同じimmutable snapshot IDだけを受理する。snapshot変更、response version不一致、重複row IDはfail-closeする。
- 同時page queryは1件に制限し、連続commandは既存Promiseへ合流させる。
- loaded rowはclient memoryへ保持するが、DOMへはviewportと前後6行だけを描画する。row heightはcompact 40px、comfortable 48pxで固定する。
- 通常表示は最初の500行だけを取得し、次pageは明示的な`Load next page` commandで読む。

## Accessibility and layout

gridにはaccessible name、`aria-rowcount`、`aria-colcount`、各rowの`aria-rowindex`を与える。row focusはroving tabindexとし、Arrow Up/Down、Home/End、Page Up/Downを提供する。headerはsticky、列選択とdensityは既定寸法を変えず、forced-colorsとfocus-visibleを維持する。

1440×900では全列を表示する。760×900ではtoolbarを折り返し、本文全体を横overflowさせず、grid内部だけを横scrollする。760pxはresponsive evidence用であり、desktop shellのminimum 960×700を変更しない。

## Evidence

[`desktop_virtual_table.json`](../../ui/evidence/desktop_virtual_table.json)のevidence IDは`desktopvirtualtableevidence_908bda8b3e78b6664f1855b8af4b902f3032920f6f6eb512d02338e77e594731`である。同一Edge runで次を確認した。

- 100,000行を500行cursorで読了し、同時query最大1、重複dispatchによる追加query 1件だけ。
- DOM rowは最大28、終端22、scroll height 4,000,000px、header height 38pxで不変。
- exact deck filterは2,500件、昇順/降順先頭IDは期待値と一致。
- keyboard focusはArrow Upで1 row移動し、列変更後の`aria-colcount`は7。
- 1440×900と760×900でcontrolがviewport内、縦順序が安定し、body横overflowなし。
- console error、page error、remote requestなし。

- [1440×900 run observations](../../ui/evidence/analytics_runs_1440x900.png)
- [760×900 run observations](../../ui/evidence/analytics_runs_760x900.png)

```powershell
python -m ygo_effect_dsl.spikes.desktop_virtual_table_evidence --out docs/ui/evidence/desktop_virtual_table.json --screenshot-dir docs/ui/evidence
python -m pytest -q tests/test_desktop_virtual_table.py
```
