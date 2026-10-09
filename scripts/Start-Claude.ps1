# Launch the approved native Claude client with only this workspace's typed Db2 binding.
[CmdletBinding()]
param([string]$Workspace = (Join-Path $PSScriptRoot '..'))
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$python = Join-Path $repository '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Run scripts/Setup.ps1 synchronously once to prepare the locked Python environment.'
}
$mcpPath = Join-Path $workspacePath '.mcp.json'
if (-not (Test-Path -LiteralPath $mcpPath -PathType Leaf)) {
    throw 'Prepare the private workspace .env and certificates folder, then run python -m workbench.db2_setup --workspace WORKSPACE --env-file WORKSPACE\.env. No connector UI or token is needed for local stdio.'
}
$claude = Get-Command claude -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $claude) { throw 'Install the organization-approved native Claude Code client and reopen PowerShell.' }
$runtimeFolder = Join-Path $workspacePath '.migration'
$runtimeMcpPath = Join-Path $runtimeFolder ('claude-runtime-' + [IO.Path]::GetRandomFileName() + '.json')
$arguments = @('--mcp-config', $runtimeMcpPath, '--strict-mcp-config')
if ($workspacePath -ne $repository) { $arguments += @('--add-dir', $workspacePath) }
$oldToken = [Environment]::GetEnvironmentVariable('WB_DB2_MCP_TOKEN', 'Process')
$tokenPointer = [IntPtr]::Zero
$tokenValue = $null
$secureToken = $null
$runtimeOwned = $false
try {
    # The fixed repository helper bounds and validates the saved config, including
    # exact local command/arguments. It preserves other saved servers but excludes
    # them from this runtime file. No credentials are read from .env into Claude.
    Push-Location -LiteralPath $repository
    try {
        & $python -m workbench.db2_setup --workspace $workspacePath --claude-runtime $runtimeMcpPath
        if ($LASTEXITCODE -ne 0) { throw 'The selected Db2 binding is invalid or unsafe. Follow the specific local setup action above; existing files are preserved.' }
        $runtimeOwned = $true
    }
    finally { Pop-Location }
    $settings = Get-Content -LiteralPath $runtimeMcpPath -Raw | ConvertFrom-Json
    $entry = $settings.mcpServers.'workbench-db2'
    # Only retained HTTP compatibility requires transport authentication. The
    # recommended fixed stdio child reads private Db2 credentials itself from .env.
    if ($null -ne $entry -and $entry.type -eq 'http' -and $null -ne $entry.headers -and
        $entry.headers.Authorization -eq 'Bearer ${WB_DB2_MCP_TOKEN}') {
        $secureToken = Read-Host 'Approved remote Db2 MCP bearer token (private; not saved)' -AsSecureString
        $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
        $tokenValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
        if ([string]::IsNullOrWhiteSpace($tokenValue) -or $tokenValue.Length -gt 8192 -or
            $tokenValue.ToCharArray().Where({ [int]$_ -lt 33 -or [int]$_ -gt 126 }).Count -ne 0) {
            throw 'A nonempty approved printable token is required for the retained authenticated HTTP binding.'
        }
        [Environment]::SetEnvironmentVariable('WB_DB2_MCP_TOKEN', $tokenValue, 'Process')
    }
    Push-Location -LiteralPath $repository
    try { & $claude.Source @arguments; $result = $LASTEXITCODE }
    finally { Pop-Location }
}
finally {
    [Environment]::SetEnvironmentVariable('WB_DB2_MCP_TOKEN', $oldToken, 'Process')
    if ($tokenPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer) }
    $tokenValue = $null
    if ($null -ne $secureToken) { $secureToken.Dispose() }
    if ($runtimeOwned -and (Test-Path -LiteralPath $runtimeMcpPath -PathType Leaf)) { Remove-Item -LiteralPath $runtimeMcpPath -Force }
}
if ($result -ne 0) { throw "Claude Code exited with code $result. Inspect the local client error; setup is not connectivity proof." }
