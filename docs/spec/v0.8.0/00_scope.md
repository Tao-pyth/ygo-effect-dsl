# 0.8.0 Scope: Japanese-Centered Desktop UI And I18n Quality

Status: released source milestone

Last updated: 2026-07-28

## Purpose

`0.8.0` は、日本人想定ユーザーが desktop research dashboard を自然に読める状態へ引き上げた UI 品質 stage である。対象は UI 文言の日本語中心化、`html lang="ja"`、文字化け除去、将来の locale 切替に備えた文言集約である。

## In scope

- Desktop static HTML の言語属性を `ja` にする。
- 主要な visible UI copy、aria-label、placeholder、status/toast/message を日本語中心にする。
- Fixture deck 名、カード表示、recent run、job/result 表示から mojibake を除去する。
- 動的 UI 文字列を日本語 text catalog に集約し、将来 locale を増やせる構造にする。
- Release-facing documentation の `0.8.0` stage と文字化け除去方針を更新する。
- Tests で `lang="ja"`、主要日本語文言、既知 mojibake パターン不在を検証する。

## Out of scope

- 多言語切替 UI の提供。
- 英語 locale の完全翻訳 catalog。
- Card text や third-party DB の翻訳保証。
- Production distribution、license、security operations。これらは `1.0.0` の責務である。

## Acceptance

- Desktop entrypoint の `<html>` は `lang="ja"` を宣言する。
- Browser preview と desktop bridge 接続時の主要な状態表示が日本語で表示される。
- U+FF82/U+FF77 などの既知文字化けmarkerが desktop static assets と release-facing version docs に残らない。
- Existing bridge/security tests と release governance checks が通る。
- `japanese-i18n-release-gate-v1` と `release-readiness-status-v1` が `0.8.0` を ready として記録する。
