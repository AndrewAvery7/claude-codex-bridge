<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.png">
    <img src="assets/logo.png" alt="claude-codex-bridge" width="540">
  </picture>
</p>

<p align="center">
  <b>One command to hand a live Claude Code session to OpenAI Codex — conversation, skills, instructions, and memory intact.</b>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue.svg" alt="Windows, macOS, Linux">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/status-tested%20end--to--end-brightgreen.svg" alt="Tested">
  <a href="https://github.com/openai/codex-plugin-cc/pull/551"><img src="https://img.shields.io/badge/upstream%20fix-codex--plugin--cc%20%23551-orange.svg" alt="Upstream PR"></a>
</p>

https://github.com/user-attachments/assets/9fa13cef-8a95-46d0-8ee9-57965a60c714

<p align="center">
  <i>65 seconds &mdash; press play, and hit &#128266; to unmute (GitHub starts videos silent).</i>
  &nbsp;·&nbsp;
  <a href="https://github.com/AndrewAvery7/claude-codex-bridge/releases/latest/download/claude-codex-bridge-promo.mp4">Download the MP4</a>
</p>

---

Running out of Claude Code tokens mid-task? Want a second model's opinion with your whole working context? **claude-codex-bridge** turns "switch to Codex" into a single step:

```
/to-codex
```

…and the OpenAI **Codex desktop app opens directly on your transferred conversation**, with the same skills, the same operating instructions, and the same memory layer your Claude Code sessions use. A desktop launcher does the same thing **without spending a single Claude token** — it works even when Claude Code is rate-limited or closed.

## Why this exists (and why not just use the official plugin)

OpenAI's [codex-plugin-cc](https://github.com/openai/codex-plugin-cc) provides `/codex:transfer` — and this kit uses its importer as the transfer engine. But by itself, on Windows, the experience breaks down in ways this kit fixes. Every fix below was diagnosed and verified on a real machine (see [docs/TESTING.md](docs/TESTING.md)):

| Problem | Official plugin | This kit |
|---|---|---|
| Windows transfer reports **false failure** ([#513](https://github.com/openai/codex-plugin-cc/issues/513) — thread is actually created) | Open bug | Detects the imported thread directly in Codex's state DB; trusts evidence, not the broken success message |
| Re-transferring an **unchanged session** creates no thread (content-hash dedupe) and looks like a failure | Unhandled | Reads Codex's import ledger and reuses the existing thread, telling you so |
| `codex` **not on PATH** for spawned shells (npm installs inside an app container are invisible outside it) | Unhandled | Resolves an absolute path to the standalone vendored `codex.exe` that is real for every process |
| Where does the session **open**? | Prints a command | Deep-links straight into the **Codex desktop app** (`codex://threads/<id>`) or the **VS Code Codex panel** (`vscode://openai.chatgpt/local/<id>`), falling back to a terminal TUI — your choice |
| Model choice | Config default | Clickable model picker at transfer time (`-m` per invocation for the TUI; app/panel keep their own selector) |
| Out of Claude tokens entirely? | Unusable (needs a live Claude session) | Desktop launcher with a session picker — zero Claude tokens involved |
| Codex knows your workflow? | Out of scope | Parity sync: flattened instructions + your skills served to Codex from the cross-tool `~/.agents/skills` root |

## How it fits together

```mermaid
flowchart LR
    A["Claude Code session"] -->|"/to-codex"| B["Model picker (clickable)"]
    B --> C["Transfer engine"]
    C -->|"codex-plugin-cc importer"| D["Codex thread"]
    C -->|"verify in state DB / ledger"| D
    D -->|"codex://threads/id"| E["Codex desktop app"]
    D -->|"vscode://openai.chatgpt/local/id"| F["VS Code Codex panel"]
    D -->|"codex resume id -m model"| G["Terminal TUI"]
    H["Desktop launcher (no Claude tokens)"] --> C
```

```mermaid
flowchart TD
    subgraph "Workbench parity (codex_bridge.py sync)"
        I["~/.claude/skills"] -->|"manifest-based sync"| J["~/.agents/skills (cross-tool root)"]
        K["CLAUDE.md + your operating manual"] -->|"flatten (Codex ignores @includes)"| L["~/.codex/AGENTS.md"]
        M["MCP servers (e.g. a personal memory server)"] --> N["~/.codex/config.toml"]
    end
    J --> O["Codex sees your skills - listed once"]
    L --> P["Codex follows your instructions"]
```

## Components

All components live in the plugin at `plugins/codex-bridge/`:

| Component | What it does |
|---|---|
| `skills/to-codex/` | Claude Code skill: locate the live transcript, clickable model pick, transfer, open in Codex |
| `scripts/codex_bridge.py` | **The engine** (cross-platform). `transfer` imports and verifies a session then opens Codex; `pick` is a terminal session picker; `sync` keeps Codex in parity; `doctor` reports what it detects |
| `scripts/codex-thread-query.py` | Standalone read-only queries against Codex state, for scripting |
| `scripts/switch-to-codex.ps1` | Native Windows GUI launcher (session + model + destination) that calls the engine. No Claude tokens needed |
| `AGENTS.md.example` (repo root) | A complete, real-world example of flattened cross-agent instructions (including a full operating manual) |
| `tools/make-promo.py` (repo root) | Renders the promo's motion-graphics core - every command string comes from source, so it is always exact |
| `tools/stitch-promo.sh` (repo root) | Assembles the finished promo (AI bookends + motion-graphics core + audio staging) |

## Quick Start

### Prerequisites
- Python 3.9+ and Node 18.18+ (Windows, macOS, or Linux)
- [Codex CLI](https://developers.openai.com/codex) (`npm i -g @openai/codex`) with a ChatGPT subscription or OpenAI API key
- [Claude Code](https://claude.com/claude-code)
- The official plugin (the transfer engine):
```bash
claude plugin marketplace add openai/codex-plugin-cc
```
```bash
claude plugin install codex@openai-codex
```

### Option 1 — Install as a Claude Code plugin (recommended, one-time)
```bash
claude plugin marketplace add AndrewAvery7/claude-codex-bridge
```
```bash
claude plugin install codex-bridge@claude-codex-bridge
```
That's it. In any Claude Code session: **`/to-codex`** — scripts and skill ship
with the plugin and update automatically.

### Option 2 — Manual install
```powershell
git clone https://github.com/AndrewAvery7/claude-codex-bridge.git
Copy-Item -Recurse claude-codex-bridge\plugins\codex-bridge\scripts "$env:USERPROFILE\.claude\codex-parity"
Copy-Item -Recurse claude-codex-bridge\plugins\codex-bridge\skills\to-codex "$env:USERPROFILE\.claude\skills\to-codex"
```
On macOS/Linux, copy the same two directories to `~/.claude/codex-parity` and
`~/.claude/skills/to-codex`.

For switching without any Claude tokens: on Windows create a desktop shortcut to
`switch-to-codex.ps1` (see [docs/DESIGN.md](docs/DESIGN.md#the-desktop-launcher));
anywhere else run `python codex_bridge.py pick` for the same picker in a terminal.

### Option 3 — Transfer engine only
Skip the skill; just get reliable session hand-off from any shell:
```bash
python plugins/codex-bridge/scripts/codex_bridge.py transfer --source "<path-to-claude-session.jsonl>" --model gpt-5.6-sol
```
The source must live under `~/.claude/projects` (importer requirement).
`--open auto|app|vscode|terminal|none`. Start with
`python plugins/codex-bridge/scripts/codex_bridge.py doctor` — it prints the codex
binary it resolved, the importer it found, and where `auto` would open a thread.

### Option 4 — Workbench parity sync
Make Codex mirror your Claude Code skills and instructions (see `AGENTS.md.example`):
```bash
python plugins/codex-bridge/scripts/codex_bridge.py sync --agents-md ./AGENTS.md --check-cli your-cli-1 your-cli-2
```

## Good to know
- **Transfers are snapshots.** Anything said in Claude after the transfer is not in the Codex thread. Transfer last — or re-transfer (unchanged content reuses the same thread; changed content creates a new one).
- **Model selection**: the `-m` flag applies to the terminal resume command. The desktop app and VS Code panel each have their own model dropdown — pick there.
- **Never put skills in `~/.codex/skills`.** Codex scans both that and `~/.agents/skills`; a skill in both is listed twice. The sync script guards against this.
- **Adapted skills are sacred.** If you hand-tune a skill copy for Codex (e.g. "dispatch Codex subagents" instead of Claude ones), the manifest logic will never overwrite it.

## Documentation
- [docs/DESIGN.md](docs/DESIGN.md) — architecture and the reasoning behind every workaround: the false-failure diagnosis, the dedupe ledger, the app-container PATH trap, how the deep-link routes were found
- [docs/TESTING.md](docs/TESTING.md) — the full verification matrix: what was tested, how, and what proved it
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — common failure modes and exact fixes
- [docs/PROMO.md](docs/PROMO.md) — how the video above is built, and why its first frame is a title card
- [CHANGELOG.md](CHANGELOG.md)

## Technology
PowerShell 5.1 · Python 3 · [codex-plugin-cc](https://github.com/openai/codex-plugin-cc) (Apache-2.0, the transfer engine) · [Codex CLI](https://developers.openai.com/codex) · [Agent Skills open standard](https://agentskills.io) (`SKILL.md`) · Codex deep-link protocols (`codex://`, `vscode://openai.chatgpt/`)

## Caveats (honest edges)
- **Platform support is honest about what is verified.** The engine is one
  cross-platform Python file and CI runs its test suite on Windows, macOS and
  Linux. The full transfer flow is verified end-to-end **on Windows**; the macOS
  and Linux code paths (protocol handler via `open`/`xdg-open`, terminal launch)
  are implemented and CI-checked but await real-world confirmation - please open
  an issue either way, it is genuinely useful feedback.
- Relies on **undocumented Codex internals**: the `state_5.sqlite` threads schema, the `external_agent_session_imports.json` ledger, and the deep-link routes. Verified against Codex CLI 0.145 / VS Code extension 26.721 / plugin 1.0.6 — future Codex updates could move these. The terminal resume command printed on every transfer is the always-works fallback.
- The transfer converts between two different agent formats; the conversation arrives as visible, continuable turns, but tool-call internals are thinned by the importer.

## Acknowledgements
- **[openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)** (Apache-2.0) — the official Claude Code plugin whose session importer powers the transfer step. This kit wraps it and works around [#513](https://github.com/openai/codex-plugin-cc/issues/513) rather than replacing it. Install it from OpenAI's marketplace; none of its code is bundled here.
- The **[Agent Skills](https://agentskills.io)** open standard, which makes one `SKILL.md` work across Claude Code, Codex, and 30+ agents.

## License
[MIT](LICENSE) © 2026 AndrewAvery7
