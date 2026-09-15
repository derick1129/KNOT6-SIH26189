"""Pydantic request/response models shared across the API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

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
    # KNOT6 Phase 1: optional -- omitted preserves pre-Phase-1 behavior
    # exactly (writes to the raw, unscoped store).
    investigation_id: Optional[str] = None


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


# ---------------------------------------------------------------------------
# KNOT6 Phase 1: Investigations / Cases / Evidence
# ---------------------------------------------------------------------------

class InvestigationCreate(BaseModel):
    name: str
    description: str = ""


class InvestigationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # ACTIVE | ARCHIVED | CLOSED


class InvestigationOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    is_demo_seed: bool = False
    created_by: str
    created_at: datetime
    updated_at: datetime
    case_count: int = 0

    model_config = {"from_attributes": True}


class CaseCreate(BaseModel):
    case_number: str
    title: str
    description: str = ""
    priority: str = "MEDIUM"  # LOW | MEDIUM | HIGH | CRITICAL


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # OPEN | UNDER_REVIEW | CLOSED | ARCHIVED
    priority: Optional[str] = None


class CaseOut(BaseModel):
    id: str
    investigation_id: str
    case_number: str
    title: str
    description: str
    status: str
    priority: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    evidence_count: int = 0

    model_config = {"from_attributes": True}


class EvidenceOut(BaseModel):
    id: str
    investigation_id: str
    case_id: str
    filename: str
    original_filename: str
    source_type: str
    mime_type: str
    file_size: int
    uploaded_by: str
    uploaded_at: datetime
    processing_status: str  # UPLOADED | PROCESSING | PROCESSED | FAILED
    description: str
    processing_summary: dict[str, Any] = Field(default_factory=dict)
    sha256_hash: str = ""

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Case Intelligence: deterministic summary, search, and the grounded copilot
# ---------------------------------------------------------------------------

class KeyEntity(BaseModel):
    entity: EntityOut
    connections: int
    relevance_label: str  # "High investigation relevance" | "Moderate investigative interest" | "Entity of investigative interest"
    relevance_score: float = 0.0


class KeyRelationship(BaseModel):
    source: EntityOut
    target: EntityOut
    type: str
    description: str
    evidence: list[str] = Field(default_factory=list)


class RecentDevelopment(BaseModel):
    id: str
    kind: str  # EVIDENCE_UPLOADED | INVESTIGATION_CREATED | CASE_CREATED | ENTITY_RESOLVED | ... (mirrors audit actions)
    description: str
    timestamp: datetime
    target: Optional[str] = None


class OpenSignal(BaseModel):
    id: str
    type: str
    severity: str
    description: str
    entities_involved: list[str] = Field(default_factory=list)
    primary_entity_id: Optional[str] = None  # for the [Investigate] action


class TimelineEventOut(BaseModel):
    id: str
    timestamp: datetime
    kind: str  # CALL | TRANSACTION | PRESENCE | EVIDENCE_UPLOADED | CASE_EVENT | OTHER
    title: str = ""  # short label; description carries the fuller sentence
    description: str
    entities_involved: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    source: str = ""  # e.g. CDR | FINANCIAL_TRANSACTION | FIR | EVIDENCE_REGISTRATION | AUDIT_LOG
    metadata: dict[str, Any] = Field(default_factory=dict)


class UndatedRelation(BaseModel):
    relationship_id: str
    type: Optional[str] = None
    description: str
    entities_involved: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class InvestigationTimelineOut(BaseModel):
    investigation_id: str
    events: list[TimelineEventOut]
    undated_relations: list[UndatedRelation] = Field(default_factory=list)
    total_events: int = 0


# ---------------------------------------------------------------------------
# Financial Intelligence backend aggregation
# ---------------------------------------------------------------------------

class FinancialAccountOut(BaseModel):
    account: EntityOut
    holder_entities: list[EntityOut] = Field(default_factory=list)  # PERSON/ORG nodes that OWN this account
    transaction_count: int = 0
    total_inbound: float = 0.0
    total_outbound: float = 0.0
    counterparty_count: int = 0


class CounterpartyOut(BaseModel):
    account: EntityOut
    transaction_count: int
    total_amount: float


class CircularFlowOut(BaseModel):
    account_ids: list[str]
    account_labels: list[str]
    description: str
    evidence: list[str] = Field(default_factory=list)


class FinancialIntelligenceOut(BaseModel):
    investigation_id: str
    accounts: list[FinancialAccountOut] = Field(default_factory=list)
    transaction_count: int = 0
    total_inbound: float = 0.0
    total_outbound: float = 0.0
    major_counterparties: list[CounterpartyOut] = Field(default_factory=list)
    transaction_timeline: list[TimelineEventOut] = Field(default_factory=list)
    suspicious_patterns: list[AnomalyFlag] = Field(default_factory=list)
    circular_flows: list[CircularFlowOut] = Field(default_factory=list)
    relevant_evidence: list[str] = Field(default_factory=list)


class EvidenceSummaryOut(BaseModel):
    total: int
    processed: int
    pending: int
    failed: int
    integrity_verified: Optional[int] = None  # None => not tracked yet (Phase 4)
    recent: list[EvidenceOut] = Field(default_factory=list)


class InvestigatorNote(BaseModel):
    id: str
    author: str
    text: str
    created_at: datetime


class InvestigatorNotesOut(BaseModel):
    available: bool
    notes: list[InvestigatorNote] = Field(default_factory=list)
    message: Optional[str] = None


class CaseBrief(BaseModel):
    summary: str
    total_entities: int
    total_relations: int
    cross_domain_entities: int
    open_signal_count: int
    domains: list[str] = Field(default_factory=list)


class IntelligenceSummary(BaseModel):
    investigation_id: str
    case_brief: CaseBrief
    key_entities: list[KeyEntity]
    key_relationships: list[KeyRelationship]
    recent_developments: list[RecentDevelopment]
    open_signals: list[OpenSignal]
    evidence_summary: EvidenceSummaryOut
    timeline_summary: list[TimelineEventOut]
    investigator_notes: InvestigatorNotesOut


class SearchEntityHit(BaseModel):
    entity: EntityOut
    connections: int


class SearchEvidenceHit(BaseModel):
    evidence: EvidenceOut


class SearchTimelineHit(BaseModel):
    event: TimelineEventOut


class SearchRelationshipHit(BaseModel):
    relationship: KeyRelationship


class SearchConversationHit(BaseModel):
    turn_id: str
    question: str
    created_at: datetime


class SearchHypothesisHit(BaseModel):
    id: str
    title: str
    status: str
    supporting_count: int = 0
    contradicting_count: int = 0


class SearchResults(BaseModel):
    query: str
    entities: list[SearchEntityHit] = Field(default_factory=list)
    related_entities: list[EntityOut] = Field(default_factory=list)
    relationships: list[SearchRelationshipHit] = Field(default_factory=list)
    evidence: list[SearchEvidenceHit] = Field(default_factory=list)
    timeline: list[SearchTimelineHit] = Field(default_factory=list)
    signals: list[OpenSignal] = Field(default_factory=list)
    conversation: list[SearchConversationHit] = Field(default_factory=list)
    hypotheses: list[SearchHypothesisHit] = Field(default_factory=list)


class CopilotCitation(BaseModel):
    evidence_id: str
    label: str


class CopilotAction(BaseModel):
    type: str  # OPEN_ENTITY | OPEN_GRAPH | VIEW_EVIDENCE | VIEW_TIMELINE | SHOW_PATH | OPEN_HYPOTHESIS | OPEN_FINANCIAL | OPEN_GEO
    label: str
    entity_id: Optional[str] = None
    target_entity_id: Optional[str] = None  # for SHOW_PATH
    evidence_id: Optional[str] = None
    hypothesis_id: Optional[str] = None  # for OPEN_HYPOTHESIS


class CopilotRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class CopilotResponse(BaseModel):
    available: bool
    answer: str
    citations: list[CopilotCitation] = Field(default_factory=list)
    actions: list[CopilotAction] = Field(default_factory=list)
    context_entity_ids: list[str] = Field(default_factory=list)
    turn_id: Optional[str] = None
    # "llm" when an AI provider generated the answer, "deterministic" when
    # app/copilot/deterministic_answerer.py did -- see its docstring. Lets
    # the frontend show it was never fabricated AI prose either way.
    mode: Literal["llm", "deterministic"] = "llm"


class ConversationTurnOut(BaseModel):
    id: str
    investigation_id: str
    username: str
    question: str
    answer: str
    citations: list[CopilotCitation] = Field(default_factory=list)
    actions: list[CopilotAction] = Field(default_factory=list)
    created_at: datetime
    mode: str = "llm"

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# KNOT6 Case Intelligence 2.0: investigation activity / "continue where you
# left off" -- see app/services/activity.py and app/db/models.py's
# InvestigationActivity docstring for the full rationale.
# ---------------------------------------------------------------------------

class ActivityIn(BaseModel):
    activity_type: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    target_label: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Entity resolution: candidate review, wired to entity_resolution_decisions
# ---------------------------------------------------------------------------

class ResolutionCandidateOut(BaseModel):
    keep_id: str
    merge_id: str
    keep_label: str
    merge_label: str
    confidence: float  # name-similarity score (0-100) the match is based on
    matching_reasons: list[str] = Field(default_factory=list)
    source_references: dict[str, list[str]] = Field(default_factory=dict)  # {"keep": [...], "merge": [...]}
    # AUTO_MERGE_ELIGIBLE (near-exact name, >=97%) | REVIEW_REQUIRED
    # (similar name + corroborating shared connection) -- never applied
    # automatically by this endpoint either way; see
    # app/resolution/entity_resolution.py's docstring for why a human
    # confirms every merge in this prototype.
    decision_status: str


class ResolutionDecisionIn(BaseModel):
    keep_id: str
    merge_id: str
    decision: str  # APPROVED | REJECTED
    reason: str = ""


class ResolutionDecisionOut(BaseModel):
    id: str
    investigation_id: str
    keep_id: str
    merge_id: str
    decision: str
    reason: str
    decided_by: str
    decided_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# KNOT6 Phase 4: Evidence Integrity + tamper-evident audit chain
# ---------------------------------------------------------------------------

class EvidenceIntegrityOut(BaseModel):
    evidence_id: str
    sha256_hash: str
    uploaded_by: str
    uploaded_at: datetime
    source_type: str
    original_filename: str
    has_reference_hash: bool


class EvidenceIntegrityVerifyOut(BaseModel):
    evidence_id: str
    status: str  # VALID | INTEGRITY_VIOLATION | UNAVAILABLE
    stored_hash: str
    computed_hash: Optional[str] = None
    checked_at: datetime
    message: str


class AuditChainVerifyOut(BaseModel):
    status: str  # VALID | INTEGRITY_VIOLATION | EMPTY
    entries_checked: int
    first_broken_entry_id: Optional[str] = None
    first_broken_seq: Optional[int] = None
    message: str
    checked_at: datetime


class ResumePoint(BaseModel):
    available: bool
    description: str
    activity_type: Optional[str] = None
    timestamp: Optional[datetime] = None
    action: Optional[CopilotAction] = None


# ---------------------------------------------------------------------------
# Hypothesis Lab persistence -- see app/db/models.py:Hypothesis's docstring
# for why the path/analytics are computed live rather than frozen here.
# ---------------------------------------------------------------------------

HYPOTHESIS_STATUSES = ("OPEN", "UNDER_REVIEW", "SUPPORTED", "CONTRADICTED", "INCONCLUSIVE")


class HypothesisCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str = ""
    case_id: Optional[str] = None
    subject_entity_id: Optional[str] = None
    target_entity_id: Optional[str] = None
    related_entity_ids: list[str] = Field(default_factory=list)


class HypothesisUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # OPEN | UNDER_REVIEW | SUPPORTED | CONTRADICTED | INCONCLUSIVE
    subject_entity_id: Optional[str] = None
    target_entity_id: Optional[str] = None
    related_entity_ids: Optional[list[str]] = None


class HypothesisNoteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class HypothesisNoteOut(BaseModel):
    id: str
    author: str
    text: str
    created_at: datetime


class HypothesisEvidenceIn(BaseModel):
    evidence_id: str
    relationship_type: str  # SUPPORTING | CONTRADICTING
    note: str = ""


class HypothesisEvidenceOut(BaseModel):
    id: str
    hypothesis_id: str
    evidence_id: str
    relationship_type: str
    note: str
    created_by: str
    created_at: datetime
    evidence: Optional[EvidenceOut] = None  # resolved for display convenience; None if the row was since deleted

    model_config = {"from_attributes": True}


class HypothesisOut(BaseModel):
    id: str
    investigation_id: str
    case_id: Optional[str] = None
    title: str
    description: str
    status: str
    subject_entity_id: Optional[str] = None
    target_entity_id: Optional[str] = None
    related_entity_ids: list[str] = Field(default_factory=list)
    supporting_count: int = 0
    contradicting_count: int = 0
    note_count: int = 0
    created_by: str
    created_at: datetime
    updated_at: datetime


class HypothesisAnalyticalContext(BaseModel):
    """Recomputed fresh on every read from the same analytics modules the
    rest of KNOT6 uses (never frozen at creation time -- new evidence
    arriving after a hypothesis is saved should change what this shows)."""
    subject_entity: Optional[EntityOut] = None
    target_entity: Optional[EntityOut] = None
    subject_influencer: Optional[InfluencerScore] = None
    target_influencer: Optional[InfluencerScore] = None
    same_community: Optional[bool] = None
    path: Optional[PathResult] = None
    relevant_signals: list[AnomalyFlag] = Field(default_factory=list)
    relevant_timeline: list[TimelineEventOut] = Field(default_factory=list)


class HypothesisDetailOut(HypothesisOut):
    notes: list[HypothesisNoteOut] = Field(default_factory=list)
    supporting_evidence: list[HypothesisEvidenceOut] = Field(default_factory=list)
    contradicting_evidence: list[HypothesisEvidenceOut] = Field(default_factory=list)
    related_entities: list[EntityOut] = Field(default_factory=list)
    analytical_context: HypothesisAnalyticalContext
    # A deterministic, non-committal narrated sentence -- "Current evidence
    # supports/contradicts/is inconclusive about this hypothesis" -- never
    # "this hypothesis is true". See app/services/hypothesis.py.
    assessment: str
