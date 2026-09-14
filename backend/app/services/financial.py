"""
Financial Intelligence backend aggregation: turns the graph's
FINANCIAL_ACCOUNT nodes and TRANSACTED_WITH edges (see
app/ingestion/loaders.py:load_financial_records) into the account-level
summary, counterparty ranking, and circular-flow view the PS spec asks for
-- computed once, server-side, from real transaction amounts already on the
graph (never invented). Reuses the existing, unmodified anomaly detectors
(app/analytics/anomaly.py) for suspicious-pattern/circular-flow detection
rather than re-implementing that logic, and app/services/timeline.py for the
transaction timeline -- so this module and the rest of KNOT6 never disagree
about what counts as a transaction or a suspicious pattern.

frontend/src/pages/FinancialIntelligence.tsx previously computed all of this
client-side from `/graph` + `/analytics/anomalies`; it now consumes this one
endpoint instead of duplicating the aggregation logic in the browser.
"""
from __future__ import annotations

from collections import defaultdict

from app.analytics.anomaly import run_all_detectors
from app.db.graph_store import GraphStore
from app.graph import schema
from app.models.schemas import (
    CircularFlowOut, CounterpartyOut, EntityOut, FinancialAccountOut, FinancialIntelligenceOut,
)
from app.services.timeline import build_timeline


def _entity_out(node) -> EntityOut:
    return EntityOut(id=node.id, type=node.type, label=node.label, attributes=node.attributes,
                      source_count=len(node.source_documents))


def build_financial_intelligence(store: GraphStore, investigation_id: str) -> FinancialIntelligenceOut:
    accounts = [n for n in store.all_nodes() if n.type == schema.FINANCIAL_ACCOUNT]
    account_ids = {a.id for a in accounts}

    # Per-account running totals, computed once over every TRANSACTED_WITH
    # edge's real recorded events -- never derived from edge `weight` alone
    # (weight is a generic centrality input, not a monetary total).
    inbound: dict[str, float] = defaultdict(float)
    outbound: dict[str, float] = defaultdict(float)
    txn_count: dict[str, int] = defaultdict(int)
    counterparty_amount: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counterparty_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    account_evidence: dict[str, set[str]] = defaultdict(set)
    total_txn_count = 0
    all_evidence: set[str] = set()

    # Real per-transaction amounts live in the raw edge dict's `events` list
    # (see app/db/graph_store.py:record_edge_event) -- `store.all_edges()`'s
    # `Edge` dataclass does not carry it (only id/type/attributes/weight/
    # evidence), so this reads the same `to_networkx()` view
    # app/services/timeline.py's `_events_from_graph` already uses, rather
    # than silently falling back to a placeholder amount.
    g = store.to_networkx()
    for u, v, k, d in g.edges(keys=True, data=True):
        if d.get("type") != schema.TRANSACTED_WITH:
            continue
        if u not in account_ids or v not in account_ids:
            continue
        events = d.get("events") or []
        evidence = list(d.get("evidence", []))

        for ev in events:
            amount = float(ev.get("amount") or 0)
            outbound[u] += amount
            inbound[v] += amount
            txn_count[u] += 1
            txn_count[v] += 1
            counterparty_amount[u][v] += amount
            counterparty_amount[v][u] += amount
            counterparty_count[u][v] += 1
            counterparty_count[v][u] += 1
            total_txn_count += 1
        account_evidence[u].update(evidence)
        account_evidence[v].update(evidence)
        all_evidence.update(evidence)

    account_summaries: list[FinancialAccountOut] = []
    for acct in accounts:
        holder_nodes = []
        neighbors, edges = store.neighbors(acct.id, hops=1)
        for edge in edges:
            if edge.type == schema.OWNS and edge.target == acct.id:
                holder = store.get_node(edge.source)
                if holder:
                    holder_nodes.append(_entity_out(holder))
        account_summaries.append(FinancialAccountOut(
            account=_entity_out(acct), holder_entities=holder_nodes,
            transaction_count=txn_count.get(acct.id, 0),
            total_inbound=round(inbound.get(acct.id, 0.0), 2),
            total_outbound=round(outbound.get(acct.id, 0.0), 2),
            counterparty_count=len(counterparty_amount.get(acct.id, {})),
        ))
    account_summaries.sort(key=lambda a: a.transaction_count, reverse=True)

    # Major counterparties: the highest-volume account-to-account pairs
    # across the whole investigation (deduplicated, undirected).
    pair_totals: dict[frozenset, float] = defaultdict(float)
    pair_counts: dict[frozenset, int] = defaultdict(int)
    for src_id, targets in counterparty_amount.items():
        for tgt_id, amt in targets.items():
            pair = frozenset((src_id, tgt_id))
            pair_totals[pair] = amt  # already symmetric (added both directions above)
            pair_counts[pair] = counterparty_count[src_id][tgt_id]
    ranked_pairs = sorted(pair_totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
    major_counterparties: list[CounterpartyOut] = []
    seen_accounts: set[str] = set()
    for pair, amt in ranked_pairs:
        for acct_id in pair:
            if acct_id in seen_accounts:
                continue
            node = store.get_node(acct_id)
            if not node:
                continue
            seen_accounts.add(acct_id)
            major_counterparties.append(CounterpartyOut(
                account=_entity_out(node), transaction_count=txn_count.get(acct_id, 0),
                total_amount=round(inbound.get(acct_id, 0) + outbound.get(acct_id, 0), 2),
            ))
        if len(major_counterparties) >= 8:
            break

    all_flags = run_all_detectors(store)
    # Any detected signal that actually touches a FINANCIAL_ACCOUNT node is a
    # financially-relevant pattern -- naturally includes every
    # CIRCULAR_TRANSACTION (whose entities_involved is exactly the cycle of
    # accounts) plus any other detector type that happens to flag an account.
    suspicious = [f for f in all_flags if set(f.entities_involved) & account_ids]
    circular_flows: list[CircularFlowOut] = []
    for f in all_flags:
        if f.type != "CIRCULAR_TRANSACTION":
            continue
        labels = []
        cycle_evidence: set[str] = set()
        for eid in f.entities_involved:
            node = store.get_node(eid)
            labels.append(node.label if node else eid)
            cycle_evidence.update(account_evidence.get(eid, set()))
        circular_flows.append(CircularFlowOut(
            account_ids=list(f.entities_involved), account_labels=labels,
            description=f.description, evidence=sorted(cycle_evidence),
        ))

    transaction_timeline = [e for e in build_timeline(store, limit=200) if e.kind == "TRANSACTION"]

    return FinancialIntelligenceOut(
        investigation_id=investigation_id, accounts=account_summaries, transaction_count=total_txn_count,
        total_inbound=round(sum(inbound.values()), 2), total_outbound=round(sum(outbound.values()), 2),
        major_counterparties=major_counterparties, transaction_timeline=transaction_timeline,
        suspicious_patterns=suspicious, circular_flows=circular_flows,
        relevant_evidence=sorted(all_evidence),
    )
