param(
  [Parameter(Mandatory=$true)][string[]]$Source,
  [string]$Period = "2026-10",
  [string]$Member = "member1",
  [switch]$Run
)
$map = [ordered]@{
  "314379443"="360159"; "310993422"="361304"; "852985806"="361331"; "311072406"="361334";
  "340714357"="363303"; "474992388"="360365"; "344429941"="361322"; "344477047"="361309";
  "310653685"="361332"; "310733259"="361330"; "2026_311724085"="361320"; "311724085"="361320";
  "310536662_1104867167"="360132"; "270712680"="360360"; "310621866_1023587045"="360368";
  "314379519"="360218"; "166189498"="360189";
  "311439334"="360012"; "310564121"="360133"; "310621866_1043233984"="360239"; "020701635"="360270"
}
$expected = [ordered]@{
  "360159"="ADENA HEALTH SYSTEM"; "361304"="GREENFIELD"; "361331"="ADENA FAYETTE"; "361334"="PIKE HEALTH";
  "363303"="AKRON CHILDRENS"; "360365"="AVITA ONTARIO"; "361322"="BLANCHARD VALLEY REGIONAL"; "361309"="HENRY COUNTY";
  "361332"="HIGHLAND DISTRICT"; "361330"="HOCKING VALLEY"; "361320"="HOLZER JACKSON"; "360132"="FORT HAMILTON";
  "360360"="BEAVERCREEK"; "360368"="KETTERING MEDICAL CENTER"; "360218"="LICKING MEMORIAL"; "360189"="MADISON COUNTY";
  "360012"="MOUNT CARMEL HEALTH SYSTEM"; "360014"="SHELTERING ARMS"; "360133"="DAYTON OSTEOPATHIC";
  "360239"="KETTERING MEDICAL CENTER (2nd)"; "360270"="MERCY DEFIANCE"; "363037"="OHRH"; "363042"="ENCOMPASS WESTERVILLE";
  "363049"="MERCY REHAB"; "364062"="MOUNT CARMEL BEHAVIORAL"
}
$stage = Join-Path $env:TEMP "meshkor_member1_stage"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null
$files = @()
foreach ($s in $Source) {
  if (-not (Test-Path -LiteralPath $s)) { Write-Host "NOT FOUND: $s  (check the path)" -ForegroundColor Red; continue }
  $item = Get-Item -LiteralPath $s
  if ($item.PSIsContainer) { $files += Get-ChildItem -LiteralPath $s -File }
  else { $files += $item }
}
$done = @{}
$plan = @()
foreach ($f in ($files | Sort-Object Name)) {
  $key = $map.Keys | Where-Object { $f.Name.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
  if (-not $key) { Write-Host ("NO MATCH, skipped : " + $f.Name) -ForegroundColor Yellow; continue }
  $ccn = $map[$key]
  if ($done.ContainsKey($ccn)) {
    Write-Host ("DUPLICATE, skipped: " + $f.Name + "   (same hospital " + $ccn + " as " + $done[$ccn] + ")") -ForegroundColor Yellow
    continue
  }
  $done[$ccn] = $f.Name
  $plan += [pscustomobject]@{ CCN=$ccn; MB=[math]::Round($f.Length/1MB,1); Name=$f.Name; Path=$f.FullName }
}
Write-Host ""
Write-Host "PLAN: $($plan.Count) hospitals" -ForegroundColor Cyan
$plan | Format-Table CCN, MB, Name -AutoSize
$missing = $expected.Keys | Where-Object { -not $done.ContainsKey($_) }
if ($missing) {
  Write-Host "NOT DELIVERED by the member (ask her):" -ForegroundColor Red
  foreach ($m in $missing) { Write-Host ("  " + $m + "  " + $expected[$m]) -ForegroundColor Red }
}
if (-not $Run) {
  Write-Host ""
  Write-Host "Check only. Nothing was moved. If the plan is right, run it again with -Run" -ForegroundColor Green
  exit 0
}
$ready = Join-Path $stage "ready"
New-Item -ItemType Directory -Path $ready | Out-Null
$ok = @(); $bad = @()
foreach ($p in $plan) {
  $tmp = Join-Path $ready $p.Name
  Copy-Item -LiteralPath $p.Path -Destination $tmp
  python -m pipeline.hpt.intake --period $Period --ccn $p.CCN --file $tmp --page ("downloaded by hand (" + $Member + ")") --write-yaml
  if ($LASTEXITCODE -eq 0) { $ok += $p.CCN } else { $bad += $p.CCN; Write-Host ("FAILED: " + $p.CCN) -ForegroundColor Red }
}
Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
Write-Host ""
Write-Host ("Moved: " + $ok.Count + "   Failed: " + $bad.Count) -ForegroundColor Cyan
if ($bad) { Write-Host ("Failed CCNs: " + ($bad -join ",")) -ForegroundColor Red }
Write-Host "Next (one line):"
Write-Host ("python backend\manage.py load_ref ref_hospital_mrf --period " + $Period + " --ccn " + ($ok -join ","))
