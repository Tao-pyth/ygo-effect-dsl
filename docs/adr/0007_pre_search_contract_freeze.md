# ADR-0007: Freeze pre-search contracts before search implementation

Status: Frozen

Date: 2026-07-13

Decision Issue: #83

Evidence: `docs/adr/evidence/0007_pre_search_contracts.json`

## Context

Search実装はBridge、Action、Replay、State、Peak Board、Evaluation、Experimentの意味へ依存する。これらの境界がDraftのまま探索を実装すると、同値判定、枝刈り、評価cache、Replay再現、妨害指定が同時に変わり、探索結果を比較できない。

固定handの実コアvertical sliceでは、API v11 MessageからDecisionRequestを生成し、Action応答、完全Replay trace、State ID、合法停止、End Phase後の耐久評価、差し替え可能Evaluator、Experiment実行をfresh workerで再現できる。契約testはraw frame、request signature、State hash、score breakdown、Route全体の一致を検証する。

## Decision

Search実装が依存してよいpre-search contractを次で固定する。

- Bridge: `ocgcore-api-11.0` DecisionRequest protocol。未知message、不正応答、worker failureを候補なしへ変換しない。
- Action: DecisionRequestへの1 responseをatomic Actionとし、semantic Action IDとoccurrence IDを分離する。
- Replay: `0.3a`。manifest、初期State、全response、raw output frame、random/progress event、request signatureを保存する。
- State: `ygo-state-id-v1`。exact identityとquery projectionを区別し、近似同値をReplay検証・合法手cache・直接枝刈りへ使わない。
- Peak Board: core由来のlegal stopだけを候補とし、Turn 1 stopとEnd Phase後のTurn 2 terminalを別checkpointで評価する。
- Evaluation: `evaluation-result-v1` と `score-breakdown-v1`。Evaluator id/version/config hash、欠損解決、重み、寄与値を保存する。
- Experiment: `0.3a`。deck/player/turn limit/search/evaluator/success/interruption/replayをversion付き設定として検証する。
- Route DSL: `0.1`。上記contractとlineageを束ねる成果物であり、カード効果や合法手を実装しない。

Search node、frontier、termination、pruning、parallel schedulingはこのADRの固定対象外であり、後続Issueで定義する。

## Change Rule

固定contractの意味を変える場合は、schema/protocol/evaluator versionを更新し、旧fixtureを黙って再解釈しない。変更には次を必須とする。

1. ADRまたは既存ADR amendment。
2. migrationまたは明示的な非互換宣言。
3. golden/contract fixture更新。
4. fresh worker replayと全testの成功。
5. Architecture Freeze manifestのversion更新。

追加fieldであってもidentity、cache key、score、候補集合へ影響する場合は意味変更として扱う。

## Known Non-Blocking Verification

- #91: core/assets再配布条件。local prototype contractの固定を妨げないが配布をblockする。
- #92: 2026-07-13にAPI v11 raw lifecycleからcost/target/option roleを実コア検証した。根拠なしselectionは単独またはgeneric roleへfallbackする。
- #93: 2026-07-13にLua wrapperで直接RNGのdraw順、range、resultを実カードscriptから記録し、計装on/offのRequest、response、State遷移一致を実コア検証した。
- #94: 2026-07-13に代表的な一時攻撃力と効果無効を実コア観測で検証した。任意effectの列挙不能範囲は`unverified`としてdurable評価から除外する。
- #99: 2026-07-13に`resource_consumption_v1`を追加した。初期Stateからcheckpointまでの正味差分を真実源とし、validated cost roleは監査証拠として分離する。
- #95: configured interruptionの実コア発火。固定 `none` scenarioのsearch開始をblockしない。
- #96: 2026-07-13に`aggregation-v1`、Hive partition、nullable metric互換、JSONL/SQLite公開境界、PyArrow Windows配布証跡を固定した。
- #107: 直接RNG traceの暫定Hint transportについてclient表示、将来衝突、専用APIへの移行を検証する。現行transportはschemaとscript hashをReplay identityへ含める。
- #108: `resource_consumption_v1`の暫定重みを、複数デッキの同一State代替Routeとblind人手順位で校正する。
- #106: 2026-07-13にAction aggregation v2でcancel、fizzle/disable、連続selection、resolution selectionのraw Replay再計算とAPI 11.0 fail-closeを固定した。
- #109: #106のedge fixtureを実カードscriptによるfresh core corpusへ昇格し、将来API版のlayoutを別versionとして検証する。

未解決項目を「検証済み」と表示してはならない。Route、report、storage policyのpending validationに残す。

## Consequences

- Search実装は固定contractへ依存して開始できる。
- 現行version内での意味変更は禁止される。
- query APIで観測不能な情報をexactと偽らない。
- performance改善はReplay/State/Evaluation identityを変えない範囲で行う。
- open verification Issueは対象機能のproduction claimを制限するが、固定scenarioの探索prototype開始を妨げない。

## Amendment: Experiment 0.3b Information Policy

Issue #97で、Frozen `0.3a` を変更せず後継 `0.3b` を追加した。`0.3b` は `information-policy-v1` とcanonical policy IDを必須化する。`0.3a` はlegacy artifactとして検証可能だが、current実行前にdeck order、opening hand、sampling referenceを明示したmigrationが必要である。

Architecture Freeze evidenceの `experiment: 0.3a` は当時の固定versionを示す履歴値として変更しない。runtime current versionは `0.3b` であり、testはlegacy freeze versionとcurrent versionを区別する。Route、Replay、information auditに同一policy IDを保存し、policy変更をRoute identityとfresh Replay検証へ反映する。
