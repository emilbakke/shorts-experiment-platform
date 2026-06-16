#!/usr/bin/env python3
"""Ensure repository-local backend Python deps match this Python ABI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_DEPS = REPO_ROOT / f".python_deps_{sys.version_info.major}{sys.version_info.minor}"
REQUIREMENTS = REPO_ROOT / "backend" / "requirements-test.txt"


def deps_importable() -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PY_DEPS}:{REPO_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}"
    probe = "import fastapi, pydantic, pydantic_core, sqlalchemy, psycopg, pytest, uvicorn"
    return subprocess.run([sys.executable, "-c", probe], cwd=REPO_ROOT, env=env).returncode == 0


def main() -> None:
    if deps_importable():
        return
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            "--target",
            str(PY_DEPS),
            "-r",
            str(REQUIREMENTS),
        ],
        cwd=REPO_ROOT,
    )


if __name__ == "__main__":
    main()
