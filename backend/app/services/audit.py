"""
Append-only audit log: every ingest, merge, and analytics query an
investigator runs is recorded with who/when/what. The PS is explicitly
for a law-enforcement / NCRB audience where evidentiary chain-of-custody
and misuse accountability matter as much as the analysis itself, so this
is not an afterthought bolt-on -- every mutating route calls `log()`.

In-memory for this prototype (a real deployment writes this to an
append-only, tamper-evident store -- e.g. Postgres with row hashing, or
a write-once object store); see docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.schemas import AuditEntry

_LOG: list[AuditEntry] = []


def log(actor: str, action: str, target: str | None = None, details: dict | None = None) -> AuditEntry:
    entry = AuditEntry(
        id=str(uuid.uuid4()), timestamp=datetime.now(timezone.utc), actor=actor,
        action=action, target=target, details=details or {},
    )
    _LOG.append(entry)
    return entry


def list_entries(limit: int = 200) -> list[AuditEntry]:
    return list(reversed(_LOG))[:limit]
