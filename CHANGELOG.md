# Changelog

## Unreleased

### Added
- `tools/verify-codex-release.ps1` - re-runs the docs/TESTING.md verification
  against whatever Codex is installed and writes a report to paste into the
  tracking issue. The version table goes stale every few Codex releases and
  re-establishing it by hand is enough work that it does not happen; this
  collects the same evidence in one run. Read-only by default (versions, the
  binary the engine resolves, the `threads` schema, the ledger, the `codex://`
  handler registration); `-RunTransfers` adds the live T1/T3/T4 scenarios, which
  create threads and so are opt-in. CI now lints `tools/*.ps1` alongside the
  plugin scripts: PSScriptAnalyzer, a Windows PowerShell 5.1 parse check, and
  the ASCII guard.

### Fixed
- Six engine bugs, each with a regression test that fails without its fix:
  - `pick` accepted `0` and negative answers and passed them straight to a list
    index, so `0` silently transferred the *oldest* session and `-1` the
    second-oldest - a session the user had not chosen. Out-of-range answers are
    now refused (`choice_index()`).
  - The macOS terminal launch built its AppleScript by interpolating the resume
    command raw. That command already quotes any path containing a space, and
    those quotes closed the AppleScript string early; the working directory was
    not shell-quoted either, so a Mac path like `~/My Projects` broke `cd`. Both
    layers are now quoted correctly (`applescript_do_script()`).
  - `recent_sessions()` called `stat()` on every transcript found by `glob()`,
    so a transcript rotated away mid-scan - or a dangling symlink - crashed
    `pick` and `doctor` with `FileNotFoundError`. Unreadable entries are now
    skipped, and each file is stat'd once instead of three times.
  - `codex-thread-query.py --ledger` could never match a UNC path: it stripped
    the `\\?\` prefix but not `\\?\UNC\`, leaving `UNC\server\share` to be
    compared against `\\server\share`. The engine already handled this; the
    helper now applies the same rule, and a test asserts the two implementations
    agree so they cannot drift apart again.
  - The same helper crashed with `KeyError` on a ledger record that has no
    `imported_thread_id`, and with `JSONDecodeError` on a half-written ledger.
    Both are now treated as a miss, matching the engine.
  - `codex-thread-query.py` folded case and separators on POSIX too, so
    `/home/A` and `/home/a` compared equal on a case-sensitive filesystem. The
    Windows path rules now apply only on Windows.
- `--cwd` was a working, tested option of `codex-thread-query.py` that its own
  usage text never mentioned.
- Corrected this changelog's and the README's description of
  [openai/codex-plugin-cc#551](https://github.com/openai/codex-plugin-cc/pull/551).
  Both called it a separate or "rival" attempt at the upstream fix that was
  closed unmerged, which read as a third party's patch that upstream turned
  down. It is neither: #551 was this project's own PR, it closed because the
  fork behind it was deleted, and it only ever normalised the path — the
  content-hash race it left in place is why #469 is the patch worth watching.
- Re-pointed the upstream-bug references (README badge/table/acknowledgements,
  docs/TROUBLESHOOTING.md, docs/DESIGN.md) from
  [openai/codex-plugin-cc#513](https://github.com/openai/codex-plugin-cc/issues/513)
  to [#618](https://github.com/openai/codex-plugin-cc/issues/618): upstream
  closed #513 on 2026-08-11 as a duplicate of #618, which is the current open
  issue describing the same Windows false-negative failure. The upstream bug
  itself is still unfixed — `codex.mjs` is unchanged (sha
  `fead00cc44c8b945a292481c490ba0a50b0c5c64`), tracking issue #417 is still
  open, and fix PR #469 is still open/unreviewed — so this kit's own
  detection logic is unchanged and still required.

### Changed
- Refreshed the dated upstream/toolchain claims after re-checking them on
  2026-08-22: the Codex CLI re-verification caveat now reads 0.149.0 (four
  releases past the 0.145.0 this kit was verified against, up from two), and the
  [#469](https://github.com/openai/codex-plugin-cc/pull/469) acknowledgement now
  records that it is still unreviewed and that a third contributor weighed in on
  2026-08-12, and describes this project's own earlier PR
  ([#551](https://github.com/openai/codex-plugin-cc/pull/551)) accurately: it is
  closed and unmerged because it covered only the path half of the bug, not
  because upstream rejected a fix. Upstream `main` is still at `db52e28` (2026-07-07) and
  `codex.mjs` still hashes to `fead00cc44c8b945a292481c490ba0a50b0c5c64`, so the
  bug and this kit's workaround are both unchanged.
- Static compatibility check of Codex CLI 0.149.0, recorded in
  docs/TESTING.md: unpacking the shipped `@openai/codex@0.149.0-win32-x64`
  binary shows `state_5.sqlite`, the `threads` columns this kit reads (`id`,
  `created_at`, `cwd`, `title`), the `external_agent_session_imports.json`
  record fields and the `codex://threads/` route all unchanged from the 0.145.0
  the kit was verified against — every `threads` migration since is additive and
  `created_at` is still written on insert. The schema drift the caveat warns
  about has not happened, so no engine change is needed; the live end-to-end
  re-run is tracked in #8. `SECURITY.md`'s supported-versions note points at
  that check while keeping the supported pin on 0.145, the last install
  verified end to end.
- Plugin identifier renamed `codex-bridge` → `claude-codex-bridge` (in
  `plugins/codex-bridge/.claude-plugin/plugin.json` and the repo's own
  `.claude-plugin/marketplace.json`). The name `codex-bridge` was already taken
  in the `anthropics/claude-plugins-community` catalog by an unrelated plugin
  (`IgorGanapolsky/ThumbGate`), which would have collided on community-catalog
  submission. The plugin directory path is unchanged; only the install command
  changes, to `claude plugin install claude-codex-bridge@claude-codex-bridge`.

### Added
- Weekly scheduled CI run (Mondays) on top of push/PR triggers - re-validates
  the suite against fresh runner images and toolchains even when the repo is
  untouched, and keeps the public Actions history a living record rather than
  a snapshot of the last push.
- **The promo opens on a title card**, so the README shows the project rather
  than a black rectangle. GitHub generates its inline player from a bare
  `user-attachments` URL and its markdown sanitiser strips author-written
  `<video>`, so there is no `poster` a README can set - the browser shows frame
  0, and frame 0 was the generative hero shot before its light builds. The card
  composites `assets/logo-dark.png` rather than redrawing the mark, and every
  line on it is already true elsewhere in the repository. `tools/make-title-card.py`
  builds it; `tools/prepend-title-card.sh` applies it to a finished film, which
  is how it was applied here - the bookends and music bed that built the original
  were never committed, and the release asset was the only surviving copy. The
  video is now 1:05 rather than 1:04, and the release asset has been replaced.
  See [docs/PROMO.md](docs/PROMO.md), which is also new.

### Fixed
- `.gitignore` had no rule for `assets/*.mp4`, which the sibling repository has
  had from the start. The promo is a release asset by design, so an 18 MB binary
  was one `git add -A` away from being committed to this repository forever.

## 1.2.0 - 2026-07-25

### Added
- **Cross-platform engine** (`plugins/codex-bridge/scripts/codex_bridge.py`).
  One Python file replaces the PowerShell transfer/sync scripts and runs on
  Windows, macOS and Linux. Subcommands: `transfer`, `pick` (terminal session
  picker), `sync` (AGENTS.md + skills parity), `doctor` (environment report).
- **Test suite** (`tests/test_codex_bridge.py`, 14 tests). The Windows path
  rules are pure functions, so they are tested on every OS by reloading the
  module with `sys.platform` patched - including a test asserting the Codex
  state DB is opened read-only and rejects writes.
- **CI matrix**: tests now run on ubuntu / macOS / windows against Python 3.9
  and 3.12, plus shellcheck, PSScriptAnalyzer, an ASCII guard, and a manifest
  check that fails if the marketplace and plugin versions disagree.
- `doctor` reports the resolved codex binary, importer path, Codex state paths
  and which surface `auto` would open - the fastest way to diagnose a bad setup.

### Fixed
- **The importer could not find `codex` even when the engine could.** It runs its
  own availability check, so inheriting PATH was not enough: an `npm -g` install
  inside a packaged app is invisible to child processes and the importer aborted
  with "Codex CLI is not installed". The engine now injects the resolved binary's
  directory into the importer's PATH. This affected fresh imports.

### Changed
- `switch-to-codex.ps1` remains the native Windows GUI but now calls the shared
  engine, so there is one implementation of the transfer logic rather than two
  that can drift.
- Removed `transfer-to-codex.ps1` and `setup-parity.ps1`, superseded by the
  engine. Manual-install and engine-only instructions in the README updated.

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
- The promo is embedded in the README as an inline player (GitHub only renders
  one for videos on its attachment CDN, so the MP4 is uploaded there; a release
  asset URL downloads instead of playing). `tools/make-readme-gif.sh` can cut a
  highlights GIF from the promo for social posts or as a fallback.
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
