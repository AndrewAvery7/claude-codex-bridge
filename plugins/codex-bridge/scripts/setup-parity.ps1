# setup-parity.ps1 - keep Codex in parity with your Claude Code workbench.
# (Windows PowerShell 5.1 compatible, ASCII only. Idempotent - safe to re-run.)
#
# What it does:
#   1. Installs your flattened AGENTS.md into ~/.codex/AGENTS.md
#      (backup only when content actually changed; aborts over Codex's 32 KiB cap)
#   2. Syncs ~/.claude/skills -> ~/.agents/skills with a hash manifest:
#        new Claude-side skill              -> copied over
#        copy provably unmodified since sync -> refreshed when Claude side changes
#        copy locally adapted for Codex      -> NEVER overwritten, listed for review
#   3. Guards against skills appearing in ~/.codex/skills (Codex scans BOTH
#      ~/.agents/skills and ~/.codex/skills - a skill in both is listed twice)
#   4. Optional sanity checks for CLIs your skills depend on
#
# Why ~/.agents/skills and not ~/.codex/skills: Codex reads both roots. Keeping
# user skills only in ~/.agents/skills (the cross-tool Agent Skills location)
# avoids double-listing AND serves every other agent that reads the same root.
#
# When to re-run: after editing the AGENTS.md source next to this script, or
# after adding/updating skills in ~/.claude/skills.

param(
    # CLIs your skills shell out to; each is checked to resolve on PATH.
    [string[]]$SanityCLIs = @()
)
$ErrorActionPreference = 'Stop'
$claudeSkills = Join-Path $env:USERPROFILE '.claude\skills'
$agentsSkills = Join-Path $env:USERPROFILE '.agents\skills'
$codexSkills  = Join-Path $env:USERPROFILE '.codex\skills'
$codexAgents  = Join-Path $env:USERPROFILE '.codex\AGENTS.md'
$newAgents    = Join-Path $PSScriptRoot 'AGENTS.md'   # your flattened instructions (create from AGENTS.md.example)
$manifestPath = Join-Path $PSScriptRoot 'sync-manifest.json'

function Get-SkillHash($dir) {
    # Hash SKILL.md only - the instruction file is what drifts on adaptation
    $f = Join-Path $dir 'SKILL.md'
    if (Test-Path $f) { (Get-FileHash $f -Algorithm MD5).Hash } else { $null }
}

Write-Host "=== 1. AGENTS.md ===" -ForegroundColor Cyan
if (-not (Test-Path $newAgents)) {
    Write-Host "No AGENTS.md found next to this kit - skipping instruction install." -ForegroundColor Yellow
    Write-Host "(Create one from AGENTS.md.example, then re-run.)"
} else {
    $size = (Get-Item $newAgents).Length
    if ($size -gt 32768) {
        Write-Host "ABORT: AGENTS.md is $size bytes (> Codex 32768 default cap). Trim it or raise project_doc_max_bytes." -ForegroundColor Red
        exit 1
    }
    if (Test-Path $codexAgents) {
        $curHash = (Get-FileHash $codexAgents -Algorithm MD5).Hash
        $newHash = (Get-FileHash $newAgents  -Algorithm MD5).Hash
        if ($curHash -eq $newHash) {
            Write-Host "AGENTS.md unchanged - no backup, no install needed ($size bytes)"
        } else {
            $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
            Copy-Item $codexAgents "$codexAgents.bak-$stamp"
            Write-Host "Backed up existing AGENTS.md -> AGENTS.md.bak-$stamp"
            Copy-Item $newAgents $codexAgents -Force
            Write-Host "Installed AGENTS.md ($size bytes; cap 32768)"
        }
    } else {
        Copy-Item $newAgents $codexAgents -Force
        Write-Host "Installed AGENTS.md ($size bytes; cap 32768)"
    }
}

Write-Host "`n=== 2. Skills sync: ~/.claude/skills -> ~/.agents/skills ===" -ForegroundColor Cyan
if (-not (Test-Path $agentsSkills)) { New-Item -ItemType Directory -Path $agentsSkills | Out-Null }
$manifest = @{}
if (Test-Path $manifestPath) {
    (Get-Content $manifestPath -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $manifest[$_.Name] = $_.Value }
}

# Skills that must NOT sync into Codex (wrong-direction or Claude-only UI).
# to-codex: "switch this session to Codex" only makes sense FROM Claude Code.
$skipSkills = @('to-codex')

$copied = 0; $refreshed = 0; $adapted = @(); $unchanged = 0; $skipped = 0
Get-ChildItem $claudeSkills -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $name = $_.Name
    if ($skipSkills -contains $name) { $script:skipped++; return }
    $src  = $_.FullName
    $dst  = Join-Path $agentsSkills $name
    $srcHash = Get-SkillHash $src
    if (-not (Test-Path $dst)) {
        Copy-Item $src $dst -Recurse
        $manifest[$name] = Get-SkillHash $dst
        $script:copied++
        Write-Host "  copied NEW skill: $name"
        return
    }
    $dstHash = Get-SkillHash $dst
    if ($dstHash -eq $srcHash) { $script:unchanged++; $manifest[$name] = $dstHash; return }
    if (-not ($manifest.ContainsKey($name) -and $manifest[$name] -eq $dstHash)) {
        # Copy differs from Claude side AND we cannot prove it is an unmodified
        # sync product. Treat as a deliberate Codex adaptation and leave it
        # alone. Never guess in this branch - refreshing here destroys
        # hand-adapted skills.
        $script:adapted += $name
        return
    }
    # Manifest proves the copy is exactly what we last synced (unmodified) and
    # the Claude side has since changed -> safe to refresh.
    Remove-Item $dst -Recurse -Force -Confirm:$false
    Copy-Item $src $dst -Recurse
    $manifest[$name] = Get-SkillHash $dst
    $script:refreshed++
    Write-Host "  refreshed from Claude side: $name"
}
$manifest | ConvertTo-Json | Out-File $manifestPath -Encoding utf8
Write-Host "New: $copied  Refreshed: $refreshed  Unchanged: $unchanged  Skipped (Claude-only): $skipped"
if ($adapted.Count -gt 0) {
    Write-Host "Codex-adapted copies left alone (review manually if the Claude side changed):" -ForegroundColor Yellow
    $adapted | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
}

Write-Host "`n=== 3. Guard: no duplicate skill root in ~/.codex/skills ===" -ForegroundColor Cyan
$stray = Get-ChildItem $codexSkills -Directory -ErrorAction SilentlyContinue | Where-Object Name -ne '.system'
if ($stray) {
    Write-Host "WARN: entries in ~/.codex/skills will DOUBLE-LIST in Codex's picker:" -ForegroundColor Yellow
    $stray | ForEach-Object { Write-Host "  $($_.Name)" -ForegroundColor Yellow }
} else {
    Write-Host "  OK  only .system present - no duplicates possible"
}

if ($SanityCLIs.Count -gt 0) {
    Write-Host "`n=== 4. Sanity checks ===" -ForegroundColor Cyan
    foreach ($cli in $SanityCLIs) {
        try { $src = (Get-Command $cli -ErrorAction Stop).Source; Write-Host "  OK  $cli -> $src" }
        catch { Write-Host "  FAIL $cli not on PATH" -ForegroundColor Red }
    }
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
Write-Host "Open Codex and type / or `$ in the chat panel: each skill should be listed ONCE."
