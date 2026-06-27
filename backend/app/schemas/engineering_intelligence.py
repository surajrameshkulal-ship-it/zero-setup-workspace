from __future__ import annotations

from pydantic import BaseModel


class EngineeringOverview(BaseModel):
    node_counts: dict
    edge_counts: dict
    top_dependencies: list
    orphans: int
    total_components: int
    summary: str


class ImpactResult(BaseModel):
    query: str
    matches: list
    impacted: list
    affected_by_type: dict
    summary: str


class DependencyResult(BaseModel):
    node: dict
    dependencies: list
    dependents: list
    summary: str


class ArchitectureReview(BaseModel):
    flags: list
    summary: str
