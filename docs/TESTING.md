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

Identifiers below are synthesized (`0199aaaa-...`) — the shapes and outcomes
are as observed.

## Transfer engine (`transfer-to-codex.ps1`)

| # | Scenario | Method | Result |
|---|---|---|---|
| T1 | Fresh session import | Run engine against a never-imported `.jsonl`; compare `threads` table before/after | New thread detected with correct title; `SUCCESS` with `codex resume` command |
| T2 | Plugin false-failure workaround (#513) | Same run: plugin printed "did not record an imported thread" | Engine ignored the message; thread existed in `state_5.sqlite`; verified id matched the ledger record |
| T3 | Unchanged-content re-transfer (dedupe) | Re-run T1's source unmodified | No new thread (expected); engine fell through to ledger lookup and reused the prior thread id, labeled "(transcript unchanged... reusing)" |
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

## Skills & parity (`setup-parity.ps1`)

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

- macOS/Linux (kit is Windows-specific as shipped)
- Non-MSIX Claude installs (the PATH-trap fallback chain should be a no-op —
  `Get-Command codex` wins — but this exact configuration wasn't exercised)
- Future Codex versions: the state DB schema, ledger format, and deep-link
  routes are undocumented internals (see README caveats)
