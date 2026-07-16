# ADR-0018: 代表カードとコストカードの利用者向けmodeを採用しない

Status: Accepted

Date: 2026-07-16

Related milestone: [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276)

## Context

初動条件を簡潔に表すため、「白き森のシルヴィと任意の魔法・罠」のようなcategory条件を、一つの代表カードで探索する案を検討した。代表Routeを他の具体カードへ束縛してfresh Replayできれば、全カードを個別探索するより処理量を減らせる可能性がある。また、ランダムドローした上振れ札を展開へ能動利用させず、手札コストとしてだけ扱う`cost card`または`resource-only` modeも候補になった。

しかし、具体カードが異なれば初期手札、残りdeck、Action payload、DecisionRequest candidate、request signature、State ID、Route IDが初期状態から異なる。墓地へ送った後も、card code、名称、種別、属性、墓地効果、回収・除外候補、他カードからの参照によって将来の合法候補と最終盤面が変わり得る。能動的な利用だけをSearch policyで禁止しても、ocgcoreが処理する誘発、強制処理、対象候補、他カードとの相互作用は同値にならない。

代表Routeを具体カードBで再現できることは、Bについてその盤面へ到達できるという下限だけを示す。B固有の効果や相互作用を使えば、より良い盤面へ到達できる可能性があり、代表盤面の再現を探索終了条件にすると最良Routeを見落とす。全variantの最良Routeを求める場合は各具体scenarioを探索する必要があり、代表Routeは最適性、frontier exhaustion、card間同値性を証明しない。

処理量も無視できない。初手へ入り得る異なるcard codeはmain deckで最大60種類であり、展開全体ではExtra Deckを含め最大75種類が関与し得る。Route長は使用カード枚数ではなく、発動、コスト、対象、option、zone、chain応答、同一カードの複数効果や再利用によるDecisionRequest responseの累積である。具体variantごとのRoute生成と独立fresh Replayは少なくともvariant数とAction列に対して線形に増え、分岐したvariantを再探索すると最悪時の削減は保証できない。

これを`resource-only`と`full-potential`等の利用者向けmodeで解決すると、利用者は検証目的だけでなく、カード効果抑制の意味、結果の比較可能性、最良性の制約まで理解して選択しなければならない。研究dashboardの主要操作にこの選択を追加することは、処理都合を利用者へ転嫁し、同じ初手条件から異なる意味の結果を生成する不要な負担になる。

## Decision

1. 代表カードを具体variant全体の代替とする機能を実装しない。代表Routeの再現成功を、他variantの探索完了、最良性、State同値性、枝刈り根拠として扱わない。
2. `cost card`、`resource-only`、効果封殺card等の利用者向けmodeを実装しない。架空card、無効果dummy、Python側の効果抑制、ocgcoreが提示した合法候補の意味的な書き換えも採用しない。
3. ExperimentとSearchは具体card code、具体deck、ocgcoreが提示する合法Actionを正本とする。カード固有の有利・不利な相互作用を、探索高速化のために黙って除外しない。
4. 「任意の魔法・罠」等のcategory入力を将来採用する場合、利用者へ検証modeを選ばせず、選択deck内の該当する具体card/scenarioへ解決する。全variantを検証していない場合は、全variant成立、最良、optimal等を表示しない。
5. 異なるcard codeを跨ぐ抽象State dedup、candidate同一視、Route終了判定は行わない。exact identityに基づく既存のState dedupとfresh Replay契約を維持する。
6. 代表Routeによるwarm start、action ordering、共通prefix推定等も現時点では製品機能またはSearch契約へ追加しない。将来再検討する場合は、具体variantごとの探索を省略せず、結果意味を変えない非semanticな最適化として別途証跡を要求する。

## User Burden and Qualification Volume

ユーザー負担と検証件数の均衡は独立機能や独立modeではなく、本ADRの継続的な設計制約として扱う。

- 利用者は「シルヴィを1枚以上含む」「シルヴィとdeck内の魔法・罠を含む」等の検証意図を一度指定する。内部の具体scenario展開、scheduler、retry、fresh Replay単位を選択させない。
- systemは対象となる具体scenario数、実行済み数、未実行数、失敗数、budgetで打ち切られた数を表示する。処理件数を隠すためにsample結果を全件結果として表示しない。
- 結果は具体scenarioごとの`best observed`、termination、coverageを保持する。全scenarioのfrontier exhaustionまたは正当なcoverage証明がない限り、category全体の最良性を主張しない。
- 処理削減は同一card codeのcopy統合、exact State identity、重複した具体opening hand、測定済みscheduler/parallelism等、意味を変えない方法を優先する。card categoryだけを根拠とした同値化は行わない。
- UI操作数を減らすために結果の意味を弱めたり、処理件数を減らすために利用者へ専門的mode選択を追加したりしない。入力の簡潔さと計算量の差は、内部計画と明示的な進捗・coverage表示で吸収する。

再検討時は、少なくとも次を同じworkloadで測定する。

- 対象となるdistinct concrete scenario数と重複除去後の件数。
- Route Action数、ocgcore内部遷移数、fresh Replay数、探索nodeごとの平均prefix長。
- wall time、CPU time、worker/main RSS、disk artifact量、cancel/resume時の再実行量。
- 代表的な短展開、長展開、chain/墓地利用のfixtureにおけるpool別throughput。
- 利用者が要求される入力項目、判断回数、誤選択率、結果解釈の不一致。
- variant固有のより良いRouteを見落とした件数と、budget停止時のcoverage差。

この測定で処理削減が確認できても、利用者へmode選択を追加する根拠にはしない。まず自動的なscenario正規化、重複除去、並列scheduler、checkpoint/resume、適応的budget、結果の段階表示で吸収できるかを評価する。

## Consequences

- 利用者はカード効果を封殺する特殊modeを理解せず、常に具体カードの合法な挙動として結果を解釈できる。
- card variant固有の上振れRouteを、代表盤面の再現だけで見落とす設計を避けられる。
- Pythonがカード効果や同値性を所有せず、ocgcoreをrule authorityとするADR-0002の境界を維持できる。
- category条件を全具体scenarioへ展開する場合、総CPU時間、fresh Replay数、artifact量は増える。並列化はwall timeを短縮できるが、総処理件数を消去しない。
- 処理量が大きい場合も、sampleを全件検証と偽らず、budget、coverage、未探索variantを利用者へ示す必要がある。
- 代表カード／コストカード機能を前提とするschema、UI、asset変更は行わない。

## Rejected Alternatives

- 代表カードの盤面を再現できたvariantを「成立グループ」として終了する案は、到達可能な下限とcard別最良Routeを混同するため採用しない。
- `resource-only`と`full-potential`を利用者が選択する案は、処理都合とsemantic差を主要workflowへ持ち込み、比較不能な結果を生みやすいため採用しない。
- 実cardへ解決した後に能動的Actionだけを禁止する案は、誘発、強制処理、他cardからの参照、candidate差を抑止できず、同値性を保証しないため採用しない。
- 無効果dummy cardやsymbolic cardをocgcoreへ投入する案は、実deckと異なるゲーム状態を検証するため採用しない。
- 全card databaseをcategory条件の対象にする案は、初手検証の対象deckを越えて件数を増やし、実際のdeck成立性を表さないため採用しない。

## Re-evaluation Conditions

次のすべてを満たす具体案が得られた場合だけ、本ADRをamendして再評価する。

1. 利用者へ追加modeやカード効果抑制の意味判断を要求しない。
2. concrete cardごとの合法Action、最終盤面、評価、より良いRouteを失わない。
3. exact Replay、State identity、Route identityをcard categoryの抽象同値で置き換えない。
4. 複数の実deck fixtureで、総処理件数またはwall timeの削減と見落とし0件を再現可能なevidenceで示す。
5. budget停止、未探索variant、coverageをfail-closeで表現し、部分結果を全件成立またはoptimalと表示しない。
6. 新しいschema、UI、scheduler契約がlegacy Experiment、Route、Replayを黙って再解釈しない。
