from __future__ import annotations
from pathlib import PurePosixPath


def safe_relative_path(path: str) -> str | None:
    normalized = str(PurePosixPath(path))
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
        return None
    return normalized

