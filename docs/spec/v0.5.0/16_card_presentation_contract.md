# Package 0.5.0 Card Presentation Contract

Status: Implemented and verified locally for the pinned English BabelCDB source; parent [#183](https://github.com/Tao-pyth/ygo-effect-dsl/issues/183)

Last updated: 2026-07-16

## Purpose and authority

`card-presentation-v1`はWindows desktop UIへカード詳細と効果テキストを供給するread-only projectionである。表示情報は人間による確認と検索highlightにのみ使用し、効果解釈、合法性、timing、Decision candidate、Replay、State、Evaluation、Search orderingの入力にしてはならない。これらの権威は実ocgcoreとEDOPro Luaに限定する。

既存`SQLiteCardDataProvider`はocgcore callbackへ`datas`行を供給する実行系providerとして維持する。表示系は`LocalizedCardPresentationProvider`へ分離し、`engine`、`experiment`、`prototype`から`ygo_effect_dsl.presentation`をimportしない依存testを必須とする。

## Versioned contracts

| Contract | Version | Responsibility |
|---|---|---|
| presentation | `card-presentation-v1` | availability、locale、text、metadata、diagnostic、source identity |
| provider | `sqlite-card-presentation-provider-v1` | verified local CDBのread-only query |
| source | `card-presentation-source-v1` | locale、DB hash、asset lock、Git OID、license、repository |
| query | `card-presentation-query-v1` | card code、requested/fallback locale、PlayerView redaction、expected versions |
| metadata | `card-metadata-presentation-v1` | CDB bit/packed fieldの機械的表示projection |
| text region | `card-text-region-v1` | `desc`と非empty `str1`から`str16`の順序保持 |
| diagnostic | `presentation-diagnostic-v1` | code、severity、field、message |

machine-readable contractは`src/ygo_effect_dsl/resources/card-presentation-contract-v1.json`に置く。契約とproviderのversion mismatchは暗黙変換せず`version_mismatch`でfail-closeする。

## Source verification

providerは利用前にCDBのSHA-256をsource manifestと照合し、SQLiteを`mode=ro&immutable=1`かつ`query_only`で開く。`datas`と`texts`の必須列が不足する場合はqueryを開始しない。host固有pathはsource identityへ含めず、次を監査可能なidentityとする。

- asset lock ID
- database filenameとSHA-256
- source repository、commit OID、tree OID
- operator-declared locale
- license status

localeはカード名や効果文から推測しない。現行pinned BabelCDBはDB内に機械可読なlocale宣言を持たないため、`en`はoperator/source設定として記録する。非英語sourceとlabel-map driftの追加qualificationは[#247](https://github.com/Tao-pyth/ygo-effect-dsl/issues/247)の`1.0.0` gateでfail-close検証する。

## Presentation behavior

availabilityは`available`、`missing_text`、`missing_card`、`redacted`、`source_unavailable`、`stale_source`、`version_mismatch`のいずれかとする。requested localeにsourceまたは名前がなければ、queryに明示された順序のfallbackだけを試す。fallback使用は`locale_fallback` diagnosticで可視化し、暗黙のlocale探索を行わない。

`texts.name`がない行は、`desc`やauxiliary textが存在しても`available`にしない。カード行自体がない場合はcodeを保持した`missing_card`を返す。推測した名前・効果文・翻訳を生成しない。

metadataはraw type/race/attribute bitsを必ず保持し、既知bitの表示labelを併記する。CDBのpacked levelからlevel、Xyz rank、Link ratingを分離し、Link markerをDEFとして表示しない。Monster以外のATK/DEF/level、Pendulum以外のscaleは`null`とし、DB上の0を適用可能な値として誤表示しない。Pendulum scaleとsetcode slotは機械的に分解する。未知bitの診断と定数追随は[#247](https://github.com/Tao-pyth/ygo-effect-dsl/issues/247)の`1.0.0` stable release gateである。

Unicodeと改行はそのまま保持する。providerは検索highlight用に本文を書き換えず、rendererが一時的なrangeとして表現する。画像は別contractであり、画像なしのtext-only表示を正常状態とする。

## PlayerView and audit

非公開カードはcard codeをproviderへ渡さず、`redacted=True` queryからtext、metadata、sourceを含まない`redacted` presentationを返す。表示時刻は決定論的presentation identityへ混入させず、desktop bridge/job audit envelopeの`rendered_at`としてcallerが記録する。presentation identityはsource hashと表示内容のdigestで再現可能にする。

## Distribution boundary

BabelCDBのlicense statusは現時点で`NOASSERTION`である。ローカルasset cacheからのread-only利用は検証対象とするが、CDB、カード名、効果文、画像をrepository、wheel、sdist、Windows executable、CI artifactへ同梱しない。再配布可否は[#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91)だけが決定する。

## Local evidence

`docs/adr/evidence/0183_card_presentation.json`はpinned BabelCDBの2 card codeについて、source identity、availability、field presence、文字数、presentation digestを保存する。カード名と効果文そのものは保存しない。

```powershell
python -m ygo_effect_dsl.spikes.card_presentation_evidence --out docs/adr/evidence/0183_card_presentation.json --locale en --card-code 2511 --card-code 10000
python -m pytest -q tests/test_card_presentation.py
```

現行evidence IDは`cardpresentationevidence_970d89f3a97ae4a01a4c5e983fccfad83907a1bf74e59673c4168f6299dbfe6c`である。
