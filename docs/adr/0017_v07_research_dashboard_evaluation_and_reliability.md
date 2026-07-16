# ADR-0017: Research Dashboard Evaluation and Route Reliability

Status: Accepted

Date: 2026-07-16

## Context

package `0.5.0`のWindows desktopはdeck-first workflow、実preflight、background real-core Search、Route/SearchRun publicationまで接続している。一方、実job成功後の結果dialogは固定synthetic値を表示し、rendererはcommit済みartifactを読んでいない。backendにはconditional hand、version付きevaluator、fresh Replay、Route summaryが存在するが、研究者が入力条件、最終盤面、評価根拠、探索範囲、再生一致を一つの画面で監査できない。

汎用board-countだけでは、プレイヤーが重視する「特定カードが手札、表側の場、set、墓地にある」といったterminal preferenceを表現できない。また、同じscoreのRouteでも、カード効果中のcoin、dice、random selection、shuffle後のdrawに依存するRouteと、player decisionだけで到達するRouteでは実戦上の信頼性が異なる。seed付きReplayが再現可能であることと、実戦で確率依存しないことも同義ではない。

## Decision

package `0.7.0`を、先攻の初期盤面構築に限定したevidence-driven research dashboard stageとする。`0.6.0`の決定論的並列探索を入力とし、結果の真正性、ユーザーterminal preference、Route gameplay randomness、独立fresh Replay、説明可能な探索範囲を追加する。

1. 実jobの結果画面はcommit済み`best-route.yaml`と`search-report.json`だけを正本とする。browser fixtureのsynthetic previewは別modeとして明示し、real jobのRoute ID、score、Action、verificationへ流用しない。
2. terminal preferenceはcard code、controller、location、position、count predicate、scoring mode、signed integer weightからなるimmutable profileとして保存する。編集はclone-on-editとし、Experiment、Route、SearchRunはprofile IDとcontent digestを保持する。
3. locationとpositionを分離する。少なくとも`HAND`、`MONSTER_ZONE`、`SPELL_TRAP_ZONE`、`FIELD_ZONE`、`GRAVEYARD`、`BANISHED`と、`ANY`、`FACE_UP`、`FACE_DOWN`を扱う。`set`はfield locationと`FACE_DOWN`の組合せで表現し、自由文字列へ解釈しない。
4. profile scoreはbase scoreへ上書きせず、matched card instanceを伴う独立breakdownとして加減算する。`once`、`per_copy`、`threshold`を明示し、double countとunsupported predicateをfail-closeする。
5. Route gameplay randomnessをExperiment opening-hand sampling、Search strategy RNG、worker completion orderから分離する。gameplay eventはocgcore/EDOPro実行の直接証跡に基づき、step、card/Action、kind、outcome、seed provenance、取得できる場合だけprobabilityを保存する。不明値を推測しない。
6. `replay deterministic`と`gameplay stochastic`を別fieldで表す。同一seedでfresh Replayできても、実戦上の確率依存Routeをdeterministicと表示しない。legacy Routeのrandomness欠落は`unknown`であり、randomnessなしとは扱わない。
7. 新ranking policyは、success、terminal composite score、gameplay reliability、random event count、peak score、Action count、Route IDの安定順を基本とする。defaultはscoreが同等なRoute間で非random Routeを優先し、明示的なrandom penaltyをtotal scoreへ適用できる。絶対排除は`require_deterministic`で別指定する。
8. 結果は網羅性を証明しない限り`best observed`と表記する。frontier exhaustionにはcoverage certificateを要求し、deadline、cancel、resource limit、unknown candidateが残るrunを`optimal`と表記しない。
9. fresh Replay verificationはSearch workerから独立したjobとし、`unverified`、`verifying`、`verified`、`mismatch`、`replay_failed`を保存する。不一致や実行失敗をverified成功へ変換しない。
10. node上限なしmodeは提供しない。frontier exhaustion、logical checkpoint/resume、adaptive budgetにもhard time、RSS、disk、Replay、frontier上限を要求し、native duel/Lua stateを保存しない。
11. UIの直近scopeは先攻初期盤面構築presetとする。後攻盤面、相手AI、複数turnリレーは別stageまでUI入力へ追加しない。Neuron取込は公式accessと規約を調査し、非公式scrapingをrelease gateにしない。
12. 保存shapeまたはcanonical semanticが変わる場合は、対象となるRoute、evaluation、result-view等のcontractを独立version upする。package `0.7.0`だけを根拠にlegacy artifactを黙って再解釈しない。

## Consequences

- 研究者は、表示されたRouteがどのjob artifact、profile、asset、seed、ranking、Replay verificationに基づくか追跡できる。
- カードの位置別価値をデッキごとに表現できる一方、profile間のscoreを無条件に同一尺度として比較できない。analyticsはprofile digestでcohortを分離する必要がある。
- gameplay randomnessの完全検出はcore由来evidenceが必要であり、未対応shapeは保守的に`unknown`となる。Pythonが効果textから確率を推測する実装は認めない。
- 新rankingはlegacy runのbest Routeを変え得るため、policy versionを保存し、旧policyをread/replay可能にする必要がある。
- checkpoint/resumeとcoverageはjob recovery metadataより広いsemantic stateを持つ。既存checkpointを探索継続可能と説明してはならない。
- UI実装量は増えるが、探索速度やnode数を増やす前に評価目的と結果の真正性を固定できる。

## Rejected Alternatives

- card codeだけに一律bonusを与える案は、手札、場、set、墓地の意味を区別できないため採用しない。
- gameplay randomnessを単一booleanだけで保存する案は、根拠、発生step、Replay再現性、未知状態を監査できないため採用しない。
- 非random Routeをscoreに関係なく常に最上位にする案は、成功条件を満たす高品質Routeより弱い確定Routeを選ぶ可能性があるためdefaultにしない。strict filterとしてのみ提供する。
- rendererがartifact pathを直接読む案は、path traversal、別job混同、checksum bypassを招くため採用しない。typed application serviceでownershipとhashを再検証する。
- node無制限探索はresource exhaustionと完了誤認を招くため採用しない。
