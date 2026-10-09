# Native exit codes are checked explicitly, including expected setup probes.
$PSNativeCommandUseErrorActionPreference = $false
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$repository = (Get-Location).Path
$venvPython = Join-Path $repository '.venv/Scripts/python.exe'
$versionCheck = 'import platform, sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and platform.python_implementation() == ''CPython'' else 1)'
$lockDirectory = Join-Path $repository '.implementation/tmp'
[IO.Directory]::CreateDirectory($lockDirectory) | Out-Null
$bootstrapLock = $null
$previousPipUser = [Environment]::GetEnvironmentVariable('PIP_USER', 'Process')
try {
    # The handle, rather than the file's existence, owns the lock. No retry or
    # stale-file deletion is needed after a stopped process releases its handle.
    try {
        $bootstrapLock = [IO.File]::Open((Join-Path $lockDirectory 'windows-bootstrap.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch [IO.IOException] {
        throw 'Setup or Start is already running, or the startup lock cannot be opened. Finish that foreground command before retrying. No second setup was started.'
    }
    # Override only user installs. Keep enterprise index and CA configuration;
    # restore the caller's environment even when bootstrap or installation fails.
    [Environment]::SetEnvironmentVariable('PIP_USER', '0', 'Process')
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        $selectedCommand = $null
        $selectedPrefix = @()
        foreach ($candidate in @(@{ Name = 'py'; Prefix = @('-3.12') }, @{ Name = 'python'; Prefix = @() }, @{ Name = 'python3'; Prefix = @() })) {
            $candidateCommand = Get-Command $candidate.Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if (-not $candidateCommand) { continue }
            $probeArguments = @($candidate.Prefix) + @('-c', $versionCheck)
            $probeExit = 1
            try {
                # An installed launcher may not have a registered 3.12. Its
                # expected failure must not prevent probing the PATH interpreter.
                $ErrorActionPreference = 'SilentlyContinue'
                & $candidateCommand.Source @probeArguments 2>$null | Out-Null
                $probeExit = $LASTEXITCODE
            } catch {
                $probeExit = 1
            } finally {
                $ErrorActionPreference = 'Stop'
            }
            if ($probeExit -eq 0) {
                $selectedCommand = $candidateCommand.Source
                $selectedPrefix = @($candidate.Prefix)
                break
            }
        }
        if (-not $selectedCommand) { throw 'CPython 3.12 is required. Neither py -3.12, python nor python3 supplied a working CPython 3.12 interpreter. Install or repair CPython 3.12, then rerun Setup.ps1.' }
        $venvArguments = $selectedPrefix + @('-m', 'venv', '.venv')
        & $selectedCommand @venvArguments
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Check Python venv/ensurepip support and folder permissions.' }
    }
    & $venvPython -c $versionCheck
    if ($LASTEXITCODE -ne 0) { throw 'Existing .venv must use CPython 3.12. Rename it, then rerun Setup.ps1 to create a compatible environment.' }
    # Windows PowerShell 5.1 promotes native stderr during redirection. The
    # missing-pip probe is expected to fail; its explicit exit-code check is below.
    try {
        $ErrorActionPreference = 'SilentlyContinue'
        & $venvPython -m pip --version 2>$null | Out-Null
    } finally {
        $ErrorActionPreference = 'Stop'
    }
    if ($LASTEXITCODE -ne 0) {
        & $venvPython -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw 'Could not restore pip in .venv. Install CPython 3.12 with ensurepip support, then rerun Setup.ps1.' }
    }
    & $venvPython -m pip --disable-pip-version-check --no-input install --no-user --require-hashes --only-binary=:all: -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the configured package index, certificate settings and wheel availability for CPython 3.12; no unverified source build was attempted.' }
    & $venvPython -m workbench.preflight --workspace $repository --initialize-knowledge
    if ($LASTEXITCODE -ne 0) { throw 'Setup checks found blockers. Follow the diagnostic actions above, then rerun setup; existing application knowledge was preserved.' }
    New-Item -ItemType Directory -Force Endeavor,knowledge/inbox | Out-Null
    Write-Host 'Environment ready. Run scripts/Start.ps1 to open the setup screen.'
} finally {
    [Environment]::SetEnvironmentVariable('PIP_USER', $previousPipUser, 'Process')
    if ($null -ne $bootstrapLock) { $bootstrapLock.Dispose() }
}
