from __future__ import annotations
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    patch: str
    additions: int
    deletions: int
    content: str | None = None


@dataclass(frozen=True)
class Finding:
    source: str
    severity: str
    title: str
    description: str
    path: str | None = None
    line: int | None = None
    recommendation: str | None = None
    category: str | None = None
    metadata: dict | None = None

    def to_dict(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value is not None}

