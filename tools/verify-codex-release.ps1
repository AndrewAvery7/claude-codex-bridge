# verify-codex-release.ps1 - re-run the docs/TESTING.md verification against the
# Codex that is installed right now, and print a report to paste into the
# tracking issue.
#
# The version table in docs/TESTING.md goes stale every few Codex releases, and
# re-establishing it by hand is enough work that it does not happen. This script
# collects the same evidence in one run.
#
# Read-only by default: it reports versions, resolves the binary the way the
# engine does, inspects the state DB schema, and checks the deep-link handler
# registration. It writes nothing to Codex state.
#
# -RunTransfers additionally performs the live scenarios (T1, T3, T4). Those DO
# create threads in your Codex install - that is what makes them a real test -
# so they are opt-in rather than the default.
#
# (Windows PowerShell 5.1 compatible, ASCII only.)
#
#   .\tools\verify-codex-release.ps1
#   .\tools\verify-codex-release.ps1 -RunTransfers
#   .\tools\verify-codex-release.ps1 -RunTransfers -Source C:\path\to\session.jsonl

param(
    [switch]$RunTransfers,
    [string]$Source = ''
)

$ErrorActionPreference = 'Continue'
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$engine   = Join-Path $repoRoot 'plugins\codex-bridge\scripts\codex_bridge.py'
$query    = Join-Path $repoRoot 'plugins\codex-bridge\scripts\codex-thread-query.py'
$report   = New-Object System.Collections.ArrayList

function Add-Line {
    param([string]$Text)
    [void]$report.Add($Text)
    Write-Host $Text
}

function Add-Row {
    param([string]$Name, [string]$Value)
    Add-Line ("| {0} | {1} |" -f $Name, $Value)
}

function Add-Row2 {
    param([string]$Name, [string]$Expected, [string]$Result)
    Add-Line ("| {0} | {1} | {2} |" -f $Name, $Expected, $Result)
}

$script:failCount = 0
$script:notExercised = 0

function Test-Expect {
    param([bool]$Ok)
    if ($Ok) { return 'PASS' }
    $script:failCount = $script:failCount + 1
    return 'FAIL'
}

function Skip-Scenario {
    param([string]$Why)
    $script:notExercised = $script:notExercised + 1
    return ('NOT EXERCISED - ' + $Why)
}

function Get-Python {
    foreach ($candidate in @('python', 'python3', 'py')) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    return $null
}

$python = Get-Python
if (-not $python) {
    Write-Error 'No python on PATH. The engine needs Python 3.9+.'
    exit 1
}

# This script drives the engine, so it only works from inside a clone. Say so
# plainly: without this check a missing engine surfaces further down as
# "Codex CLI NOT FOUND", which blames Codex for a checkout problem.
if (-not (Test-Path $engine)) {
    Write-Error ("Could not find the engine at {0}." -f $engine)
    Write-Host  ''
    Write-Host  'Run this from inside a clone of the repository:'
    Write-Host  '    git clone https://github.com/AndrewAvery7/claude-codex-bridge'
    Write-Host  '    cd claude-codex-bridge'
    Write-Host  '    .\tools\verify-codex-release.ps1'
    exit 1
}

Add-Line ('## Verification run - {0}' -f (Get-Date -Format 'yyyy-MM-dd'))
Add-Line ''
Add-Line ('Machine: {0}, PowerShell {1}' -f [System.Environment]::OSVersion.VersionString, $PSVersionTable.PSVersion)
Add-Line ('Repo: {0}' -f $repoRoot)
Add-Line ''
Add-Line '### Versions'
Add-Line ''
Add-Line '| Component | Version |'
Add-Line '|---|---|'

# Resolve the binary the same way the engine does, rather than trusting PATH -
# this is scenario T5, and on Windows a bare `codex` can be an npm shim that
# only resolves inside a packaged app container.
$codexPath = & $python $engine doctor 2>$null | Select-String -Pattern '^codex binary\s+(.+)$' | ForEach-Object { $_.Matches[0].Groups[1].Value.Trim() }
if ($codexPath -and $codexPath -ne 'NOT FOUND' -and (Test-Path $codexPath)) {
    $codexVersion = & $codexPath --version 2>&1 | Select-Object -First 1
    Add-Row 'Codex CLI' ('{0} (resolved to {1})' -f $codexVersion, $codexPath)
} else {
    Add-Row 'Codex CLI' 'NOT FOUND - the engine could not resolve a binary'
}

$pluginJson = Get-ChildItem (Join-Path $env:USERPROFILE '.claude\plugins\cache\openai-codex\codex\*\.claude-plugin\plugin.json') -ErrorAction SilentlyContinue |
    Sort-Object FullName | Select-Object -Last 1
if ($pluginJson) {
    $pluginVersion = (Get-Content $pluginJson.FullName -Raw | ConvertFrom-Json).version
    Add-Row 'codex-plugin-cc' $pluginVersion
} else {
    Add-Row 'codex-plugin-cc' 'NOT FOUND - install it with: claude plugin install codex@openai-codex'
}

$code = Get-Command code -ErrorAction SilentlyContinue
if ($code) {
    $ext = & code --list-extensions --show-versions 2>$null | Select-String -Pattern '^openai\.chatgpt@(.+)$'
    if ($ext) { Add-Row 'VS Code extension (openai.chatgpt)' $ext.Matches[0].Groups[1].Value }
    else { Add-Row 'VS Code extension (openai.chatgpt)' 'not installed' }
} else {
    Add-Row 'VS Code extension (openai.chatgpt)' 'code not on PATH'
}

$appx = Get-AppxPackage -Name '*Codex*' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($appx) { Add-Row 'Codex desktop app' ('{0} {1}' -f $appx.Name, $appx.Version) }
else { Add-Row 'Codex desktop app' 'not installed (or not an MSIX install)' }

# ---------------------------------------------------------------------------
# Internals the engine reads - the schema-drift risk docs/TESTING.md warns about
# ---------------------------------------------------------------------------

Add-Line ''
Add-Line '### Internals the engine reads'
Add-Line ''
Add-Line '| Internal | Status |'
Add-Line '|---|---|'

$codexHome = $env:CODEX_HOME
if (-not $codexHome) { $codexHome = Join-Path $env:USERPROFILE '.codex' }
$stateDb = Join-Path $codexHome 'state_5.sqlite'
$ledger  = Join-Path $codexHome 'external_agent_session_imports.json'

if (Test-Path $stateDb) {
    # Read-only, and the WAL matters: a live state DB keeps recent writes in
    # state_5.sqlite-wal, so anything that copies the .sqlite alone sees nothing.
    $schemaProbe = @'
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
cols = [r[1] for r in con.execute("PRAGMA table_info(threads)")]
need = ["id", "created_at", "cwd", "title"]
missing = [c for c in need if c not in cols]
print("columns=%d missing=%s rows=%d" % (
    len(cols), ",".join(missing) if missing else "none",
    con.execute("SELECT COUNT(*) FROM threads").fetchone()[0]))
'@
    $schemaFile = Join-Path $env:TEMP 'codex-schema-probe.py'
    Set-Content -Path $schemaFile -Value $schemaProbe -Encoding ASCII
    $schema = & $python $schemaFile $stateDb 2>&1
    Add-Row 'state_5.sqlite threads table' $schema
    Remove-Item $schemaFile -ErrorAction SilentlyContinue
} else {
    Add-Row 'state_5.sqlite' 'MISSING - Codex has not created its state DB here'
}

if (Test-Path $ledger) {
    $records = (Get-Content $ledger -Raw | ConvertFrom-Json).records
    Add-Row 'external_agent_session_imports.json' ('present, {0} record(s)' -f @($records).Count)
} else {
    Add-Row 'external_agent_session_imports.json' 'MISSING - no import has been recorded yet'
}

# The codex:// handler is what O1 depends on; HKCR\codex is where it registers.
$handler = Get-Item 'Registry::HKEY_CLASSES_ROOT\codex' -ErrorAction SilentlyContinue
if ($handler) { Add-Row 'codex:// protocol handler' 'registered' }
else { Add-Row 'codex:// protocol handler' 'NOT registered - the app deep link will not open' }

# ---------------------------------------------------------------------------
# Live scenarios - these create threads, so they are opt-in
# ---------------------------------------------------------------------------

if ($RunTransfers) {
    Add-Line ''
    Add-Line '### Live transfer scenarios'
    Add-Line ''

    # Transcripts Codex has already imported. One of these can only ever produce
    # a dedupe hit, never the fresh import T1 is supposed to be testing.
    $imported = @{}
    if (Test-Path $ledger) {
        foreach ($rec in @((Get-Content $ledger -Raw | ConvertFrom-Json).records)) {
            $sp = [string]$rec.source_path
            if ($sp) {
                if ($sp.StartsWith('\\?\UNC\')) { $sp = '\\' + $sp.Substring(8) }
                elseif ($sp.StartsWith('\\?\')) { $sp = $sp.Substring(4) }
                $imported[$sp.ToLower()] = $true
            }
        }
    }

    if (-not $Source) {
        # Deliberately NOT the newest transcript. The newest one is usually the
        # session you are sitting in, and Claude Code keeps appending to it - so
        # its content hash moves between runs and T3 can never test dedupe.
        $all = Get-ChildItem (Join-Path $env:USERPROFILE '.claude\projects\*\*.jsonl') -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending
        # Only look at recent transcripts. Searching the whole history for one
        # Codex has never imported walks back into transcripts old enough to
        # predate format changes, or large enough to be a stress test rather
        # than a smoke test - neither tells you anything about this release.
        $recent = @($all | Select-Object -First 10)
        $settled = @($recent | Where-Object {
            $_.LastWriteTime -lt (Get-Date).AddMinutes(-5) -and $_.Length -lt 25MB
        })
        # Prefer one Codex has never seen, so T1 is a real first import.
        $never = $settled | Where-Object { -not $imported.ContainsKey($_.FullName.ToLower()) } | Select-Object -First 1
        if ($never) {
            $Source = $never.FullName
        } elseif ($settled.Count -gt 0) {
            $Source = $settled[0].FullName
        } elseif ($all) {
            $Source = $all[0].FullName
            Add-Line '_No transcript has been idle for 5 minutes; using the newest one. If it is still being written, T3 cannot test dedupe._'
            Add-Line ''
        }
    }
    $expectFresh = $false
    if ($Source) { $expectFresh = -not $imported.ContainsKey($Source.ToLower()) }
    if (-not $Source) {
        Add-Line 'No transcript found under ~/.claude/projects - cannot run T1/T3/T4.'
    } else {
        Add-Line ('Source: `{0}`' -f (Split-Path -Leaf $Source))
        if ($expectFresh) {
            Add-Line 'Not present in Codex import ledger, so T1 is a genuine first import.'
        } else {
            Add-Line 'Already in Codex import ledger, so T1 can only dedupe - it cannot test a fresh import.'
        }
        $hashBefore = (Get-FileHash $Source -Algorithm SHA256).Hash
        Add-Line ''
        Add-Line '```'

        # T1: fresh import. --open none keeps the run headless.
        Add-Line '--- T1 first transfer ---'
        $t1 = & $python $engine transfer --source $Source --open none 2>&1
        $t1 | ForEach-Object { Add-Line $_ }

        # T3: the dedupe case. Codex keys dedupe on the content hash, so this
        # only tests anything if the transcript really did not move. Check that
        # rather than asserting it in a heading.
        $hashAfter = (Get-FileHash $Source -Algorithm SHA256).Hash
        Add-Line ''
        if ($hashBefore -eq $hashAfter) {
            Add-Line '--- T3 re-transfer, source verified unchanged ---'
            $t3 = & $python $engine transfer --source $Source --open none 2>&1
            $t3 | ForEach-Object { Add-Line $_ }
        } else {
            $t3 = $null
            Add-Line '--- T3 SKIPPED: the transcript changed while T1 ran ---'
            Add-Line ("    before: {0}" -f $hashBefore)
            Add-Line ("    after:  {0}" -f $hashAfter)
            Add-Line '    Codex dedupes on content, so a moving transcript cannot exercise it.'
        }

        # T4: the resume command must carry the model and effort flags through.
        Add-Line ''
        Add-Line '--- T4 model and effort flags ---'
        $t4 = & $python $engine transfer --source $Source --open none --model gpt-5.6-luna --effort high 2>&1
        $t4 | ForEach-Object { Add-Line $_ }
        Add-Line '```'

        # Check the recorded expectations instead of leaving them to the eye.
        Add-Line ''
        Add-Line '| Scenario | Expected | Result |'
        Add-Line '|---|---|---|'
        $t1Text = ($t1 | Out-String)
        $t1Resolved = ($t1Text -match 'SUCCESS\s+thread:')
        $t1Reused = ($t1Text -match 'reusing its thread')
        Add-Row2 'T0 engine resolves a thread' 'SUCCESS with a thread id' (Test-Expect $t1Resolved)
        if ($expectFresh) {
            Add-Row2 'T1 fresh import' 'a new thread, not a ledger reuse' (Test-Expect ($t1Resolved -and (-not $t1Reused)))
        } else {
            Add-Row2 'T1 fresh import' 'a new thread, not a ledger reuse' (Skip-Scenario 'source already in the ledger')
        }
        if ($null -eq $t3) {
            Add-Row2 'T3 dedupe' 'reuses the existing thread' (Skip-Scenario 'source changed during T1')
        } else {
            $t3Text = ($t3 | Out-String)
            Add-Row2 'T3 dedupe' 'reuses the existing thread' (Test-Expect ($t3Text -match 'reusing its thread'))
        }
        $t4Text = ($t4 | Out-String)
        $t4ok = ($t4Text -match '-m gpt-5\.6-luna') -and ($t4Text -match 'model_reasoning_effort')
        Add-Row2 'T4 model and effort flags' 'both rendered into the resume command' (Test-Expect $t4ok)

        # T6: the thread's original working directory, prefix stripped.
        $threadId = $t1 | Select-String -Pattern 'SUCCESS\s+thread:\s+(\S+)' | ForEach-Object { $_.Matches[0].Groups[1].Value }
        if ($threadId) {
            Add-Line ''
            Add-Line ('T6 thread cwd: `{0}`' -f (& $python $query --cwd $threadId 2>&1))
            Add-Line ''
            Add-Line 'O1/O2 need your eyes - these open the app and the VS Code panel:'
            Add-Line ('    Start-Process "codex://threads/{0}"' -f $threadId)
            Add-Line ('    Start-Process "vscode://openai.chatgpt/local/{0}"' -f $threadId)
        }
    }
} else {
    Add-Line ''
    Add-Line '_Live transfer scenarios skipped. Re-run with `-RunTransfers` to perform T1/T3/T4 - they create threads in your Codex install._'
}

$out = Join-Path $repoRoot 'verification-report.md'
Set-Content -Path $out -Value ($report -join "`r`n") -Encoding ASCII
Write-Host ''
Write-Host ('Report written to {0} - paste it into the tracking issue.' -f $out)
if ($script:notExercised -gt 0) {
    Write-Host ('{0} scenario(s) could not be exercised - see the table.' -f $script:notExercised)
}
if ($script:failCount -gt 0) {
    # Exit non-zero so a failed verification cannot be mistaken for a clean run,
    # by a person skimming or by anything that checks the exit code.
    Write-Host ('{0} scenario(s) FAILED.' -f $script:failCount)
    exit 1
}
