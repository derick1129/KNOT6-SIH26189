"""
KNOT6 Case Intelligence 2.0: investigation activity -- the smallest clean
mechanism that lets "Continue where you left off" and "what changed since
my last review" be backed by real data instead of invented.

Recorded from two places only (see docs on InvestigationActivity in
app/db/models.py for why this is a deliberate scope boundary, not an
oversight): the shared frontend navigation layer
(frontend/src/components/copilotActions.ts, whenever a KNOT6-generated
action opens an entity/path/evidence, or a search is run) and the copilot
itself (every answered question is an activity -- see
app/copilot/copilot.py). A user browsing NetworkExplorer/PathFinder/
EvidenceVault/Entities directly, outside a KNOT6-generated deep link, is
not recorded here.

Takes `db: Session` as a parameter, like app/services/investigation_
intelligence.py and investigation_search.py do (the routes calling this
already have a request-scoped session) -- unlike app/services/audit.py,
which opens its own session because its callers historically didn't have one.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import InvestigationActivity
from app.models.schemas import CopilotAction, ResumePoint

# Activity types whose target is a real page a "Continue" button can
# deep-link back to. SEARCH_PERFORMED and QUESTION_ASKED are recorded (and
# feed "what changed since my last review") but have no single page to
# resume into, so they're excluded from resume-point candidates.
_RESUMABLE_TYPES = ("ENTITY_VIEWED", "NETWORK_FOCUSED", "PATH_VIEWED", "EVIDENCE_VIEWED")

_DESCRIPTION = {
    "ENTITY_VIEWED": "You were last reviewing {label}.",
    "NETWORK_FOCUSED": "You were last exploring the network around {label}.",
    "PATH_VIEWED": "You were last reviewing the relationship path from {label}.",
    "EVIDENCE_VIEWED": "You were last reviewing evidence: {label}.",
}


def _resume_action(row: InvestigationActivity) -> CopilotAction:
    # Deliberately the PLAIN target label here, not a "Continue: "-prefixed
    # display string: frontend/src/components/ResumePanel.tsx's button text
    # is hardcoded to "Continue" and never renders `action.label` -- this
    # label's only real consumer is copilotActions.ts's `runAction`, which
    # re-records a fresh activity using it as the new `target_label`.
    # Prefixing it here previously meant clicking "Continue" recorded
    # "Continue: X" as the new label, so the *next* resume point read back
    # "You were last reviewing Continue: X" -- and would compound further
    # ("Continue: Continue: X") on every subsequent click. Caught by
    # actually clicking through the feature, not just by reading the code.
    label = row.target_label or "this"
    if row.activity_type in ("ENTITY_VIEWED", "NETWORK_FOCUSED"):
        return CopilotAction(type="OPEN_GRAPH" if row.activity_type == "NETWORK_FOCUSED" else "OPEN_ENTITY",
                              label=label, entity_id=row.target_id)
    if row.activity_type == "PATH_VIEWED":
        return CopilotAction(type="SHOW_PATH", label=label,
                              entity_id=row.target_id, target_entity_id=(row.extra or {}).get("target_entity_id"))
    return CopilotAction(type="VIEW_EVIDENCE", label=label, evidence_id=row.target_id)


def record_activity(db: Session, investigation_id: str, username: str, activity_type: str,
                     target_type: str | None = None, target_id: str | None = None,
                     target_label: str | None = None, extra: dict | None = None) -> InvestigationActivity:
    row = InvestigationActivity(
        investigation_id=investigation_id, username=username, activity_type=activity_type,
        target_type=target_type, target_id=target_id, target_label=target_label, extra=extra or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_resume_point(db: Session, investigation_id: str, username: str) -> ResumePoint:
    """Never fabricated: `available=False` when nothing has been recorded yet
    (see the Case Intelligence 2.0 brief's "START INVESTIGATING" state)."""
    row = (
        db.query(InvestigationActivity)
        .filter(InvestigationActivity.investigation_id == investigation_id,
                InvestigationActivity.username == username,
                InvestigationActivity.target_id.isnot(None),
                InvestigationActivity.activity_type.in_(_RESUMABLE_TYPES))
        .order_by(InvestigationActivity.created_at.desc())
        .first()
    )
    if row is None:
        return ResumePoint(available=False, description="", activity_type=None, timestamp=None, action=None)
    label = row.target_label or "an entity"
    return ResumePoint(
        available=True, description=_DESCRIPTION[row.activity_type].format(label=label),
        activity_type=row.activity_type, timestamp=row.created_at, action=_resume_action(row),
    )


def get_previous_visit_cutoff(db: Session, investigation_id: str, username: str) -> datetime | None:
    """This user's second-most-recent activity timestamp in this
    investigation -- i.e. "before whatever they're doing right now". Used to
    answer "what changed since my last review"; `None` when there's fewer
    than two recorded activities (first-ever visit has nothing to compare
    against, which is itself the correct/honest answer, not a bug)."""
    rows = (
        db.query(InvestigationActivity.created_at)
        .filter(InvestigationActivity.investigation_id == investigation_id,
                InvestigationActivity.username == username)
        .order_by(InvestigationActivity.created_at.desc())
        .limit(2)
        .all()
    )
    return rows[1][0] if len(rows) == 2 else None
