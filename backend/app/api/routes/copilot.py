"""
KNOT6 Case Intelligence: deterministic summary, universal search, and the
grounded AI Investigation Copilot -- all nested under one investigation,
mirroring the existing `cases.py`/`evidence.py` pattern
(`/investigations/{investigation_id}/...`) rather than inventing a new
top-level API shape.

RBAC follows the same role gate every other investigation-scoped route
already uses (`_READ_ROLES` = investigator/analyst/admin/viewer) -- Phase 1's
authorization is role-based, not per-case-membership (see
docs/KNOT6_ARCHITECTURE.md), so this doesn't add a new access model, only a
new resource under the existing one. Conversation history is additionally
scoped to the asking user (see ConversationRepository) so it never leaks
between investigators sharing role-based access to the same investigation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.copilot.conversation_repository import ConversationRepository
from app.copilot.copilot import InvestigationCopilot
from app.core.security import AuthUser
from app.db.graph_store import ScopedGraphStore, get_graph_store
from app.db.models import Investigation
from app.models.schemas import (
    ActivityIn, ConversationTurnOut, CopilotRequest, CopilotResponse, IntelligenceSummary, ResumePoint,
    SearchResults,
)
from app.services.activity import get_resume_point, record_activity
from app.services.investigation_intelligence import build_intelligence_summary
from app.services.investigation_search import search_investigation

router = APIRouter(prefix="/investigations/{investigation_id}", tags=["case-intelligence"])

_READ_ROLES = ("investigator", "analyst", "admin", "viewer")


def _require_investigation(investigation_id: str, db: Session) -> Investigation:
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise HTTPException(404, "Investigation not found.")
    return inv


@router.get("/intelligence", response_model=IntelligenceSummary)
def get_intelligence(investigation_id: str,
                      user: AuthUser = Depends(require_role(*_READ_ROLES)),
                      db: Session = Depends(get_db)):
    """
    Deterministic -- no LLM involved. Works identically whether or not an
    AI provider is configured (see app/services/investigation_intelligence.py).
    """
    _require_investigation(investigation_id, db)
    store = ScopedGraphStore(get_graph_store(), investigation_id)
    return build_intelligence_summary(store, db, investigation_id)


@router.get("/search", response_model=SearchResults)
def search(investigation_id: str, q: str = Query(..., min_length=1),
           user: AuthUser = Depends(require_role(*_READ_ROLES)),
           db: Session = Depends(get_db)):
    """Also deterministic -- a plain multi-source fan-out, no LLM. See
    app/services/investigation_search.py."""
    _require_investigation(investigation_id, db)
    store = ScopedGraphStore(get_graph_store(), investigation_id)
    return search_investigation(store, db, investigation_id, user.username, q)


@router.post("/copilot", response_model=CopilotResponse)
def ask_copilot(investigation_id: str, payload: CopilotRequest,
                 user: AuthUser = Depends(require_role(*_READ_ROLES)),
                 db: Session = Depends(get_db)):
    """
    Grounded question answering. Returns `available: false` with a plain
    explanation (never a fake answer) when no LLM provider is configured --
    see app/copilot/llm_provider.py. Every successful turn is persisted to
    this user's conversation history for this investigation.
    """
    _require_investigation(investigation_id, db)
    store = ScopedGraphStore(get_graph_store(), investigation_id)
    copilot = InvestigationCopilot(store, db, investigation_id, user.username)
    return copilot.answer(payload.question)


@router.post("/activity", status_code=204)
def post_activity(investigation_id: str, payload: ActivityIn,
                   user: AuthUser = Depends(require_role(*_READ_ROLES)),
                   db: Session = Depends(get_db)):
    """
    KNOT6 Case Intelligence 2.0: records a real, non-fabricated investigation
    activity (see app/db/models.py's InvestigationActivity docstring) --
    fired by the frontend's shared navigation layer
    (frontend/src/components/copilotActions.ts) whenever it opens an
    entity/path/evidence or runs a search. Read-role gated like every other
    route on this router: recording what was *viewed* is not itself a data
    mutation.
    """
    _require_investigation(investigation_id, db)
    record_activity(db, investigation_id, user.username, payload.activity_type,
                     payload.target_type, payload.target_id, payload.target_label, payload.extra)


@router.get("/resume", response_model=ResumePoint)
def get_resume(investigation_id: str,
                user: AuthUser = Depends(require_role(*_READ_ROLES)),
                db: Session = Depends(get_db)):
    """"Continue where you left off" -- see app/services/activity.py.
    `available: false` (never a fabricated resume point) until this user has
    a real recorded activity in this investigation."""
    _require_investigation(investigation_id, db)
    return get_resume_point(db, investigation_id, user.username)


@router.get("/conversations", response_model=list[ConversationTurnOut])
def get_conversations(investigation_id: str, limit: int = 50,
                       user: AuthUser = Depends(require_role(*_READ_ROLES)),
                       db: Session = Depends(get_db)):
    """This user's own conversation history for this investigation only --
    never another investigator's (see ConversationRepository / KNOT6_
    ARCHITECTURE.md's RBAC note)."""
    _require_investigation(investigation_id, db)
    rows = ConversationRepository(db).recent_turns(investigation_id, user.username, limit=limit)
    return [ConversationTurnOut.model_validate(r) for r in rows]


@router.delete("/conversations", status_code=204)
def clear_conversations(investigation_id: str,
                         user: AuthUser = Depends(require_role(*_READ_ROLES)),
                         db: Session = Depends(get_db)):
    """"Clear conversation" (Case Intelligence UI). Deletes only the calling
    user's own Copilot turns for this investigation -- see
    ConversationRepository.clear. Read-role gated like every other route on
    this router: an investigator clearing their own chat memory is not an
    investigation-data mutation, so this intentionally does not require a
    write role, and it never touches investigation/case/evidence/entity/
    relationship/hypothesis/audit data."""
    _require_investigation(investigation_id, db)
    ConversationRepository(db).clear(investigation_id, user.username)
