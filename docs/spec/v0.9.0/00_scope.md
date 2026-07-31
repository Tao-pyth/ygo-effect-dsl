# 0.9.0 Scope: Terminal Preference And Card Selection UX

Status: planned source milestone

Last updated: 2026-07-31

Parent: [#324](https://github.com/Tao-pyth/ygo-effect-dsl/issues/324)

## Purpose

`0.9.0` は、`0.7.0` で導入された terminal preference profile を、日本人想定ユーザーが理解しやすい「終端評価ルール」として扱えるようにする minor UX release である。プロファイルはデッキに紐づく複数の論理プロファイルとして管理し、UI ではデッキ内カードから選択させる。内部正本としての `card_code` は維持するが、利用者に直接入力させない。

## Boundaries

- `card_code` は保存形式、bridge payload、評価ロジックの内部識別子として維持する。
- Desktop UI は `[P] プロファイル` ページを新設し、上部のデッキ選択から対象デッキを切り替え、終端評価ルールプロファイルの新規作成、編集、アーカイブを行う。
- 探索実行画面はプロファイル選択だけを残し、編集は `[P] プロファイル` ページへ遷移する。
- ルール対象カードは選択中デッキ内のカード一覧から選ぶ。raw `card_code` 入力欄やカード名の自由入力欄は置かない。
- ローカルの日本語カード表示情報が利用できない場合は fail-closed とし、直接 `card_code` を入力できる fallback は提供しない。
- `terminal-preference-profile-v1` は immutable content profile として維持する。Desktop 専用 catalog `desktop-deck-terminal-profile-catalog-v1` で `deck_profile_id`、`deck_id`、`display_name`、`active_profile_id`、`state`、`revision` を管理する。
- プロファイル更新時は `deck_profile_id` を維持し、更新後の rule set から新しい `active_profile_id` を生成して差し替える。削除は物理削除ではなく `state=archived` にする。
- カード効果テキストは表示情報として扱い、合法性、タイミング、終端評価ルールの自動生成には使わない。
- デッキ名とタグは deck 本体ではなく desktop metadata catalog で管理し、`deck_id`、`deck_sha256`、既存ジョブ、過去 evidence を変更しない。
- デッキカタログと終端評価ルール picker は、日本語カード表示 source が利用できる場合にカード名を表示する。取得失敗時は未構成として扱い、カードコードをカード名として偽装しない。
- 「インラインデッキを作成」は非推奨の可視導線として隠す。ただし互換性のため `deck.register_inline` bridge/service は残す。
- 経路結果画面は、各指標の Help、内部 ID の詳細化、ノード予算を使い切らない終了理由、初期手札条件、最大スコア盤面 snapshot を表示する。

## GitHub work items

- [#325](https://github.com/Tao-pyth/ygo-effect-dsl/issues/325) Define terminal preference and card-code UX boundaries.
- [#326](https://github.com/Tao-pyth/ygo-effect-dsl/issues/326) Rename terminal profile UI to end-board evaluation rules.
- [#327](https://github.com/Tao-pyth/ygo-effect-dsl/issues/327) Replace raw card-code input with deck-card selection.
- [#328](https://github.com/Tao-pyth/ygo-effect-dsl/issues/328) Add deck card options and deck profile bridge contracts.
- [#329](https://github.com/Tao-pyth/ygo-effect-dsl/issues/329) Fail closed when presentation source is unavailable.
- [#330](https://github.com/Tao-pyth/ygo-effect-dsl/issues/330) Add frontend and bridge tests for card selection UX.
- [#331](https://github.com/Tao-pyth/ygo-effect-dsl/issues/331) Capture desktop/mobile screenshots for terminal preference editor.
- [#332](https://github.com/Tao-pyth/ygo-effect-dsl/issues/332) Update roadmap and release docs for v0.9.0.
- [#333](https://github.com/Tao-pyth/ygo-effect-dsl/issues/333) Synchronize local release evidence and generated YDK artifact.
- [#334](https://github.com/Tao-pyth/ygo-effect-dsl/issues/334) Show card names instead of raw codes in deck catalog.
- [#335](https://github.com/Tao-pyth/ygo-effect-dsl/issues/335) Hide deprecated inline deck creation entry point.
- [#336](https://github.com/Tao-pyth/ygo-effect-dsl/issues/336) Make deck-card selection work in profile rules.
- [#337](https://github.com/Tao-pyth/ygo-effect-dsl/issues/337) Add deck tag management workflow.
- [#338](https://github.com/Tao-pyth/ygo-effect-dsl/issues/338) Add deck rename workflow.
- [#339](https://github.com/Tao-pyth/ygo-effect-dsl/issues/339) Wire Japanese card presentation provider into desktop startup.
- [#340](https://github.com/Tao-pyth/ygo-effect-dsl/issues/340) Define deck metadata catalog for rename and tags.
- [#341](https://github.com/Tao-pyth/ygo-effect-dsl/issues/341) Add deck metadata get/update contract.
- [#342](https://github.com/Tao-pyth/ygo-effect-dsl/issues/342) Add deck settings edit drawer for name and tags.
- [#343](https://github.com/Tao-pyth/ygo-effect-dsl/issues/343) Preserve existing desktop deck catalog compatibility.
- [#344](https://github.com/Tao-pyth/ygo-effect-dsl/issues/344) Correct stale card-name search wording in v0.9.0 issues and docs.
- [#345](https://github.com/Tao-pyth/ygo-effect-dsl/issues/345) Add real desktop card-presentation smoke for imported YDK.
- [#346](https://github.com/Tao-pyth/ygo-effect-dsl/issues/346) Add regression tests for hidden inline deck entry point.
- [#347](https://github.com/Tao-pyth/ygo-effect-dsl/issues/347) Add contextual help for route result metrics.
- [#348](https://github.com/Tao-pyth/ygo-effect-dsl/issues/348) Hide internal hashes from primary route and catalog views.
- [#349](https://github.com/Tao-pyth/ygo-effect-dsl/issues/349) Explain search termination when node budget is not exhausted.
- [#350](https://github.com/Tao-pyth/ygo-effect-dsl/issues/350) Surface opening hand and replay inputs in verification views.
- [#351](https://github.com/Tao-pyth/ygo-effect-dsl/issues/351) Show peak-score board state and route snapshot details.

## Acceptance

- `version:0.9.0` label と `v0.9.0` milestone が存在し、親 Issue と子 Issue 27 件がすべて紐づく。
- Roadmap、release stage index、CHANGELOG、release governance は `0.9.0` を planned source milestone として扱う。
- Desktop 実装フェーズでは、デッキ内カード選択で選んだ結果が内部 payload で `card_code` として保持され、デッキ外カードとアーカイブ済みプロファイルが拒否されることをテストで証明する。
- `[P] プロファイル` ページで、デッキ別プロファイルの一覧、新規作成、編集、アーカイブ、デッキ内カード picker を操作できる。
- 探索実行画面には終端評価ルールの編集フォームを置かず、選択と「プロファイルを編集」遷移だけを置く。
- デッキ設定で表示名とタグを変更でき、変更後も `deck_id`、`deck_sha256`、既存ジョブ、過去 evidence は変わらない。
- デッキカタログはカード名を主表示し、カード名 source がない場合は未構成として扱い、カードコードを名前として表示しない。
- 経路結果画面は Help、停止理由、初期手札、最大スコア盤面を表示し、Route/state/action hash を通常一覧の主表示にしない。
- `python -m ygo_effect_dsl.release_governance --check` が `finding_count: 0` を返す。

## Explicit non-goals

- 効果テキストから合法性、タイミング、カード効果を推測しない。
- カード効果から終端評価ルールを自動生成しない。
- 内部 `card_code` 契約を廃止、改名、外部表示用の主導線にしない。
- 終端評価ルールでカード名検索や raw `card_code` 手入力 fallback を提供しない。
- アーカイブ済みプロファイルの復元 UI は含めない。
- 固定初手、条件付きドロー、相手カードコードなど、終端評価ルール以外の入力改善は含めない。
- released である `v0.8.0` milestone を再オープンしない。
- `1.0.0` の production distribution、license、security、operations gate はこの stage に含めない。
