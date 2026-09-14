"""
SQLAlchemy ORM models for KNOT6's PostgreSQL-backed application/business
metadata layer (Phase 1).

This is deliberately a separate store from the graph: PostgreSQL owns
investigations, cases, evidence *metadata*, users, audit history and
entity-resolution review state; the graph (entities/relationships) stays in
NetworkX/Neo4j via `app/db/graph_store.py`. See docs/KNOT6_ARCHITECTURE.md
for the split and why the graph is never duplicated into Postgres.

Column types are kept deliberately portable (String/Text/DateTime/JSON, no
Postgres-only types) so the same models work against SQLite for zero-infra
local dev/tests and against real PostgreSQL in Docker/production without a
different migration path for each.

Status/role/priority fields are plain `String` columns rather than a native
SQL ENUM type -- valid values are enforced at the Pydantic/API layer
(`app/models/schemas.py`), which keeps a status vocabulary change a
one-line application change rather than a database migration, and keeps the
schema portable across dialects.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Users (persistent replacement for core/security.py's in-memory dict)
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # ADMIN|INVESTIGATOR|ANALYST|VIEWER
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------
# Investigation -> Case -> Evidence
# ---------------------------------------------------------------------------

class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE|ARCHIVED|CLOSED
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    cases: Mapped[list["Case"]] = relationship(back_populates="investigation", cascade="all, delete-orphan")


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id"), nullable=False, index=True
    )
    case_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN|UNDER_REVIEW|CLOSED|ARCHIVED
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM")  # LOW|MEDIUM|HIGH|CRITICAL
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    investigation: Mapped["Investigation"] = relationship(back_populates="cases")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Evidence(Base):
    """
    Metadata + a storage reference only -- never the file bytes themselves
    (see app/services/storage.py). Phase 1 scope is registration + basic
    processing status; SHA-256 hashing and tamper-evident verification are
    Phase 4 (Evidence Integrity).
    """
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(500), default="")
    uploaded_by: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processing_status: Mapped[str] = mapped_column(String(20), default="UPLOADED")
    description: Mapped[str] = mapped_column(Text, default="")
    # Ingestion pipeline output summary (entities/relations extracted, any
    # warnings) -- diagnostic only, the graph itself is the source of truth.
    processing_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    # Evidence Integrity (Phase 4): SHA-256 of the uploaded bytes, computed
    # once at upload time and never recomputed -- this is the reference a
    # later `POST /api/evidence/{id}/verify-integrity` re-hashes the stored
    # file against. Empty string for evidence uploaded before this column
    # existed (see the backfill note in the Phase 4 migration) rather than a
    # fabricated hash. See app/services/integrity.py.
    sha256_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")

    case: Mapped["Case"] = relationship(back_populates="evidence")


# ---------------------------------------------------------------------------
# Audit (persistent replacement for services/audit.py's in-memory list)
# ---------------------------------------------------------------------------

class AuditEntryRow(Base):
    """
    Append-only history, now tamper-evident (Phase 4): each row's
    `entry_hash` is SHA256(prev_hash + action + actor + timestamp + target +
    canonical(details)), chaining it to the row immediately before it in
    insertion order (`seq`). Editing or deleting any historical row breaks
    every subsequent row's hash -- detectable by
    app/services/integrity.py:verify_audit_chain() without needing a real
    blockchain; see that module's docstring for why this is a deliberate,
    clean abstraction rather than a claim of Hyperledger Fabric.

    `seq` (not `id`, which is a UUID with no ordering) is the chain's
    ordering key -- assigned as (current max seq + 1) at insert time. Rows
    written before this column existed keep `seq=0`/`entry_hash=""` (see the
    Phase 4 migration's backfill, which computes real hashes for all
    pre-existing rows rather than leaving them at these placeholder values).
    """
    __tablename__ = "audit_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    investigation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    prev_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    entry_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")


# ---------------------------------------------------------------------------
# Entity resolution review state
# ---------------------------------------------------------------------------

class CopilotConversationTurn(Base):
    """
    KNOT6 Case Intelligence: one investigator question + grounded answer,
    scoped to both the investigation *and* the asking user -- conversation
    memory must never leak between investigators sharing the same
    investigation (see docs/KNOT6_ARCHITECTURE.md's RBAC note: Phase 1
    authorization is role-based, not per-case-membership, so this is the one
    place KNOT6 Case Intelligence adds its own isolation rather than relying
    on investigation access alone).

    `citations` is the list of evidence IDs the answer actually referenced
    (validated server-side against retrieved evidence -- see
    app/copilot/copilot.py -- never taken from the raw LLM output
    unvalidated). `actions` are deterministic UI affordances (open entity /
    open graph / show path / view evidence) computed from real retrieval
    results, not generated by the LLM. `context_entity_ids` is the small set
    of entities the question resolved to, kept so a later turn in the same
    conversation can resolve a pronoun ("his financial connections") back to
    the right entity.
    """
    __tablename__ = "copilot_conversation_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    context_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    # KNOT6 Case Intelligence 2.0: "llm" when an AI provider generated the
    # answer, "deterministic" when app/copilot/deterministic_answerer.py did
    # (no fabricated prose either way -- see that module's docstring).
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="llm", server_default="llm")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class InvestigationActivity(Base):
    """
    KNOT6 Case Intelligence 2.0: a real record of what an investigator
    actually looked at, per-(investigation, user) -- same isolation
    rationale as CopilotConversationTurn (Phase 1 authorization is
    role-based, not per-case-membership; see docs/KNOT6_ARCHITECTURE.md).
    Powers "Continue where you left off" (app/services/activity.py's
    get_resume_point) and "what changed since my last review"
    (get_previous_visit_cutoff). Deliberately not a full audit trail --
    that's AuditEntryRow, for mutating actions -- this is read/navigation
    activity, recorded only when navigation flows through the shared
    frontend action layer (frontend/src/components/copilotActions.ts) or
    the copilot itself (asking a question is an activity too). Never
    fabricated: if no row exists yet, the resume panel says so honestly.
    """
    __tablename__ = "investigation_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # ENTITY_VIEWED | EVIDENCE_VIEWED | PATH_VIEWED | NETWORK_FOCUSED | SEARCH_PERFORMED | QUESTION_ASKED
    activity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ENTITY|PATH|EVIDENCE|SEARCH|QUESTION
    target_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class EntityResolutionDecision(Base):
    """
    Records an analyst's accept/reject decision on a merge candidate so a
    rejected pair (e.g. two different people who happen to share a name)
    doesn't keep resurfacing every time
    `GET /api/entities/resolution/candidates` is called. See
    app/resolution/entity_resolution.py for the (unchanged) matching logic
    this layers on top of.
    """
    __tablename__ = "entity_resolution_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    keep_id: Mapped[str] = mapped_column(String(80), nullable=False)
    merge_id: Mapped[str] = mapped_column(String(80), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)  # APPROVED|REJECTED
    reason: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------
# Hypothesis Lab persistence (KNOT6 next-phase, Priority 1)
# ---------------------------------------------------------------------------

class Hypothesis(Base):
    """
    A saved investigative hypothesis -- "Entity A may be coordinating with
    Entity B" -- persisted so it survives a reload and can be revisited
    ("reopen existing hypotheses after returning later"), unlike the
    original Hypothesis Lab (frontend/src/pages/HypothesisLab.tsx) which
    only ever composed its analysis live, in the browser, with nothing
    saved (see app/services/investigation_intelligence.py's
    build_investigator_notes() docstring, written at the time that was
    still true).

    Deliberately NOT storing a frozen graph path or a frozen analytical
    signal snapshot here: `subject_entity_id`/`target_entity_id` are
    persisted, but the path between them and the current centrality/
    community/signal context are recomputed live at read time (same
    pathfinder/analytics modules the original client-side lab already
    called) -- a graph that gains new evidence after a hypothesis is saved
    should show the *current* path, not a stale one frozen at creation
    time. `related_entity_ids` covers entities the investigator explicitly
    tags as relevant beyond the subject/target pair.
    """
    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # OPEN | UNDER_REVIEW | SUPPORTED | CONTRADICTED | INCONCLUSIVE -- never
    # "TRUE"/"CONFIRMED"/"GUILTY": see app/api/routes/hypotheses.py's module
    # docstring for the ethics-language guarantee this vocabulary enforces.
    status: Mapped[str] = mapped_column(String(20), default="OPEN", server_default="OPEN")
    subject_entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    related_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[list] = mapped_column(JSON, default=list)  # [{id, author, text, created_at}]
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    evidence_links: Mapped[list["HypothesisEvidence"]] = relationship(
        back_populates="hypothesis", cascade="all, delete-orphan"
    )


class HypothesisEvidence(Base):
    """
    One evidence item explicitly tagged as SUPPORTING or CONTRADICTING a
    hypothesis, with an optional investigator note explaining why. Many
    rows per hypothesis; an evidence item may support one hypothesis and
    contradict another. `evidence_id` references `evidence.id` -- no FK
    constraint declared (matching this codebase's existing convention of
    plain indexed string columns rather than DB-enforced FKs across the
    Postgres/SQLite dual-backend boundary, e.g. Evidence.case_id above) but
    validated at the API layer (app/api/routes/hypotheses.py) before insert.
    """
    __tablename__ = "hypothesis_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    hypothesis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hypotheses.id"), nullable=False, index=True
    )
    evidence_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(15), nullable=False)  # SUPPORTING | CONTRADICTING
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    hypothesis: Mapped["Hypothesis"] = relationship(back_populates="evidence_links")
