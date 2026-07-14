# CLI Operating Interface

Status: V0.3a prototype contract

Last updated: 2026-07-13

## Commands

| Command | Responsibility | Core execution |
| --- | --- | --- |
| `experiment-run` | Experimentを解決し、新しいrunとRouteを生成する | yes |
| `experiment-replay` | 記録済みExperiment/Routeをfresh workerで再実行し一致検証する | yes |
| `experiment-inspect` | Experiment/Route整合性とscore概要を表示する | no |
| `experiment-interrupt` | interruption definitionを持つ派生Experimentを生成する | no |
| `experiment-report` | Routeから人間向けMarkdownを再生成する | no |

`interrupt` はカード効果を実行せず、入力Experimentを派生させる。実行可否はrun時にrunnerが判定する。`report` はReplayやscoreのsource of truthを変更しない。

## Identifiers

- `RUN_ID`: 1回のCLI/worker実行を識別する。既定はUUID由来で、`--run-id` により外部orchestratorが指定できる。SQLite catalogとJSONL raw logのjoin keyであり、決定的Route identityには含めない。
- `ROUTE_ID`: Experiment、Replay、Peak/Terminal State等から得る再現可能artifact id。同じ入力と環境のfresh replayで一致する。
- `ACTION_ID`: Actionの意味内容を識別する。同じ意味のActionは複数runで一致し得る。
- `ACTION_OCCURRENCE_ID`: Action ID、Replay step、State hash、turn/chain座標から1回の実行を識別する。

RUN_IDとROUTE_IDを兼用してはならない。runが失敗してRouteを生成しない場合もRUN_IDとfailure raw logは残せる。

## Run Tracking

`experiment-run --catalog runs.sqlite3 --raw-log run.jsonl` は開始時にrunを `running` として登録し、成功時にRoute参照と `complete`、失敗時にerror summaryと `failed` を保存する。raw logは `run_started` の後に `run_completed` または `run_failed` を連番で保存する。

## Output And Exit Codes

- `0`: command成功。1行の機械可読なkey/value要約をstdoutへ出す。
- `1`: `validate-*` が読込可能だがschema違反を検出。issue一覧をstdoutへ出す。
- `2`: 引数、I/O、設定解決、worker、replay mismatch等のcommand失敗。`error:` 要約をstderrへ出す。argparse自身のusage errorも2である。

Route、report、catalog、raw logの本文をstdoutへ混在させず、`--out` 等で指定したartifactへ保存する。成功要約には可能な範囲でRUN_ID、Experiment ID、Route ID、event数、出力先を含める。tokenや非公開カード情報をerror summaryへ出してはならない。
