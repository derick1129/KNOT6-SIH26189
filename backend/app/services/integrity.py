"""
KNOT6 Phase 4: Evidence Integrity + tamper-evident audit chain.

This is a deliberately clean, self-contained integrity *abstraction* -- not
a claim that KNOT6 runs on a real distributed ledger. Two independent
guarantees live here, both built from stdlib `hashlib` (no new dependency):

1. **Evidence integrity**: `sha256_hash()` is computed once, at upload time
   (`app/api/routes/evidence.py`), over the exact bytes written to storage.
   `verify_evidence()` re-reads those bytes and re-hashes them on demand --
   a mismatch means the stored file no longer matches what was registered
   (corruption, or tampering with the file on disk).

2. **Audit chain integrity**: every `AuditEntryRow` is written with
   `entry_hash = SHA256(prev_hash + action + actor + timestamp + target +
   canonical_json(details))`, chaining it to the row immediately before it
   (`app/services/audit.py:log()`). `verify_audit_chain()` walks every row
   in insertion order and recomputes each hash from its own fields plus the
   previous row's *stored* hash -- if a row's content, its stored
   `prev_hash`, or the row ordering has been altered after the fact, the
   recomputed hash will not match what was stored, and the chain is
   reported broken from that row forward. This is the same core idea a
   blockchain uses (each block committing to the previous one's hash)
   without standing up actual distributed consensus for a single-writer
   prototype database -- a real Hyperledger Fabric integration later would
   plug in at exactly these two functions (write the same hash to a
   ledger transaction instead of/alongside the Postgres row) without
   changing any caller.

Nothing here is a claim of production blockchain infrastructure -- see
docs/KNOT6_IMPLEMENTATION_ROADMAP.md Phase 4 and the PS instructions this
module was built against.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import AuditEntryRow, Evidence
from app.services.storage import get_storage

GENESIS_HASH = ""  # the first row in the chain has no predecessor


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_details(details: dict) -> str:
    """Stable JSON serialization so the same details dict always hashes the
    same way regardless of key insertion order."""
    return json.dumps(details or {}, sort_keys=True, separators=(",", ":"), default=str)


def compute_entry_hash(prev_hash: str, action: str, actor: str, timestamp: datetime,
                        target: str | None, details: dict) -> str:
    payload = "|".join([
        prev_hash or "",
        action,
        actor,
        timestamp.isoformat(),
        target or "",
        _canonical_details(details),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Evidence integrity
# ---------------------------------------------------------------------------

@dataclass
class EvidenceIntegrityResult:
    evidence_id: str
    status: str  # "VALID" | "INTEGRITY_VIOLATION" | "UNAVAILABLE"
    stored_hash: str
    computed_hash: str | None
    checked_at: datetime
    message: str


def verify_evidence(evidence: Evidence) -> EvidenceIntegrityResult:
    now = datetime.utcnow()
    if not evidence.sha256_hash:
        return EvidenceIntegrityResult(
            evidence_id=evidence.id, status="UNAVAILABLE", stored_hash="", computed_hash=None,
            checked_at=now,
            message="No reference hash was recorded for this evidence item (uploaded before integrity "
                    "tracking was enabled). Nothing to verify against.",
        )
    try:
        data = get_storage().read(evidence.storage_path)
    except (OSError, ValueError) as exc:
        return EvidenceIntegrityResult(
            evidence_id=evidence.id, status="INTEGRITY_VIOLATION", stored_hash=evidence.sha256_hash,
            computed_hash=None, checked_at=now,
            message=f"Stored file could not be read: {exc}",
        )
    computed = sha256_bytes(data)
    if computed == evidence.sha256_hash:
        return EvidenceIntegrityResult(
            evidence_id=evidence.id, status="VALID", stored_hash=evidence.sha256_hash,
            computed_hash=computed, checked_at=now,
            message="The stored file's SHA-256 hash matches the hash recorded at upload time.",
        )
    return EvidenceIntegrityResult(
        evidence_id=evidence.id, status="INTEGRITY_VIOLATION", stored_hash=evidence.sha256_hash,
        computed_hash=computed, checked_at=now,
        message="The stored file's current SHA-256 hash does not match the hash recorded at upload "
                "time -- the file has changed since it was registered as evidence.",
    )


# ---------------------------------------------------------------------------
# Audit chain integrity
# ---------------------------------------------------------------------------

@dataclass
class AuditChainResult:
    status: str  # "VALID" | "INTEGRITY_VIOLATION" | "EMPTY"
    entries_checked: int
    first_broken_entry_id: str | None = None
    first_broken_seq: int | None = None
    message: str = ""
    checked_at: datetime = field(default_factory=datetime.utcnow)


def verify_audit_chain(db: Session) -> AuditChainResult:
    rows = db.query(AuditEntryRow).order_by(AuditEntryRow.seq.asc()).all()
    if not rows:
        return AuditChainResult(status="EMPTY", entries_checked=0, message="No audit entries recorded yet.")

    prev_hash = GENESIS_HASH
    for row in rows:
        expected = compute_entry_hash(prev_hash, row.action, row.actor, row.timestamp, row.target, row.details)
        if row.prev_hash != prev_hash or row.entry_hash != expected:
            return AuditChainResult(
                status="INTEGRITY_VIOLATION", entries_checked=len(rows),
                first_broken_entry_id=row.id, first_broken_seq=row.seq,
                message=f"Audit chain integrity violation detected at entry {row.id} (sequence {row.seq}): "
                        "its stored hash does not match what its content and its predecessor imply. Every "
                        "entry from this point forward is unverifiable.",
            )
        prev_hash = row.entry_hash

    return AuditChainResult(
        status="VALID", entries_checked=len(rows),
        message=f"All {len(rows)} audit entries form an unbroken hash chain -- no tampering detected.",
    )
