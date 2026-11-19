param(
    [string]$Python = "",
    [switch]$Dev,
    [string]$Config = ""
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $projectRoot ".venv/Scripts/python.exe" }
if (-not (Test-Path -LiteralPath $Python)) { throw "Install the VERA Python environment first, or pass -Python with its interpreter." }
$nodeCommand = Get-Command node -ErrorAction Stop
$nodeMajor = [int]((& $nodeCommand.Source --version).TrimStart('v').Split('.')[0])
if ($nodeMajor -lt 22 -or $nodeMajor -ge 26) { throw "Use Node.js 24 LTS (supported: 22-25)." }
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
$npmRoots = @((Split-Path -Parent $nodeCommand.Source))
if ($npmCommand) { $npmRoots += Split-Path -Parent $npmCommand.Source }
$npmRoots += ([Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')).Split(';')
$npmCli = $npmRoots | Where-Object { $_ } | ForEach-Object { Join-Path $_ 'node_modules/npm/bin/npm-cli.js' } | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $npmCli) { throw "Install npm with Node.js 24 LTS." }
$previousPath = $env:PATH
$previousRunAsNode = $env:ELECTRON_RUN_AS_NODE
$previousConnection = $env:VERA_DESKTOP_CONNECTION_FILE
$env:PATH = (Split-Path -Parent $nodeCommand.Source) + ';' + $env:PATH
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$connectionDirectory = Join-Path $env:LOCALAPPDATA "VERA/desktop-connections"
New-Item -ItemType Directory -Force -Path $connectionDirectory | Out-Null
$connectionFile = Join-Path $connectionDirectory ([guid]::NewGuid().ToString("N") + ".json")
$logFile = [IO.Path]::ChangeExtension($connectionFile, ".log")
$errorFile = [IO.Path]::ChangeExtension($connectionFile, ".error.log")
$arguments = @("-m", "vera.desktop.server", "--port", "0", "--connection-file", ('"' + $connectionFile + '"'))
if ($Config) { $arguments += @("--config", ('"' + (Resolve-Path -LiteralPath $Config).Path + '"')) }
$env:VERA_SILENT_STARTUP = "1"
$backend = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errorFile
try {
    $deadline = [datetime]::UtcNow.AddSeconds(30)
    while (-not (Test-Path -LiteralPath $connectionFile)) {
        if ($backend.HasExited) { throw "VERA service exited. See $errorFile" }
        if ([datetime]::UtcNow -gt $deadline) { throw "VERA service startup timed out. See $errorFile" }
        Start-Sleep -Milliseconds 100
    }
    $env:VERA_DESKTOP_CONNECTION_FILE = $connectionFile
    Push-Location (Join-Path $projectRoot "desktop")
    try {
        if (-not (Test-Path -LiteralPath node_modules)) { & $nodeCommand.Source $npmCli ci; if ($LASTEXITCODE) { throw "Desktop dependency installation failed." } }
        if ($Dev) { & $nodeCommand.Source $npmCli run dev }
        else {
            & $nodeCommand.Source $npmCli run build
            if ($LASTEXITCODE) { throw "Desktop build failed." }
            & $nodeCommand.Source $npmCli start
        }
    } finally { Pop-Location }
} finally {
    # Only the service created by this launcher and its owned descendants are stopped.
    if (-not $backend.HasExited) { & taskkill.exe /PID $backend.Id /T /F | Out-Null }
    Remove-Item -LiteralPath $connectionFile -Force -ErrorAction SilentlyContinue
    $env:VERA_DESKTOP_CONNECTION_FILE = $previousConnection
    $env:ELECTRON_RUN_AS_NODE = $previousRunAsNode
    $env:PATH = $previousPath
}
