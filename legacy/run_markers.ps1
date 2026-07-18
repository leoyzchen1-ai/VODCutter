# Adds recap markers to the current DaVinci Resolve timeline.
# Prereqs (one-time):
#   Resolve > Preferences > System > General > External scripting using: Local
# Then: open Resolve, load the VOD on a timeline, and run this script:
#   powershell -ExecutionPolicy Bypass -File D:\CutterDavinci\run_markers.ps1
# Optional: pass a different CSV as the first argument.

param(
    [string]$Csv = "E:\Videos\VersionRecaps\ZZZ3.1\work\matches.csv"
)

$env:RESOLVE_SCRIPT_API = "C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
$env:RESOLVE_SCRIPT_LIB = "D:\Resolve\fusionscript.dll"
$env:PYTHONPATH = "$env:PYTHONPATH;$env:RESOLVE_SCRIPT_API\Modules\"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$vpy = "D:\CutterDavinci\.venv\Scripts\python.exe"

if (-not (Test-Path $env:RESOLVE_SCRIPT_LIB)) {
    Write-Host "fusionscript.dll not found at $env:RESOLVE_SCRIPT_LIB" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Csv)) {
    Write-Host "matches CSV not found: $Csv" -ForegroundColor Red
    exit 1
}

Write-Host "Adding markers from $Csv ..." -ForegroundColor Cyan
& $vpy "D:\CutterDavinci\legacy\resolve_markers.py" $Csv
