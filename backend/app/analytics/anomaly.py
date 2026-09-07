"""
Suspicious-pattern detection over the built graph. Each detector targets
a pattern investigators specifically look for, rather than a generic
statistical outlier score, so every flag comes with a plain-language
reason attached:

  BURST_CALLING        - unusually many calls between the same two
                          numbers packed into a short window (classic
                          before/after-an-incident coordination signal)
  SHORT_DURATION_CALLS  - a pair whose calls are mostly a few seconds --
                          consistent with coded "missed call" signalling
                          rather than genuine conversation
  CIRCULAR_TRANSACTION  - money that leaves an account and, through a
                          chain of transfers, returns to it -- a classic
                          layering/laundering signature
  NEW_HIGH_DEGREE_NODE  - an entity whose connectivity is a statistical
                          outlier versus the rest of the network (a
                          sudden, unexplained hub)
  LOCATION_CONVERGENCE  - multiple distinct people placed at the same
                          location around the same time by independent
                          reports -- a possible meeting/handover

These are heuristics tuned for explainability and a fast demo, not a
learned anomaly model -- see docs/ARCHITECTURE.md for how this module
is meant to evolve (e.g. an isolation-forest / temporal-GNN layer)
once real, labelled case outcomes exist to validate against.
"""
from __future__ import annotations

import statistics
import uuid
from datetime import datetime, timedelta

import networkx as nx

from app.core.config import get_settings
from app.db.graph_store import GraphStore
from app.graph import schema
from app.models.schemas import AnomalyFlag


def _parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def detect_burst_and_short_calls(store: GraphStore) -> list[AnomalyFlag]:
    settings = get_settings()
    g = store.to_networkx()
    flags: list[AnomalyFlag] = []

    for u, v, k, d in g.edges(keys=True, data=True):
        if d.get("type") != schema.CALLED:
            continue
        events = d.get("events", [])
        if not events:
            continue
        timestamps = sorted(t for t in (_parse_dt(e.get("timestamp")) for e in events) if t)
        durations = [e.get("duration_seconds") for e in events if isinstance(e.get("duration_seconds"), (int, float))]

        # Burst: N+ calls within a rolling window
        window = timedelta(hours=settings.burst_call_window_hours)
        for i, start in enumerate(timestamps):
            count = sum(1 for t in timestamps if start <= t <= start + window)
            if count >= settings.burst_call_min_count:
                a, b = store.get_node(u), store.get_node(v)
                flags.append(AnomalyFlag(
                    id=str(uuid.uuid4()), type="BURST_CALLING", severity="high",
                    description=(f"{count} calls between {a.label if a else u} and {b.label if b else v} "
                                 f"within a {settings.burst_call_window_hours}-hour window starting {start.isoformat()}."),
                    entities_involved=[u, v],
                    evidence={"call_count": count, "window_start": start.isoformat()},
                ))
                break  # one flag per pair is enough signal

        # Short-duration ratio
        if len(durations) >= 4:
            short_ratio = sum(1 for dur in durations if dur <= settings.short_call_max_seconds) / len(durations)
            if short_ratio >= 0.6:
                a, b = store.get_node(u), store.get_node(v)
                flags.append(AnomalyFlag(
                    id=str(uuid.uuid4()), type="SHORT_DURATION_CALLS", severity="medium",
                    description=(f"{round(short_ratio * 100)}% of calls between {a.label if a else u} and "
                                 f"{b.label if b else v} last {settings.short_call_max_seconds}s or less -- "
                                 "consistent with signalling rather than conversation."),
                    entities_involved=[u, v],
                    evidence={"short_call_ratio": round(short_ratio, 2), "sample_size": len(durations)},
                ))

    return flags


def detect_circular_transactions(store: GraphStore) -> list[AnomalyFlag]:
    settings = get_settings()
    g = store.to_networkx()
    txn_graph = nx.DiGraph()
    for u, v, d in g.edges(data=True):
        if d.get("type") == schema.TRANSACTED_WITH:
            txn_graph.add_edge(u, v, weight=d.get("weight", 1.0))

    flags: list[AnomalyFlag] = []
    seen_cycles: set[frozenset] = set()
    try:
        cycles = list(nx.simple_cycles(txn_graph, length_bound=settings.circular_txn_max_hops))
    except TypeError:  # older networkx without length_bound
        cycles = [c for c in nx.simple_cycles(txn_graph) if len(c) <= settings.circular_txn_max_hops]

    for cycle in cycles:
        if len(cycle) < 2:
            continue
        key = frozenset(cycle)
        if key in seen_cycles:
            continue
        seen_cycles.add(key)
        labels = [store.get_node(n).label if store.get_node(n) else n for n in cycle]
        flags.append(AnomalyFlag(
            id=str(uuid.uuid4()), type="CIRCULAR_TRANSACTION", severity="high",
            description=f"Funds cycle through {len(cycle)} accounts and return to origin: "
                        + " -> ".join(labels) + f" -> {labels[0]}.",
            entities_involved=list(cycle),
            evidence={"cycle_length": len(cycle)},
        ))

    return flags


def detect_high_degree_outliers(store: GraphStore, z_threshold: float = 2.0) -> list[AnomalyFlag]:
    g = store.to_networkx()
    if g.number_of_nodes() < 5:
        return []
    degrees = {n: g.degree(n) for n in g.nodes}
    values = list(degrees.values())
    mean, stdev = statistics.mean(values), statistics.pstdev(values) or 1.0

    flags = []
    for node_id, deg in degrees.items():
        z = (deg - mean) / stdev
        if z >= z_threshold:
            node = store.get_node(node_id)
            if not node or node.type not in (schema.PERSON, schema.ORGANIZATION):
                continue
            flags.append(AnomalyFlag(
                id=str(uuid.uuid4()), type="NEW_HIGH_DEGREE_NODE", severity="medium",
                description=f"{node.label} has {deg} connections, {z:.1f} std. deviations above the network "
                            "average -- a disproportionate hub worth reviewing.",
                entities_involved=[node_id],
                evidence={"degree": deg, "z_score": round(z, 2), "network_mean_degree": round(mean, 2)},
            ))
    return flags


def detect_location_convergence(store: GraphStore, window_hours: int = 72, min_people: int = 3) -> list[AnomalyFlag]:
    g = store.to_networkx()
    flags = []
    for loc_id in [n for n, d in g.nodes(data=True) if d.get("type") == schema.LOCATION]:
        visitors: list[tuple[str, datetime]] = []
        for u, v, d in g.in_edges(loc_id, data=True):
            if d.get("type") != schema.PRESENT_AT:
                continue
            src_node = g.nodes.get(u, {})
            if src_node.get("type") != schema.PERSON:
                continue
            dt = _parse_dt(d.get("attributes", {}).get("document_date"))
            if dt:
                visitors.append((u, dt))

        if len(visitors) < min_people:
            continue
        visitors.sort(key=lambda t: t[1])
        for i in range(len(visitors)):
            window_people = [p for p, t in visitors if visitors[i][1] <= t <= visitors[i][1] + timedelta(hours=window_hours)]
            unique_people = set(window_people)
            if len(unique_people) >= min_people:
                loc_node = store.get_node(loc_id)
                labels = [store.get_node(p).label for p in unique_people if store.get_node(p)]
                flags.append(AnomalyFlag(
                    id=str(uuid.uuid4()), type="LOCATION_CONVERGENCE", severity="medium",
                    description=f"{len(unique_people)} distinct individuals placed at "
                                f"{loc_node.label if loc_node else loc_id} within a {window_hours}-hour window: "
                                + ", ".join(labels) + ".",
                    entities_involved=[loc_id, *unique_people],
                    evidence={"window_hours": window_hours, "person_count": len(unique_people)},
                ))
                break
    return flags


def run_all_detectors(store: GraphStore) -> list[AnomalyFlag]:
    flags: list[AnomalyFlag] = []
    flags.extend(detect_burst_and_short_calls(store))
    flags.extend(detect_circular_transactions(store))
    flags.extend(detect_high_degree_outliers(store))
    flags.extend(detect_location_convergence(store))
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: severity_rank.get(f.severity, 3))
    return flags
