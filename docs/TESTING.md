# Verification record

Everything in the README's comparison table was verified on a real Windows 11
machine on 2026-07-24, against these versions:

| Component | Version |
|---|---|
| Codex CLI | 0.145.0 |
| Codex VS Code extension (`openai.chatgpt`) | 26.721.x |
| Codex desktop app (`OpenAI.Codex` MSIX) | 26.721.x |
| codex-plugin-cc | 1.0.6 |
| Claude Code | desktop app, July 2026 |
| Windows | 11 Pro 26200, PowerShell 5.1 |

> **Re-verified on 0.149.0 (2026-08-22).** The live scenarios were re-run on
> Windows against Codex CLI 0.149.0 — see the section below. Everything the
> script can assert automatically passes, including a genuine first import. The
> two deep links still need a human looking at a screen. The table above stays
> as the 2026-07-24 record; the newer results are their own section.

## Re-run on Codex CLI 0.149.0, 2026-08-22

Run with `tools/verify-codex-release.ps1 -RunTransfers -SynthesizeFreshSource`
on Windows, after the CLI was upgraded and the engine was fixed to resolve it
(see below). Exit code 0, every automated scenario passing.

T1 needed the synthesized source: Codex had already imported every settled
transcript on the machine, so no first import was possible from what was on
disk. The synthesized copy is a real transcript with a real content hash and
produced a real thread - but a first import proved with a manufactured source
is worth distinguishing from one that happened to be lying around, so it is
recorded that way.

| Component | Version |
|---|---|
| Codex CLI | 0.149.0, resolved to `%APPDATA%\npm\codex.CMD` |
| codex-plugin-cc | 1.0.6 |
| Codex desktop app | 26.818.5229.0 |
| `threads` table | 38 columns, all four the engine reads present, 410 rows |
| import ledger | 292 records |
| `codex://` handler | registered |

| # | Result on 0.149.0 |
|---|---|
| T0 engine resolves a thread | PASS |
| T1 fresh import | PASS - via `-SynthesizeFreshSource`, since every transcript on disk had already been imported |
| T3 dedupe | PASS - reused the prior thread |
| T4 model and effort flags | PASS |
| T5 absolute binary path | PASS - the emitted resume command uses the resolved `codex.CMD` |
| T6 thread working directory | PASS |
| O1 / O2 deep links | not run - they need a human looking at a screen |

Getting here took six engine fixes, every one of them found by running the
thing on Windows rather than reasoning about it from a Linux container:

1. A Windows Store app-execution alias returned as an executable path.
2. A successful import reported as a failure once it outran a fixed
   15-second detection window.
3. A failed transfer whose only diagnostic was filtered away as known noise.
4. Resolution that gave up after the first PATH candidate.
5. An `%APPDATA%\npm` guard that rejected the user's real install.
6. A PATH walk that preferred npm's extensionless Git Bash shim, which
   Windows cannot execute, over the `codex.cmd` beside it.

## Earlier partial re-run, 2026-08-22 (Codex CLI still 0.145.0)

Run with `tools/verify-codex-release.ps1 -RunTransfers` on Windows. The CLI had
not moved, so this does **not** retire the note above — what it establishes is
that the flow still works on 0.145.0 against a much newer desktop app.

| Component | Version at this run |
|---|---|
| Codex CLI | 0.145.0 (resolved to the vendored exe in the Claude app container) |
| codex-plugin-cc | 1.0.6 |
| Codex desktop app | 26.818.5229.0 (recorded above as 26.721.x) |
| `threads` table | 38 columns, all four the engine reads present, 405 rows |
| `codex://` handler | registered |

| # | Result |
|---|---|
| T0 engine resolves a thread | PASS |
| T1 fresh import | NOT EXERCISED - every recent settled transcript was already in the ledger |
| T3 dedupe | PASS - reused the prior thread |
| T4 model and effort flags | PASS |
| T5 absolute binary path | PASS |
| T6 thread working directory | PASS |
| O1 / O2 deep links | not run - they need a human looking at a screen |

Three engine bugs were found by running this rather than reasoning about it: a
Windows Store app-execution alias returned as an executable path, a successful
import reported as a failure once it outran a fixed 15-second window, and a
failed transfer whose only diagnostic was filtered away as known noise. All are
fixed in the changelog's Unreleased section.
>
> A **static** compatibility check of the shipped 0.149.0 Windows binary
> (`@openai/codex@0.149.0-win32-x64`,
> `vendor/x86_64-pc-windows-msvc/bin/codex.exe`) was done on 2026-08-22, and
> every internal this kit reads is intact:
>
> | Internal the kit depends on | Status in 0.149.0 |
> |---|---|
> | `~/.codex/state_5.sqlite` | Still the only `state_N.sqlite` in the binary; no `state_6` |
> | `threads` columns `id` / `created_at` / `cwd` / `title` | All present; every migration since is an additive `ADD COLUMN`, no rename or drop |
> | `created_at` still populated | Yes — `INSERT INTO threads` writes it alongside the newer `created_at_ms` |
> | `external_agent_session_imports.json` | Same filename; `records[]` still carries `source_path`, `imported_thread_id`, `imported_at` |
> | `codex://threads/<id>` | Still a registered route (`codex://threads/`, `codex://threads/new`) |
>
> This proves the shapes still exist, not that the flow still works — that is
> what the live re-run is for. The VS Code route
> (`vscode://openai.chatgpt/local/<id>`) ships in the extension rather than the
> CLI, so this check says nothing about it.

Identifiers below are synthesized (`0199aaaa-...`) — the shapes and outcomes
are as observed.

## Transfer engine — PowerShell era (superseded by `codex_bridge.py` in v1.2.0)

| # | Scenario | Method | Result |
|---|---|---|---|
| T1 | Fresh session import | Run engine against a never-imported `.jsonl`; compare `threads` table before/after | New thread detected with correct title; `SUCCESS` with `codex resume` command |
| T2 | Plugin false-failure workaround (#513) | Same run: plugin printed "did not record an imported thread" | Engine ignored the message; thread existed in `state_5.sqlite`; verified id matched the ledger record |
| T3 | Unchanged-content re-transfer (dedupe) | Re-run T1's source unmodified - it must be a *settled* transcript; Codex keys dedupe on the content hash, and a live session keeps appending, so re-running against the session you are sitting in tests nothing | No new thread (expected); engine fell through to ledger lookup and reused the prior thread id, labeled "(transcript unchanged... reusing)" |
| T4 | Model + effort flags | `-Model gpt-5.6-luna -Effort high` | Resume command rendered `-m gpt-5.6-luna -c model_reasoning_effort="high"` |
| T5 | Absolute binary path | Inspect emitted command | Full path to vendored `codex.exe`; the exe itself executed standalone (`codex-cli 0.145.0`) |
| T6 | Thread working directory | `codex-thread-query.py --cwd <id>` | Returned the session's original cwd with `\\?\` prefix stripped |
| T7 | Large session | 6.1 MB transcript (a full working day) | Imported; thread titled and continuable |

## Opening destinations

| # | Scenario | Method | Result |
|---|---|---|---|
| O1 | Desktop app deep link | `Start-Process "codex://threads/<id>"`, then screen inspection | App opened directly on the target thread: title, full turn history, composer with model dropdown |
| O2 | VS Code deep link | `Start-Process "vscode://openai.chatgpt/local/<id>"`, then screen inspection | Codex panel navigated to the imported conversation, turns visible and continuable |
| O3 | `-OpenIn auto` selection | Engine run with no flag on a machine with the desktop app installed | Chose the desktop app; printed "Opened the Codex desktop app on this thread" |
| O4 | Terminal fallback path | User-reported failure before the PATH fix; re-verified after | Pre-fix: `codex not recognized` in spawned shell (container PATH trap). Post-fix: absolute path embedded; vendored exe runs from any shell |

## Skills & parity — PowerShell era (now `codex_bridge.py sync`)

| # | Scenario | Method | Result |
|---|---|---|---|
| P1 | Skill discovery ground truth | `codex debug prompt-input` (renders the model-visible prompt) | All 49 user skills listed exactly once from `~/.agents/skills`; zero duplicates; instructions (AGENTS.md) present in the developer message |
| P2 | Double-listing reproduction | Skills present in both `~/.codex/skills` (junctions) and `~/.agents/skills` | Every skill listed twice in the picker (three times when a third copy existed) — this motivated the single-root design |
| P3 | Adaptation-safe sync | Re-run sync with 6 hand-adapted copies present | `Refreshed: 0`; all 6 listed as "left alone"; unchanged copies counted correctly |
| P4 | First-run ancestry bug (regression test) | Empty manifest + drifted copies | Original logic wrongly refreshed (destroying adaptations — recovered by re-deriving them); fixed logic treats unprovable ancestry as adapted. Re-run confirms 0 refreshed |
| P5 | Skip list | `to-codex` present on the Claude side | `Skipped (Claude-only): 1`; never copied to Codex |
| P6 | No-op backup hygiene | Re-run with unchanged AGENTS.md | "unchanged - no backup, no install needed"; backup count stable |
| P7 | 32 KiB cap guard | Size check in installer | Aborts before installing an oversized AGENTS.md (Codex default cap 32,768 bytes) |
| P8 | Junction removal safety | Reparse-point-gated `Directory.Delete(path, $false)` on 48 junctions | All removed; every target directory verified intact afterward |

## Launcher (`switch-to-codex.ps1`)

| # | Scenario | Method | Result |
|---|---|---|---|
| L1 | Session enumeration | `-ListOnly` headless mode | 10 most recent sessions with timestamps, project labels, first-message previews (UTF-8 correct) |
| L2 | Live model catalog | `codex debug models` parsed at runtime | Current model ids enumerated; static fallback exercised when parsing is unavailable |
| L3 | Full GUI flow | Human-in-the-loop | Dialog → transfer → destination opened; confirmed working by the author in real use |

## End-to-end confirmation

The complete flow — `/to-codex` in a live Claude Code session → clickable model
pick → transfer → Codex desktop app opens on the conversation — was run by the
author on real work sessions multiple times, including the failure that exposed
O4 and the re-run that confirmed its fix.

## What is NOT covered

- macOS/Linux runtime confirmation (see the v1.2.0 section below)
- Non-MSIX Claude installs (the PATH-trap fallback chain should be a no-op —
  `Get-Command codex` wins — but this exact configuration wasn't exercised)
- Future Codex versions: the state DB schema, ledger format, and deep-link
  routes are undocumented internals (see README caveats)

## Cross-platform engine (v1.2.0)

| # | Scenario | Method | Result |
|---|---|---|---|
| X1 | Engine detects its environment | `codex_bridge.py doctor` on Windows | Resolved the vendored codex.exe inside the app container (which `shutil.which` could NOT find), the importer, both Codex state files, and `auto` -> desktop app |
| X2 | Fresh import via the Python engine | Real never-imported transcript | New thread created and titled ("Day of week trading analysis report") |
| X3 | Dedupe-reuse via the Python engine | Re-ran an already-imported transcript | Reused the existing thread and said so |
| X4 | Importer PATH injection | Fresh import failed first with "Codex CLI is not installed"; retried after injecting the resolved binary's directory into the child PATH | Failed before the fix, succeeded after - see the Fixed note in CHANGELOG 1.2.0 |
| X5 | Windows path rules tested off-Windows | Reload the module with `sys.platform` patched, then assert prefix stripping, UNC handling, case-insensitivity, and that different paths still differ | 5 tests pass on every CI OS |
| X6 | State DB is read-only | Open via the engine and attempt an INSERT | `sqlite3.OperationalError` - write rejected |
| X7 | Graceful degradation | Missing state DB, missing/corrupt ledger, unreadable transcript | Returns 0 / None / "(no preview)" instead of raising |
| X8 | Invalid source rejected | `transfer --source README.md` (outside ~/.claude/projects) | Non-zero exit with a clear message; asserted in CI |
| X9 | CLI surface | `--help` for every subcommand on all three OSes | Green in CI (ubuntu / macOS / windows, Python 3.9 and 3.12) |

**Not covered:** the macOS and Linux protocol-handler and terminal-launch paths
have not been run against a real Codex install. They are implemented and
CI-exercised; confirmation is welcome via an issue.
