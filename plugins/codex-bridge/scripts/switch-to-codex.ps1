# switch-to-codex.ps1 - one-click Claude Code -> Codex switch (desktop launcher).
# (Windows PowerShell 5.1 compatible, ASCII only. Needs NO Claude tokens - works
#  even when Claude Code is rate-limited or closed.)
#
# Shows a small window: pick a recent Claude Code session + a Codex model,
# then transfers the session and opens Windows Terminal resumed into it.
#
#   -ListOnly   headless mode: print the sessions and models that would be shown

param([switch]$ListOnly)
$ErrorActionPreference = 'Stop'
$parityDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$transferPs1 = Join-Path $parityDir 'transfer-to-codex.ps1'
$projects    = Join-Path $env:USERPROFILE '.claude\projects'

# ---------- gather recent Claude sessions ----------
function Get-SessionSnippet($jsonlPath) {
    # First real user-message text in the transcript, trimmed for display
    try {
        foreach ($line in (Get-Content $jsonlPath -TotalCount 40 -Encoding UTF8 -ErrorAction Stop)) {
            try { $obj = $line | ConvertFrom-Json } catch { continue }
            if ($obj.type -ne 'user') { continue }
            $c = $obj.message.content
            $text = $null
            if ($c -is [string]) { $text = $c }
            elseif ($c) {
                $t = @($c) | Where-Object { $_.type -eq 'text' } | Select-Object -First 1
                if ($t) { $text = $t.text }
            }
            if ($text) {
                $text = ($text -replace '\s+', ' ').Trim()
                if ($text.StartsWith('<')) { continue }   # skip system-reminder-style content
                if ($text.Length -gt 70) { $text = $text.Substring(0, 70) + '...' }
                return $text
            }
        }
    } catch {}
    return '(no preview)'
}

$sessions = Get-ChildItem (Join-Path $projects '*\*.jsonl') -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 10 | ForEach-Object {
        $proj = Split-Path -Leaf (Split-Path -Parent $_.FullName)
        [PSCustomObject]@{
            Label = "{0:MM-dd HH:mm}  [{1}]  {2}" -f $_.LastWriteTime, $proj, (Get-SessionSnippet $_.FullName)
            Path  = $_.FullName
        }
    }
if (-not $sessions) { Write-Host "No Claude sessions found under $projects" -ForegroundColor Red; exit 1 }

# ---------- gather Codex models (live, with static fallback) ----------
$models = @()
try {
    $raw = codex debug models 2>$null | Out-String
    $parsed = $raw | ConvertFrom-Json
    $models = @($parsed) | ForEach-Object { $_.id } | Where-Object { $_ -and $_ -notmatch 'auto-review' }
} catch {}
if (-not $models) { $models = @('gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna','gpt-5.5','gpt-5.4','gpt-5.4-mini') }
$efforts = @('(config default)','low','medium','high','xhigh')

if ($ListOnly) {
    Write-Host "=== Sessions ==="; $sessions | ForEach-Object { Write-Host ("  " + $_.Label) }
    Write-Host "=== Models ===";   $models   | ForEach-Object { Write-Host ("  " + $_) }
    exit 0
}

# ---------- picker window ----------
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Switch to Codex'
$form.Size = New-Object System.Drawing.Size(640, 420)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false

$lbl1 = New-Object System.Windows.Forms.Label
$lbl1.Text = 'Claude Code session to transfer:'; $lbl1.Location = '12,12'; $lbl1.AutoSize = $true
$list = New-Object System.Windows.Forms.ListBox
$list.Location = '12,34'; $list.Size = '600,200'
$sessions | ForEach-Object { [void]$list.Items.Add($_.Label) }
$list.SelectedIndex = 0

$lbl2 = New-Object System.Windows.Forms.Label
$lbl2.Text = 'Codex model:'; $lbl2.Location = '12,248'; $lbl2.AutoSize = $true
$combo = New-Object System.Windows.Forms.ComboBox
$combo.Location = '12,270'; $combo.Size = '290,24'; $combo.DropDownStyle = 'DropDownList'
$models | ForEach-Object { [void]$combo.Items.Add($_) }
$combo.SelectedIndex = 0

$lbl3 = New-Object System.Windows.Forms.Label
$lbl3.Text = 'Reasoning effort:'; $lbl3.Location = '322,248'; $lbl3.AutoSize = $true
$combo2 = New-Object System.Windows.Forms.ComboBox
$combo2.Location = '322,270'; $combo2.Size = '290,24'; $combo2.DropDownStyle = 'DropDownList'
$efforts | ForEach-Object { [void]$combo2.Items.Add($_) }
$combo2.SelectedIndex = 0

$lbl4 = New-Object System.Windows.Forms.Label
$lbl4.Text = 'Open in:'; $lbl4.Location = '12,300'; $lbl4.AutoSize = $true
$combo3 = New-Object System.Windows.Forms.ComboBox
$combo3.Location = '75,297'; $combo3.Size = '227,24'; $combo3.DropDownStyle = 'DropDownList'
@('Codex app (desktop)','VS Code (Codex panel)','Terminal (TUI)') | ForEach-Object { [void]$combo3.Items.Add($_) }
$combo3.SelectedIndex = 0
if (-not (Test-Path 'Registry::HKEY_CLASSES_ROOT\codex')) { $combo3.SelectedIndex = 1 }  # app not installed

$ok = New-Object System.Windows.Forms.Button
$ok.Text = 'Transfer and open Codex'; $ok.Location = '12,330'; $ok.Size = '290,36'
$ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancel'; $cancel.Location = '322,330'; $cancel.Size = '290,36'
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.AddRange(@($lbl1,$list,$lbl2,$combo,$lbl3,$combo2,$lbl4,$combo3,$ok,$cancel))
$form.AcceptButton = $ok; $form.CancelButton = $cancel

if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 0 }

$chosen = $sessions[$list.SelectedIndex]
$model  = $combo.SelectedItem
$effort = $combo2.SelectedItem
$openIn = @('app','vscode','terminal')[$combo3.SelectedIndex]
$args = @('-NoProfile','-ExecutionPolicy','Bypass','-File', $transferPs1, '-Source', $chosen.Path, '-Model', $model, '-OpenIn', $openIn)
if ($effort -ne '(config default)') { $args += @('-Effort', $effort) }

# Run the transfer in a visible console so progress/errors are seen
Start-Process powershell -ArgumentList $args
