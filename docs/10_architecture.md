# Architecture

Status: Route DSL baseline

Last updated: 2026-07-13

## 1. Architectural Direction

`ygo-effect-dsl` はocgcore / EDOPro Luaを実行系の真実源とし、Pythonを探索・再現・評価・実験制御層とする。Route DSLは実行系の代替ではなく、探索成果物を保存・交換する境界である。

```text
Experiment
  -> Search
  -> Bridge <-> ocgcore <-> EDOPro Lua
  -> Replay
  -> Evaluation
  -> Route DSL
  -> Statistics / Comparison / Report
```

## 2. Components

### Experiment

デッキ、初手、先攻・後攻、ターン、カードプール、禁止制限、探索予算、妨害、成功条件、評価器を固定する。状態遷移や探索戦略を実装しない。

### Bridge

ocgcore MessageをDecisionRequestへ変換し、選択されたActionをcore inputへ戻す。候補の合法性はocgcoreの出力に従い、Python独自のカードルールを追加しない。

### Action

一つのDecisionRequestへの一つの応答を表す。Action IDはrequest署名と選択内容から決定的に生成する。表示用labelはidentityに含めない。

### Replay

初期snapshot、version metadata、seed、DecisionRequest署名、Action履歴を保持する。再実行中に署名が一致しなければ失敗し、近い候補へ自動補正しない。

### Search

Replay prefixから候補Actionを分岐させ、探索予算と枝刈りを管理する。状態価値はEvaluationへ委譲し、合法性はBridge / ocgcoreへ委譲する。

### Evaluation

停止可能状態のevaluation vector、score、successを返す。評価器は状態を変更しない。success predicateとscore evaluatorは独立したversion付きpluginとする。

### Route DSL

Replayに探索・分析上の意味を加えた正式成果物である。実験条件、checkpoints、Peak Board、Terminal Board、妨害、lineageを保持する。Route DSL validatorは構造と参照整合性だけを検証する。

### Statistics / Comparison / Report

複数Route DSLを集計し、初動率、事故率、成功率、盤面分布、妨害耐性、リカバリ成功率、カード依存度を計算する。人間向け表示はRoute DSLから派生させる。

## 3. Route DSL Structure

```text
Route Document
  experiment
  replay
    initial_snapshot
    version_metadata
    events[]
      DecisionRequest signature
      Action
      state hashes
  checkpoints[]
    replay step
    board summary
    evaluation
  result
    success
    peak_board
    terminal_board
  interruptions[]
  lineage
```

Replay eventとActionの `request_signature`、checkpointとresultの `state_hash` は一致しなければならない。表示名やtimestampは決定性の根拠にしない。

## 4. Main Flows

### Search

```text
Initial Experiment
  -> initialize ocgcore
  -> receive DecisionRequest
  -> enumerate Action candidates
  -> replay/apply Action
  -> test legal stop
  -> evaluate checkpoint
  -> branch or stop
  -> build Route DSL
```

### Interruption and Recovery

```text
Base Route DSL
  -> replay to selected step
  -> ask ocgcore whether interruption is available
  -> apply interruption
  -> resume Search
  -> build child Route DSL with lineage
  -> compare base and child routes
```

### Re-evaluation

```text
Existing Route DSL
  -> verify Replay or load trusted checkpoints
  -> run another evaluator / success predicate
  -> update derived evaluation result
  -> preserve original Action history
```

## 5. Data Ownership

| Data | Owner |
| --- | --- |
| Card behavior | EDOPro Lua |
| Legality and state transition | ocgcore |
| Message conversion | Bridge |
| Decision identity | DecisionRequest |
| Player/search choice | Action |
| Re-execution history | Replay |
| Branching policy | Search |
| Board value | Evaluation |
| Route exchange format | Route DSL |
| Aggregate metrics | Statistics |

## 6. Source Layout

Current engine contracts are under `src/ygo_effect_dsl/engine/`. Route DSL code is under `src/ygo_effect_dsl/route_dsl/`. The old root-level transform modules remain temporary migration code.

Target layout:

```text
src/ygo_effect_dsl/
  engine/
    action/
    bridge/
    replay/
    search/
    evaluation/
    experiment/
    statistics/
  route_dsl/
    validator.py
    serializer.py
    migration.py
  report/
  legacy/
    card_text/
```

## 7. Dependency Rules

- `bridge` は `search`、`evaluation`、`route_dsl` に依存しない。
- `replay` は探索戦略や評価器に依存しない。
- `search` は評価結果を利用できるが、評価式を所有しない。
- `evaluation` は状態を読み取るが、ocgcore入力を送信しない。
- `route_dsl` はReplay / Actionの保存形を参照できるが、ocgcoreを実行しない。
- `statistics` と `report` はRoute DSLを読み、探索中の状態を変更しない。
- legacy card-text modulesからengine / Route DSLへの依存を追加しない。

## 8. Failure Policy

- request署名不一致: Replay failure。
- version不一致: strict modeではfailure。
- unsupported core message: partial routeとして理由を保存できるが、成功ルートにしない。
- timeout / budget exhaustion: partial routeとしてTerminal BoardとPeak Boardを区別する。
- 妨害使用不可: interruption resultとして保存し、Pythonで強制適用しない。
- Route DSL参照不整合: schema validation failure。

## 9. Migration Boundary

v0.0のカードテキストYAMLはRoute DSLへrenameしない。意味が異なるため自動migration対象にもせず、`legacy card-text artifact` として隔離する。Route DSLはocgcore由来のReplayまたは契約fixtureからのみ生成する。
