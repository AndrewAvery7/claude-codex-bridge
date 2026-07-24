# Contributing

Issues and PRs welcome. The most valuable contributions right now:

- **macOS / Linux ports.** The design carries over (the importer, the state DB,
  the dedupe ledger, the deep links); the scripts are Windows PowerShell 5.1.
- **Deep-link route updates.** `codex://threads/<id>` and
  `vscode://openai.chatgpt/local/<id>` are undocumented internals — if a Codex
  update changes them, an issue with your app version is gold.
- **Repro reports for the upstream bugs** this kit works around, especially
  [codex-plugin-cc#513](https://github.com/openai/codex-plugin-cc/issues/513).

House rules for script changes:
- Windows PowerShell **5.1** compatible (no `&&`, no ternary, no null-coalescing)
- **Pure ASCII** in `.ps1` files (PS 5.1 reads BOM-less UTF-8 as ANSI and
  mojibakes non-ASCII into parse errors)
- Never write to Codex state — `codex-thread-query.py` opens the DB read-only;
  keep it that way
- The adapted-skill protection rule is inviolable: when sync ancestry cannot be
  proven, do not touch the file
