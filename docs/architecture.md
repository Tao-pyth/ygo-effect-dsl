# Architecture

Status: V0.1 baseline

## 1. 方針

`ygo-effect-dsl` は、カード効果テキストを DSL 化するだけのツールではなく、将来の展開探索エンジンへ進むための研究 CORE である。V0.1 では、現在の DSL 変換基盤を維持しつつ、最終設計を「ゲームエンジン + AI 探索」として固定する。

本アーキテクチャは DDD を主軸にしない。責務境界、再現性、探索可能性、評価可能性を優先する。

## 2. レイヤー

```text
Documentation
  ▼
DSL Conversion CORE
  ▼
Engine Boundary
  ▼
Replay / Search / Evaluation
  ▼
ocgcore / EDOPro Lua
```

### Documentation

Charter、Architecture、Specifications、ADR を管理する。破壊的変更は、まずここで理由を説明する。

### DSL Conversion CORE

現在の実装範囲である。

```text
ingest
  ▼
transform
  ▼
validate
  ▼
analyze
```

ここでは ETL export artifact から DSL YAML を生成し、Action、Target、Cost、Restriction、Diagnostics、Analyze metrics を観測可能にする。

### Engine Boundary

将来の Bridge / Replay / Search / Evaluation へ DSL を渡す境界である。V0.1 では、この境界を文書と minimal semantics で定義する。

### Replay / Search / Evaluation

将来の中心領域である。

- Replay: 再現可能な Action 履歴と実験条件を保持する。
- Search: Action 単位で分岐を探索する。
- Evaluation: State Evaluation と Action Evaluation を分離して評価する。

### ocgcore / EDOPro Lua

ルールの真実源である。Python はルールを再実装しない。

## 3. Target Source Layout

長期的な実装構成は次を目標とする。

```text
src/
  engine/
    bridge/
    replay/
    search/
    evaluation/
    logging/
    statistics/
    experiment/
    util/
```

現在の `src/ygo_effect_dsl/` は、上記 `engine/` へ進む前の DSL Conversion CORE として維持する。既存コードを即時削除するのではなく、V0.1 の境界に合う形へ段階的に整理する。

## 4. Responsibility Rules

- Bridge は Message と Action の変換を担当し、ルール判断をしない。
- Replay は再現性を担当し、探索アルゴリズムを持たない。
- Search は探索制御を担当し、盤面価値を直接決めない。
- Evaluation は評価値を担当し、状態遷移そのものを実行しない。
- Statistics は観測結果を集計し、探索判断を直接変更しない。
- Experiment は条件比較を担当し、コア責務を混ぜない。

## 5. V0.1 Completion Definition

V0.1 の完了条件は、フルエンジン実装ではない。完了条件は次の通りである。

1. Project Charter が最上位方針として存在する。
2. README が V0.1 の目的と非目標を説明している。
3. Minimal Semantics が既存 DSL 出力から将来の state/action へ接続できる。
4. ADR が Charter 採用理由を記録している。
5. 既存 ingest / transform / validate / analyze の開発ループが維持されている。

この定義により、V0.1 は「設計基盤の確立」として扱う。
