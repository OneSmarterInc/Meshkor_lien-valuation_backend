<#  One hospital, start to finish, after you downloaded its price file in the browser.

    .\tools\hpt_one.ps1 -Ccn 360051 -Period 2026-11 -File "C:\Users\hansa\Downloads\310536568_miami-valley-hospital_standardcharges.csv" -Page "https://www.premierhealth.com/..."

    Steps: intake (move + hash + log + yaml) -> load_ref -> build_duckdb -> hpt.verify -> hpt.quality -> progress.
    Stops at the first error. Run from the repo root with the venv active.
#>
param(
  [Parameter(Mandatory=$true)][string]$Ccn,
  [Parameter(Mandatory=$true)][string]$Period,
  [string]$File = "",
  [string]$Page = ""
)
$ErrorActionPreference = "Stop"
$args_ = @("-m","pipeline.hpt.intake","--period",$Period,"--ccn",$Ccn,"--write-yaml")
if ($File) { $args_ += @("--file",$File) }
if ($Page) { $args_ += @("--page",$Page) }
Write-Host "== 1/6 intake" -ForegroundColor Cyan
python @args_;                                            if ($LASTEXITCODE) { exit $LASTEXITCODE }
Write-Host "== 2/6 load_ref ref_hospital_mrf" -ForegroundColor Cyan
python backend\manage.py load_ref ref_hospital_mrf --period $Period;       if ($LASTEXITCODE) { exit $LASTEXITCODE }
Write-Host "== 3/6 build_duckdb --only ref_hospital_mrf (fast refresh)" -ForegroundColor Cyan
python backend\manage.py build_duckdb --only ref_hospital_mrf;                    if ($LASTEXITCODE) { exit $LASTEXITCODE }
Write-Host "== 4/6 verify" -ForegroundColor Cyan
python -m pipeline.hpt.verify --period $Period --quarantine;                            if ($LASTEXITCODE) { exit $LASTEXITCODE }
Write-Host "== 5/6 quality" -ForegroundColor Cyan
python -m pipeline.hpt.quality --ccn $Ccn --period $Period; if ($LASTEXITCODE) { exit $LASTEXITCODE }
Write-Host "== 6/6 progress" -ForegroundColor Cyan
python -m pipeline.hpt.progress
Write-Host "done: $Ccn $Period. Commit config\sources_local.yaml, data\ref\_manifest, data\reports." -ForegroundColor Green
