"""Pydantic request/response models shared across the API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Graph primitives
# ---------------------------------------------------------------------------

class EntityOut(BaseModel):
    id: str
    type: str  # PERSON | PHONE | VEHICLE | LOCATION | ORGANIZATION | FINANCIAL_ACCOUNT | EVENT | CASE
    label: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    risk_score: float = 0.0
    source_count: int = 0


class RelationOut(BaseModel):
    id: str
    source: str
    target: str
    type: str  # CALLED | TRANSACTED_WITH | ASSOCIATED_WITH | OWNS | PRESENT_AT | MEMBER_OF | MENTIONED_WITH
    attributes: dict[str, Any] = Field(default_factory=dict)
    weight: float = 1.0
    evidence: list[str] = Field(default_factory=list)


class GraphOut(BaseModel):
    nodes: list[EntityOut]
    edges: list[RelationOut]


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class TextIngestRequest(BaseModel):
    source_type: str  # "fir" | "surveillance" | "social_media" | "intel_report"
    document_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResult(BaseModel):
    document_id: str
    entities_extracted: int
    relations_extracted: int
    entities: list[EntityOut]
    relations: list[RelationOut]


class BulkIngestSummary(BaseModel):
    documents_processed: int
    records_processed: int
    entities_created: int
    entities_merged: int
    relations_created: int
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class InfluencerScore(BaseModel):
    entity: EntityOut
    degree_centrality: float
    betweenness_centrality: float
    pagerank: float
    composite_score: float
    rank: int


class Community(BaseModel):
    community_id: int
    size: int
    members: list[EntityOut]
    density: float
    label: str


class AnomalyFlag(BaseModel):
    id: str
    type: str  # BURST_CALLING | SHORT_DURATION_CALLS | CIRCULAR_TRANSACTION | NEW_HIGH_DEGREE_NODE | LOCATION_CONVERGENCE
    severity: str  # low | medium | high
    description: str
    entities_involved: list[str]
    evidence: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PathHop(BaseModel):
    entity: EntityOut
    via_relation: Optional[RelationOut] = None


class PathResult(BaseModel):
    source: str
    target: str
    found: bool
    hops: int = 0
    path: list[PathHop] = Field(default_factory=list)
    all_paths_count: int = 0


class DashboardSummary(BaseModel):
    total_entities: int
    total_relations: int
    total_persons: int
    total_cases: int
    top_influencers: list[InfluencerScore]
    community_count: int
    open_anomalies: int
    recent_anomalies: list[AnomalyFlag]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    id: str
    timestamp: datetime
    actor: str
    action: str
    target: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
