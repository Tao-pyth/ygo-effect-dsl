# Roadmap

Status: Package 0.2.0 / General Search MVP candidate

Last updated: 2026-07-14

## 1. Version Baseline

package/CLI releaseは`0.2.0`、対応Git tagは`v0.2.0`とする。package versionは配布物全体のSemVer、機能契約versionは保存形式とAPIの互換境界であり、両者を同じ番号へ揃えない。

| 機能領域 | 現行version | 次にversion更新が必要になる条件 |
|---|---|---|
| Package / CLI | `0.2.0` | 利用者に見える機能追加はminor、互換修正はpatch、production安定契約はmajor |
| Project identity | `project-identity-v1` | repository、import、CLIなど安定名を変更する場合 |
| Experiment | `0.4` | scenario/searchの必須入力または意味を非互換変更する場合。`0.3b`は実行互換、`0.3a`は読み取り・migration入力 |
| Scenario | `scenario-v1` / `scenario-manifest-v1` / `scenario-preflight-v1` | deck、初手、preflight診断の保存契約を変更する場合 |
| Decision / Action / Replay | `0.3a` / manifest `ygo-replay-manifest-v1` | request、Action、Replayの意味または必須fieldを変更する場合 |
| Route DSL | `0.1` / normalization `route-normalization-v2` | Route交換形式またはcanonical normalizationを変更する場合 |
| Information | `information-policy-v1` / `information-audit-v1` | 情報参照境界またはaudit意味論を変更する場合 |
| State / Evaluation | `ygo-state-id-v1` / `evaluation-result-v1` / `score-breakdown-v1` / `route-resource-consumption-v1` | exact identity、score、資源評価の意味論を変更する場合 |
| Search | `search-executor-v1` / `search-run-result-v1` / `random-search-strategy-v1` | 探索順、結果順位、永続化fieldを変更する場合。新strategyは専用versionを追加する |
| Search support | `search-termination-v1` / `prefix-cache-policy-v1` / `parallel-search-result-v2` / `pruning-guardrail-policy-v2` | budget、cache、parallel、pruningの互換境界を変更する場合 |
| Real-core / interruption | `real-core-frontier-v1` / `core-interruption-candidate-policy-v1` / `interruption-support-taxonomy-v1` | worker frontierまたは妨害candidate/taxonomyの意味を変更する場合 |
| Storage | `raw-event-log-v1` / `run-catalog-v2` / `aggregation-v1` | JSONL、catalog、Parquetの読み取り互換を破る場合 |
| Benchmark / policy | `general-search-benchmark-v1` / `cache-worker-policy-v2` / `memory-preflight-v2` | workload、cache/worker既定値、memory判定根拠を変更する場合 |
| Runtime lock | ocgcore API `11.0` / assets `202504` | core、CardScripts、BabelCDBを更新し、lockと回帰evidenceを再生成する場合 |

`0.2.0`はPythonエンジニア向けsource milestoneであり、第三者assetを含む一般公開distributionではない。一般公開、対応環境、長期互換性は`#91/#127`完了後に別途宣言する。

## 2. Completed Foundations

- Project Charterと責務境界
- Pythonがカードルールを所有しないADR
- DecisionRequest、Action、Replay v0.3aの最小契約
- request signatureとaction IDの決定性
- STOP_LINEとEND_TURNの分離仕様
- Peak Board、Evaluation、Experimentの仕様
- 旧カードテキスト変換を本流から除外する判断
- Route DSL 0.1の責務、最小schema、validator、fixture

## 3. Completed Runtime Baseline

Route DSL Baselineと固定fixture中心の実core validation sliceは完了している。これらはGeneral Search MVPの入力・出力契約として維持する。

- pin済みocgcore / EDOPro Lua assetのbootstrap、検証、隔離worker
- API v11 Message、DecisionRequest、Action、完全Replay trace
- fresh worker Replay、canonical State ID、Peak / Terminal Board評価
- Experiment run / inspect / replay / reportとRoute DSL 0.1
- STOP_LINEとEND_TURN、探索予算、prefix cache、並列schedulerの独立contract
- 固定matrix/sequence fixtureによる妨害、lineage、失敗分類
- 初手sampling、資源消費評価、Route比較、optional Parquet集計

この到達点は任意カード、任意デッキ、一般探索、production規模を保証しない。

## 4. Released Scope: Package 0.2.0

対象利用者は、ローカルasset cacheを準備できるPythonエンジニアである。目標は、任意YDK/inlineデッキを事前検査し、実ocgcore上で決定論的Random Searchと指定妨害探索を実行し、再生可能な最良Route DSLをCLI/APIから出力できる状態である。

依存順は次のとおりとし、scenario入力契約を一般探索executorより先に固定した。

1. `[完了] #119` 開発環境: editable install、pytest、CLI subprocess、real-core workerのimport元を現在checkoutへ統一した。
2. `[完了] #124` 文書: 実装済み、MVP対象、production前を本ロードマップ基準へ同期した。
3. `[完了] #121` scenario: Experiment `0.4`、任意YDK/inline、fixed/random/conditional初手、manifest、preflightを追加した。
4. `[完了] #120` search: real-core frontier、Random Search、予算、決定論的tie-break、`experiment-search`を追加した。
5. `[完了] #122` interruption: 指定カードの全発動機会とsupport taxonomyをcore candidateだけから生成した。未検証categoryのfixture拡張は`#123`で継続する。
6. `[完了] #105 logical calibration` hardening: 3 fixture、10万logical node、pool 1/2/4/8/16の性能・メモリ・再現性evidenceを固定した。pool別の実core Replay throughput/RSSは`#128`で継続する。

## 5. MVP Contracts

### Scenario and preflight

- Experiment `0.4`を追加し、`0.3a/0.3b`の読み取り・Replay互換を維持する。
- `deck.source`は`fixed`、`inline`、`ydk`とし、YDK内容SHA-256をmanifestへ保存する。
- preflightはDB行、Lua script、asset lock、重複枚数、構造上のdeck制約を検査する。
- 欠落、不一致、conditional hand不成立をstructured diagnosticとして保存し、実行前にfail-closeする。

### Search executor

- MVPで実動させるstrategyは`RandomSearchStrategyV1`だけとする。
- RNGはseedとsemantic node IDから導出し、pool size、完了順、retryへ依存させない。
- STOP_LINEを合法候補として扱い、END_TURNと区別する。
- `max_nodes`、`max_seconds`、`max_depth`、`max_replays`を強制する。
- best Route順序はsuccess、peak score、terminal score、Action数、Route IDで固定する。
- prefix cacheは検証済みReplay hintだけに使い、native stateを再利用しない。枝削除はexact State identityだけに限定する。
- Beam Search / MCTSは同じinterfaceへ接続可能にするが、MVPでは指定時に未実装エラーを返す。

### Specified interruption

- ユーザー指定カードについて、coreが提示した全発動機会をPASS/発動へ分岐する。
- activation、cost、target、optionはDecisionRequest制約から生成し、Pythonで効果、合法性、タイミングを推測しない。
- targetless、cost、single/multi-target、hand/field sourceを機械可読taxonomyとして保存する。
- 未知candidate形状、候補消失、曖昧な対応はconfiguration failureまたはpath failureにする。
- damage step、mandatory trigger、SEGOC等の未検証categoryは成功扱いにしない。

### Production-scale evidence

- 短展開、長展開、墓地・除外またはchain多発の3 fixtureをpin済みassetから固定する。
- 各fixtureで同一の10万logical node workloadをpool 1/2/4/8/16で実行する。
- throughput、worker/main RSS、prefix/cache、fresh Replay、artifact量、write amplification、crash recoveryをJSON/Parquetへ保存する。
- semantic結果とbest Routeがpool sizeに依存しないことを必須とする。
- 10万node計測は手動またはself-hosted workflowで行い、通常CIは縮小smoke corpusを使う。
- 現行evidenceはlogical workload校正であり、pool別の実core Replay throughput/RSSをproduction性能の根拠にはしない。実worker校正は`#128`で行う。

## 6. MVP Completion Gate

- clean checkout、editable install、親/子Pythonプロセスのimport元一致
- YDK/inline正規化、deck hash、asset欠落、未知card/script、conditional hand失敗の検査
- 同一seed/budgetでSearchRunとbest Routeが再現し、pool sizeでsemantic結果が変化しない
- STOP_LINE、END_TURN、全budget、frontier exhausted、worker crash/timeout/retryの検査
- 指定妨害の全発動機会、cost/target、候補消失、unsupported taxonomyの検査
- Route ID、Replay、Experiment `0.3a/0.3b`の回帰
- wheel/sdist、Windows executable、clean venv CLI smoke。第三者assetは同梱しない
- 全テスト、GitHub Actions、10万node evidence、commit、push、PR、merge、`main`同期
- package metadata、CLI `--version`、README、Roadmap、changelogが`0.2.0`で一致し、review済み`main`へ`v0.2.0`を付与する

## 7. Release-based Implementation Plan

schema番号を先に予約してpackage番号へ合わせることはしない。各段階で既存契約を維持できる実装は既存schemaのまま追加し、保存形式や意味論を変える場合だけ対象契約をversion upする。

| Package目標 | 実装内容 | 機能契約への影響 | 完了gate |
|---|---|---|---|
| `0.2.x` | `0.2.0`の不具合修正、文書・CLI・packaging整合 | 原則として現行schemaを変更しない。互換修正だけをpatch releaseに含める | 全回帰、wheel/sdist/Windows smoke、既存Route Replay互換 |
| `0.3.0` | `#123`妨害fixture拡張、`#105/#128`実core 10万node・pool RSS校正、`#110`枝刈り校正、`#108`評価weight校正 | evidence追加だけなら現行version維持。既定policyやscore意味論を変える場合は該当policy/evaluation契約を更新 | 複数deckでsemantic一致、実worker throughput/RSS上限、未検証妨害categoryのfail-close解除根拠 |
| `0.4.0` | `#125` PlayerView Replay、Beam Search/MCTS、複数妨害、妨害位置探索、後攻盤面突破、複数turn | 新strategy contractとPlayerView Replay契約を追加。Experiment変更が必要な場合だけ`0.4`後継schemaを定義 | Random/Beam/MCTS共通executor回帰、private information非漏洩、baseline/interrupted/recovery lineage |
| `0.5.0` | `#126`大規模deck統計、Route比較API/UI、長時間job管理 | aggregation/catalogの読み取り互換を維持し、必要なら後継schemaを追加 | 大規模partition、再集計、比較再現性、UI/APIの同一結果 |
| `1.0.0` | `#91/#127`ライセンス、互換性matrix、release provenance、監視、upgrade/rollback、配布品質 | 公開stable contractを選定し、support期間とmigration policyを固定 | 第三者成果物審査、clean install、署名/checksum、incident手順、production benchmark |

`snapshot / clone`最適化やdistributed workerは、`0.3.0`のfresh Replay実測で必要性を示してから採用判断する。性能改善を理由にReplayの決定性やexact State identityを弱めない。

## 8. Explicit Non-Goals for MVP

- Python製カード効果エンジン
- カードごとのRoute DSL手書き
- 全ルート完全列挙
- 完全な相手AI
- 勝率予測
- オンライン対戦クライアント
- 一般公開配布

## 9. Legacy Removal

`ingest / transform / validate / analyze` とカードテキスト辞書は、Route DSL runtimeが依存していないことをテストで固定した後に削除する。旧出力をRoute DSLへ変換するmigrationは作らない。両者は意味的に別形式である。
