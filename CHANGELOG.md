# Changelog

## 1.1.0 — 2026-07-24

### Added
- **Claude Code plugin marketplace**: install with
  `claude plugin marketplace add AndrewAvery7/claude-codex-bridge` +
  `claude plugin install codex-bridge@claude-codex-bridge` — no manual copying;
  skill and scripts ship together and update automatically
- **Promo video** (65s, 1080p, attached to this release) built as a hybrid:
  generative-video bookends for the cinematic opener and title card, and a
  motion-graphics core (`tools/make-promo.py`) for every scene containing exact
  text — commands are rendered from source, so they can never be misspelled.
  `tools/stitch-promo.sh` assembles the two with staged audio (the opener keeps
  its own native audio; the music bed enters afterwards and is loudness-
  normalised so it stays present throughout).
- **Animated demo** (`assets/demo.gif`) at the top of the README, cut from the
  promo itself so the preview matches the real video
- CI: PSScriptAnalyzer + PowerShell 5.1 parse check + ASCII guard +
  Python compile + manifest validation
- Issue templates and Discussions

### Changed
- Repo restructured into plugin layout: scripts and skill now live under
  `plugins/codex-bridge/` (manual-install paths updated in the README)
- Skill resolves its scripts via `CLAUDE_PLUGIN_ROOT` with a
  `~/.claude/codex-parity` fallback for manual installs

## 1.0.0 — 2026-07-24

Initial public release. Everything below was built, broken, diagnosed, and
re-verified in a single intensive day on a real machine — see
[docs/TESTING.md](docs/TESTING.md) for the evidence and
[docs/DESIGN.md](docs/DESIGN.md) for the reasoning.

### Added
- `to-codex` Claude Code skill: one-word session hand-off with clickable model
  picker
- Transfer engine (`transfer-to-codex.ps1`):
  - wraps the official codex-plugin-cc importer
  - independent thread verification via Codex's state DB (works around the
    Windows false-failure, codex-plugin-cc#513)
  - unchanged-content dedupe handling via the import ledger (reuses the
    existing thread instead of failing)
  - absolute-path Codex binary resolution (survives MSIX app-container
    virtualization)
  - `-OpenIn auto|app|vscode|terminal|none`; auto prefers the Codex desktop
    app (`codex://threads/<id>`), then the VS Code panel
    (`vscode://openai.chatgpt/local/<id>`), then a terminal in the thread's
    working directory
- GUI desktop launcher (`switch-to-codex.ps1`): recent-session picker, live
  model catalog, effort + destination choice; needs no Claude tokens
- Workbench parity sync (`setup-parity.ps1`): flattened AGENTS.md install with
  32 KiB guard and change-detection backups; manifest-based skill sync that
  never overwrites Codex-adapted copies; double-listing guard; Claude-only
  skill exclusion list
- Read-only Codex state helper (`codex-thread-query.py`)
- `AGENTS.md.example` — complete real-world flattened instruction file,
  including a full operating manual
- Documentation: design rationale, verification record, troubleshooting
