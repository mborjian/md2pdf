from __future__ import annotations

import os
import sys
from pathlib import Path

BREW_LIBRARY_DIRS = (
    "/opt/homebrew/lib",
    "/usr/local/lib",
    "/home/linuxbrew/.linuxbrew/lib",
)
LIBRARY_PATH_VARIABLE = "DYLD_FALLBACK_LIBRARY_PATH"
RELAUNCH_SENTINEL = "MD2PDF_RELAUNCHED"


def brew_library_paths() -> list[str]:
    return [item for item in BREW_LIBRARY_DIRS if Path(item).is_dir()]


def missing_library_paths() -> list[str]:
    if sys.platform != "darwin":
        return []
    current = os.environ.get(LIBRARY_PATH_VARIABLE, "").split(":")
    return [item for item in brew_library_paths() if item not in current]


def environment_with_library_path(env: dict[str, str] | None = None) -> dict[str, str]:
    target = dict(os.environ if env is None else env)
    missing = missing_library_paths()
    if not missing:
        return target
    existing = target.get(LIBRARY_PATH_VARIABLE, "")
    target[LIBRARY_PATH_VARIABLE] = ":".join(missing + ([existing] if existing else []))
    return target


def was_launched_as_cli() -> bool:
    if "pytest" in sys.modules:
        return False
    if Path(sys.argv[0]).name in {"md2pdf", "md2pdf.exe"}:
        return True
    main_module = sys.modules.get("__main__")
    spec = getattr(main_module, "__spec__", None)
    return getattr(spec, "name", "") == "md2pdf.__main__"


def cli_relaunch_needed() -> bool:
    if sys.platform != "darwin" or os.environ.get(RELAUNCH_SENTINEL):
        return False
    return bool(was_launched_as_cli() and missing_library_paths())


def relaunch_with_library_path(arguments: list[str]) -> None:
    env = environment_with_library_path()
    if env.get(LIBRARY_PATH_VARIABLE) == os.environ.get(LIBRARY_PATH_VARIABLE, ""):
        return
    env[RELAUNCH_SENTINEL] = "1"
    os.execve(sys.executable, [sys.executable, "-m", "md2pdf", *arguments], env)


def library_path_hint() -> str:
    paths = missing_library_paths() or brew_library_paths()
    if not paths:
        return ""
    return f'{LIBRARY_PATH_VARIABLE}="{":".join(paths)}:${{{LIBRARY_PATH_VARIABLE}}}"'
