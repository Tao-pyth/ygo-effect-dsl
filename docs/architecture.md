# Architecture

Status: V0.1 baseline

## 1. 方針

`ygo-effect-dsl` は、遊戯王 OCG の展開探索エンジンへ進むための研究基盤である。V0.1 以降の実行系は ocgcore / EDOPro Lua を真実源とし、既存 DSL CORE は legacy / deprecated / removal target として隔離する。

本アーキテクチャは DDD を主軸にしない。責務境界、再現性、探索可能性、評価可能性を優先する。

## 2. レイヤー

```text
Documentation
  ▼
ocgcore / EDOPro Lua
  ▼
Bridge
  ▼
Replay / Search / Evaluation
```

### Documentation

Charter、Architecture、Specifications、ADR を管理する。破壊的変更は、まずここで理由を説明する。

### Legacy DSL CORE

現在残っている互換維持用の実装範囲である。

```text
ingest
  ▼
transform
  ▼
validate
  ▼
analyze
```

ここでは ETL export artifact から DSL YAML を生成し、Action、Target、Cost、Restriction、Diagnostics、Analyze metrics を観測可能にする。ただし、これらは探索エンジンの入力、補助分析基盤、Action 生成元として扱わない。

### Bridge

ocgcore / EDOPro Lua 由来の Message / DecisionRequest を Python 側へ渡す境界である。Bridge は変換責務のみを持ち、合法性や状態遷移を判断しない。

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

現在の `src/ygo_effect_dsl/` には legacy DSL CORE が残っている。これは `engine/` へ進む前段ではなく、互換維持のための一時残置であり、V0.2 Bridge / Replay baseline 後の破壊的変更で削除対象とする。

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
3. Primary Runtime Path が ocgcore / EDOPro Lua -> Bridge -> Replay / Search / Evaluation として説明されている。
4. ADR が Charter 採用理由を記録している。
5. 既存 ingest / transform / validate / analyze が legacy / deprecated / removal target として明記されている。

この定義により、V0.1 は「設計基盤の確立」として扱う。
