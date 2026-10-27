<#  Start a dedicated Chrome for hospital downloads, with remote control enabled.
    The pipeline (python -m pipeline.hpt.run --via chrome|auto) drives THIS window, so the
    VPN extension installed in it (Urban VPN, set to a US server) covers every download.

    First time only, in the window that opens:
      1. chrome.google.com/webstore -> install "Urban VPN Proxy" -> pin it -> choose United States -> ON
      2. leave the window open
    Every later time: just run this script, check the VPN icon says US, run the pipeline.
#>
param([int]$Port = 9222, [string]$Profile = "D:\Meshkor_Backend\chrome-hpt")
$candidates = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
                "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
                "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
$chrome = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { Write-Error "chrome.exe not found. Install Google Chrome."; exit 1 }
New-Item -ItemType Directory -Force -Path $Profile | Out-Null
Start-Process -FilePath $chrome -ArgumentList @("--remote-debugging-port=$Port", "--user-data-dir=$Profile", "--no-first-run", "--no-default-browser-check", "https://ipinfo.io/json")
Start-Sleep -Seconds 4
try {
  $v = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 5
  Write-Host "Chrome ready for the pipeline: $($v.Browser) on port $Port" -ForegroundColor Green
  Write-Host "In that window: Urban VPN -> United States -> ON. The ipinfo.io tab must show ""country"": ""US""."
} catch {
  Write-Warning "Chrome started but port $Port is not answering yet. Wait 5 s and run:  curl.exe http://127.0.0.1:$Port/json/version"
}
