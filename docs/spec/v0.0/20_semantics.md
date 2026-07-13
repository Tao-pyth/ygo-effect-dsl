# ygoEffectDSL Spec v0.0 - Semantics

> Status: Historical baseline / conversion semantics
> Last updated: 2026-07-13

## 1. 目的

本仕様は、v0.0 DSL が表す意味の読み方を定義する。ここでいう semantics は、Python が遊戯王 OCG の実ルールを実行するという意味ではない。

v0.0 の役割は、カード効果テキストから後続処理が読める候補構造を作ることである。実ルールの合法性、状態遷移、Lua 実行は ocgcore / EDOPro Lua の責務であり、Python はそれを再実装しない。

## 2. 基本方針

v0.0 semantics は次を優先する。

1. DSL shape の安定性
2. `actions[]` と `targets[]` の観測可能性
3. 未解決の意味を diagnostics として残すこと
4. 後続の V0.1 state/action candidate へ接続できること
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

これらは実ルールの完全な裁定ではなく、後続処理が検証・分析できる構造である。

## 4. Action Semantics

`actions[]` は v0.0 の canonical action 表現である。単数の `action` は legacy fallback として残る場合があるが、新しい consumer は `actions[]` を優先する。

Action は、将来の Bridge / Replay / Search / Evaluation へ渡す候補情報である。v0.0 では Action を実行して盤面を変更しない。

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

対象情報が不足する場合は、空に見せかけず diagnostics として残す。これは、将来の Bridge / Replay / Search がどの情報不足で止まるかを可視化するためである。

## 6. Cost / Action Separation

コストと効果処理は混同しない。セミコロン等で分離される cost fragment は `cost` として保持し、`actions[]` を過剰に膨らませない。

この分離は、将来の Replay や妨害注入で「どの選択が cost で、どの選択が effect resolution か」を追跡するために必要である。

## 7. Diagnostics

Diagnostics は v0.0 semantics の重要な出力である。

- `error`: DSL shape が壊れており、後続処理が安全に読めない
- `warning`: shape は読めるが、意味が未解決、曖昧、互換 fallback である
- `info`: 分析補助情報

代表的な warning:

- `unknown_action`
- `unresolved_target`
- `missing_selector`
- `legacy_action_fallback`

## 8. V0.1 への接続

V0.1 は、v0.0 の `actions[]` と `targets[]` を読み、read-only の state/action candidate を作る。これは engine boundary contract であり、実 duel 実行ではない。

変換の流れは次の通り。

```text
Card text
  ▼
v0.0 DSL actions[] / targets[]
  ▼
V0.1 state/action candidate
  ▼
future Bridge / Replay compatible Action
```

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
4. V0.1 以降の engine boundary に渡せる拡張性
