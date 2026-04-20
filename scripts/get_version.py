#!/usr/bin/env python3
"""Print project version from backend/pyproject.toml."""

from __future__ import annotations

from pathlib import Path
import tomllib


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = repo_root / "backend" / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    version = str(data["project"]["version"]).strip()
    if not version:
        raise SystemExit("empty version")
    print(version)


if __name__ == "__main__":
    main()
