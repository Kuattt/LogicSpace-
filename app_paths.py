"""Per-user LogicSpace data location, independent of the installation folder."""
from __future__ import annotations

import os
from pathlib import Path
import sys


def user_data_dir() -> Path:
    """Keep the existing Linux path; use LocalAppData for Windows installs."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "LogicSpace"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "logicspace"
