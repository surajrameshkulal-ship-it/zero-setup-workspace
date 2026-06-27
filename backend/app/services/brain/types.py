from __future__ import annotations

from dataclasses import dataclass, field


def evidence(source: str, detail: str, reference: str | None = None) -> dict:
    return {"source": source, "detail": detail, "reference": reference}


def action(title: str, rationale: str, brain: str) -> dict:
    return {"title": title, "rationale": rationale, "brain": brain}


@dataclass
class BrainResult:
    brain: str
    confidence: float
    summary: str
    evidence: list[dict] = field(default_factory=list)
    suggested_actions: list[dict] = field(default_factory=list)
