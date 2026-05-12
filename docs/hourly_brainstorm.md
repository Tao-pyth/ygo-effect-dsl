# Hourly Brainstorm Workflow

この文書は、毎時ブレストを「作業前の雑談」ではなく、`ygo-effect-dsl` を研究用 CORE へ近づけるための主要な成果物として残すための運用ルールです。

ブレストの目的は、すぐに実装へ飛び込むことではありません。まず仮説を立て、根拠を見て、課題候補を整理し、Issue 化するかどうかを判断します。そのうえで、Worker への依頼、検証、コミットを行います。

## 確認観点

毎回、少なくとも次の観点を確認します。

- v0.0 stabilization: DSL 出力が測定可能で、回帰を検出できる状態に近づいているか。
- analyze / validate: 次に直すべき dictionary、transform、contract の課題が出力から読めるか。
- representative benchmark / golden: 代表カードと golden test が意図しない DSL 変更を検出できるか。
- `actions[]` / `targets[]`: canonical action と target 参照が、将来の状態遷移に必要な情報を持っているか。
- v0.1 connection: v0.0 の診断や DSL 形状が、最小 state/action semantics へつながるか。
- 日本語での追跡性: 新人日本語プログラマーが、課題、根拠、次に見るファイルを追えるか。

## 毎回残すテンプレート

Automation の最終報告も、この順序に合わせます。

```markdown
## Hourly Brainstorm Report

### 今回の仮説
- TBD

### 観察した根拠
- TBD

### ブレスト要点
- TBD

### 課題候補と Issue 化判断
- TBD

### Issue を追加しなかった場合の確認観点と理由
- TBD

### 作成・更新した Issue
- TBD

### Worker に依頼した課題と結果
- TBD

### 統合・修正した内容
- TBD

### 検証結果
- TBD

### クローズした Issue / クローズしなかった Issue と理由
- TBD

### Docs / README / コメント更新内容
- TBD

### コミット
- TBD

### 残課題と次回優先事項
- TBD
```

## Issue 化しない場合のルール

Issue を追加しない場合でも、「何も見なかった」と扱ってはいけません。次の2点を必ず残します。

- 確認した観点: 例として v0.0 stabilization、analyze/validate、representative benchmark/golden、`actions[]`/`targets[]`、v0.1 connection、日本語での追跡性。
- Issue 化しない理由: 既存 Issue に含まれる、根拠がまだ弱い、検証待ち、Worker に観察だけ依頼する、など。

この記録により、Issue が増えなかった回でも「どの観点で見て、なぜ今は課題化しなかったか」を後から追跡できます。

## Worker 依頼の考え方

Worker は、ブレストで見つかった仮説や課題候補を検証可能な形に進めるために使います。

依頼時には、次を明確にします。

- 対象 Issue または課題候補。
- 目的と期待成果物。
- 編集対象ファイルまたは責務範囲。
- 検証方法。
- 他の Worker や親エージェントと衝突しないための注意。

Worker の成果は、未確認のまま完了扱いにしません。親エージェントが差分、docs/spec 同期、テスト、CLI 出力、JSON/YAML fixture などで確認します。

## コミットの考え方

検証済みで、作業単位として意味のある差分だけをコミットします。

- 関連ファイルだけを stage します。
- コミットメッセージは Conventional Commits 風にします。
- 対象 Issue がある場合は `Refs #番号` または `Closes #番号` を含めます。
- 未検証差分、ユーザー由来の無関係な差分、途中失敗の差分はコミットしません。

コミットはブレストの代替ではありません。ブレストで立てた仮説と判断を、あとから追える状態に固定するための記録です。
