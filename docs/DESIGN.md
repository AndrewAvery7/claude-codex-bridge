# Design & reasoning

This document records *why* the kit is built the way it is. Every decision below
came out of a diagnosed failure on a real Windows machine, not speculation. The
verification evidence for each claim is in [TESTING.md](TESTING.md).

## The problem being solved

Claude Code and OpenAI Codex are both excellent agentic coding tools, and both
meter usage. When a Claude Code session runs low on tokens — or you simply want
a second model's judgment — the naive hand-off loses three things at once:

1. **The conversation** — everything discussed so far
2. **The working context** — skills, standing instructions, memory
3. **The moment** — you're mid-task; friction here is expensive

OpenAI's official [codex-plugin-cc](https://github.com/openai/codex-plugin-cc)
solves (1) via `/codex:transfer`, which drives Codex's external-agent session
importer. This kit exists because on Windows the official path breaks in
practice, and because (2) and (3) are out of its scope entirely.

## Discovery 1 — the transfer "fails" on Windows, except it doesn't

`/codex:transfer` on Windows reports:

> Codex reported that the Claude import completed, but did not record an
> imported thread.

This is [issue #513](https://github.com/openai/codex-plugin-cc/issues/513) — a
**false negative**. The import succeeds; the plugin's success check fails.
Codex's import ledger (`~/.codex/external_agent_session_imports.json`) records
source paths with Windows extended-length prefixes (`\\?\C:\...`), and the
plugin's path comparison doesn't normalize them.

**Design consequence:** never trust the plugin's message. After invoking the
importer, the engine verifies the outcome independently:

- snapshot `MAX(created_at)` from the `threads` table in `~/.codex/state_5.sqlite`
  (opened read-only, always)
- run the import
- poll for a thread with `created_at` greater than the snapshot

The thread id, title, and working directory come from the database — the same
source of truth the Codex UI reads.

## Discovery 2 — Codex dedupes unchanged re-imports

Re-transferring a session whose content hasn't changed creates **no new
thread**: Codex hashes transcript content (`content_sha256` in the ledger) and
skips duplicates. Naive detection then times out and looks like a failure.

**Design consequence:** on timeout, the engine looks the source path up in the
import ledger (normalizing the `\\?\` prefix) and **reuses the previously
imported thread**, saying so explicitly. Unchanged → same thread; changed →
new thread. Both paths verified.

## Discovery 3 — the app-container PATH trap

Installing the Codex CLI with `npm i -g` from *inside* a packaged (MSIX)
desktop app — such as the Claude Code desktop app — lands the files in the
container's virtualized file system
(`%LOCALAPPDATA%\Packages\<app>\LocalCache\Roaming\npm\...`). Inside the
container, `codex` resolves fine. A terminal spawned for the user is **outside**
the container: for it, neither the PATH entry nor (depending on virtualization)
the files exist. Result: `codex : The term 'codex' is not recognized...`

**Design consequence:** never emit a bare `codex` in a command another shell
will run. `codex_command()` prefers the **standalone vendored
`codex.exe`** inside the container's `LocalCache` backing store — which is a
real directory on disk, readable by every process, and needs no Node — and
embeds the absolute path. A genuinely global install (done from a normal
terminal) is picked up ahead of the fallback chain.

## Discovery 4 — where a transferred thread can open (deep links)

Three destinations, two of them via URL protocols found by inspecting the
respective app bundles:

| Destination | Mechanism | How it was found |
|---|---|---|
| Codex desktop app | `codex://threads/<thread-id>` | The `OpenAI.Codex` package manifest declares the `codex` protocol; the app bundle contains `codex://threads/` route strings |
| VS Code Codex panel | `vscode://openai.chatgpt/local/<thread-id>` | The extension's `handleUri` forwards the URI path into its webview router; the router serves local threads at `/local/<id>` |
| Terminal TUI | `codex resume <id> [-m model]` from the thread's working directory (read from the state DB) | Documented CLI |

The engine's `--open auto` prefers the desktop app when its protocol is
registered, then VS Code, then the terminal.

**Model selection nuance:** `-m` is honored by the CLI per invocation. The
desktop app and the VS Code panel each use their own in-UI model selector —
a URL can't carry a model. The kit applies the chosen model to the terminal
command and tells the user to use the dropdown otherwise. Honest limitation,
stated rather than hidden.

## Discovery 5 — Codex reads TWO skill roots (the double-listing bug you'll hit)

Codex discovers skills from both `~/.codex/skills` **and** `~/.agents/skills`
(the cross-tool [Agent Skills](https://agentskills.io) root). Put your skills
in both — for example by junctioning your Claude skills into `~/.codex/skills`
while an import previously populated `~/.agents/skills` — and every skill is
listed **twice** in the picker.

**Design consequence:** `~/.agents/skills` is the single user-skill root
(it also serves every other standard-compliant agent); `~/.codex/skills` is
left to Codex's own `.system` bundle, and the sync script warns if anything
else ever appears there.

## Discovery 6 — adapted skill copies must survive syncs

A skill written for Claude Code may deserve Codex-specific adaptation (e.g.
"dispatch Codex subagents" instead of "Claude subagents"; "AGENTS.md" instead
of "CLAUDE.md"). Those hand-adapted copies live in `~/.agents/skills` — and a
naive "sync from Claude" overwrites them. This kit learned that the hard way
during its own development (six adapted skills were clobbered by a first-run
sync and had to be re-derived line by line).

**Design consequence:** manifest-based three-way sync. `sync-manifest.json`
records the hash of each skill at last sync. On the next run:

- destination missing → copy (new skill)
- destination == source → nothing to do
- destination == manifest hash (provably unmodified) and source changed → refresh
- **anything else → never touch it**; list it for manual review

The rule is asymmetric on purpose: when ancestry can't be proven, the script
refuses to guess.

## Instructions: why AGENTS.md is fully flattened

Claude Code's `CLAUDE.md` supports `@file` includes; **Codex's AGENTS.md does
not** (open feature request:
[openai/codex#17401](https://github.com/openai/codex/issues/17401)). An
`@~/.codex/manual.md` line in AGENTS.md is inert text — your instructions
silently don't load, which is worse than failing loudly. So the kit's
convention is a single flattened AGENTS.md with everything inline, kept under
Codex's default 32,768-byte cap (the installer aborts if you exceed it, rather
than letting Codex truncate silently). See `AGENTS.md.example` for a complete
real-world example.

## The desktop launcher

`switch-to-codex.ps1` exists for the day Claude Code can't help you launch the
hand-off — you're rate-limited or the app is closed. It enumerates recent
Claude sessions from `~/.claude/projects` (with first-message previews),
offers model / effort / destination choices in a small native dialog, and runs
the same engine. Zero Claude tokens involved.

To get the one-click desktop button, create a shortcut:

```powershell
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\Switch to Codex.lnk")
$lnk.TargetPath = 'powershell.exe'
$lnk.Arguments  = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$env:USERPROFILE\.claude\codex-parity\switch-to-codex.ps1`""
$lnk.IconLocation = 'shell32.dll,137'
$lnk.Save()
```

## Engineering notes that will save you a day

- **PowerShell 5.1 + BOM-less UTF-8 = mojibake.** A `.ps1` saved as UTF-8
  without a BOM is read as ANSI by PS 5.1; an em-dash becomes a stray smart
  quote and the parser explodes mid-string. All scripts here are pure ASCII.
- **PS 5.1 + `$ErrorActionPreference='Stop'` + native stderr redirection**
  turns harmless stderr (Node deprecation warnings) into spurious throws.
  The engine relaxes EAP around the importer call and captures output for
  display only on real failure.
- **`Remove-Item` vs junctions:** deleting a directory junction with recursion
  can traverse into the target. The safe pattern is
  `[System.IO.Directory]::Delete(path, $false)` gated on the entry actually
  having the ReparsePoint attribute.
- **Snapshots, not live links:** a transferred thread does not follow the
  Claude session afterward. The kit says this on every transfer.

## Going cross-platform (v1.2.0)

The original engine was PowerShell, because the bug it works around is a Windows
bug. That capped the addressable audience: the AI-coding-tool crowd skews heavily
macOS, and a Windows-only tool is invisible to most of it.

Almost everything load-bearing was already portable — the importer is Node, the
state store is SQLite, the ledger is JSON, and the deep links are URL protocols.
Only the shell around them was Windows-specific. So the engine became a single
Python file with the OS differences isolated in four functions:

| Function | Windows | macOS | Linux |
|---|---|---|---|
| `normalize_ledger_path` | strip the extended-length prefix, case-fold | identity | identity |
| `codex_command` | prefer the vendored exe in the app container's LocalCache | `which`, then common npm/brew locations | same as macOS |
| `open_url` | `os.startfile` | `open` | `xdg-open` |
| `launch_terminal` | Windows Terminal, else `cmd` | AppleScript to Terminal.app | `x-terminal-emulator`, gnome-terminal, konsole, xfce4-terminal, xterm |

Because those are pure or thinly-wrapped functions, the Windows path rules are
testable **on Linux** by reloading the module with `sys.platform` patched — which
is exactly what the CI matrix does. That gives real coverage of the
extended-length-prefix logic on machines that have never seen a Windows path.

### One bug the port surfaced

Porting exposed a defect the PowerShell version had been getting away with by
accident. The importer runs its **own** `codex` availability check, so it is not
enough for the engine to know where the binary is — the child process has to be
able to find it too. With an `npm -g` install inside a packaged app, it cannot,
and the importer aborts with "Codex CLI is not installed" on what would otherwise
be a successful fresh import. The engine now prepends the resolved binary's
directory to the importer's `PATH`.

The general lesson, which is the same one behind the false-failure bug: knowing a
fact yourself is not the same as the process you delegate to knowing it.

### What is verified, where

Stated plainly because the distinction matters:

- **Windows:** full transfer flow verified end-to-end, both the fresh-import and
  the dedupe-reuse paths, plus `doctor`, the GUI launcher, and parity sync.
- **macOS / Linux:** implemented, and the test suite plus CLI surface run green in
  CI on both. Not yet confirmed against a real Codex install on those platforms —
  specifically the protocol handler (`open` / `xdg-open`) and the terminal
  launchers. Reports either way are genuinely useful.

The `codex resume <id>` command printed on every transfer is the fallback that
works regardless of platform, which is why it is always printed rather than only
shown on failure.
