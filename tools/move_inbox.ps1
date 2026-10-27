param(
  [Parameter(Mandatory=$true)][string[]]$Source,
  [string]$Period = "2026-10",
  [string]$Member = "member",
  [string]$Raw = "E:\Hansavahini\Datasetof CMS",
  [switch]$Run
)
$stage = Join-Path $env:TEMP "meshkor_inbox_stage"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null
$files = @()
foreach ($s in $Source) {
  if (-not (Test-Path -LiteralPath $s)) { Write-Host "NOT FOUND: $s  (check the path)" -ForegroundColor Red; continue }
  $item = Get-Item -LiteralPath $s
  if ($item.PSIsContainer) { $files += Get-ChildItem -LiteralPath $s -File } else { $files += $item }
}
$done = @{}
$plan = @()
foreach ($f in ($files | Sort-Object Name)) {
  if ($f.Name -notmatch '^(\d{6})__(.+)$') { Write-Host ("NO CCN IN NAME, skipped: " + $f.Name) -ForegroundColor Yellow; continue }
  if ($f.Extension -in '.crdownload','.part','.tmp') { Write-Host ("UNFINISHED, skipped: " + $f.Name) -ForegroundColor Yellow; continue }
  $ccn = $Matches[1]; $orig = $Matches[2]
  if ($done.ContainsKey($ccn)) { Write-Host ("DUPLICATE, skipped: " + $f.Name + "  (CCN " + $ccn + " already has " + $done[$ccn] + ")") -ForegroundColor Yellow; continue }
  $done[$ccn] = $f.Name
  $plan += [pscustomobject]@{ CCN=$ccn; MB=[math]::Round($f.Length/1MB,1); Name=$orig; Path=$f.FullName }
}
Write-Host ""
Write-Host "PLAN: $($plan.Count) hospitals" -ForegroundColor Cyan
$plan | Format-Table CCN, MB, Name -AutoSize
if (-not $Run) { Write-Host "Check only. Nothing was moved. If the plan is right, run it again with -Run" -ForegroundColor Green; exit 0 }
$ready = Join-Path $stage "ready"
New-Item -ItemType Directory -Path $ready | Out-Null
New-Item -ItemType Directory -Force (Join-Path (Split-Path $Raw -Parent) "_partial") | Out-Null
$ok = @(); $bad = @()
foreach ($p in $plan) {
  $folder = Join-Path $Raw ("MRF\" + $Period + "\" + $p.CCN)
  if (Test-Path -LiteralPath $folder) {
    Get-ChildItem -LiteralPath $folder -File | Where-Object { $_.Extension -in '.part','.crdownload' } | ForEach-Object { Move-Item -LiteralPath $_.FullName -Destination (Join-Path (Split-Path $Raw -Parent) ("_partial\" + $p.CCN + "__" + $_.Name)) }
  }
  $tmp = Join-Path $ready $p.Name
  Copy-Item -LiteralPath $p.Path -Destination $tmp
  python -m pipeline.hpt.intake --period $Period --ccn $p.CCN --file $tmp --page ("downloaded by hand (" + $Member + ")") --write-yaml
  if ($LASTEXITCODE -eq 0) { $ok += $p.CCN } else { $bad += $p.CCN; Write-Host ("FAILED: " + $p.CCN) -ForegroundColor Red }
  Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
Write-Host ""
Write-Host ("Moved: " + $ok.Count + "   Failed: " + $bad.Count) -ForegroundColor Cyan
if ($bad) { Write-Host ("Failed CCNs: " + ($bad -join ",")) -ForegroundColor Red }
Write-Host "CHECK (each line must show a real file and size):" -ForegroundColor Cyan
foreach ($c in $ok) {
  $d = Join-Path $Raw ("MRF\" + $Period + "\" + $c)
  $f = Get-ChildItem -LiteralPath $d -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.csv','.json','.xlsx','.txt' } | Sort-Object Length -Descending | Select-Object -First 1
  if ($f) { "{0}  OK  {1,9:N1} MB  {2}" -f $c, ($f.Length/1MB), $f.Name } else { "{0}  NO DATA FILE" -f $c }
}
Write-Host ""
Write-Host "Next (one line):"
Write-Host ("python backend\manage.py load_ref ref_hospital_mrf --period " + $Period + " --ccn " + ($ok -join ","))
