# Package 0.7.0 Research Dashboard Workflow

Status: Planned product contract; parent [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276)

Last updated: 2026-07-16

## 1. Product role

desktopは「最適Routeを断定する画面」ではなく、入力条件、探索範囲、評価根拠、成果物、Replay一致を研究者が反証できるworkbenchである。最初の画面はdeck一覧を維持し、deck選択からstatistics、Search、Runs、Result、Replay Verificationへ移動する。

## 2. Primary navigation

| View | Required content |
|---|---|
| Decks | catalog、YDK/inline登録、deck hash、asset/preflight state |
| Deck Detail | main/extra/side、card detail/effect text、deck composition statistics |
| Search | scenario preset、opening hand、evaluator/success、preference profile、interruption、budget、effective pool |
| Job Monitor | logical nodes、physical Replay、best score、elapsed、pool、retry、cancel、censor/resource state |
| Result | real Route、Action、terminal board、score breakdown、reliability、termination、artifact identity |
| Replay Verification | independent job state、identity、first difference、verification artifact |
| Runs | Top-K、candidate/path evidence、conditioned cohort、baseline/interrupted/recovery comparison |

## 3. Search input policy

- UIは先攻初期盤面構築presetを既定とし、starting-player toggleとraw turn-count inputを直近scopeへ追加しない。
- opening handはseeded random、fixed、conditionalを選べる。conditionalはcard codeとmin/max countを使用し、成立した実手札とsampling provenanceを保存する。
- evaluatorとsuccess predicateはPython serviceが提示するqualified presetだけを選択する。任意scriptや自由式をrendererから実行しない。
- preference profileはimmutable catalogから選択し、編集時はcloneする。
- inline deckはmain/extra/side code listをtyped bridgeへ渡す。unknown card、重複、構造違反をpreflight前後で同じdiagnosticとして表示する。
- specified interruptionはcard pickerとsupport taxonomyを表示し、coreが提示していないcandidateや未検証timingを生成しない。
- node、Replay、depth、time、RSS、diskにはbounded valueを要求する。frontier exhaustion modeでもhard limitを外さない。
- 代表カード、cost-card、resource-only/full-potential等のmodeを利用者へ選択させない。category条件を将来追加する場合も、選択deck内の具体scenarioへの解決、処理件数、coverageをsystem側で管理し、代表Routeの再現だけで全variant成立または最良と表示しない。

## 4. Result truthfulness

real desktop jobが`succeeded`になっただけではresultをverifiedと表示しない。rendererはjob artifact read serviceから検証済みresult viewを取得し、Route/report/profile/ranking/randomness digestを保持する。artifact取得、checksum、schema、identityのいずれかが失敗した場合はresultをfail-closeし、固定fallback値を表示しない。

Route ActionはAction IDだけでなく、card presentation、decision kind、selected candidate、target/option、state transition、legal stopを表示する。terminal boardはhand、monster、spell/trap、field、graveyard、banishedを区別し、face-up、face-down/set、unknown/redactedを視覚とtextの両方で示す。

scoreはsuccess、base、preference rule、random penalty、terminal composite、peakを分離する。terminationはsuccess predicate、STOP_LINE、END_TURN、frontier exhausted、node/replay/depth/time/resource、cancel、failureを区別する。coverage証明がなければ`best observed`と表示する。

## 5. Reliability and Replay

Resultには`gameplay deterministic`、`gameplay stochastic`、`randomness unknown`を表示し、eventからsource card、step、kind、outcome evidenceへdrill downできる。Search seedによる再現性を実戦上の確実性labelへ流用しない。

fresh Replayは明示操作で独立jobをenqueueし、unverified、verifying、verified、mismatch、replay failedを表示する。mismatchでは最初のAction/request/State/score/randomness差分を提示する。verification jobはUI threadとSearch worker stateを共有しない。

## 6. Explainability and analytics

Top-Kはrank、score、reliability、Action count、terminal summaryを表示し、同一terminal Stateや同一Action prefixのduplicateをdiversity groupへまとめる。Decision drill-downはcandidate別logical node、explored、unexplored、pruned、failed、censoredを区別する。未探索を不合法または失敗と表示しない。

analyticsはseeded random、conditional、fixedを別cohortとして扱う。profile digest、evaluator、success predicate、ranking policy、asset/core lock、termination/censor stateが異なるrunをsilent mergeしない。JSON/CSV/Parquet exportはUI queryと同じsnapshot/query semanticを使用する。

## 7. Desktop quality gates

- 1440×900、960×700、760×900でcontrol、card name、Action、score、dialogが重ならない。
- long card name/effect、100+ Action、Top-K/candidate tableはbounded scrollまたはvirtualizationを使用する。
- keyboard focus、accessible name、high contrast、reduced motionを維持する。
- default-deny CSP、typed bridge allowlist、payload/path/row/byte上限を維持する。
- browser previewとdesktop real modeを明示し、synthetic resultをreal artifactとしてexportしない。
- third-party asset、card text、private PlayerView data、absolute local pathをevidenceへ無審査で含めない。

## 8. Deferred workflow

後攻はopponent board snapshot、public/private information、固定妨害、opponent policyを先に定義する必要があるため、本stageのtoggleにはしない。複数turnリレーは継続評価と相手行動modelを必要とするため、初期盤面構築の強みを薄めない。Neuron取込は[#303](https://github.com/Tao-pyth/ygo-effect-dsl/issues/303)の公式access decision後にだけ実装Issueを切る。category条件の自動展開と処理量削減は[ADR-0018](../../adr/0018_reject_representative_and_cost_card_modes.md)の再評価条件を満たすまで実装scopeへ追加しない。
