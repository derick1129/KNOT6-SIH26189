"""
Two related graph-durability operations, both stemming from the same fact:
`GraphStore` (see app/db/graph_store.py) lives only in-process memory (the
NetworkX backend) or, even with Neo4j, is never the thing PostgreSQL's
Evidence rows are transactionally tied to. Nothing keeps them in sync
automatically.

1. `reseed_demo_investigation` -- restore the bundled "Operation Nexus" demo
   investigation to its canonical, seed_demo.py-generated graph, from
   scratch, without disturbing any other investigation. This is the fix for
   the incident described in `Investigation.is_demo_seed`'s docstring: once
   a demo investigation has (incorrectly, pre-fix) accumulated real upload
   data, this is how an operator restores it from the one canonical source
   (backend/data/demo/ via app/services/seed_demo.py) rather than by hand.

2. `rebuild_missing_investigation_graphs` -- on startup, replay any
   already-PROCESSED Evidence row whose investigation's scoped graph came up
   empty (a process restart, most commonly) so a real investigation's graph
   is durable across restarts too, not just the demo one. Demo investigations
   are skipped here -- `_seed_on_startup` (app/main.py) is their reseed path,
   and they should never have Evidence rows in the first place now that
   `ensure_not_demo_protected` blocks new ones.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.graph_store import ScopedGraphStore, get_graph_store
from app.db.models import Evidence, Investigation
from app.services.evidence_processing import process_evidence
from app.services.storage import get_storage

logger = logging.getLogger("prahari")


def reseed_demo_investigation(investigation: Investigation, db: Session) -> dict:
    """
    Wipe this investigation's graph (and only this investigation's -- see
    `ScopedGraphStore.clear()`) plus any Evidence rows it has accumulated,
    then re-run the canonical `seed_demo.seed()` against it. Refuses to run
    against anything that isn't flagged `is_demo_seed` -- this is a
    "restore the demo" operation, not a general "wipe an investigation"
    one; a real investigation's data has no canonical source to restore
    from and this must never be reachable for one.
    """
    if not investigation.is_demo_seed:
        raise ValueError(
            f"'{investigation.name}' is not a demo-seeded investigation; refusing to reseed it "
            "(this would destroy real casework with no way to recover it)."
        )

    stray_evidence = db.query(Evidence).filter(Evidence.investigation_id == investigation.id).all()
    removed_evidence = [e.id for e in stray_evidence]
    for e in stray_evidence:
        db.delete(e)
    db.commit()

    store = ScopedGraphStore(get_graph_store(), investigation.id)
    nodes_before, edges_before = len(store.all_nodes()), len(store.all_edges())
    store.clear()

    from app.services.seed_demo import seed  # local import: avoid a module-load-order cycle with main.py
    summary = seed(store)

    result = {
        "investigation_id": investigation.id,
        "removed_evidence_ids": removed_evidence,
        "nodes_before": nodes_before,
        "edges_before": edges_before,
        "nodes_after": len(store.all_nodes()),
        "edges_after": len(store.all_edges()),
        "seed_summary": summary,
    }
    logger.info("Reseeded demo investigation %s from canonical source: %s", investigation.id, result)
    return result


def rebuild_missing_investigation_graphs(db: Session) -> dict:
    """
    For every non-demo investigation whose scoped graph is currently empty
    but which has PROCESSED evidence on record, replay that evidence
    through the same ingestion pipeline it originally ran through (in
    upload order) so the graph is reconstructed rather than silently left
    empty. A no-op (and cheap: one query) for the common case where nothing
    needs rebuilding.
    """
    rebuilt: dict[str, list[str]] = {}
    storage = get_storage()

    investigations = db.query(Investigation).filter(Investigation.is_demo_seed.is_(False)).all()
    for investigation in investigations:
        store = ScopedGraphStore(get_graph_store(), investigation.id)
        if store.all_nodes():
            continue  # graph already populated -- nothing lost, nothing to do

        processed = (
            db.query(Evidence)
            .filter(Evidence.investigation_id == investigation.id, Evidence.processing_status == "PROCESSED")
            .order_by(Evidence.uploaded_at.asc())
            .all()
        )
        if not processed:
            continue

        replayed = []
        for evidence in processed:
            try:
                data = storage.read(evidence.storage_path)
            except (FileNotFoundError, ValueError):
                logger.warning(
                    "Cannot rebuild graph for investigation %s: evidence %s's stored file is missing.",
                    investigation.id, evidence.id,
                )
                continue
            process_evidence(evidence, data, db, store=store)
            replayed.append(evidence.id)

        if replayed:
            rebuilt[investigation.id] = replayed
            logger.info(
                "Rebuilt graph for investigation %s from %d persisted evidence record(s) after an "
                "empty-graph restart.", investigation.id, len(replayed),
            )

    return rebuilt
