## What this changes

<!-- One or two sentences. If it fixes an issue, add "Fixes #123". -->

## How you tested it

<!-- Be specific - this project's whole credibility rests on claims being
     verified rather than assumed. Which platform, which Codex version, what
     you actually ran and saw. "Transferred a real session and the desktop app
     opened on it" beats "looks right". -->

- Platform:
- Codex CLI version (`codex --version`):
- What you ran:
- What you observed:

## Checklist

- [ ] Windows PowerShell **5.1** compatible (no `&&`, no ternary, no `??`, no `?.`)
- [ ] `.ps1` files are **pure ASCII** (PS 5.1 reads BOM-less UTF-8 as ANSI and mojibakes non-ASCII into parse errors)
- [ ] Nothing writes to Codex's state database - `codex-thread-query.py` stays read-only
- [ ] The adapted-skill rule holds: when sync ancestry cannot be proven, the file is left alone
- [ ] No personal paths, usernames, emails, or machine-specific identifiers added
- [ ] Docs updated if behaviour changed (README / docs/DESIGN.md / docs/TROUBLESHOOTING.md)

## Notes for the reviewer

<!-- Anything you are unsure about, or deliberately left out of scope. -->
