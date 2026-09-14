"""
Append-only audit log: every ingest, merge, and analytics query an
investigator runs is recorded with who/when/what. The PS is explicitly
for a law-enforcement / NCRB audience where evidentiary chain-of-custody
and misuse accountability matter as much as the analysis itself, so this
is not an afterthought bolt-on -- every mutating route calls `log()`.

KNOT6 Phase 1: this now writes to PostgreSQL (`AuditEntryRow`,
`app/db/models.py`) instead of an in-memory list, so the log survives a
backend restart -- directly closing the biggest risk flagged in the Phase 0
audit. `log()` and `list_entries()` keep their exact pre-Phase-1 call
signature (only an optional `investigation_id` was added, additive and
defaulted to None) so every existing call site
(`api/routes/auth.py`, `entities.py`, `ingestion.py`) needed zero changes.

Tamper-evidence (hash-chaining each row to the previous one) is Phase 4 --
now implemented: see app/services/integrity.py for the hash formula and
verification, and docs/KNOT6_IMPLEMENTATION_ROADMAP.md for the design
rationale.
"""
from __future__ import annotations

from app.db.models import AuditEntryRow
from app.db.postgres import SessionLocal
from app.models.schemas import AuditEntry
from app.services.integrity import GENESIS_HASH, compute_entry_hash


def log(actor: str, action: str, target: str | None = None, details: dict | None = None,
        investigation_id: str | None = None) -> AuditEntry:
    row = AuditEntryRow(
        actor=actor, action=action, target=target, details=details or {},
        investigation_id=investigation_id,
    )
    db = SessionLocal()
    try:
        # Chain this row to whatever the current last row is (by sequence,
        # not insertion-unordered UUID `id`) -- see app/services/integrity.py
        # for why `seq` is the ordering key and why this is computed here,
        # at write time, rather than lazily.
        last = db.query(AuditEntryRow).order_by(AuditEntryRow.seq.desc()).first()

        # Flush + refresh BEFORE hashing so `row.timestamp` (and every other
        # field) reflects exactly what a later read of this same row will
        # return -- SQLite's DateTime(timezone=True) does not reliably
        # round-trip tzinfo, so hashing the pre-commit, timezone-aware
        # Python object here (rather than the DB's canonical round-tripped
        # form) would make verify_audit_chain() report a false violation on
        # every single row the first time anyone re-reads them. Hashing
        # post-refresh values means the hash is defined purely in terms of
        # "what this database will hand back," which is backend-agnostic.
        db.add(row)
        db.flush()
        db.refresh(row)

        row.seq = (last.seq + 1) if last else 1
        row.prev_hash = last.entry_hash if last else GENESIS_HASH
        row.entry_hash = compute_entry_hash(row.prev_hash, row.action, row.actor, row.timestamp,
                                             row.target, row.details)
        db.commit()
        db.refresh(row)
        return AuditEntry(id=row.id, timestamp=row.timestamp, actor=row.actor, action=row.action,
                           target=row.target, details=row.details)
    finally:
        db.close()


def list_entries(limit: int = 200, investigation_id: str | None = None) -> list[AuditEntry]:
    db = SessionLocal()
    try:
        query = db.query(AuditEntryRow)
        if investigation_id:
            query = query.filter(AuditEntryRow.investigation_id == investigation_id)
        rows = query.order_by(AuditEntryRow.timestamp.desc()).limit(limit).all()
        return [AuditEntry(id=r.id, timestamp=r.timestamp, actor=r.actor, action=r.action,
                            target=r.target, details=r.details) for r in rows]
    finally:
        db.close()
