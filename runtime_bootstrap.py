from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable


def _normalize_path(path: str | os.PathLike[str] | None) -> str | None:
    if not path:
        return None
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def get_relaunch_command(
    project_dir,
    current_executable=None,
    current_version=None,
    which: Callable[[str], str | None] | None = None,
):
    project_path = Path(project_dir)
    current_executable = current_executable or sys.executable
    current_version = current_version or sys.version_info[:2]
    which = which or shutil.which

    repo_python = project_path / ".venv311" / "Scripts" / "python.exe"
    if repo_python.exists():
        if _normalize_path(current_executable) == _normalize_path(repo_python):
            return None
        return [str(repo_python)]

    if tuple(current_version[:2]) == (3, 11):
        return None

    py_launcher = which("py")
    if not py_launcher:
        return None

    return [py_launcher, "-3.11"]


def maybe_relaunch(
    project_dir,
    argv=None,
    current_executable=None,
    current_version=None,
    cwd=None,
    env=None,
    which: Callable[[str], str | None] | None = None,
    popen=subprocess.Popen,
):
    argv = list(argv if argv is not None else sys.argv)
    relaunch_command = get_relaunch_command(
        project_dir=project_dir,
        current_executable=current_executable,
        current_version=current_version,
        which=which,
    )
    if not relaunch_command:
        return False

    popen(relaunch_command + argv, cwd=cwd, env=env)
    return True
