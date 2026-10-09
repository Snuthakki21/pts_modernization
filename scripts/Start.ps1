param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [switch]$NoBrowser
)
# Native exit codes are checked explicitly, including expected setup probes.
$PSNativeCommandUseErrorActionPreference = $false
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$repository = (Get-Location).Path
$venvPython = Join-Path $repository '.venv/Scripts/python.exe'
$lockDirectory = Join-Path $repository '.implementation/tmp'
[IO.Directory]::CreateDirectory($lockDirectory) | Out-Null
function Open-BootstrapLock {
    try {
        return [IO.File]::Open((Join-Path $lockDirectory 'windows-bootstrap.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch [IO.IOException] {
        throw 'Setup or Start is already running, or the startup lock cannot be opened. Finish that foreground command before retrying. No second startup was started.'
    }
}
$bootstrapLock = $null
try {
    $bootstrapLock = Open-BootstrapLock
    $needsSetup = -not (Test-Path -LiteralPath $venvPython -PathType Leaf)
    if (-not $needsSetup) {
        & $venvPython -m workbench.launch --check-environment
        $needsSetup = $LASTEXITCODE -ne 0
    }
    if ($needsSetup) {
        Write-Host 'Preparing the locked Python environment. This is only needed on first launch or when dependencies change.'
        # Setup owns the same lease during its synchronous install. Reacquire
        # before the readiness check; another command cannot install beside UI.
        $bootstrapLock.Dispose()
        $bootstrapLock = $null
        & (Join-Path $PSScriptRoot 'Setup.ps1')
        if ($LASTEXITCODE -ne 0) { throw 'Environment setup failed. Follow the diagnostics above, then run Start.ps1 again.' }
        $bootstrapLock = Open-BootstrapLock
        & $venvPython -m workbench.launch --check-environment
        if ($LASTEXITCODE -ne 0) { throw 'Environment setup returned, but readiness checks still failed. Follow the diagnostics above; the workbench was not started.' }
    }
    $launchArguments = @('-m', 'workbench.launch', '--port', "$Port")
    if ($NoBrowser) { $launchArguments += '--no-browser' }
    & $venvPython @launchArguments
    if ($LASTEXITCODE -ne 0) { throw 'Workbench stopped with an error. Follow its diagnostics, preserve the workspace, then launch again.' }
} finally {
    if ($null -ne $bootstrapLock) { $bootstrapLock.Dispose() }
}
