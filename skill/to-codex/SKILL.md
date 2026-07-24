---
name: to-codex
description: "Switch the current Claude Code session to Codex - transfers this conversation into a resumable Codex thread and opens the OpenAI Codex desktop app directly on it (VS Code panel or terminal TUI on request), with a clickable model picker. Use when the user types /to-codex, says 'switch to codex', 'transfer to codex', 'move this to codex', 'continue in codex', or is running low on Claude tokens and wants to hand the work to Codex. Optional inline argument: a model shorthand (sol, terra, luna, 5.5, 5.4, mini) to skip the picker."
---

# to-codex — hand this conversation to Codex

Transfers the CURRENT Claude Code session into a Codex thread (via the official
codex-plugin-cc importer) and opens Codex directly on it, on a model the user
picks. Requires the claude-codex-bridge scripts installed at
`~/.claude/codex-parity/` (see the repo README).

## Steps

### 1. Locate the current session transcript
The transcript is the newest `.jsonl` in this session's project directory:
`~/.claude/projects/<munged-cwd>/` where munged-cwd = the session's working
directory with `:`, `\`, `/`, and `.` each replaced by `-` (e.g. `C:\` -> `C--`).

```powershell
Get-ChildItem "$env:USERPROFILE\.claude\projects\<munged-cwd>\*.jsonl" | Sort-Object LastWriteTime | Select-Object -Last 1
```

Sanity-check: its LastWriteTime must be within the last few minutes (the live
session file is written continuously). If the munged directory guess misses,
fall back to the newest `.jsonl` under all of `~/.claude/projects\*\` modified
in the last 5 minutes. If nothing matches, STOP and tell the user — do not
transfer a stale session silently.

### 2. Model choice (clickable)
If the user passed a model shorthand argument, map it and skip the question:
sol -> gpt-5.6-sol, terra -> gpt-5.6-terra, luna -> gpt-5.6-luna,
5.5 -> gpt-5.5, 5.4 -> gpt-5.4, mini -> gpt-5.4-mini.

Otherwise ask with AskUserQuestion (one question, header "Codex model"),
offering the current strong default first, marked "(Recommended)". Refresh the
catalog with `codex debug models` if these look stale. Do NOT ask about
reasoning effort unless the user raises it; if they do, pass
`-Effort low|medium|high|xhigh`.

### 3. Transfer and open
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\codex-parity\transfer-to-codex.ps1" -Source "<transcript-path>" -Model "<model-id>"
```
Run it exactly like that — do NOT pass `-OpenIn` unless the user asked for a
specific destination. The default (`auto`) opens the OpenAI Codex desktop app
directly on the imported thread when installed, falling back to the VS Code
Codex panel and then the terminal. Explicit choices ONLY when the user asks:
`-OpenIn vscode`, `-OpenIn terminal` (TUI), `-OpenIn none` (print only).
NOTE on model: the desktop app and VS Code panel each use their own model
dropdown — the chosen -Model applies only to the printed terminal resume
command; in app/panel the user picks the model from the dropdown (mention this).
The script imports the session and detects the new thread in Codex's state DB
(the plugin's own success message is unreliable on Windows — issue #513 — the
script works around it; trust the script's SUCCESS/ERROR, not the plugin text).

### 4. Report
Tell the user: the thread id, WHERE it opened — report what the script printed
("Opened the Codex desktop app..." / "Opened the Codex panel in VS Code...") and
remind them to pick the model from that surface's own dropdown — and print the
terminal fallback command from the script output in a bash-fenced block. Remind
them the transfer is a snapshot — anything said in Claude after the transfer is
not in the Codex thread.

## Notes
- Requires: Codex CLI (`npm i -g @openai/codex` from a regular terminal),
  codex-plugin-cc (`claude plugin marketplace add openai/codex-plugin-cc` +
  `claude plugin install codex@openai-codex`), and the bridge scripts at
  `~/.claude/codex-parity/`.
- The transcript must live under `~/.claude/projects` (importer requirement).
- Desktop alternative when Claude Code is out of tokens: a shortcut to
  `~/.claude/codex-parity/switch-to-codex.ps1` (session picker; no Claude
  tokens needed).
