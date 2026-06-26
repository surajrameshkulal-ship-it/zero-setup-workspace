from __future__ import annotations

from pydantic import BaseModel


class RoadmapPhase(BaseModel):
    id: str
    title: str
    summary: str


class Blocker(BaseModel):
    type: str
    severity: str
    title: str
    reason: str
    reference_id: str


class Priority(BaseModel):
    title: str
    rationale: str
    category: str
    score: int


class ProductBrainOverview(BaseModel):
    roadmap: list[RoadmapPhase]
    delivery: dict
    blockers: list[Blocker]
    priorities: list[Priority]
    summary: str
