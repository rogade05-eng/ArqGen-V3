"""Resource location (dev tree and PyInstaller frozen bundle).

resources/ is bundled with --add-data; when frozen it lives under
sys._MEIPASS. This helper is the ONLY sanctioned way to reach data files.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_root() -> str:
    if is_frozen():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidate = os.path.join(base, "resources")
        if os.path.isdir(candidate):
            return candidate
        return base
    return os.path.join(PROJECT_ROOT, "resources")


def resource_path(*parts: str) -> str:
    return os.path.join(resource_root(), *parts)


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def default_log_dir() -> str:
    return ensure_dir(os.path.join(os.getcwd(), "logs"))


def default_backup_dir() -> str:
    return ensure_dir(os.path.join(os.getcwd(), "backups"))


def default_output_dir() -> str:
    return ensure_dir(os.path.join(os.getcwd(), "output"))


__all__ = [
    "PROJECT_ROOT", "is_frozen", "resource_root", "resource_path",
    "ensure_dir", "default_log_dir", "default_backup_dir", "default_output_dir",
]
