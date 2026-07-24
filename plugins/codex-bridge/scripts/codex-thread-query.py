"""Query Codex's thread database (read-only).

Usage:
  codex-thread-query.py --max-created        print newest thread created_at epoch (0 if none)
  codex-thread-query.py --after <epoch>      print id|created_at|title of newest thread created AFTER epoch
  codex-thread-query.py --recent [N]         print N most recent threads: id|created_at|title
  codex-thread-query.py --ledger <source>    print thread id previously imported for this Claude
                                             transcript path (Codex dedupes unchanged re-imports)
"""
import json
import sqlite3
import sys
from pathlib import Path

DB = Path.home() / ".codex" / "state_5.sqlite"
LEDGER = Path.home() / ".codex" / "external_agent_session_imports.json"


def normalize(p):
    # Ledger paths carry the \\?\ extended prefix and mixed separators
    return str(p).replace("\\\\?\\", "").replace("/", "\\").lower()


def connect():
    # Read-only URI so we can never corrupt Codex state, even mid-write
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def main(argv):
    if "--ledger" in argv:
        source = normalize(argv[argv.index("--ledger") + 1])
        if not LEDGER.exists():
            return 1
        records = json.loads(LEDGER.read_text(encoding="utf-8")).get("records", [])
        hits = [r for r in records if normalize(r.get("source_path", "")) == source]
        if not hits:
            return 1
        best = max(hits, key=lambda r: r.get("imported_at", 0))
        print(f"{best['imported_thread_id']}|{best.get('imported_at', 0)}|")
        return 0
    if not DB.exists():
        print("ERROR: Codex state DB not found", file=sys.stderr)
        return 2
    con = connect()
    try:
        if "--max-created" in argv:
            row = con.execute("SELECT MAX(created_at) FROM threads").fetchone()
            print(row[0] or 0)
            return 0
        if "--after" in argv:
            after = int(argv[argv.index("--after") + 1])
            row = con.execute(
                "SELECT id, created_at, COALESCE(title,'') FROM threads "
                "WHERE created_at > ? ORDER BY created_at DESC LIMIT 1",
                (after,),
            ).fetchone()
            if row:
                print(f"{row[0]}|{row[1]}|{row[2]}")
                return 0
            return 1  # no new thread
        if "--cwd" in argv:
            tid = argv[argv.index("--cwd") + 1]
            row = con.execute("SELECT cwd FROM threads WHERE id = ?", (tid,)).fetchone()
            if row and row[0]:
                print(str(row[0]).replace("\\\\?\\", ""))
                return 0
            return 1
        if "--recent" in argv:
            i = argv.index("--recent")
            n = int(argv[i + 1]) if len(argv) > i + 1 and argv[i + 1].isdigit() else 5
            for row in con.execute(
                "SELECT id, created_at, COALESCE(title,'') FROM threads "
                "ORDER BY created_at DESC LIMIT ?",
                (n,),
            ):
                print(f"{row[0]}|{row[1]}|{row[2]}")
            return 0
    finally:
        con.close()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
