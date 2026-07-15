# CHANGELOG・Issue・Milestone運用規約

Status: mandatory repository governance

Last updated: 2026-07-15

## 目的

package release、保存contract、GitHub Issueの進行段階を混同せず、利用者が変更点を追跡でき、未割当Issueを機械検出できる状態を維持する。本規約のmachine-readable sourceは[`.github/release-governance.yml`](../../.github/release-governance.yml)である。

## CHANGELOG

`CHANGELOG.md`はpackage/CLI単位の利用者向け変更履歴であり、Issue一覧やcommit logの複製ではない。保存形式のversionはpackage versionと独立しているため、互換境界へ影響する場合だけcontract名とversionを明記する。

通常のPRは次の規則に従う。

1. 利用者、CLI/API利用者、運用者、artifact読取側へ観測可能な変更は、同じPRで`Unreleased`へ1項目以上追加する。
2. 各項目は`[vX.Y.Z]`でtarget package releaseを示し、`Added`、`Changed`、`Deprecated`、`Removed`、`Fixed`、`Security`、`Compatibility`、`Governance`の適切な節へ置く。
3. 実装手段ではなく、利用可能になった挙動、互換性、移行要否、既知制限を書く。Issue/PR番号だけの項目は不可とする。
4. typo、内部整形、結果へ影響しないtest-only refactorは省略できる。ただしPR本文に省略理由を書く。
5. evidence再生成だけの変更は、判断、閾値、対応環境、主張範囲が変わる場合のみ記載する。

release時は対象`[vX.Y.Z]`項目だけを`## X.Y.Z - YYYY-MM-DD`へ移し、空の`Unreleased`を残す。package `__version__`、tag、release heading、README、roadmap、milestoneが一致しない状態ではtagを作成しない。過去release entryは誤記訂正を除いて書き換えず、訂正理由を新しいentryへ残す。

## Issue version label

管理対象Issueは、次を必須とする。

- package targetを表す`version:X.Y.Z` labelを正確に1個持つ。
- labelと同じversionの`vX.Y.Z` milestoneを正確に1個持つ。
- titleに`[vX.Y.Z]`または`[milestone vX.Y.Z]`を含める。titleは人間向け補助であり、label/milestoneがworkflow上の正本である。
- parentとchildは原則同じtargetとする。複数releaseへ跨る作業は、最初のdelivery単位でchild Issueへ分割する。
- release後に見つかった互換修正は、既にclosedのrelease milestoneを再開せず、patch milestoneへ割り当てる。

例外はlegacy issueだけである。`managed_issue_minimum`より前のIssueは履歴を保持する。以後の例外割当は設定の`overrides`へ理由を伴って追加し、黙示的な未割当を許可しない。

## Milestone lifecycle

- `planned`: scopeを分解中。完了条件と親Issueを持つ。
- `active`: 現在の主作業段階。新規childを追加できる。
- `released`: release tagとmain同期が完了したclosed milestone。open Issueを0件とし、新規Issueを追加しない。

milestoneをclosedにできるのは、対象CHANGELOG heading、package version、tag、CI/release evidence、全必須Issueの状態が一致した後だけである。未完了作業を次releaseへ移す場合は、Issue本文に理由を追記してversion labelとmilestoneを同時変更する。

## 機械監査

GitHub CLIで認証済みの環境から次を実行する。

```powershell
python -m ygo_effect_dsl.release_governance --check
python -m ygo_effect_dsl.release_governance --apply
python -m ygo_effect_dsl.release_governance --check
```

`--check`は未分類、version label欠落・重複、label不一致、milestone欠落・不一致を非zeroで報告する。`--apply`は設定からtargetを一意に決定できるIssueだけを修正し、未分類Issueを推測しない。新しいversionを開始する場合は、先にlabelとmilestoneをGitHubへ作成し、設定、roadmap、親Issue、CHANGELOG targetを同じPR/作業単位で更新する。
