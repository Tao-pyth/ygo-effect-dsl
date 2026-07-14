# ygoEffectDSL Spec v0.0 - Semantics

> Status: Historical baseline / legacy conversion semantics / removal target
> Last updated: 2026-07-13

## 1. 目的

本仕様は、v0.0 DSL が表す意味の読み方を定義する。ここでいう semantics は、Python が遊戯王 OCG の実ルールを実行するという意味ではない。

v0.0の役割は、カード効果テキストから候補構造を作る過去の実験を記録することである。本書内のDSLは歴史的なv0.0名称であり、現在のRoute DSLではない。現在の探索エンジン設計では、この候補構造をBridge / Replay / Search / Evaluation / Route DSLの入力にしない。実ルールの合法性、状態遷移、Lua実行はocgcore / EDOPro Luaの責務であり、Pythonはそれを再実装しない。

## 2. 基本方針

v0.0 semantics は次を優先する。

1. DSL shape の安定性
2. `actions[]` と `targets[]` の観測可能性
3. 未解決の意味を diagnostics として残すこと
4. 過去の V0.1 state/action candidate 検討を再現できること
5. Python-only executor と誤解されないこと

## 3. Effect の読み方

各 `effects[]` 要素は、カードテキスト中の効果候補を表す。

主なフィールド:

- `trigger`: 発動、適用、誘発の候補情報
- `restriction`: 1ターンに1度などの制約候補
- `condition`: 適用条件候補
- `cost`: コスト候補
- `actions[]`: 効果が行う処理候補
- `targets[]`: action / cost / condition が参照する対象候補

これらは実ルールの完全な裁定ではなく、旧カードテキスト変換が検証・分析できる構造である。

## 4. Action Semantics

`actions[]` は v0.0 の canonical action 表現である。単数の `action` は legacy fallback として残る場合があるが、新しい consumer は `actions[]` を優先する。

Actionは旧カードテキスト変換内の候補情報である。Bridge / Replay / Search / Evaluation / Route DSLへ渡す情報ではない。v0.0ではActionを実行して盤面を変更しない。

代表的な action type:

- `draw`
- `add_to_hand`
- `send_to_gy`
- `destroy`
- `special_summon`
- `banish`
- `negate`

未知の action type は無理に既知語彙へ押し込まず、`unknown_action` などの diagnostics として可視化する。

## 5. Target Semantics

`targets[]` は、action / cost / condition が参照する対象候補を分離するための構造である。

Target は以下をできるだけ保持する。

- 対象の種類
- 枚数
- 領域
- controller
- targeting mode
- raw text
- 未解決 constraints

対象情報が不足する場合は、空に見せかけずdiagnosticsとして残す。これは旧カードテキスト変換の品質を可視化するためである。

## 6. Cost / Action Separation

コストと効果処理は混同しない。セミコロン等で分離される cost fragment は `cost` として保持し、`actions[]` を過剰に膨らませない。

この分離は旧カードテキスト変換の構造化結果を確認するために残す。Replay、Route DSL、妨害注入の実行系入力にはしない。

## 7. Diagnostics

Diagnostics は v0.0 semantics の重要な出力である。

- `error`: DSL shape が壊れており、legacy処理が安全に読めない
- `warning`: shape は読めるが、意味が未解決、曖昧、互換 fallback である
- `info`: 分析補助情報

代表的な warning:

- `unknown_action`
- `unresolved_target`
- `missing_selector`
- `legacy_action_fallback`

## 8. V0.1 との関係

V0.1 は、v0.0 の `actions[]` と `targets[]` から read-only の state/action candidate を作る過去の検討である。現在の方針では、これは境界契約ではなく legacy 記録として扱う。

過去の検討で想定した流れは次の通り。

```text
Card text
  ▼
v0.0 DSL actions[] / targets[]
  ▼
V0.1 state/action candidate
  ▼
deprecated Bridge / Replay compatible Action idea
```

この流れは現在の Primary Runtime Path ではない。現在の実行系入力は ocgcore / EDOPro Lua -> Bridge である。

## 9. 非目標

v0.0 semantics は次を定義しない。

- Python による合法手判定
- Python による実盤面の State -> State 実行
- chain / stack resolution
- opponent response modeling
- priority / timing window
- card-by-card ruling
- ocgcore の代替実装

## 10. 正しさ

v0.0 の正しさは、実ルール実行の完全性ではなく、次の観点で評価する。

1. 同一入力から同一 DSL を出力できる再現性
2. 主要な action / target 候補を落とさない観測可能性
3. 未解決情報を diagnostics として残す透明性
4. 過去の v0.1 検討を説明できる追跡性
