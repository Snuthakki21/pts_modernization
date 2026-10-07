param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [switch]$NoBrowser
)
# Native exit codes are checked explicitly, including expected setup probes.
$PSNativeCommandUseErrorActionPreference = $false
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$venvPython = Join-Path (Get-Location).Path '.venv/Scripts/python.exe'
$needsSetup = -not (Test-Path -LiteralPath $venvPython -PathType Leaf)
if (-not $needsSetup) {
    & $venvPython -m workbench.launch --check-environment
    $needsSetup = $LASTEXITCODE -ne 0
}
if ($needsSetup) {
    Write-Host 'Preparing the locked Python environment. This is only needed on first launch or when dependencies change.'
    & (Join-Path $PSScriptRoot 'Setup.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Environment setup failed. Follow the diagnostics above, then run Start.ps1 again.' }
}
$launchArguments = @('-m', 'workbench.launch', '--port', "$Port")
if ($NoBrowser) { $launchArguments += '--no-browser' }
& $venvPython @launchArguments
if ($LASTEXITCODE -ne 0) { throw 'Workbench stopped with an error. Follow its diagnostics, preserve the workspace, then launch again.' }
