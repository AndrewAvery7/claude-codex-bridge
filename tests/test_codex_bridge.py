"""Tests for the cross-platform engine.

These run on every OS in CI. The point is to verify the platform-specific logic
without needing that platform: the Windows path rules are pure functions, so they
can be tested on Linux by reloading the module with sys.platform patched.

Run:  python -m pytest tests/ -q        (or: python tests/test_codex_bridge.py)
"""

from __future__ import annotations

import importlib
import json
import os
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


# ---------------------------------------------------------------------------
# a failed transfer must say why - the filter used to swallow the whole answer
# ---------------------------------------------------------------------------

def test_diagnosis_always_reports_the_exit_code():
    cb = importlib.reload(codex_bridge)
    assert cb.importer_diagnosis("", 0)[0] == "importer exit code: 0"
    assert cb.importer_diagnosis("boom", 3)[0] == "importer exit code: 3"


def test_diagnosis_shows_real_importer_output():
    cb = importlib.reload(codex_bridge)
    lines = cb.importer_diagnosis("Error: ENOENT missing thing\n", 1)
    assert "importer: Error: ENOENT missing thing" in lines
    assert not any("known noise" in ln for ln in lines)


def test_diagnosis_shows_noise_raw_when_it_is_all_there_is():
    cb = importlib.reload(codex_bridge)
    # Both of these are filtered from normal reporting. Filtering them here
    # would leave an error message containing no evidence whatsoever.
    only_noise = (
        "(node:1) [DEP0190] DeprecationWarning: something\n"
        "Codex reported that the Claude import completed, but did not record an "
        "imported thread.\n"
    )
    lines = cb.importer_diagnosis(only_noise, 1)
    assert any("known noise" in ln for ln in lines)
    assert any("did not record an imported thread" in ln for ln in lines)


def test_diagnosis_says_so_when_the_importer_was_silent():
    cb = importlib.reload(codex_bridge)
    lines = cb.importer_diagnosis("   \n\n", 0)
    assert any("printed nothing at all" in ln for ln in lines)


# ---------------------------------------------------------------------------
# import detection - a slow import is not a failed one
# ---------------------------------------------------------------------------

class _Clock:
    """Fake monotonic clock; every sleep advances it, so tests never wait."""

    def __init__(self):
        self.t = 0.0

    def sleep(self, seconds):
        self.t += seconds

    def monotonic(self):
        return self.t


def test_wait_returns_a_thread_that_lands_late(monkeypatch):
    cb = importlib.reload(codex_bridge)
    clock = _Clock()
    # The thread row appears 30s in - well past the old fixed 15-tick window.
    monkeypatch.setattr(cb, "thread_created_after",
                        lambda before: ("t-late", "Landed late") if clock.t >= 30 else None)
    monkeypatch.setattr(cb, "ledger_thread_for", lambda source: None)
    got = cb.wait_for_import(0, None, Path("/x.jsonl"), 60,
                             sleep=clock.sleep, monotonic=clock.monotonic)
    assert got == ("t-late", "Landed late")


def test_wait_gives_up_after_the_window(monkeypatch):
    cb = importlib.reload(codex_bridge)
    clock = _Clock()
    monkeypatch.setattr(cb, "thread_created_after", lambda before: None)
    monkeypatch.setattr(cb, "ledger_thread_for", lambda source: None)
    assert cb.wait_for_import(0, None, Path("/x.jsonl"), 5,
                              sleep=clock.sleep, monotonic=clock.monotonic) is None
    assert clock.t >= 5


def test_wait_accepts_a_new_ledger_record_as_the_import(monkeypatch):
    cb = importlib.reload(codex_bridge)
    clock = _Clock()
    # No thread row ever appears, but the ledger gains a record that was not
    # there when we started - that is this import, landing late.
    monkeypatch.setattr(cb, "thread_created_after", lambda before: None)
    monkeypatch.setattr(cb, "ledger_thread_for",
                        lambda source: "t-new" if clock.t >= 10 else "t-old")
    got = cb.wait_for_import(0, "t-old", Path("/x.jsonl"), 60,
                             sleep=clock.sleep, monotonic=clock.monotonic)
    assert got == ("t-new", "")


def test_wait_does_not_mistake_a_prior_ledger_record_for_this_import(monkeypatch):
    cb = importlib.reload(codex_bridge)
    clock = _Clock()
    # The only ledger record is the one from a previous transfer. That is the
    # dedupe case, and it is the caller's to report - not a fresh import.
    monkeypatch.setattr(cb, "thread_created_after", lambda before: None)
    monkeypatch.setattr(cb, "ledger_thread_for", lambda source: "t-old")
    assert cb.wait_for_import(0, "t-old", Path("/x.jsonl"), 5,
                              sleep=clock.sleep, monotonic=clock.monotonic) is None


def _parse(argv):
    """Run the engine's own parser and capture the parsed args, running nothing."""
    cb = importlib.reload(codex_bridge)
    holder = {}
    real = cb.cmd_transfer
    cb.cmd_transfer = lambda args: holder.setdefault("args", args) and 0
    try:
        cb.main(argv)
    finally:
        cb.cmd_transfer = real
    return holder["args"]


def test_wait_window_is_adjustable_and_defaults_to_sixty():
    assert _parse(["transfer", "--source", "x.jsonl"]).wait == 60
    assert _parse(["transfer", "--source", "x.jsonl", "--wait", "5"]).wait == 5


# ---------------------------------------------------------------------------
# Windows binary resolution - a path can be on PATH and still refuse to run
# ---------------------------------------------------------------------------

def test_which_all_returns_every_path_hit_not_just_the_first(tmp_path, monkeypatch):
    cb = _reload_as("linux")
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (first / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
    (second / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("PATH", os.pathsep.join([str(first), str(second)]))
    found = cb.which_all("codex")
    # Order matters: PATH order is the caller's preference order.
    assert found == [str(first / "codex"), str(second / "codex")]


def test_codex_command_survives_a_machine_with_no_codex(tmp_path, monkeypatch):
    cb = _reload_as("linux")
    # A machine with no codex at all is a supported state - `doctor` calls this
    # precisely to report NOT FOUND. Walking an empty candidate list used to
    # raise UnboundLocalError, which CI's doctor smoke-run caught and these
    # tests did not.
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(cb, "HOME", tmp_path)
    result = cb.codex_command()
    assert result is None or isinstance(result, str)


def test_which_all_is_empty_when_nothing_matches(tmp_path, monkeypatch):
    cb = _reload_as("linux")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert cb.which_all("codex") == []


def test_npm_appdata_is_only_rejected_inside_a_packaged_container(monkeypatch):
    cb = _reload_as("win32")
    npm_codex = r"C:\Users\someone\AppData\Roaming\npm\codex.cmd"

    # Outside a container %APPDATA%\npm is an ordinary executable directory.
    monkeypatch.setenv("APPDATA", r"C:\Users\someone\AppData\Roaming")
    assert not cb._is_unusable_windows_path(npm_codex)

    # Inside one it is the app's private store, invisible to other processes.
    monkeypatch.setenv(
        "APPDATA",
        r"C:\Users\someone\AppData\Local\Packages\Some.App_abc\LocalCache\Roaming",
    )
    assert cb._is_unusable_windows_path(
        r"C:\Users\someone\AppData\Local\Packages\Some.App_abc\LocalCache\Roaming\npm\codex.cmd"
    )


def test_program_files_windowsapps_payload_is_rejected():
    cb = _reload_as("win32")
    # Not the alias directory - the real MSIX payload, which Windows refuses to
    # execute from another process. Observed on a real machine 2026-08-22:
    # `codex --version` there exits 1 with access denied.
    payload = (r"C:\Program Files\WindowsApps\OpenAI.Codex_26.818.5229.0_x64__2p2nqsd0c76g0"
               r"\app\resources\codex.exe")
    assert cb._is_unusable_windows_path(payload)


def test_windowsapps_alias_is_rejected():
    cb = _reload_as("win32")
    # A Store app-execution alias: resolves on PATH, then a spawned process is
    # denied with "Access is denied". Observed on a real machine 2026-08-22.
    alias = r"C:\Users\someone\AppData\Local\Microsoft\WindowsApps\codex.exe"
    assert cb._is_unusable_windows_path(alias)
    assert cb._is_unusable_windows_path(alias.lower())
    assert cb._is_unusable_windows_path(alias.replace("\\", "/"))


def test_real_looking_exe_is_accepted(tmp_path):
    cb = _reload_as("win32")
    real = tmp_path / "codex.exe"
    real.write_bytes(b"MZ not really an exe, but not empty either")
    assert not cb._is_unusable_windows_path(str(real))


def test_zero_length_binary_is_rejected(tmp_path):
    cb = _reload_as("win32")
    # An unresolved reparse point reads as a zero-length file; a real
    # executable never does.
    stub = tmp_path / "codex.exe"
    stub.write_bytes(b"")
    assert cb._is_unusable_windows_path(str(stub))


# ---------------------------------------------------------------------------
# picker choice - an out-of-range answer must be refused, never reinterpreted
# ---------------------------------------------------------------------------

def test_choice_index_accepts_valid_picks():
    cb = importlib.reload(codex_bridge)
    assert cb.choice_index("1", 3) == 0
    assert cb.choice_index("3", 3) == 2
    assert cb.choice_index("", 3) == 0      # Enter means the most recent session
    assert cb.choice_index(" 2 ".strip(), 3) == 1


def test_choice_index_rejects_out_of_range_and_junk():
    cb = importlib.reload(codex_bridge)
    # Python would read these as list indices and transfer a session the user
    # never picked: 0 -> the oldest, -1 -> the second-to-oldest.
    assert cb.choice_index("0", 3) is None
    assert cb.choice_index("-1", 3) is None
    assert cb.choice_index("4", 3) is None
    assert cb.choice_index("abc", 3) is None


# ---------------------------------------------------------------------------
# macOS terminal launch - two layers of quoting, both of which must hold
# ---------------------------------------------------------------------------

def test_applescript_quotes_workdir_and_escapes_command():
    cb = importlib.reload(codex_bridge)
    script = cb.applescript_do_script('"/Users/me/My Tools/codex" resume abc-123',
                                      "/Users/me/My Projects")
    # The shell must see one argument for cd, not two.
    assert "cd '/Users/me/My Projects'" in script
    # The command's own quotes must not terminate the AppleScript string early:
    # everything between the outer quotes is the script, so the only unescaped
    # double quotes in the whole line are the four AppleScript delimiters.
    assert script.count('"') - script.count('\\"') == 4
    assert '\\"/Users/me/My Tools/codex\\"' in script


# ---------------------------------------------------------------------------
# recent_sessions - the transcripts directory is written while we read it
# ---------------------------------------------------------------------------

def test_recent_sessions_skips_unreadable_entries(tmp_path, monkeypatch):
    cb = importlib.reload(codex_bridge)
    proj = tmp_path / "proj"
    proj.mkdir()
    real = proj / "real.jsonl"
    real.write_text("{}", encoding="utf-8")
    try:
        # A dangling symlink: glob still lists it, but stat() raises.
        (proj / "vanished.jsonl").symlink_to(proj / "gone.jsonl")
    except (OSError, NotImplementedError):  # Windows without symlink privilege
        pass
    monkeypatch.setattr(cb, "CLAUDE_PROJECTS", tmp_path)
    found = cb.recent_sessions()
    assert [p.name for p, _, _ in found] == ["real.jsonl"]


# ---------------------------------------------------------------------------
# the path rule is implemented twice - the copies must not drift apart
# ---------------------------------------------------------------------------

def _load_query_helper():
    import importlib.util

    path = ENGINE / "codex-thread-query.py"
    spec = importlib.util.spec_from_file_location("codex_thread_query", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_query_helper_path_rule_matches_the_engine():
    q = _load_query_helper()
    cases = [
        r"\\?\C:\Users\Someone\.claude\projects\p\a.jsonl",
        r"C:\Users\someone\.claude\projects\p\a.jsonl",
        r"\\?\UNC\server\share\a.jsonl",
        r"\\server\share\a.jsonl",
        "/home/someone/.claude/projects/p/a.jsonl",
    ]
    for plat in ("win32", "linux"):
        cb = _reload_as(plat)
        real = sys.platform
        sys.platform = plat
        try:
            for c in cases:
                assert q.normalize(c) == cb.normalize_ledger_path(c), (plat, c)
        finally:
            sys.platform = real


def test_query_helper_matches_unc_ledger_records():
    q = _load_query_helper()
    real = sys.platform
    sys.platform = "win32"
    try:
        # \\?\UNC\server\share and \\server\share are the same location.
        assert q.normalize(r"\\?\UNC\srv\share\x.jsonl") == q.normalize(r"\\srv\share\x.jsonl")
    finally:
        sys.platform = real


def test_query_helper_ledger_tolerates_bad_input(tmp_path, monkeypatch):
    q = _load_query_helper()
    ledger = tmp_path / "ledger.json"
    monkeypatch.setattr(q, "LEDGER", ledger)

    # A record with no imported_thread_id is a miss, not a KeyError.
    ledger.write_text(json.dumps({"records": [
        {"source_path": "/p/x.jsonl", "imported_at": 5},
    ]}), encoding="utf-8")
    assert q.main(["--ledger", "/p/x.jsonl"]) == 1

    # A half-written ledger is a miss, not a JSONDecodeError.
    ledger.write_text("{not json", encoding="utf-8")
    assert q.main(["--ledger", "/p/x.jsonl"]) == 1

    # A good record still resolves.
    ledger.write_text(json.dumps({"records": [
        {"source_path": "/p/x.jsonl", "imported_thread_id": "t-1", "imported_at": 5},
    ]}), encoding="utf-8")
    assert q.main(["--ledger", "/p/x.jsonl"]) == 0


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
