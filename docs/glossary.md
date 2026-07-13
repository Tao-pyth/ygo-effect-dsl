# Glossary

Status: V0.1 baseline

## Action

探索の最小単位。NormalSummon、SpecialSummon、ActivateEffect、SelectCard、SelectOption、EndTurn などを想定する。Action は ocgcore / EDOPro Lua 由来の Bridge / DecisionRequest から得る。DSL `actions[]` は legacy であり、engine Action の前段ではない。

## Action Evaluation

特定の行動選択の価値を評価する処理。成功率、平均 Peak Score、将来期待値、訪問回数などを扱う。State Evaluation とは分離する。

## Bridge

Python と ocgcore の境界。ocgcore Message を Python Action に変換し、Python Action を ocgcore に入力できる形式へ戻す。ルール判断はしない。

## DSL Conversion CORE

過去の実験由来の legacy / deprecated / removal target。ETL export artifact を ingest し、DSL YAML へ transform し、validate と analyze を行うが、探索エンジンの入力、補助分析基盤、Action 生成元として扱わない。

## END_TURN

探索対象の Action。「探索を止める」という意思決定を表す。単なる制御命令ではない。

## Evaluation

探索結果や行動候補を評価する責務。State Evaluation と Action Evaluation を混同しない。

## ocgcore

遊戯王 OCG ルール、合法手判定、状態遷移、Lua 実行の真実源。Python は ocgcore の代替ルールエンジンにならない。

## Peak Board

探索途中で到達した最も評価値の高い停止可能盤面。Terminal Board より優先して正式結果として扱う。

## Replay

Seed、Deck、Action 履歴、選択履歴、バージョン情報、評価結果、実験条件を保持し、結果の再現性を担保する仕組み。

## Search Engine

Action 単位で分岐を作り、Replay と Evaluation を利用して探索する中核。Random Search、Beam Search、MCTS などを段階的に導入する。

## State Evaluation

盤面やリソースの価値を評価する処理。妨害数、手札、墓地、リソース、継続力、制圧力などを扱う。

## Terminal Board

探索が最後まで進んだ結果の盤面。比較や失敗理由の分析には使うが、正式な主成果は Peak Board とする。
