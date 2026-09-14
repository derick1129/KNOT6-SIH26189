"""
ConversationRepository: per-(investigation, user) conversation memory.

Scoped to the asking user as well as the investigation -- deliberately, not
just an investigation-wide log -- so one investigator's line of questioning
never leaks into another's session even when both have access to the same
investigation (Phase 1's authorization is role-based, not per-membership;
see docs/KNOT6_ARCHITECTURE.md -- this repository is where Case Intelligence
adds the isolation that RBAC alone doesn't give it).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import CopilotConversationTurn
from app.models.schemas import CopilotAction, CopilotCitation


class ConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def recent_turns(self, investigation_id: str, username: str, limit: int = 20) -> list[CopilotConversationTurn]:
        rows = (
            self.db.query(CopilotConversationTurn)
            .filter(CopilotConversationTurn.investigation_id == investigation_id,
                    CopilotConversationTurn.username == username)
            .order_by(CopilotConversationTurn.created_at.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(rows))  # oldest first, matching a chat transcript's reading order

    def add_turn(self, investigation_id: str, username: str, question: str, answer: str,
                 citations: list[CopilotCitation], actions: list[CopilotAction],
                 context_entity_ids: list[str], mode: str = "llm") -> CopilotConversationTurn:
        row = CopilotConversationTurn(
            investigation_id=investigation_id, username=username, question=question, answer=answer,
            citations=[c.model_dump() for c in citations], actions=[a.model_dump() for a in actions],
            context_entity_ids=context_entity_ids, mode=mode,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def clear(self, investigation_id: str, username: str) -> int:
        """"Clear conversation" -- deletes only this user's Copilot turns for
        this investigation (never another investigator's, same isolation
        rule as recent_turns/add_turn above). Deliberately narrow: this
        table is conversation memory only, so clearing it can never touch
        investigation/case/evidence/entity/relationship/hypothesis/audit
        data, all of which live in entirely separate tables/the graph store.
        Returns the number of turns removed, for the route's own bookkeeping
        if ever needed."""
        deleted = (
            self.db.query(CopilotConversationTurn)
            .filter(CopilotConversationTurn.investigation_id == investigation_id,
                    CopilotConversationTurn.username == username)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted
