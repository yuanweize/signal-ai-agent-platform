"""Application version utilities.

Single source of truth: backend/pyproject.toml -> [project].version
Optional override: APP_VERSION environment variable.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
import tomllib


@lru_cache(maxsize=1)
def get_app_version() -> str:
    env_version = os.getenv("APP_VERSION", "").strip()
    if env_version:
        return env_version

    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        project = data.get("project", {})
        version = str(project.get("version", "")).strip()
        if version:
            return version
    except Exception:
        pass

    return "0.0.0"
