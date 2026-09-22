from __future__ import annotations

import sys

from md2pdf import native_env


def test_environment_gains_brew_library_paths(monkeypatch):
    monkeypatch.setattr(native_env, "brew_library_paths", lambda: ["/opt/homebrew/lib"])
    monkeypatch.setattr(native_env, "missing_library_paths", lambda: ["/opt/homebrew/lib"])
    monkeypatch.delenv(native_env.LIBRARY_PATH_VARIABLE, raising=False)
    env = native_env.environment_with_library_path({})
    assert env[native_env.LIBRARY_PATH_VARIABLE] == "/opt/homebrew/lib"


def test_environment_keeps_existing_library_paths(monkeypatch):
    monkeypatch.setattr(native_env, "missing_library_paths", lambda: ["/opt/homebrew/lib"])
    monkeypatch.setenv(native_env.LIBRARY_PATH_VARIABLE, "/already/there")
    env = native_env.environment_with_library_path()
    assert env[native_env.LIBRARY_PATH_VARIABLE] == "/opt/homebrew/lib:/already/there"


def test_environment_is_untouched_when_nothing_is_missing(monkeypatch):
    monkeypatch.setattr(native_env, "missing_library_paths", lambda: [])
    env = native_env.environment_with_library_path({})
    assert native_env.LIBRARY_PATH_VARIABLE not in env


def test_module_launch_of_another_tool_is_not_our_cli(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["/Users/someone/Projects/md2pdf/.venv/lib/python3.9/site-packages/pytest/__main__.py", "-q"],
    )
    assert native_env.was_launched_as_cli() is False


def test_console_script_name_is_recognized(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["/Users/someone/.venv/bin/md2pdf", "convert", "note.md"])
    assert native_env.was_launched_as_cli() is False


def test_relaunch_is_never_requested_inside_a_test_runner(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["/Users/someone/.venv/bin/md2pdf", "convert", "note.md"])
    monkeypatch.setattr(native_env.sys, "platform", "darwin")
    monkeypatch.setattr(native_env, "missing_library_paths", lambda: ["/opt/homebrew/lib"])
    assert native_env.cli_relaunch_needed() is False


def test_relaunch_is_not_requested_on_other_platforms(monkeypatch):
    monkeypatch.setattr(native_env.sys, "platform", "linux")
    monkeypatch.setattr(native_env, "missing_library_paths", lambda: [])
    assert native_env.cli_relaunch_needed() is False


def test_library_path_hint_mentions_the_variable(monkeypatch):
    monkeypatch.setattr(native_env, "missing_library_paths", lambda: ["/opt/homebrew/lib"])
    hint = native_env.library_path_hint()
    assert native_env.LIBRARY_PATH_VARIABLE in hint
    assert "/opt/homebrew/lib" in hint
