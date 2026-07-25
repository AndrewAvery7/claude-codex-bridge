# Troubleshooting

## "codex : The term 'codex' is not recognized" in the launched terminal
You installed the Codex CLI with `npm i -g` from inside a packaged app (e.g. a
desktop AI assistant's shell). The install landed in that app's virtualized
container, invisible to normal shells. Two fixes:
- Preferred: run `npm i -g @openai/codex` once from a **regular** terminal —
  the kit's resolver picks up genuinely global installs first.
- Or do nothing: the engine embeds an absolute path to the container's
  standalone `codex.exe`, which works from any shell. If you see this error,
  you are likely running an old command by hand — re-run the transfer and use
  the freshly printed command.

## "Codex reported that the Claude import completed, but did not record an imported thread"
That text comes from codex-plugin-cc and is a **false negative on Windows**
([#513](https://github.com/openai/codex-plugin-cc/issues/513)). Ignore it —
trust the engine's own `SUCCESS`/`ERROR`, which is based on Codex's state DB.

## "no new Codex thread appeared after import ... and no prior import of this transcript exists"
Genuine failure. Check in order:
1. Is the source `.jsonl` under `~/.claude/projects`? The importer refuses
   sources outside it.
2. Is codex-plugin-cc installed? (`claude plugin install codex@openai-codex`)
3. Is the Codex CLI authenticated? Run `codex doctor`.
4. Run `codex resume` and check the picker — very slow imports can land after
   the 15-second detection window.

## The transfer "succeeded" but nothing new appears in Codex
Almost certainly the dedupe case: the transcript hasn't changed since a
previous transfer, so Codex reuses the existing thread — and the engine's
output says "(transcript unchanged since a prior transfer - reusing its
existing Codex thread)". Say something new in the Claude session and
re-transfer to get a fresh snapshot.

## Every skill shows up twice in Codex's picker
You have user skills in **both** `~/.codex/skills` and `~/.agents/skills`.
Remove everything except `.system` from `~/.codex/skills` (if entries are
junctions, delete only the reparse points — the sync guard will
warn you which entries are the problem). Restart the Codex surface afterwards;
its skill index caches until restart.

## Codex ignores my AGENTS.md instructions
- Codex does **not** expand `@file` include lines — anything included that way
  silently doesn't load. Flatten everything inline (`AGENTS.md.example` shows
  the shape).
- Over 32,768 bytes? Codex's default cap truncates. The installer aborts
  oversized files; check `project_doc_max_bytes` if you need more.
- Verify what Codex actually sees: `codex debug prompt-input` renders the full
  model-visible prompt — search it for a distinctive phrase from your file.

## The deep link opens the app but not the thread
The `codex://threads/<id>` and `vscode://openai.chatgpt/local/<id>` routes are
undocumented internals and may change with app updates. Use the terminal
resume command printed on every transfer (always works), and open an issue
with your app version.

## The picker choice of model doesn't apply in the app / VS Code panel
Expected: URL protocols can't carry a model. The `-m` flag shapes the terminal
command only; in the desktop app and VS Code panel, pick the model from the
composer's own dropdown.

## A hand-adapted skill copy got overwritten by the sync
Current versions refuse to touch any copy whose ancestry the manifest can't
prove (see DESIGN.md, Discovery 6). If it happened anyway: restore the copy,
run the sync once (it will be listed as "left alone"), and from then on it is
protected. The manifest lives next to the script as `sync-manifest.json`.
