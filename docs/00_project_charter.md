# Project Charter

Version: 0.3

Status: Authoritative Baseline

Last updated: 2026-07-13

## 1. Purpose

本プロジェクトは、遊戯王OCGのデッキについて、展開可能性、到達盤面、妨害耐性、リカバリ力を再現可能に自動検証する「ゲームエンジン連携 + AI探索」基盤を構築する。

中心となる利用フローは次の通りである。

```text
初手を与える
  -> 妨害なしの最良展開を探す
  -> 指定地点へ妨害を入れる
  -> 妨害後の最良リカバリを探す
  -> 結果を比較・集計する
```

本プロジェクトはデュエルクライアント、完全な対戦AI、Python製ルールエンジンの開発を目的としない。

## 2. DSL Definition

本プロジェクトで無修飾の「DSL」はRoute Information DSL（Route DSL）を指す。

Route DSLは、ocgcore / EDOPro Lua由来の実行結果と探索結果を、保存、再生、比較、再評価、集計するための構造化データ契約である。実験条件、Replay、Action履歴、途中盤面、Peak Board、Terminal Board、評価内訳、妨害、lineageを保持する。

Route DSLはカード効果を記述・実行しない。v0.0のカードテキスト変換物は `legacy card-text artifact` と呼び、現在のDSLには含めない。

## 3. Design Priorities

設計判断の優先順位は次の通りとする。

1. ocgcore / EDOPro Luaによるルールの正当性
2. Replayによる再現性
3. DecisionRequest / Action境界の安定性
4. 任意停止とPeak Boardの正確性
5. Route DSLによる結果の比較・再評価可能性
6. 妨害・リカバリ実験の拡張性
7. 探索効率
8. 実装の単純さ

## 4. Responsibility Boundary

- EDOPro Lua: カード効果と既存カード資産の真実源。
- ocgcore: ルール、合法手判定、チェーン処理、状態遷移、Lua実行。
- Bridge: ocgcore MessageとDecisionRequest / Actionの相互変換。
- Replay: 初期条件とAction履歴による決定的な再実行。
- Search: Action単位の分岐、予算管理、枝刈り。
- Evaluation: 状態とルートの評価。状態遷移は実行しない。
- Experiment: デッキ、初手、妨害、探索予算、成功条件、評価器の設定。
- Route DSL: 探索成果物の保存、交換、比較、再評価用契約。
- Statistics / Report: 複数ルートと複数初手の集計・表示。

Pythonはカード効果、合法性、コスト、対象、チェーン、状態遷移を自然言語や独自ルールから推測しない。

## 5. System Overview

```text
Deck / Hand / Experiment
  -> Bridge
  -> ocgcore + EDOPro Lua
  -> DecisionRequest
  -> Search selects Action
  -> Replay records execution
  -> Evaluation records checkpoints
  -> Route DSL
  -> Comparison / Statistics / Report
```

Route DSLは実行系の前段ではなく、実行・探索後の正式成果物である。ただし再実行時には、Route DSL内のReplayを入力としてocgcore実行を再構築する。

## 6. Core Functional Requirements

最優先機能:

1. デッキ、先攻・後攻、固定初手、ランダム初手の指定
2. 妨害なしの展開探索
3. 合法な任意停止
4. Peak Boardの抽出
5. Route DSLによるルート保存・表示
6. ユーザー指定位置への妨害挿入
7. 妨害後のリカバリ探索
8. 妨害前後の比較

次段階:

1. 多数初手の統計集計
2. デッキ構築比較
3. 類似ルートの分類
4. 結果検索・絞り込み
5. Markdown、CSV、JSON、HTML、可視化データ出力

将来機能:

1. 妨害位置の自動探索
2. 複数妨害の組み合わせ
3. 後攻展開・盤面突破
4. 複数ターン探索
5. デッキ自動調整
6. 対戦AI統合

## 7. Action and DecisionRequest

Actionは一つのDecisionRequestに対する応答であり、探索の最小単位である。通常召喚、特殊召喚、効果発動、対象選択、コスト選択、任意効果の拒否、フェイズ進行、ターン終了などを、ocgcoreの要求境界に従って表す。

Action IDは表示名や探索node IDではなく、request署名と選択内容から決定的に生成する。Bridgeは候補を変換するが、合法性を独自判断しない。

## 8. Replay

Replayは同じ環境、初期条件、Action履歴から同じDecisionRequestへ戻ることを保証する。seedだけでなく初期デッキ順、カード資産version、ocgcore build、Lua scripts commit、禁止制限、rule configを保存する。

探索分岐は、初期状態またはReplay prefixを再実行して別Actionを選択する。snapshot / clone最適化は、Replay基準実装の正当性を維持した上で導入する。

## 9. Legal Stop and Peak Board

探索では、選択肢が残っていても合法な時点で `STOP_LINE` を選べる。チェーン解決中、強制処理中、未応答DecisionRequestがある状態では停止できない。停止可否はPythonのカードルール推測ではなく、ocgcore由来の進行状態で判断する。

正式なルート成果はTerminal Boardだけではなく、途中で到達した最良の停止可能盤面であるPeak Boardとする。Route DSLはPeak BoardまでのAction数、停止理由、評価内訳、Terminal Boardとの差を保持できる。

## 10. Evaluation and Success

成功条件と盤面評価は分離する。成功条件は「2妨害以上」「特定カードへ到達」などの真偽値を返す。評価器は妨害数、手札、場、墓地・除外、後続、打点、耐性、使用済み資源、EX消費などのvectorと総合scoreを返す。

評価器と成功条件はID、version、設定hashを持つ。同じReplayを別の条件で再評価できることを必須とする。

## 11. Interruption and Recovery

初期段階では相手AIによる最適妨害探索を行わず、利用者がカード、効果、発動回数、DecisionRequest、チェーン位置、対象を指定する。妨害の使用可否はocgcoreで検証し、不可能な場合も結果として記録する。

リカバリルートは妨害なしルートのReplay prefixから分岐し、Route DSLのlineageで親ルートと分岐stepを参照する。比較では評価低下、失った妨害・資源、元の成功条件、代替到達先を扱う。

## 12. Experiment and Statistics

Experimentはデッキ、初手生成方法、先攻・後攻、ターン、禁止制限、カードプール、妨害、探索予算、成功条件、評価器を固定する。

集計対象には初動率、事故率、成功率、平均Peak Board評価、盤面分布、妨害耐性、リカバリ成功率、ルート多様性、カード依存度を含む。集計値は参照元Route DSLへ遡れるようにする。

## 13. Route DSL Requirements

Route DSLは次を満たす。

- Replayを内包または不変参照し、Action履歴を再実行できる。
- 各主要checkpointをReplay stepとstate hashで関連付ける。
- Peak BoardとTerminal Boardを区別する。
- successとscoreを区別する。
- 妨害とリカバリ分岐のlineageを表せる。
- 決定性に関わるfieldと表示用metadataを分離する。
- schema versionとmigration方針を持つ。
- JSON / YAMLで機械処理でき、Markdown / CSV / HTMLへ派生出力できる。

## 14. Legacy Card-Text Conversion

`ingest / transform / validate / analyze` と `resources/dict/v0_0` は過去のカードテキスト構造化実験である。移行期間中は既存テストのため残せるが、次の用途には使用しない。

- Route DSL生成の前段
- 探索Action生成
- 合法手判定
- 状態遷移
- ocgcore結果を補正するルール推論

過去仕様は `docs/spec/v0.0` と `docs/spec/v0.1` に歴史資料として保存する。

## 15. Documentation and Source Policy

文書の優先順位は次の通りとする。

```text
Project Charter
  -> Architecture
  -> Specifications
  -> ADR
  -> Implementation
```

目標ソース構成:

```text
src/ygo_effect_dsl/
  engine/
    bridge/
    action/
    replay/
    search/
    evaluation/
    experiment/
    statistics/
  route_dsl/
  report/
  legacy/
```

重要な責務変更は、実装と同じ変更単位でCharter、Architecture、Specification、ADRのいずれかへ反映する。

## 16. Development Rules

- EDOPro Luaの既存カード資産を優先し、カード効果をPythonへ転記しない。
- Bridge、Replay、Search、Evaluation、Route DSLの責務を混ぜない。
- Replayできない探索結果を正式結果として保存しない。
- Route DSL validatorでカードルールを検証しない。
- schema変更にはversion、migration要否、fixture、contract testを伴わせる。
- 最初に固定初手・先攻1ターン・妨害なしの垂直スライスを成立させる。
- 正当性をReplayで確立してからsnapshot、cache、並列化を導入する。

## 17. Long-Term Goal

全カードプールを対象に、初手からの展開、Peak Board、指定妨害後のリカバリ、デッキ構築差を再現可能に自動検証し、その結果をRoute DSLとして保存・比較・再評価できる状態を長期目標とする。
