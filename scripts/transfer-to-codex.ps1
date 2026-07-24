# transfer-to-codex.ps1 - transfer a Claude Code session into a resumable Codex thread.
# (Windows PowerShell 5.1 compatible, ASCII only.)
#
# Wraps the official codex-plugin-cc importer, working around its Windows bug
# (openai/codex-plugin-cc#513: import succeeds but the companion reports failure)
# by detecting the new thread directly in Codex's state DB.
#
# Usage:
#   transfer-to-codex.ps1 -Source <path-to-claude-jsonl> [-Model gpt-5.6-sol]
#                         [-Effort high] [-Launch]
#
#   -Source  Claude transcript (.jsonl under ~/.claude/projects) to transfer
#   -Model   Codex model id for the resumed session (omit = config default)
#   -Effort  Reasoning effort override (e.g. low/medium/high/xhigh)
#   -Launch  Open Windows Terminal running the resume command

param(
    [Parameter(Mandatory=$true)][string]$Source,
    [string]$Model = "",
    [string]$Effort = "",
    [ValidateSet('auto','app','vscode','terminal','none')][string]$OpenIn = 'auto',
    [switch]$Launch    # back-compat: same as -OpenIn terminal
)
$ErrorActionPreference = 'Stop'
$parityDir = $PSScriptRoot
$queryPy   = Join-Path $parityDir 'codex-thread-query.py'
if ($Launch -and ($OpenIn -eq 'auto' -or $OpenIn -eq 'vscode')) { $OpenIn = 'terminal' }
if ($OpenIn -eq 'auto') {
    # Prefer the OpenAI Codex desktop app when installed (codex:// protocol
    # registered), then the VS Code extension, then the terminal TUI.
    if (Test-Path 'Registry::HKEY_CLASSES_ROOT\codex') { $OpenIn = 'app' }
    elseif (Get-Command code -ErrorAction SilentlyContinue) { $OpenIn = 'vscode' }
    else { $OpenIn = 'terminal' }
}

function Resolve-CodexCommand {
    # Absolute path that works OUTSIDE Claude's app container too. npm -g from
    # inside Claude lands in MSIX-virtualized Roaming: paths under
    # $env:APPDATA\npm resolve INSIDE the container but do not exist for
    # external shells (the ones this script launches). The one location that is
    # real disk for everyone is the container's LocalCache backing store, and
    # the vendored codex.exe there is standalone (no node needed) - prefer it.
    $vendor = Get-ChildItem "$env:LOCALAPPDATA\Packages\Claude_*\LocalCache\Roaming\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($vendor) { return $vendor.FullName }
    $c = Get-Command codex -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notlike "$env:APPDATA\npm\*") { return $c.Source }
    if ($c) { return $c.Source }   # container-only path: better than nothing
    return $null
}

# --- resolve the plugin companion script (newest installed version) ---
$pluginGlob = Join-Path $env:USERPROFILE '.claude\plugins\cache\openai-codex\codex\*\scripts\codex-companion.mjs'
$companion = Get-ChildItem $pluginGlob -ErrorAction SilentlyContinue |
    Sort-Object { [Version]($_.FullName -replace '.*\\codex\\([0-9.]+)\\.*','$1') } |
    Select-Object -Last 1
if (-not $companion) {
    Write-Host "ERROR: codex-plugin-cc not found. Install with:" -ForegroundColor Red
    Write-Host "  claude plugin marketplace add openai/codex-plugin-cc"
    Write-Host "  claude plugin install codex@openai-codex"
    exit 1
}

# --- validate source ---
if (-not (Test-Path $Source)) { Write-Host "ERROR: source not found: $Source" -ForegroundColor Red; exit 1 }
$Source = (Resolve-Path $Source).Path
if ($Source -notlike "*.jsonl") { Write-Host "ERROR: source must be a .jsonl Claude transcript" -ForegroundColor Red; exit 1 }

# --- snapshot thread state, run the import, detect the new thread ---
$before = & python $queryPy --max-created
Write-Host "Transferring Claude session -> Codex thread..." -ForegroundColor Cyan
Write-Host "  source: $Source"
# EAP relaxed around the native call: node writes to stderr (deprecation noise,
# plus a FALSE "did not record an imported thread" error on Windows - #513),
# which PS 5.1 + Stop would turn into a spurious throw. We capture all output
# and only show it if our own thread detection below also comes up empty.
$eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$companionOutput = & node $companion.FullName transfer --source $Source 2>&1 | Out-String
$ErrorActionPreference = $eap

$threadLine = $null
foreach ($attempt in 1..15) {
    $threadLine = & python $queryPy --after $before
    if ($LASTEXITCODE -eq 0 -and $threadLine) { break }
    Start-Sleep -Seconds 1
}
$reused = $false
if (-not $threadLine) {
    # Codex dedupes: re-importing an UNCHANGED transcript creates no new thread.
    # Look up the previously imported thread for this source in the ledger.
    $threadLine = & python $queryPy --ledger $Source
    if ($LASTEXITCODE -eq 0 -and $threadLine) { $reused = $true }
}
if (-not $threadLine) {
    Write-Host "ERROR: no new Codex thread appeared after import (waited 15s)," -ForegroundColor Red
    Write-Host "and no prior import of this transcript exists in the ledger."
    Write-Host "Importer output follows:" -ForegroundColor Yellow
    Write-Host ($companionOutput -replace '(?m)^.*Deprecation.*$','').Trim()
    Write-Host "Run 'codex resume' to check the picker manually; the import may still have landed late."
    exit 1
}
$threadId = $threadLine.Split('|')[0]
$title    = $threadLine.Split('|')[2]
if ($reused) { Write-Host "  (transcript unchanged since a prior transfer - reusing its existing Codex thread)" -ForegroundColor Yellow }

# --- build the resume command (absolute codex path: survives external shells) ---
$codexCmd = Resolve-CodexCommand
if (-not $codexCmd) { $codexCmd = 'codex' }   # last resort; may fail outside container
$resumeArgs = @('resume', $threadId)
if ($Model)  { $resumeArgs += @('-m', $Model) }
if ($Effort) { $resumeArgs += @('-c', "model_reasoning_effort=`"$Effort`"") }
$resumeCmd = "& `"$codexCmd`" " + ($resumeArgs -join ' ')

Write-Host ""
Write-Host "SUCCESS  thread: $threadId" -ForegroundColor Green
if ($title) { Write-Host "         title:  $title" }
Write-Host "         resume: $resumeCmd"

if ($OpenIn -eq 'app') {
    # OpenAI Codex desktop app: routes threads at codex://threads/<id>
    # (route verified in the app bundle, package OpenAI.Codex).
    Start-Process "codex://threads/$threadId"
    Write-Host "Opened the Codex desktop app on this thread." -ForegroundColor Green
    Write-Host "(Pick the model in the app's own dropdown; terminal fallback above.)"
} elseif ($OpenIn -eq 'vscode') {
    # Deep-link straight into the Codex panel on this thread. The extension's
    # URI handler routes vscode://openai.chatgpt/<path> into its webview router,
    # which serves local threads at /local/<id>.
    Start-Process "vscode://openai.chatgpt/local/$threadId"
    Write-Host "Opened the Codex panel in VS Code on this thread." -ForegroundColor Green
    Write-Host "(Terminal fallback if needed: the resume command above.)"
} elseif ($OpenIn -eq 'terminal') {
    # Resume from the directory the work lives in, so Codex sees the same repo.
    $workDir = & python $queryPy --cwd $threadId
    if ($LASTEXITCODE -ne 0 -or -not $workDir -or -not (Test-Path $workDir)) { $workDir = $env:USERPROFILE }
    $wt = Get-Command wt -ErrorAction SilentlyContinue
    if ($wt) {
        Start-Process wt -ArgumentList (@('new-tab', '-d', "`"$workDir`"", 'powershell', '-NoExit', '-Command', $resumeCmd) -join ' ')
    } else {
        Start-Process cmd -WorkingDirectory $workDir -ArgumentList "/k powershell -NoExit -Command $resumeCmd"
    }
    Write-Host "Launched terminal in $workDir with the resumed Codex session." -ForegroundColor Green
}
exit 0
