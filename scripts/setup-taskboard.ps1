<# Install the pinned upstream Taskboard in the user profile, without running Codex injectors. #>
param([string]$Node = "", [string]$NpmCli = "")
$ErrorActionPreference = "Stop"
if (-not $Node) { $Node = (Get-Command node -ErrorAction Stop).Source }
if (-not $NpmCli) {
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    $npmRoots = @((Split-Path -Parent $Node))
    if ($npmCommand) { $npmRoots += Split-Path -Parent $npmCommand.Source }
    $npmRoots += ([Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')).Split(';')
    $NpmCli = $npmRoots | Where-Object { $_ } | ForEach-Object { Join-Path $_ 'node_modules/npm/bin/npm-cli.js' } | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $NpmCli) { throw "Install npm with Node.js, or pass -NpmCli." }
$revision = 'bc25451c5c49a14abb6c4e8250b62c626b007f8a'
$root = if ($env:VERA_GLOBAL_CONFIG_DIR) { $env:VERA_GLOBAL_CONFIG_DIR } else { Join-Path $env:LOCALAPPDATA 'VERA' }
$integration = Join-Path $root 'integrations/dashi-taskboard'
$installation = Join-Path $integration $revision.Substring(0, 12)
New-Item -ItemType Directory -Path $integration -Force | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $installation '.git'))) {
    git clone 'https://github.com/chuspeeism/dashi-taskboard.git' $installation
    if ($LASTEXITCODE) { throw 'Taskboard clone failed.' }
}
git -C $installation checkout --detach $revision
if ($LASTEXITCODE) { throw 'Taskboard revision is unavailable.' }
$previousPath = $env:PATH
try {
    $env:PATH = (Split-Path -Parent $Node) + ';' + $env:PATH
    Push-Location $installation
    try {
        & $Node $NpmCli ci --ignore-scripts --no-audit --no-fund
        if ($LASTEXITCODE) { throw 'Taskboard dependencies failed to install.' }
        & $Node 'node_modules/vite/bin/vite.js' build --config 'web/vite.config.ts'
        if ($LASTEXITCODE) { throw 'Taskboard web build failed.' }
    } finally { Pop-Location }
    @{directory = $installation; revision = $revision; version = '1.1.27'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $integration 'current.json') -Encoding utf8
    Write-Output "Installed Taskboard 1.1.27. Open the Taskboard entry in VERA."
} finally { $env:PATH = $previousPath }
