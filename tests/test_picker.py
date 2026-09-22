from __future__ import annotations

import subprocess
import types
from pathlib import Path

import pytest

from md2pdf import picker


def completed(returncode, stdout="", stderr=""):
    return subprocess.CompletedProcess(["python"], returncode, stdout=stdout, stderr=stderr)


def test_dialog_script_is_valid_python():
    compile(picker.DIALOG_SCRIPT, "<folder dialog>", "exec")


def test_the_dialog_reports_the_tk_version_it_can_start():
    ok, message = picker.probe()
    if not ok:
        pytest.skip(f"tkinter cannot start here: {message}")
    assert message.startswith("Tk ")


def test_choose_directory_returns_the_picked_folder(monkeypatch):
    monkeypatch.setattr(
        picker.subprocess, "run", lambda *args, **kwargs: completed(0, "/tmp/some where/Reports\n")
    )
    chosen, reason = picker.choose_directory("Pick a folder")
    assert chosen == Path("/tmp/some where/Reports")
    assert reason == ""


def test_choose_directory_treats_a_cancel_as_nothing_picked(monkeypatch):
    monkeypatch.setattr(picker.subprocess, "run", lambda *args, **kwargs: completed(0, ""))
    chosen, reason = picker.choose_directory()
    assert chosen is None
    assert reason == ""


def test_choose_directory_surfaces_the_dialog_error(monkeypatch):
    message = "tkinter is not available in this Python: no module named tkinter\n"
    monkeypatch.setattr(picker.subprocess, "run", lambda *args, **kwargs: completed(3, "", message))
    chosen, reason = picker.choose_directory()
    assert chosen is None
    assert "tkinter is not available" in reason


def test_choose_directory_reports_a_timeout(monkeypatch):
    def boom(*args, **kwargs):
        raise picker.subprocess.TimeoutExpired(cmd="python", timeout=1)

    monkeypatch.setattr(picker.subprocess, "run", boom)
    chosen, reason = picker.choose_directory(timeout=1)
    assert chosen is None
    assert "time limit" in reason


def test_choose_directory_without_a_usable_python(monkeypatch):
    monkeypatch.setattr(picker, "sys", types.SimpleNamespace(executable="/nonexistent/python"))
    chosen, reason = picker.choose_directory(timeout=10)
    assert chosen is None
    assert "cannot start the folder dialog" in reason


def test_choose_directory_without_tkinter(monkeypatch):
    monkeypatch.setattr(picker, "dialog_available", lambda: False)
    chosen, reason = picker.choose_directory()
    assert chosen is None
    assert "tkinter" in reason
