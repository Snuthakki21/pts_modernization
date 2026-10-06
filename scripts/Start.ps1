$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Run scripts/Setup.ps1 first' }
& .venv/Scripts/python.exe -m workbench.preflight --workspace (Get-Location).Path --port 8765
if ($LASTEXITCODE -ne 0) { throw 'Startup checks found blockers. Follow the diagnostic actions above, then run Start.ps1 again.' }
Write-Host 'When the Workbench address appears below, open http://127.0.0.1:8765 in your browser. Keep this window open; Ctrl+C stops the server safely.'
& .venv/Scripts/python.exe -m workbench --root (Get-Location).Path
if ($LASTEXITCODE -ne 0) { throw 'Workbench stopped with an error. Preserve the workspace and inspect its diagnostic before restarting.' }
