param(
  [Parameter(Mandatory=$true)][string[]]$Source,
  [string]$Period = "2026-10",
  [string]$Member = "member2",
  [string]$Raw = "E:\Hansavahini\Datasetof CMS",
  [switch]$Run
)
$map = [ordered]@{
  "310537095"="360174"; "310537504"="360051"; "311079309"="360076"; "310678022"="360008";
  "311518658"="361337"; "314379441"="363305"; "316402480"="360092"; "340753531"="360155";
  "340898745"="361318"; "341041385"="360185"; "341407259"="360197"; "341883132"="360259";
  "344441792"="361314"; "WMH-MRF-PT-4.8-4-increased"="361329";
  "34-1623770"="360058"; "271952573"="363035"; "310672132"="363306"; "310833936"="363300";
  "344434676"="360009"; "346004382"="360059"
}
$expected = [ordered]@{
  "361314"="H.B. MAGRUDER"; "360197"="MARY RUTAN"; "360092"="MEMORIAL HOSPITAL OF UNION COUNTY";
  "361319"="SELBY GENERAL"; "363305"="NATIONWIDE CHILDRENS"; "361337"="POMERENE";
  "360051"="MIAMI VALLEY"; "360076"="ATRIUM"; "360174"="UPPER VALLEY"; "360259"="BAY PARK";
  "361318"="FOSTORIA"; "360185"="SALEM"; "360008"="SOUTHERN OHIO MEDICAL CENTER";
  "360155"="SOUTHWEST GENERAL"; "361335"="WAYNE HOSPITAL"; "361329"="WYANDOT MEMORIAL";
  "360009"="LIMA MEMORIAL"; "360058"="MERCER COUNTY / GRAND LAKE"; "360059"="METROHEALTH";
  "363035"="SUMMA REHAB"; "363041"="TRIHEALTH REHAB"; "363300"="CHILDRENS HOSPITAL MEDICAL CENTER CINCINNATI";
  "363306"="DAYTON CHILDRENS"
}
$stage = Join-Path $env:TEMP "meshkor_member2_stage"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null
$files = @()
foreach ($s in $Source) {
  if (-not (Test-Path -LiteralPath $s)) { Write-Host "NOT FOUND: $s  (check the path)" -ForegroundColor Red; continue }
  $item = Get-Item -LiteralPath $s
  if ($item.PSIsContainer) { $files += Get-ChildItem -LiteralPath $s -Recurse -File }
  elseif ($item.Extension -eq ".zip") {
    $d = Join-Path $stage ("unzip_" + $item.BaseName)
    Expand-Archive -LiteralPath $item.FullName -DestinationPath $d -Force
    $files += Get-ChildItem -LiteralPath $d -Recurse -File
  } else { $files += $item }
}
$done = @{}
$plan = @()
foreach ($f in ($files | Sort-Object Name)) {
  $key = $map.Keys | Where-Object { $f.Name.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
  if (-not $key) { Write-Host ("NO MATCH, skipped : " + $f.Name) -ForegroundColor Yellow; continue }
  $ccn = $map[$key]
  if ($done.ContainsKey($ccn)) { Write-Host ("DUPLICATE, skipped: " + $f.Name + "  (CCN " + $ccn + " already has " + $done[$ccn] + ")") -ForegroundColor Yellow; continue }
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
