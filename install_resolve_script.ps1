# Installs (or re-syncs) resolve_cut.lua into DaVinci Resolve's script menu.
# After running, the script appears under: Workspace > Scripts > resolve_cut
# Re-run this any time you edit resolve_cut.lua so Resolve picks up the changes.

$src     = Join-Path $PSScriptRoot "resolve_cut.lua"
$menuDir = Join-Path $env:APPDATA "Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"

if (-not (Test-Path $src))     { Write-Error "Missing $src"; exit 1 }
if (-not (Test-Path $menuDir)) { New-Item -ItemType Directory -Force -Path $menuDir | Out-Null }

$dst = Join-Path $menuDir "resolve_cut.lua"
Copy-Item $src $dst -Force
Write-Host "Installed: $dst"
Write-Host "In Resolve: Workspace > Scripts > resolve_cut  (restart Resolve if it isn't listed yet)"
