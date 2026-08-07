#!/usr/bin/env python3
r"""claude-codex-bridge - cross-platform engine (Windows, macOS, Linux).

Hands a live Claude Code session to OpenAI Codex: imports the transcript with the
official codex-plugin-cc importer, verifies the result against Codex's own state
rather than trusting the importer's return value, then opens Codex on the thread.

Commands
    transfer   import a Claude transcript into a Codex thread and open it
    pick       choose a recent Claude session interactively, then transfer it
    sync       keep Codex in parity: install AGENTS.md, sync skills
    doctor     report what the engine can see on this machine

Why it verifies instead of trusting: on Windows the official plugin reports
"did not record an imported thread" for imports that actually succeeded, because
Codex writes ledger paths with the \\?\ extended-length prefix while Node's
realpathSync returns the plain form, so its strict path comparison never matches
(openai/codex-plugin-cc#513, still unfixed upstream). This engine looks the
thread up in Codex's own state DB, so it is correct either way.

All state access is READ-ONLY. Nothing here writes to Codex's database.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
CODEX_HOME = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))
STATE_DB = CODEX_HOME / "state_5.sqlite"
LEDGER = CODEX_HOME / "external_agent_session_imports.json"
CLAUDE_PROJECTS = HOME / ".claude" / "projects"
AGENTS_MD = CODEX_HOME / "AGENTS.md"
CODEX_SKILLS = CODEX_HOME / "skills"
AGENTS_SKILLS = HOME / ".agents" / "skills"
CLAUDE_SKILLS = HOME / ".claude" / "skills"

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
AGENTS_MD_CAP = 32768  # Codex's default project_doc_max_bytes

# Skills that must never sync into Codex (wrong direction / Claude-only UI).
SKIP_SKILLS = {"to-codex"}


# ---------------------------------------------------------------------------
# platform abstraction - the only place OS differences live
# ---------------------------------------------------------------------------

def normalize_ledger_path(p: str | os.PathLike[str]) -> str:
    r"""Make a ledger path comparable to what realpath returns.

    Codex records Windows paths with the \\?\ extended-length prefix (and
    \\?\UNC\ for network paths) while resolved paths come back plain. Strip the
    prefix and compare case-insensitively on Windows, where paths are not
    case-sensitive. On POSIX this is close to identity - exactly the behaviour
    we want, since there is no prefix to strip there.
    """
    s = str(p)
    if IS_WIN:
        if s.startswith("\\\\?\\UNC\\"):
            s = "\\\\" + s[8:]
        elif s.startswith("\\\\?\\"):
            s = s[4:]
        return s.replace("/", "\\").lower()
    return s


def codex_command() -> str | None:
    """Absolute path to the codex binary, usable from any process.

    Never return a bare "codex": a terminal we spawn may not share our PATH.
    On Windows there is an extra trap - `npm -g` run inside a packaged (MSIX)
    desktop app installs into that app's virtualised Roaming directory, which
    external processes cannot resolve. The container's LocalCache backing store
    is real for everyone, and the vendored exe there is standalone.
    """
    found = shutil.which("codex")
    if found and not (IS_WIN and _is_virtualized_npm(found)):
        return found

    if IS_WIN:
        pattern = (
            "Packages/*/LocalCache/Roaming/npm/node_modules/@openai/codex/"
            "node_modules/@openai/codex-win32-x64/vendor/*/bin/codex.exe"
        )
        local = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData/Local"))
        for candidate in sorted(local.glob(pattern)):
            return str(candidate)

    # Common global-npm locations that `which` can miss in restricted shells.
    for candidate in (
        HOME / ".npm-global/bin/codex",
        HOME / ".local/bin/codex",
        Path("/usr/local/bin/codex"),
        Path("/opt/homebrew/bin/codex"),
    ):
        if candidate.exists():
            return str(candidate)
    return found  # may be None


def _is_virtualized_npm(p: str) -> bool:
    """True for a Windows path that only resolves inside an app container."""
    appdata = os.environ.get("APPDATA", "")
    return bool(appdata) and p.lower().startswith(str(Path(appdata) / "npm").lower())


def open_url(url: str) -> bool:
    """Hand a URL to the OS so a registered protocol handler picks it up."""
    try:
        if IS_WIN:
            os.startfile(url)  # noqa: S606  - the documented Windows shell open
        elif IS_MAC:
            subprocess.run(["open", url], check=True)
        else:
            subprocess.run(["xdg-open", url], check=True)
        return True
    except Exception as exc:  # noqa: BLE001 - report, never crash the transfer
        print(f"  could not open {url}: {exc}", file=sys.stderr)
        return False


def launch_terminal(command: str, cwd: Path | None = None) -> bool:
    """Open a terminal window running `command`, ideally in `cwd`."""
    workdir = str(cwd) if cwd and Path(cwd).is_dir() else str(HOME)
    try:
        if IS_WIN:
            if shutil.which("wt"):
                subprocess.Popen(
                    ["wt", "new-tab", "-d", workdir, "powershell", "-NoExit", "-Command", command]
                )
            else:
                subprocess.Popen(["cmd", "/k", command], cwd=workdir)
            return True
        if IS_MAC:
            # osascript keeps the window open after the command finishes.
            script = f'tell application "Terminal" to do script "cd {_q(workdir)} && {command}"'
            subprocess.run(["osascript", "-e", script], check=True)
            subprocess.run(["open", "-a", "Terminal"], check=False)
            return True
        for term, args in (
            ("x-terminal-emulator", ["-e", "bash", "-lc", f"{command}; exec bash"]),
            ("gnome-terminal", ["--working-directory", workdir, "--", "bash", "-lc", f"{command}; exec bash"]),
            ("konsole", ["--workdir", workdir, "-e", "bash", "-lc", f"{command}; exec bash"]),
            ("xfce4-terminal", ["--working-directory", workdir, "-e", f"bash -lc '{command}; exec bash'"]),
            ("xterm", ["-e", "bash", "-lc", f"{command}; exec bash"]),
        ):
            if shutil.which(term):
                subprocess.Popen([term, *args], cwd=workdir)
                return True
        print("  no terminal emulator found - run the command above yourself", file=sys.stderr)
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  could not launch a terminal: {exc}", file=sys.stderr)
        return False


def _q(s: str) -> str:
    """Quote a path for embedding in an AppleScript double-quoted string."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def default_open_target() -> str:
    """Pick where a transferred thread should open on this machine."""
    if IS_WIN:
        try:
            import winreg  # noqa: PLC0415 - Windows-only import

            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "codex").Close()
            return "app"
        except OSError:
            pass
    elif IS_MAC and Path("/Applications/Codex.app").exists():
        return "app"
    if shutil.which("code"):
        return "vscode"
    return "terminal"


# ---------------------------------------------------------------------------
# Codex state (read-only)
# ---------------------------------------------------------------------------

def _connect_ro() -> sqlite3.Connection:
    """Open the state DB read-only so we can never corrupt Codex state."""
    return sqlite3.connect(f"file:{STATE_DB.as_posix()}?mode=ro", uri=True)


def max_thread_created() -> int:
    if not STATE_DB.exists():
        return 0
    con = _connect_ro()
    try:
        return con.execute("SELECT COALESCE(MAX(created_at), 0) FROM threads").fetchone()[0] or 0
    finally:
        con.close()


def thread_created_after(epoch: int) -> tuple[str, str] | None:
    """Newest thread created after `epoch`, as (id, title)."""
    if not STATE_DB.exists():
        return None
    con = _connect_ro()
    try:
        row = con.execute(
            "SELECT id, COALESCE(title, '') FROM threads WHERE created_at > ? "
            "ORDER BY created_at DESC LIMIT 1",
            (epoch,),
        ).fetchone()
        return (row[0], row[1]) if row else None
    finally:
        con.close()


def thread_cwd(thread_id: str) -> Path | None:
    if not STATE_DB.exists():
        return None
    con = _connect_ro()
    try:
        row = con.execute("SELECT cwd FROM threads WHERE id = ?", (thread_id,)).fetchone()
    finally:
        con.close()
    if not row or not row[0]:
        return None
    raw = str(row[0])
    for prefix in ("\\\\?\\UNC\\", "\\\\?\\"):
        if raw.startswith(prefix):
            raw = ("\\\\" + raw[8:]) if prefix.endswith("UNC\\") else raw[4:]
            break
    p = Path(raw)
    return p if p.is_dir() else None


def ledger_thread_for(source: Path) -> str | None:
    """Thread previously imported from this transcript.

    Codex dedupes unchanged re-imports by content hash, so a legitimate repeat
    transfer creates no new thread. Without this lookup that looks like failure.
    """
    if not LEDGER.exists():
        return None
    try:
        records = json.loads(LEDGER.read_text(encoding="utf-8")).get("records", [])
    except (OSError, json.JSONDecodeError):
        return None
    target = normalize_ledger_path(source)
    hits = [
        r for r in records
        if normalize_ledger_path(r.get("source_path", "")) == target and r.get("imported_thread_id")
    ]
    if not hits:
        return None
    return max(hits, key=lambda r: r.get("imported_at", 0))["imported_thread_id"]


def importer_env() -> dict[str, str]:
    """Environment for the importer subprocess, with codex guaranteed on PATH.

    The importer runs its own `codex` availability check, so inheriting our PATH
    is not enough: if codex was installed with `npm -g` inside a packaged app,
    a child process may not resolve it and the importer aborts with "Codex CLI is
    not installed". We already know the real binary's location, so put its
    directory on the front of PATH for the child.
    """
    env = dict(os.environ)
    codex = codex_command()
    if codex:
        bindir = str(Path(codex).parent)
        if bindir not in env.get("PATH", ""):
            env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    return env


def companion_script() -> Path | None:
    """Newest installed codex-plugin-cc companion script."""
    base = HOME / ".claude" / "plugins" / "cache" / "openai-codex" / "codex"
    if not base.is_dir():
        return None
    candidates = sorted(base.glob("*/scripts/codex-companion.mjs"))
    return candidates[-1] if candidates else None


# ---------------------------------------------------------------------------
# transfer
# ---------------------------------------------------------------------------

def cmd_transfer(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser()
    if not source.is_file():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 1
    source = source.resolve()
    if source.suffix != ".jsonl":
        print("ERROR: source must be a .jsonl Claude transcript", file=sys.stderr)
        return 1
    try:
        source.relative_to(CLAUDE_PROJECTS.resolve())
    except (ValueError, OSError):
        print(f"ERROR: Codex imports only from {CLAUDE_PROJECTS}", file=sys.stderr)
        return 1

    companion = companion_script()
    if companion is None:
        print("ERROR: codex-plugin-cc not found. Install it with:", file=sys.stderr)
        print("  claude plugin marketplace add openai/codex-plugin-cc", file=sys.stderr)
        print("  claude plugin install codex@openai-codex", file=sys.stderr)
        return 1
    if shutil.which("node") is None:
        print("ERROR: node not found on PATH (the importer needs Node 18.18+)", file=sys.stderr)
        return 1

    print("Transferring Claude session -> Codex thread...")
    print(f"  source: {source}")

    before = max_thread_created()
    proc = subprocess.run(
        ["node", str(companion), "transfer", "--source", str(source)],
        capture_output=True, text=True, env=importer_env(),
    )
    importer_output = (proc.stdout or "") + (proc.stderr or "")

    thread_id = title = None
    reused = False
    for _ in range(15):  # poll: the import lands asynchronously
        found = thread_created_after(before)
        if found:
            thread_id, title = found
            break
        time.sleep(1)

    if thread_id is None:
        thread_id = ledger_thread_for(source)
        if thread_id:
            reused = True
            title = ""

    if thread_id is None:
        print("ERROR: no new Codex thread appeared, and no prior import of this", file=sys.stderr)
        print("       transcript exists in the ledger.", file=sys.stderr)
        noise = ("DeprecationWarning", "--trace-deprecation", "did not record an imported thread")
        for line in importer_output.splitlines():
            if line.strip() and not any(n in line for n in noise):
                print(f"       importer: {line.strip()}", file=sys.stderr)
        print("       Try 'codex resume' - a slow import can land late.", file=sys.stderr)
        return 1

    if reused:
        print("  (transcript unchanged since a prior transfer - reusing its thread)")

    codex = codex_command() or "codex"
    resume = [codex, "resume", thread_id]
    if args.model:
        resume += ["-m", args.model]
    if args.effort:
        resume += ["-c", f'model_reasoning_effort="{args.effort}"']
    resume_cmd = " ".join(f'"{p}"' if " " in p else p for p in resume)

    print()
    print(f"SUCCESS  thread: {thread_id}")
    if title:
        print(f"         title:  {title}")
    print(f"         resume: {resume_cmd}")

    target = args.open if args.open != "auto" else default_open_target()
    if target == "app":
        if open_url(f"codex://threads/{thread_id}"):
            print("Opened the Codex desktop app on this thread.")
            print("(Pick the model in the app's own dropdown.)")
    elif target == "vscode":
        if open_url(f"vscode://openai.chatgpt/local/{thread_id}"):
            print("Opened the Codex panel in VS Code on this thread.")
            print("(Pick the model in the panel's own dropdown.)")
    elif target == "terminal":
        launch_terminal(resume_cmd, thread_cwd(thread_id))
        print("Launched a terminal with the resumed session.")
    return 0


# ---------------------------------------------------------------------------
# pick
# ---------------------------------------------------------------------------

def recent_sessions(limit: int = 10) -> list[tuple[Path, float, str]]:
    if not CLAUDE_PROJECTS.is_dir():
        return []
    files = sorted(
        CLAUDE_PROJECTS.glob("*/*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    return [(p, p.stat().st_mtime, session_preview(p)) for p in files]


def session_preview(path: Path, max_len: int = 68) -> str:
    """First real user message in a transcript, for identifying it at a glance."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line:
                    break
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "user":
                    continue
                content = obj.get("message", {}).get("content")
                text = None
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = next(
                        (b.get("text") for b in content
                         if isinstance(b, dict) and b.get("type") == "text"),
                        None,
                    )
                if text:
                    text = " ".join(text.split())
                    if text.startswith("<"):  # system-reminder style payload
                        continue
                    return text[: max_len - 3] + "..." if len(text) > max_len else text
    except OSError:
        pass
    return "(no preview)"


def cmd_pick(args: argparse.Namespace) -> int:
    sessions = recent_sessions()
    if not sessions:
        print(f"No Claude sessions found under {CLAUDE_PROJECTS}", file=sys.stderr)
        return 1
    print("Recent Claude Code sessions:\n")
    for i, (path, mtime, preview) in enumerate(sessions, 1):
        stamp = time.strftime("%m-%d %H:%M", time.localtime(mtime))
        print(f"  {i:2}) {stamp}  [{path.parent.name[:28]}]  {preview}")
    print()
    try:
        raw = input(f"Session to transfer [1-{len(sessions)}, Enter=1, q=quit]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    if raw.lower().startswith("q"):
        return 0
    try:
        idx = int(raw) if raw else 1
        chosen = sessions[idx - 1][0]
    except (ValueError, IndexError):
        print("Not a valid choice.", file=sys.stderr)
        return 1
    args.source = str(chosen)
    return cmd_transfer(args)


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

def _skill_hash(directory: Path) -> str | None:
    import hashlib  # noqa: PLC0415 - only needed here

    f = directory / "SKILL.md"
    if not f.is_file():
        return None
    return hashlib.md5(f.read_bytes()).hexdigest()  # noqa: S324 - change detection, not security


def cmd_sync(args: argparse.Namespace) -> int:
    print("=== 1. AGENTS.md ===")
    src = Path(args.agents_md).expanduser() if args.agents_md else None
    if src is None or not src.is_file():
        print("  no AGENTS.md supplied (--agents-md) - skipping instruction install")
    else:
        size = src.stat().st_size
        if size > AGENTS_MD_CAP:
            print(f"  ABORT: {size} bytes exceeds Codex's {AGENTS_MD_CAP}-byte cap.", file=sys.stderr)
            return 1
        if AGENTS_MD.is_file() and AGENTS_MD.read_bytes() == src.read_bytes():
            print(f"  unchanged - no backup, no install needed ({size} bytes)")
        else:
            CODEX_HOME.mkdir(parents=True, exist_ok=True)
            if AGENTS_MD.is_file():
                backup = AGENTS_MD.with_name(f"AGENTS.md.bak-{time.strftime('%Y%m%d-%H%M%S')}")
                shutil.copy2(AGENTS_MD, backup)
                print(f"  backed up -> {backup.name}")
            shutil.copy2(src, AGENTS_MD)
            print(f"  installed AGENTS.md ({size} bytes; cap {AGENTS_MD_CAP})")

    print("\n=== 2. Skills sync: ~/.claude/skills -> ~/.agents/skills ===")
    if not CLAUDE_SKILLS.is_dir():
        print(f"  {CLAUDE_SKILLS} does not exist - nothing to sync")
    else:
        AGENTS_SKILLS.mkdir(parents=True, exist_ok=True)
        manifest_path = Path(__file__).with_name("sync-manifest.json")
        manifest: dict[str, str] = {}
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
        new = refreshed = unchanged = skipped = 0
        adapted: list[str] = []
        for d in sorted(p for p in CLAUDE_SKILLS.iterdir() if p.is_dir()):
            name = d.name
            if name in SKIP_SKILLS:
                skipped += 1
                continue
            dest = AGENTS_SKILLS / name
            src_hash = _skill_hash(d)
            if not dest.exists():
                shutil.copytree(d, dest)
                manifest[name] = _skill_hash(dest) or ""
                new += 1
                print(f"  copied NEW skill: {name}")
                continue
            dest_hash = _skill_hash(dest)
            if dest_hash == src_hash:
                unchanged += 1
                manifest[name] = dest_hash or ""
                continue
            if manifest.get(name) != dest_hash:
                # Cannot prove this copy is an unmodified sync product, so treat
                # it as a deliberate Codex adaptation and never overwrite it.
                # Guessing here once destroyed six hand-adapted skills.
                adapted.append(name)
                continue
            shutil.rmtree(dest)
            shutil.copytree(d, dest)
            manifest[name] = _skill_hash(dest) or ""
            refreshed += 1
            print(f"  refreshed from Claude side: {name}")
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"New: {new}  Refreshed: {refreshed}  Unchanged: {unchanged}  Skipped: {skipped}")
        if adapted:
            print("Codex-adapted copies left alone (review if the Claude side changed):")
            for name in adapted:
                print(f"  {name}")

    print("\n=== 3. Guard: no duplicate skill root in ~/.codex/skills ===")
    stray = [p.name for p in CODEX_SKILLS.iterdir() if p.is_dir() and p.name != ".system"] \
        if CODEX_SKILLS.is_dir() else []
    if stray:
        print("  WARN: these will DOUBLE-LIST in Codex's picker:")
        for name in stray:
            print(f"    {name}")
    else:
        print("  OK  only .system present - no duplicates possible")

    if args.check_cli:
        print("\n=== 4. Sanity checks ===")
        for cli in args.check_cli:
            found = shutil.which(cli)
            print(f"  {'OK  ' if found else 'FAIL'} {cli}" + (f" -> {found}" if found else " not on PATH"))
    return 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def cmd_doctor(_args: argparse.Namespace) -> int:
    print(f"platform      {platform.platform()}  (sys.platform={sys.platform})")
    print(f"python        {sys.version.split()[0]}")
    codex = codex_command()
    print(f"codex binary  {codex or 'NOT FOUND'}")
    print(f"node          {shutil.which('node') or 'NOT FOUND'}")
    comp = companion_script()
    print(f"importer      {comp or 'NOT FOUND (install codex-plugin-cc)'}")
    print(f"CODEX_HOME    {CODEX_HOME}{'' if CODEX_HOME.is_dir() else '  (missing)'}")
    print(f"state DB      {STATE_DB}{'' if STATE_DB.is_file() else '  (missing)'}")
    print(f"import ledger {LEDGER}{'' if LEDGER.is_file() else '  (missing)'}")
    print(f"transcripts   {CLAUDE_PROJECTS}{'' if CLAUDE_PROJECTS.is_dir() else '  (missing)'}")
    print(f"open target   {default_open_target()} (auto)")
    if STATE_DB.is_file():
        try:
            print(f"threads       {max_thread_created()} = newest created_at")
        except sqlite3.Error as exc:
            print(f"threads       unreadable: {exc}")
    sessions = recent_sessions(3)
    print(f"recent claude sessions: {len(sessions)}")
    for path, mtime, preview in sessions:
        print(f"  {time.strftime('%m-%d %H:%M', time.localtime(mtime))}  {preview[:48]}")
    return 0


# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="codex_bridge", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_transfer_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--model", default="", help="Codex model id for the resumed session")
        p.add_argument("--effort", default="", help="reasoning effort override")
        p.add_argument(
            "--open", default="auto", choices=["auto", "app", "vscode", "terminal", "none"],
            help="where to open the thread (default: auto)",
        )

    t = sub.add_parser("transfer", help="import a transcript and open Codex on it")
    t.add_argument("--source", required=True, help="path to a .jsonl under ~/.claude/projects")
    add_transfer_args(t)
    t.set_defaults(func=cmd_transfer)

    p = sub.add_parser("pick", help="choose a recent session interactively, then transfer")
    add_transfer_args(p)
    p.set_defaults(func=cmd_pick)

    s = sub.add_parser("sync", help="install AGENTS.md and sync skills into ~/.agents/skills")
    s.add_argument("--agents-md", default="", help="flattened AGENTS.md to install")
    s.add_argument("--check-cli", nargs="*", default=[], help="CLIs to verify on PATH")
    s.set_defaults(func=cmd_sync)

    d = sub.add_parser("doctor", help="report what the engine can see here")
    d.set_defaults(func=cmd_doctor)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
