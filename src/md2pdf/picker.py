from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

DIALOG_SCRIPT = """
import sys

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception as error:
    sys.stderr.write("tkinter is not available in this Python: %s" % error)
    sys.exit(3)

mode = sys.argv[1] if len(sys.argv) > 1 else "choose"
title = sys.argv[2] if len(sys.argv) > 2 else "Choose a folder"
initial = sys.argv[3] if len(sys.argv) > 3 else ""

try:
    root = tk.Tk()
except Exception as error:
    sys.stderr.write("cannot start Tk: %s" % error)
    sys.exit(4)

root.withdraw()
root.update()

if mode == "probe":
    sys.stdout.write("Tk %s" % root.tk.call("info", "patchlevel"))
    root.destroy()
    sys.exit(0)

try:
    try:
        root.wm_attributes("-topmost", 1)
    except Exception:
        pass
    options = {"parent": root, "title": title}
    if initial:
        options["initialdir"] = initial
    chosen = filedialog.askdirectory(**options)
except Exception as error:
    sys.stderr.write("the folder dialog failed: %s" % error)
    sys.exit(5)

root.destroy()
sys.stdout.write(chosen or "")
"""

DEFAULT_TITLE = "Choose a folder"
TIMEOUT = 900.0


def dialog_available() -> bool:
    return importlib.util.find_spec("tkinter") is not None


def run_dialog(
    mode: str = "choose",
    title: str = DEFAULT_TITLE,
    initial: str | Path | None = None,
    timeout: float = TIMEOUT,
) -> tuple[subprocess.CompletedProcess | None, str]:
    command = [sys.executable, "-c", DIALOG_SCRIPT, mode, title, str(initial or "")]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "the folder dialog did not return within the time limit"
    except (OSError, ValueError) as error:
        return None, f"cannot start the folder dialog: {error}"
    if completed.returncode != 0:
        lines = (completed.stderr or "").strip().splitlines()
        reason = lines[-1] if lines else f"the folder dialog exited with code {completed.returncode}"
        return None, reason
    return completed, ""


def choose_directory(
    title: str = DEFAULT_TITLE,
    initial: str | Path | None = None,
    timeout: float = TIMEOUT,
) -> tuple[Path | None, str]:
    if not dialog_available():
        return None, "this Python has no tkinter, so the system folder dialog cannot be shown"
    completed, reason = run_dialog("choose", title, initial, timeout)
    if completed is None:
        return None, reason
    chosen = (completed.stdout or "").strip()
    return (Path(chosen).expanduser() if chosen else None), ""


def probe(timeout: float = 60.0) -> tuple[bool, str]:
    completed, reason = run_dialog("probe", DEFAULT_TITLE, None, timeout)
    if completed is None:
        return False, reason
    return True, (completed.stdout or "").strip()
