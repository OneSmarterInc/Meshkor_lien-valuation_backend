# check_downloads.ps1  -  checks the new team downloads on E:
# Run:  powershell -ExecutionPolicy Bypass -File .\check_downloads.ps1
# Output: screen + D:\meshkor-data\data\reports\check_downloads.txt
# 1st run saves a hash list. Next runs compare with it: CHANGED = a file was replaced.

$R    = "E:\Hansavahini\Datasetof CMS"
$Rep  = "D:\meshkor-data\data\reports"
$Hash = "$Rep\download_hashes.csv"
New-Item -ItemType Directory $Rep -Force | Out-Null
$out = New-Object System.Collections.Generic.List[string]
$bad = 0
function Say($s){ $script:out.Add($s); Write-Host $s }
function Bad($s){ $script:bad++; Say "  FAIL  $s" }
function Ok($s){ Say "  OK    $s" }
function Warn($s){ Say "  WARN  $s" }

$mon = @{1='jan(uary)?';2='apr(il)?';3='jul(y)?';4='oct(ober)?'}
$qs  = foreach($y in 2024..2026){ foreach($q in 1..4){ ,@($y,$q) } }

# ---------------- 1. ASP ----------------
Say "=== 1. ASP (expect 12 folders, 32 zips) ==="
if (-not (Test-Path "$R\ASP")) { Bad "folder ASP missing" } else {
  foreach($p in $qs){ $y=$p[0]; $q=$p[1]; $d="$R\ASP\${y}Q$q"
    if (-not (Test-Path $d)) { Bad "${y}Q$q folder missing"; continue }
    $f = Get-ChildItem $d -File | Where-Object Extension -ne ".sha256"
    $z = $f | Where-Object Extension -eq '.zip'
    $pr = $z | Where-Object { $_.Name -match '(?i)asp-pricing|payment-limit' }
    $cw = $z | Where-Object { $_.Name -match '(?i)crosswalk' }
    $nc = $z | Where-Object { $_.Name -match '(?i)noc' }
    if (@($pr).Count -ne 1) { Bad "${y}Q$q pricing zip count = $(@($pr).Count) (expect 1)" }
    if (@($cw).Count -ne 1) { Bad "${y}Q$q crosswalk zip count = $(@($cw).Count) (expect 1)" }
    if ($y -le 2025 -and @($nc).Count -ne 1) { Bad "${y}Q$q NOC zip count = $(@($nc).Count) (expect 1)" }
    if (-not ($f | Where-Object { $_.Name -match '(?i)^section 508.*(pricing|payment limit)' })) { Bad "${y}Q$q pricing 508 CSV not extracted" }
    if (-not ($f | Where-Object { $_.Name -match '(?i)^section 508.*ASP NDC-HCPCS' })) { Bad "${y}Q$q ASP crosswalk 508 CSV not extracted" }
    # wrong quarter: any file naming another month/year
    foreach($x in $f){ if ($x.Name -match '(?i)introduction') { continue }
      if ($x.Name -notmatch "(?i)$($mon[$q])[\s_\-]*$y") { Bad "${y}Q$q wrong place? $($x.Name)" } }
    $sub = Get-ChildItem $d -Directory
    foreach($s in $sub){ Bad "${y}Q$q extra subfolder (delete it): $($s.Name)" }
    if (-not $sub) { Ok "${y}Q$q  files=$(@($f).Count) zips=$(@($z).Count)" }
  }
}

# ---------------- 2. HCPCS ----------------
Say ""; Say "=== 2. HCPCS (expect 12 folders, 1 zip each) ==="
if (-not (Test-Path "$R\HCPCS")) { Say "  NOT YET  folder HCPCS missing" } else {
  foreach($p in $qs){ $y=$p[0]; $q=$p[1]; $d="$R\HCPCS\${y}Q$q"
    if (-not (Test-Path $d)) { Bad "${y}Q$q folder missing"; continue }
    $z = Get-ChildItem $d -File -Filter *.zip
    if (@($z).Count -eq 0) { Say "  NOT YET  ${y}Q$q no zip"; continue }
    $good = $z | Where-Object { $_.Name -match "(?i)^$($mon[$q])-$y-alpha-numeric-hcpcs-files?\.zip$" }
    if (@($good).Count -eq 1 -and @($z).Count -eq 1) { Ok "${y}Q$q $($good.Name)" }
    else { foreach($x in $z){ if ($good -notcontains $x) { Bad "${y}Q$q wrong file here: $($x.Name)" } } }
  }
}

# ---------------- 3. MS-DRG ----------------
Say ""; Say "=== 3. MSDRG (expect 7 folders, 2 zips each) ==="
$drg = [ordered]@{
 'V41'  =@('icd-10-ms-drg-definitions-manual-files-v41.zip','ms-drg-mce-v41-javasourcecode-binaries.zip')
 'V41.1'=@('icd-10-ms-drg-definitions-manual-files-v411.zip','medicare-severity-diagnosis-related-group-ms-drg-and-medicare-code-editor-mce-version-v411-java.zip')
 'V42'  =@('msdrgv420icd10r0definitionsmanualtext.zip','standalone-jars.zip')
 'V42.1'=@('icd-10-ms-drg-definitions-manual-files-v42.1*.zip','medicare-severity-diagnosis-related-group-ms-drg-and-medicare-code-editor-mce-version-42-java-source.zip')
 'V43'  =@('icd10-ms-drg-definitions-manual-files-v43.zip','ms-drg-mce-v43-standalone-jars.zip')
 'V43.1'=@('icd10-ms-drg-definitions-manual-files-v43-1.zip','ms-drg-mce-v43-1-standalone-jars.zip')
 'V44'  =@('fy2027-fr-icd10-ms-drg-definitions-manual-files-v44.zip','ms-drg-mce-v44-java-jars.zip') }
if (-not (Test-Path "$R\MSDRG")) { Say "  NOT YET  folder MSDRG missing" } else {
  foreach($v in $drg.Keys){ $d="$R\MSDRG\$v"
    if (-not (Test-Path $d)) { Bad "$v folder missing"; continue }
    $z = Get-ChildItem $d -File -Filter *.zip
    if (@($z).Count -eq 0) { Say "  NOT YET  $v no zip"; continue }
    $miss = $drg[$v] | Where-Object { $pat=$_; -not ($z | Where-Object { $_.Name -like $pat }) }
    foreach($m in $miss){ Bad "$v missing $m" }
    foreach($x in $z){ if (-not ($drg[$v] | Where-Object { $x.Name -like $_ })) { Bad "$v wrong file here: $($x.Name)" } }
    if (-not $miss) { Ok "$v 2 zips" }
  }
}

# ---------------- 4. Part B spending ----------------
Say ""; Say "=== 4. PARTB_SPEND ==="
if (-not (Test-Path "$R\PARTB_SPEND")) { Say "  NOT YET  folder PARTB_SPEND missing" } else {
  Get-ChildItem "$R\PARTB_SPEND" -Directory | ForEach-Object {
    $c = Get-ChildItem $_.FullName -File -Filter *.csv
    if (@($c).Count -ge 1) { Ok "$($_.Name) csv=$(@($c).Count)" } else { Bad "$($_.Name) no CSV" } }
}

# ---------------- 5. Hospital price files ----------------
Say ""; Say "=== 5. MRF (price files) ==="
$hosp = @{ '360085'='(?i)31-1340739|ohio-state'; '360051'='(?i)310537504|miami-valley'; '360180'='(?i)cleveland|340714585' }
if (-not (Test-Path "$R\MRF")) { Say "  NOT YET  folder MRF missing" } else {
  Get-ChildItem "$R\MRF" -Directory | ForEach-Object { $m=$_
    Get-ChildItem $m.FullName -Directory | ForEach-Object { $ccn=$_.Name
      $f = Get-ChildItem $_.FullName -File
      $data = $f | Where-Object { $_.Extension -in '.zip','.json','.csv','.gz' }
      $page = $f | Where-Object { $_.Extension -in '.html','.htm','.pdf' }
      if (-not $data) { Say "  NOT YET  $($m.Name)\$ccn no price file"; return }
      if ($hosp.ContainsKey($ccn)) {
        foreach($x in $data){ if ($x.Name -notmatch $hosp[$ccn]) { Warn "$($m.Name)\$ccn file of another hospital? check: $($x.Name)" } } }
      $gb = [math]::Round((($data | Measure-Object Length -Sum).Sum)/1GB,2)
      if (-not $page) { Say "  WARN  $($m.Name)\$ccn price page (html/pdf) not saved" }
      Ok "$($m.Name)\$ccn files=$(@($data).Count) size=$gb GB" } }
}

# ---------------- 6. Duplicates + replaced files ----------------
Say ""; Say "=== 6. Duplicates and replaced files (hash, files < 2 GB) ==="
$dirs = "ASP","HCPCS","MSDRG","PARTB_SPEND","MRF" | ForEach-Object { "$R\$_" } | Where-Object { Test-Path $_ }
$rows = foreach($d in $dirs){ Get-ChildItem $d -File -Recurse | Where-Object { $_.Length -lt 2GB -and $_.Extension -ne ".sha256" } | ForEach-Object {
  [pscustomobject]@{ Path=$_.FullName.Substring($R.Length+1); Size=$_.Length; SHA256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash } } }
$rows | Group-Object SHA256 | Where-Object Count -gt 1 | ForEach-Object {
  Warn ("same file in 2 places: " + (($_.Group.Path) -join "  |  ")) }
if (Test-Path $Hash) {
  $old = @{}; Import-Csv $Hash | ForEach-Object { $old[$_.Path]=$_.SHA256 }
  foreach($r in $rows){ if ($old.ContainsKey($r.Path) -and $old[$r.Path] -ne $r.SHA256) { Bad "CHANGED since last check: $($r.Path)" } }
  foreach($k in $old.Keys){ if (-not ($rows | Where-Object Path -eq $k)) { Bad "REMOVED since last check: $k" } }
  $new = @($rows | Where-Object { -not $old.ContainsKey($_.Path) }).Count
  Say "  new files since last check: $new"
}
$rows | Export-Csv $Hash -NoTypeInformation
Say "  hash list saved: $Hash  ($(@($rows).Count) files)"

Say ""; Say "=== RESULT: $bad FAIL ==="
$out | Set-Content "$Rep\check_downloads.txt"
Write-Host "Saved: $Rep\check_downloads.txt"
