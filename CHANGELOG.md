# Changelog

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
