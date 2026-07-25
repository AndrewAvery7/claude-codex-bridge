---
name: to-codex
description: "Switch the current Claude Code session to Codex - transfers this conversation into a resumable Codex thread and opens the OpenAI Codex desktop app directly on it (VS Code panel or terminal on request), with a clickable model picker. Use when the user types /to-codex, says 'switch to codex', 'transfer to codex', 'move this to codex', 'continue in codex', or is running low on Claude tokens and wants to hand the work to Codex. Optional inline argument: a model shorthand (sol, terra, luna, 5.5, 5.4, mini) to skip the picker."
---

# to-codex — hand this conversation to Codex

Transfers the CURRENT Claude Code session into a Codex thread (via the official
codex-plugin-cc importer) and opens Codex directly on it, on a model the user
picks. Works on Windows, macOS, and Linux.

## Step 0. Locate the engine

```
$ENGINE = <plugin scripts dir>/codex_bridge.py
```

Resolve the scripts directory as `$CLAUDE_PLUGIN_ROOT/scripts` when that variable
is set (plugin installs), otherwise `~/.claude/codex-parity` (manual installs).
The engine is a single cross-platform Python file; call it with `python` (or
`python3` where that is the only name available). If it is missing, STOP and tell
the user the bridge scripts are not installed.

Sanity-check the environment first if anything seems off:
```
python <ENGINE> doctor
```
That prints the resolved codex binary, the importer path, Codex's state DB and
ledger, and which surface `auto` would open.

## Step 1. Find the current session transcript

The transcript is the newest `.jsonl` in this session's project directory:
`~/.claude/projects/<munged-cwd>/`, where munged-cwd is the session's working
directory with `:`, `\`, `/`, and `.` each replaced by `-` (e.g. `C:\` -> `C--`,
`/Users/me/proj` -> `-Users-me-proj`).

Its modification time must be within the last few minutes — the live session file
is written continuously. If the munged-directory guess misses, fall back to the
newest `.jsonl` under any `~/.claude/projects/*/` modified in the last 5 minutes.
If nothing matches, STOP and tell the user rather than transferring a stale
session.

## Step 2. Model choice (clickable)

If the user passed a shorthand, map it and skip the question:
sol -> gpt-5.6-sol, terra -> gpt-5.6-terra, luna -> gpt-5.6-luna,
5.5 -> gpt-5.5, 5.4 -> gpt-5.4, mini -> gpt-5.4-mini.

Otherwise ask with AskUserQuestion (one question, header "Codex model"), offering
the current strong default first, marked "(Recommended)". Refresh the catalog with
`codex debug models` if the list looks stale. Do NOT ask about reasoning effort
unless the user raises it; if they do, add `--effort low|medium|high|xhigh`.

## Step 3. Transfer and open

```
python <ENGINE> transfer --source "<transcript-path>" --model "<model-id>"
```

Run it exactly like that — do NOT pass `--open` unless the user asked for a
specific destination. The default (`auto`) opens the OpenAI Codex desktop app
directly on the imported thread when available, falling back to the VS Code Codex
panel and then a terminal. Explicit choices ONLY when the user asks:
`--open app`, `--open vscode`, `--open terminal`, `--open none` (print only).

NOTE on model: the desktop app and the VS Code panel each use their own model
dropdown — the chosen `--model` applies only to the printed terminal resume
command. Mention this so the user knows to pick the model in the app.

The engine verifies the imported thread in Codex's own state DB rather than
trusting the importer's message, which is unreliable on Windows
(openai/codex-plugin-cc#513). Trust the engine's SUCCESS/ERROR output, not any
"did not record an imported thread" text from the importer. If the transcript
has not changed since a previous transfer, Codex dedupes it and the engine
reuses the existing thread — it says so when that happens.

## Step 4. Report

Tell the user: the thread id, WHERE it opened (quote what the engine printed —
"Opened the Codex desktop app…" / "Opened the Codex panel in VS Code…"), and that
the model is chosen in that surface's own dropdown. Print the terminal resume
command from the output in a bash-fenced block as a fallback. Remind them the
transfer is a snapshot: anything said in Claude afterwards is not in the Codex
thread.

## Notes

- Requires the Codex CLI (`npm i -g @openai/codex`), Node 18.18+, Python 3.9+,
  and codex-plugin-cc (`claude plugin marketplace add openai/codex-plugin-cc`
  then `claude plugin install codex@openai-codex`).
- The transcript must live under `~/.claude/projects` — an importer requirement.
- No-Claude-tokens alternative: `python <ENGINE> pick` gives a terminal session
  picker. On Windows there is also a native GUI launcher
  (`switch-to-codex.ps1`), which the "Switch to Codex" desktop shortcut uses.
- Parity sync (install a flattened AGENTS.md, sync skills to `~/.agents/skills`):
  `python <ENGINE> sync --agents-md <path>`.
