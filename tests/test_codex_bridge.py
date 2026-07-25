"""Tests for the cross-platform engine.

These run on every OS in CI. The point is to verify the platform-specific logic
without needing that platform: the Windows path rules are pure functions, so they
can be tested on Linux by reloading the module with sys.platform patched.

Run:  python -m pytest tests/ -q        (or: python tests/test_codex_bridge.py)
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "plugins" / "codex-bridge" / "scripts"
sys.path.insert(0, str(ENGINE))

import codex_bridge  # noqa: E402


def _reload_as(monkeypatch_platform: str):
    """Reload the engine as if running on a given sys.platform."""
    real = sys.platform
    sys.platform = monkeypatch_platform
    try:
        return importlib.reload(codex_bridge)
    finally:
        sys.platform = real


# ---------------------------------------------------------------------------
# normalize_ledger_path - the heart of the #513 workaround
# ---------------------------------------------------------------------------

def test_windows_strips_extended_length_prefix():
    cb = _reload_as("win32")
    ledger = r"\\?\C:\Users\someone\.claude\projects\C--\abc.jsonl"
    plain = r"C:\Users\someone\.claude\projects\C--\abc.jsonl"
    assert cb.normalize_ledger_path(ledger) == cb.normalize_ledger_path(plain)


def test_windows_comparison_is_case_insensitive():
    cb = _reload_as("win32")
    assert cb.normalize_ledger_path(r"\\?\C:\Users\Someone\X.jsonl") == \
           cb.normalize_ledger_path(r"c:\users\someone\x.jsonl")


def test_windows_handles_unc_prefix():
    cb = _reload_as("win32")
    assert cb.normalize_ledger_path(r"\\?\UNC\server\share\x.jsonl") == \
           cb.normalize_ledger_path(r"\\server\share\x.jsonl")


def test_windows_still_distinguishes_different_paths():
    cb = _reload_as("win32")
    assert cb.normalize_ledger_path(r"C:\a\one.jsonl") != cb.normalize_ledger_path(r"C:\a\two.jsonl")


def test_posix_is_effectively_identity_and_case_sensitive():
    cb = _reload_as("linux")
    p = "/home/someone/.claude/projects/proj/abc.jsonl"
    assert cb.normalize_ledger_path(p) == p
    # POSIX filesystems are case-sensitive; do not fold case there.
    assert cb.normalize_ledger_path("/home/A") != cb.normalize_ledger_path("/home/a")


# ---------------------------------------------------------------------------
# ledger lookup (the dedupe case)
# ---------------------------------------------------------------------------

def test_ledger_lookup_matches_prefixed_record(tmp_path, monkeypatch):
    cb = _reload_as("win32")
    source = r"C:\Users\someone\.claude\projects\C--\s.jsonl"
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"records": [
        {"source_path": r"\\?\C:\Users\someone\.claude\projects\C--\s.jsonl",
         "imported_thread_id": "thread-old", "imported_at": 100},
        {"source_path": r"\\?\C:\Users\someone\.claude\projects\C--\s.jsonl",
         "imported_thread_id": "thread-new", "imported_at": 200},
        {"source_path": r"\\?\C:\Users\someone\.claude\projects\C--\other.jsonl",
         "imported_thread_id": "thread-other", "imported_at": 300},
    ]}), encoding="utf-8")
    monkeypatch.setattr(cb, "LEDGER", ledger)
    # Most recent import for that exact source wins; other sources are ignored.
    assert cb.ledger_thread_for(Path(source)) == "thread-new"


def test_ledger_lookup_returns_none_when_absent(tmp_path, monkeypatch):
    cb = _reload_as("linux")
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"records": []}), encoding="utf-8")
    monkeypatch.setattr(cb, "LEDGER", ledger)
    assert cb.ledger_thread_for(Path("/tmp/nope.jsonl")) is None


def test_ledger_lookup_survives_corrupt_file(tmp_path, monkeypatch):
    cb = _reload_as("linux")
    ledger = tmp_path / "ledger.json"
    ledger.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(cb, "LEDGER", ledger)
    assert cb.ledger_thread_for(Path("/tmp/x.jsonl")) is None


# ---------------------------------------------------------------------------
# state DB is opened read-only - we must never be able to corrupt Codex state
# ---------------------------------------------------------------------------

def test_state_db_is_opened_read_only(tmp_path, monkeypatch):
    import sqlite3

    cb = importlib.reload(codex_bridge)
    db = tmp_path / "state.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE threads (id TEXT, created_at INT, title TEXT, cwd TEXT)")
    con.execute("INSERT INTO threads VALUES ('t1', 500, 'Hello', NULL)")
    con.commit()
    con.close()
    monkeypatch.setattr(cb, "STATE_DB", db)

    assert cb.max_thread_created() == 500
    assert cb.thread_created_after(400) == ("t1", "Hello")
    assert cb.thread_created_after(600) is None

    ro = cb._connect_ro()
    try:
        raised = False
        try:
            ro.execute("INSERT INTO threads VALUES ('t2', 600, 'Nope', NULL)")
            ro.commit()
        except sqlite3.OperationalError:
            raised = True
        assert raised, "write to the state DB should be rejected"
    finally:
        ro.close()


def test_missing_state_db_degrades_gracefully(tmp_path, monkeypatch):
    cb = importlib.reload(codex_bridge)
    monkeypatch.setattr(cb, "STATE_DB", tmp_path / "does-not-exist.sqlite")
    assert cb.max_thread_created() == 0
    assert cb.thread_created_after(0) is None
    assert cb.thread_cwd("anything") is None


# ---------------------------------------------------------------------------
# session preview / picker helpers
# ---------------------------------------------------------------------------

def test_session_preview_finds_first_real_user_message(tmp_path):
    cb = importlib.reload(codex_bridge)
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join([
        json.dumps({"type": "assistant", "message": {"content": "ignore me"}}),
        json.dumps({"type": "user", "message": {"content": "<system-reminder>skip</system-reminder>"}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "text", "text": "refactor   the auth\nmiddleware"}]}}),
    ]), encoding="utf-8")
    # Whitespace collapsed, system-reminder-style payload skipped.
    assert cb.session_preview(f) == "refactor the auth middleware"


def test_session_preview_handles_unreadable_file(tmp_path):
    cb = importlib.reload(codex_bridge)
    assert cb.session_preview(tmp_path / "missing.jsonl") == "(no preview)"


def test_skip_skills_excludes_to_codex():
    cb = importlib.reload(codex_bridge)
    # A "switch to Codex" skill must never be synced into Codex itself.
    assert "to-codex" in cb.SKIP_SKILLS


def test_agents_md_cap_matches_codex_default():
    cb = importlib.reload(codex_bridge)
    assert cb.AGENTS_MD_CAP == 32768


if __name__ == "__main__":  # allow running without pytest
    try:
        import pytest
    except ImportError:
        print("pytest not installed; running the no-fixture tests only")
        passed = failed = 0
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and fn.__code__.co_argcount == 0:
                try:
                    fn()
                    passed += 1
                except AssertionError as exc:
                    failed += 1
                    print(f"FAIL {name}: {exc}")
        print(f"{passed} passed, {failed} failed")
        sys.exit(1 if failed else 0)
    sys.exit(pytest.main([__file__, "-q"]))
