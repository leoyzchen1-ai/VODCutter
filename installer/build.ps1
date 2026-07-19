# Builds the VODCutter installer payload and compiles the setup exe.
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1 [-SkipGpu] [-SkipCompile]
param([switch]$SkipGpu, [switch]$SkipCompile)
$ErrorActionPreference = "Stop"

$root  = Split-Path $PSScriptRoot -Parent          # repo root
$stage = Join-Path $PSScriptRoot "payload"
$pyDir = Join-Path $stage "python"
$cache = Join-Path $PSScriptRoot "cache"
$PyVer = "3.12.10"
New-Item -ItemType Directory -Force $stage, $cache | Out-Null

Write-Host "== 1/7 embeddable Python $PyVer =="
$zip = Join-Path $cache "python-$PyVer-embed-amd64.zip"
if (-not (Test-Path $zip)) {
  Invoke-WebRequest "https://www.python.org/ftp/python/$PyVer/python-$PyVer-embed-amd64.zip" -OutFile $zip
}
if (Test-Path $pyDir) { Remove-Item $pyDir -Recurse -Force }
Expand-Archive $zip -DestinationPath $pyDir

Write-Host "== 2/7 enable site-packages =="
$pth = Join-Path $pyDir "python312._pth"
(Get-Content $pth) -replace '^#import site$', 'import site' | Set-Content $pth -Encoding ascii

Write-Host "== 3/7 bootstrap pip =="
$getpip = Join-Path $cache "get-pip.py"
if (-not (Test-Path $getpip)) { Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip }
& "$pyDir\python.exe" $getpip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }

Write-Host "== 4/7 install runtime deps + cutter =="
& "$pyDir\python.exe" -m pip install --no-warn-script-location -r (Join-Path $PSScriptRoot "requirements-payload.txt")
if ($LASTEXITCODE -ne 0) { throw "dependency install failed" }
& "$pyDir\python.exe" -m pip install --no-warn-script-location $root
if ($LASTEXITCODE -ne 0) { throw "cutter install failed" }

Write-Host "== 5/7 GPU component staging =="
if (-not $SkipGpu) {
  $gpu = Join-Path $stage "gpu"
  if (Test-Path $gpu) { Remove-Item $gpu -Recurse -Force }
  & "$pyDir\python.exe" -m pip install --no-warn-script-location --target $gpu "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"
  if ($LASTEXITCODE -ne 0) { throw "GPU libs install failed" }
} else { Write-Host "   (skipped)" }

Write-Host "== 6/7 stage shim/config/postinstall =="
Copy-Item (Join-Path $PSScriptRoot "cutter.cmd") $stage -Force
Copy-Item (Join-Path $PSScriptRoot "config-default.toml") $stage -Force
Copy-Item (Join-Path $PSScriptRoot "POSTINSTALL.txt") $stage -Force

Write-Host "== 7/7 payload smoke test (isolated, CPU path) =="
$tmp = Join-Path $PSScriptRoot "tmp-smoke"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Force $tmp | Out-Null
$env:HF_HOME = Join-Path $tmp "hf"
$help = & "$pyDir\python.exe" -m cutter --help
if ($LASTEXITCODE -ne 0) { throw "cutter --help failed" }
if (-not (($help -join " ") -match "beatify")) { throw "--help missing subcommands" }
$job = Join-Path $tmp "smokejob"
New-Item -ItemType Directory -Force $job | Out-Null
Set-Content (Join-Path $job "vod.mp4") "dummy" -Encoding ascii   # beatify never decodes video
Set-Content (Join-Path $job "recap.txt") "First we see the intro. Then we see the gameplay." -Encoding ascii
& "$pyDir\python.exe" -m cutter beatify $job
if ($LASTEXITCODE -ne 0) { throw "beatify smoke failed" }
$beats = @(Get-Content (Join-Path $job "work\beats.txt"))
if ($beats.Count -ne 2) { throw "expected 2 beats, got $($beats.Count)" }
Write-Host "Smoke test OK (2 beats)"

$payloadMB = [math]::Round(((Get-ChildItem $stage -Recurse -File | Measure-Object Length -Sum).Sum)/1MB)
Write-Host "Payload size: $payloadMB MB"

$version = (Select-String -Path (Join-Path $root "pyproject.toml") -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Version: $version"

if (-not $SkipCompile) {
  $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $iscc) { throw "Inno Setup 6 not found. Install with: winget install -e --id JRSoftware.InnoSetup" }
  & $iscc "/DAppVersion=$version" (Join-Path $PSScriptRoot "vodcutter.iss")
  if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
  Write-Host "Installer: $(Join-Path $PSScriptRoot "Output\VODCutterSetup-$version.exe")"
} else { Write-Host "(compile skipped)" }
