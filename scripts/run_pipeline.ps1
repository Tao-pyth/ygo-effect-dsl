param(
    [string]$Dataset = "examples/sample_dataset",
    [string]$DslOut = "data/dsl_out/yaml",
    [string]$ReportOut = "data/reports"
)

python -m ygo_effect_dsl transform --dataset $Dataset --out (Split-Path -Parent $DslOut)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m ygo_effect_dsl validate $DslOut
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m ygo_effect_dsl analyze $DslOut --out $ReportOut
exit $LASTEXITCODE
