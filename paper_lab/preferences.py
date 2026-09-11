"""Small machine-local preferences that do not belong in a paper workspace."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path


def _directory() -> Path:
    override = os.getenv("PAPER_LAB_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Paper Lab"
    return Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "paper-lab"


def recent_workspace() -> str | None:
    """Return only a previously initialized Paper Lab workspace."""
    try:
        value = json.loads((_directory() / "launcher.json").read_text())
        root = Path(value["recent_workspace"]).expanduser().resolve()
        marker = json.loads((root / "workspace.json").read_text())
        if marker == {"schema_version": 1, "application": "paper-lab"}:
            return str(root)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return None


def remember_workspace(path: str) -> None:
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "launcher.json"
    temporary = directory / "launcher.json.tmp"
    temporary.write_text(
        json.dumps({"recent_workspace": path}, ensure_ascii=False, indent=2) + "\n"
    )
    temporary.replace(target)
