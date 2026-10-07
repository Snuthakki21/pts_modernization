# Native exit codes are checked explicitly, including expected setup probes.
$PSNativeCommandUseErrorActionPreference = $false
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$venvPython = Join-Path (Get-Location).Path '.venv/Scripts/python.exe'
$versionCheck = 'import platform, sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and platform.python_implementation() == ''CPython'' else 1)'

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -c $versionCheck
        if ($LASTEXITCODE -ne 0) { throw 'CPython 3.12 is required. Install CPython 3.12 with its py launcher and pip, then rerun Setup.ps1.' }
        & py -3.12 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c $versionCheck
        if ($LASTEXITCODE -ne 0) { throw 'CPython 3.12 is required. Install CPython 3.12 and add it to PATH, then rerun Setup.ps1.' }
        & python -m venv .venv
    } else {
        throw 'CPython 3.12 is required. Install CPython 3.12 with its py launcher and pip, then rerun Setup.ps1.'
    }
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
& $venvPython -m pip --disable-pip-version-check --no-input install --require-hashes --only-binary=:all: -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check access to pypi.org/files.pythonhosted.org and wheel availability for CPython 3.12; no unverified source build was attempted.' }
& $venvPython -m workbench.preflight --workspace (Get-Location).Path --initialize-knowledge
if ($LASTEXITCODE -ne 0) { throw 'Setup checks found blockers. Follow the diagnostic actions above, then rerun setup; existing application knowledge was preserved.' }
New-Item -ItemType Directory -Force Endeavor,knowledge/inbox | Out-Null
Write-Host 'Environment ready. Run scripts/Start.ps1 to open the setup screen.'
