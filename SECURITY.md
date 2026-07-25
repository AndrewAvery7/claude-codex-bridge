# Security policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/AndrewAvery7/claude-codex-bridge/security/advisories/new)
rather than opening a public issue. I aim to acknowledge reports within a few
days.

## What this tool touches

Worth knowing before you install it, because it reads more than a typical
plugin:

| Resource | Access | Why |
|---|---|---|
| `~/.claude/projects/**/*.jsonl` | read | Your Claude Code session transcripts - the thing being transferred |
| `~/.codex/state_5.sqlite` | **read-only** (opened with `mode=ro`) | To verify an imported thread actually exists, since the upstream plugin reports false failures on Windows |
| `~/.codex/external_agent_session_imports.json` | read | To detect Codex's unchanged-content dedupe and reuse the existing thread |
| `~/.codex/AGENTS.md` | write (with timestamped backup) | Installs your flattened instructions, only when content changed |
| `~/.agents/skills/**` | write | Syncs your skills; never overwrites a copy whose ancestry it cannot prove |
| `~/.codex/config.toml` | read only | Reads a configured MCP server's URL host for an optional reachability check; **secrets are never printed or copied** |

## Design choices that matter for security

- **The Codex state database is opened read-only** (`file:...?mode=ro`) so the
  tool can never corrupt Codex state, even mid-write.
- **No credentials are read, stored, logged, or transmitted.** The reachability
  check in `setup-parity.ps1` extracts only the origin (scheme + host) from a
  configured MCP URL; bearer tokens stay in `config.toml` and are never echoed.
- **No network calls** are made except that optional origin reachability check,
  and whatever the Codex CLI itself does.
- **Nothing is uploaded anywhere.** Session transfer is entirely local: the
  official `codex-plugin-cc` importer hands your transcript to your own local
  Codex install.
- **Backups before overwrite.** `AGENTS.md` is copied to a timestamped `.bak-*`
  before replacement, and only when its content actually differs.

## Your session transcripts contain whatever you discussed

A transferred session carries your full conversation into Codex. If a session
contains secrets, credentials, or client-confidential material, that content
moves with it. Transfer deliberately, the same way you would treat any export.

## Supported versions

Only the latest release is supported. Verified against Codex CLI 0.145,
VS Code extension 26.721, and codex-plugin-cc 1.0.6 - see the caveats in the
[README](README.md#caveats-honest-edges) about relying on undocumented Codex
internals.
