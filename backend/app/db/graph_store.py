"""
Graph storage abstraction.

`GraphStore` is the single interface every other module (graph builder,
analytics, API routes) talks to. Two implementations exist:

  - NetworkXGraphStore: pure in-process, zero external dependencies.
    This is the default so the whole system runs with nothing but
    `pip install` -- no Docker, no Neo4j server -- which matters for a
    hackathon demo/judge environment and for unit tests.

  - Neo4jGraphStore: talks to a real Neo4j instance over Bolt. This is
    the intended production backend: Neo4j's native graph storage and
    (with the GDS plugin) built-in centrality/community algorithms scale
    to the millions-of-nodes, billions-of-edges size that real CDR +
    financial + case data reaches at NCRB scale, which an in-memory
    NetworkX graph cannot.

Both implementations satisfy the exact same method signatures, so
`app/analytics/*.py` and `app/api/routes/*.py` never need to know which
one is active. Only `app/db/graph_store.py` (this file) and
`docker-compose.yml` / `.env` know.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

import networkx as nx

from app.core.config import get_settings


@dataclass
class Node:
    id: str
    type: str
    label: str
    attributes: dict[str, Any] = field(default_factory=dict)
    source_documents: set[str] = field(default_factory=set)


@dataclass
class Edge:
    id: str
    source: str
    target: str
    type: str
    attributes: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    evidence: list[str] = field(default_factory=list)


class GraphStore(ABC):
    @abstractmethod
    def upsert_node(self, node_id: str, type: str, label: str, attributes: dict, source_document: str | None = None) -> Node: ...

    @abstractmethod
    def upsert_edge(self, source: str, target: str, type: str, attributes: dict | None = None,
                     weight: float = 1.0, evidence: str | None = None) -> Edge: ...

    @abstractmethod
    def record_edge_event(self, source: str, target: str, type: str, event: dict,
                           evidence: str | None = None) -> Edge:
        """
        Append a timestamped event (a single CDR call, a single financial
        transaction) to an edge, on top of the aggregate upsert_edge.
        Anomaly detection (burst calling, short-duration-call ratios,
        circular transactions) reads these event logs. Full event-level
        history is kept faithfully on the NetworkX backend; the Neo4j
        backend keeps an aggregate count/weight (see class docstring) --
        swap in a proper event/relationship-per-call model there before
        relying on it for anomaly detection at scale.
        """
        ...

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[Node]: ...

    @abstractmethod
    def all_nodes(self) -> list[Node]: ...

    @abstractmethod
    def all_edges(self) -> list[Edge]: ...

    @abstractmethod
    def neighbors(self, node_id: str, hops: int = 1) -> tuple[list[Node], list[Edge]]: ...

    @abstractmethod
    def search_nodes(self, query: str, type: str | None = None, limit: int = 25) -> list[Node]: ...

    @abstractmethod
    def merge_nodes(self, keep_id: str, merge_id: str) -> None:
        """Merge `merge_id` into `keep_id`: re-point edges, union attributes/sources, delete merge_id."""
        ...

    @abstractmethod
    def to_networkx(self) -> nx.MultiDiGraph:
        """Return a NetworkX view for analytics that always run in-process (centrality, community, paths)."""
        ...

    @abstractmethod
    def remove_nodes(self, node_ids: list[str]) -> None:
        """
        Delete exactly these nodes (and every edge touching them), nothing
        else. This is the primitive `ScopedGraphStore.clear()` builds on to
        support a safe, targeted, investigation-scoped reset -- see that
        class's docstring. `node_ids` are physical (already-namespaced) ids
        as returned by `all_nodes()`/`all_edges()` on this store.
        """
        ...

    @abstractmethod
    def clear(self) -> None: ...


class NetworkXGraphStore(GraphStore):
    """Default zero-infra backend. Thread-unsafe by design (single demo process)."""

    def __init__(self) -> None:
        self._g = nx.MultiDiGraph()

    def upsert_node(self, node_id: str, type: str, label: str, attributes: dict,
                     source_document: str | None = None) -> Node:
        if self._g.has_node(node_id):
            data = self._g.nodes[node_id]
            data["attributes"].update({k: v for k, v in attributes.items() if v})
            if source_document:
                data["source_documents"].add(source_document)
            if label and len(label) > len(data.get("label", "")):
                data["label"] = label
        else:
            self._g.add_node(
                node_id,
                type=type,
                label=label,
                attributes=dict(attributes),
                source_documents={source_document} if source_document else set(),
            )
        return self.get_node(node_id)  # type: ignore[return-value]

    def upsert_edge(self, source: str, target: str, type: str, attributes: dict | None = None,
                     weight: float = 1.0, evidence: str | None = None) -> Edge:
        attributes = attributes or {}
        # Check for an existing edge of the same type between the pair -> strengthen it
        for _, _, key, data in self._g.edges(source, keys=True, data=True):
            if data.get("_target") == target and data.get("type") == type:
                data["weight"] = data.get("weight", 1.0) + weight
                if evidence and evidence not in data["evidence"]:
                    data["evidence"].append(evidence)
                data["attributes"].update(attributes)
                return Edge(id=key, source=source, target=target, type=type,
                            attributes=data["attributes"], weight=data["weight"], evidence=data["evidence"])

        edge_id = str(uuid.uuid4())
        self._g.add_edge(
            source, target, key=edge_id,
            type=type, attributes=attributes, weight=weight,
            evidence=[evidence] if evidence else [], _target=target,
        )
        return Edge(id=edge_id, source=source, target=target, type=type,
                     attributes=attributes, weight=weight, evidence=[evidence] if evidence else [])

    def record_edge_event(self, source: str, target: str, type: str, event: dict,
                           evidence: str | None = None) -> Edge:
        for _, _, key, data in self._g.edges(source, keys=True, data=True):
            if data.get("_target") == target and data.get("type") == type:
                data.setdefault("events", []).append(event)
                data["weight"] = data.get("weight", 1.0) + 1
                if evidence and evidence not in data["evidence"]:
                    data["evidence"].append(evidence)
                return Edge(id=key, source=source, target=target, type=type,
                            attributes=data["attributes"], weight=data["weight"], evidence=data["evidence"])
        edge_id = str(uuid.uuid4())
        self._g.add_edge(
            source, target, key=edge_id, type=type, attributes={}, weight=1.0,
            evidence=[evidence] if evidence else [], events=[event], _target=target,
        )
        return Edge(id=edge_id, source=source, target=target, type=type,
                     attributes={}, weight=1.0, evidence=[evidence] if evidence else [])

    def get_node(self, node_id: str) -> Optional[Node]:
        if not self._g.has_node(node_id):
            return None
        d = self._g.nodes[node_id]
        return Node(id=node_id, type=d["type"], label=d["label"],
                    attributes=d["attributes"], source_documents=set(d["source_documents"]))

    def all_nodes(self) -> list[Node]:
        return [self.get_node(n) for n in self._g.nodes]  # type: ignore[misc]

    def all_edges(self) -> list[Edge]:
        out = []
        for u, v, k, d in self._g.edges(keys=True, data=True):
            out.append(Edge(id=k, source=u, target=v, type=d["type"],
                             attributes=d["attributes"], weight=d["weight"], evidence=d["evidence"]))
        return out

    def neighbors(self, node_id: str, hops: int = 1) -> tuple[list[Node], list[Edge]]:
        if not self._g.has_node(node_id):
            return [], []
        undirected = self._g.to_undirected(as_view=True)
        reachable: set[str] = {node_id}
        frontier = {node_id}
        for _ in range(hops):
            next_frontier = set()
            for n in frontier:
                next_frontier |= set(undirected.neighbors(n))
            frontier = next_frontier - reachable
            reachable |= frontier
        nodes = [self.get_node(n) for n in reachable]
        edges = []
        for u, v, k, d in self._g.edges(keys=True, data=True):
            if u in reachable and v in reachable:
                edges.append(Edge(id=k, source=u, target=v, type=d["type"],
                                   attributes=d["attributes"], weight=d["weight"], evidence=d["evidence"]))
        return [n for n in nodes if n], edges

    def search_nodes(self, query: str, type: str | None = None, limit: int = 25) -> list[Node]:
        q = query.lower().strip()
        results = []
        for n in self.all_nodes():
            if type and n.type != type:
                continue
            haystack = n.label.lower() + " " + " ".join(str(v).lower() for v in n.attributes.values())
            if q in haystack:
                results.append(n)
            if len(results) >= limit:
                break
        return results

    def merge_nodes(self, keep_id: str, merge_id: str) -> None:
        if keep_id == merge_id or not self._g.has_node(merge_id):
            return
        keep = self._g.nodes[keep_id]
        merged = self._g.nodes[merge_id]
        keep["attributes"] = {**merged["attributes"], **keep["attributes"]}
        keep["source_documents"] |= merged["source_documents"]

        for u, v, k, d in list(self._g.in_edges(merge_id, keys=True, data=True)):
            self._g.add_edge(u, keep_id, key=k, **{**d, "_target": keep_id})
        for u, v, k, d in list(self._g.out_edges(merge_id, keys=True, data=True)):
            self._g.add_edge(keep_id, v, key=k, **{**d, "_target": v})
        self._g.remove_node(merge_id)

    def to_networkx(self) -> nx.MultiDiGraph:
        return self._g

    def remove_nodes(self, node_ids: list[str]) -> None:
        self._g.remove_nodes_from(node_ids)

    def clear(self) -> None:
        self._g = nx.MultiDiGraph()


class Neo4jGraphStore(GraphStore):
    """
    Production backend. Requires `neo4j` package + a reachable Neo4j 5.x
    instance (see docker-compose.yml). Cypher below uses a single generic
    `:Entity {id, type, label}` label plus a `type` property rather than
    dynamic Neo4j labels, so new entity types (added by future data
    sources) never require a schema migration.
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase  # imported lazily: optional dependency path

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._ensure_constraints()

    def _ensure_constraints(self) -> None:
        with self._driver.session() as session:
            session.run(
                "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE"
            )

    def upsert_node(self, node_id: str, type: str, label: str, attributes: dict,
                     source_document: str | None = None) -> Node:
        with self._driver.session() as session:
            session.run(
                """
                MERGE (e:Entity {id: $id})
                ON CREATE SET e.type = $type, e.label = $label, e.attributes = $attrs,
                              e.source_documents = $sources
                ON MATCH SET e.label = CASE WHEN size($label) > size(e.label) THEN $label ELSE e.label END,
                             e.attributes = apoc.map.merge(e.attributes, $attrs)
                """,
                id=node_id, type=type, label=label, attrs=attributes,
                sources=[source_document] if source_document else [],
            )
        return self.get_node(node_id)  # type: ignore[return-value]

    def upsert_edge(self, source: str, target: str, type: str, attributes: dict | None = None,
                     weight: float = 1.0, evidence: str | None = None) -> Edge:
        edge_id = str(uuid.uuid4())
        with self._driver.session() as session:
            session.run(
                """
                MATCH (a:Entity {id: $source}), (b:Entity {id: $target})
                MERGE (a)-[r:RELATION {type: $type}]->(b)
                ON CREATE SET r.id = $edge_id, r.weight = $weight, r.attributes = $attrs, r.evidence = $evidence_list
                ON MATCH SET r.weight = coalesce(r.weight, 0) + $weight
                """,
                source=source, target=target, type=type, edge_id=edge_id,
                weight=weight, attrs=attributes or {},
                evidence_list=[evidence] if evidence else [],
            )
        return Edge(id=edge_id, source=source, target=target, type=type,
                     attributes=attributes or {}, weight=weight, evidence=[evidence] if evidence else [])

    def record_edge_event(self, source: str, target: str, type: str, event: dict,
                           evidence: str | None = None) -> Edge:
        # See ABC docstring: aggregate-only here (count + weight); full
        # per-event history is a NetworkX-backend feature in this
        # prototype. A production build would model each call/transaction
        # as its own :EVENT node timestamped and linked to both parties.
        import json
        with self._driver.session() as session:
            session.run(
                """
                MATCH (a:Entity {id: $source}), (b:Entity {id: $target})
                MERGE (a)-[r:RELATION {type: $type}]->(b)
                ON CREATE SET r.id = $edge_id, r.weight = 1, r.attributes = {}, r.evidence = $evidence_list,
                              r.event_count = 1, r.last_event = $event_json
                ON MATCH SET r.weight = coalesce(r.weight, 0) + 1,
                             r.event_count = coalesce(r.event_count, 0) + 1,
                             r.last_event = $event_json
                """,
                source=source, target=target, type=type, edge_id=str(uuid.uuid4()),
                evidence_list=[evidence] if evidence else [], event_json=json.dumps(event, default=str),
            )
        return Edge(id="", source=source, target=target, type=type, attributes={}, weight=1.0,
                     evidence=[evidence] if evidence else [])

    def get_node(self, node_id: str) -> Optional[Node]:
        with self._driver.session() as session:
            rec = session.run("MATCH (e:Entity {id: $id}) RETURN e", id=node_id).single()
            if not rec:
                return None
            e = rec["e"]
            return Node(id=e["id"], type=e["type"], label=e["label"],
                        attributes=e.get("attributes", {}), source_documents=set(e.get("source_documents", [])))

    def all_nodes(self) -> list[Node]:
        with self._driver.session() as session:
            rows = session.run("MATCH (e:Entity) RETURN e")
            return [Node(id=r["e"]["id"], type=r["e"]["type"], label=r["e"]["label"],
                         attributes=r["e"].get("attributes", {}),
                         source_documents=set(r["e"].get("source_documents", []))) for r in rows]

    def all_edges(self) -> list[Edge]:
        with self._driver.session() as session:
            rows = session.run(
                "MATCH (a:Entity)-[r:RELATION]->(b:Entity) RETURN a.id AS s, b.id AS t, r"
            )
            return [Edge(id=r["r"].get("id", str(uuid.uuid4())), source=r["s"], target=r["t"],
                         type=r["r"]["type"], attributes=r["r"].get("attributes", {}),
                         weight=r["r"].get("weight", 1.0), evidence=r["r"].get("evidence", [])) for r in rows]

    def neighbors(self, node_id: str, hops: int = 1) -> tuple[list[Node], list[Edge]]:
        with self._driver.session() as session:
            rows = session.run(
                f"""
                MATCH (start:Entity {{id: $id}})
                CALL apoc.path.subgraphAll(start, {{maxLevel: $hops}})
                YIELD nodes, relationships
                RETURN nodes, relationships
                """,
                id=node_id, hops=hops,
            )
            rec = rows.single()
            if not rec:
                return [], []
            nodes = [Node(id=n["id"], type=n["type"], label=n["label"],
                          attributes=n.get("attributes", {}), source_documents=set(n.get("source_documents", [])))
                     for n in rec["nodes"]]
            edges = [Edge(id=r.get("id", str(uuid.uuid4())), source=r.start_node["id"], target=r.end_node["id"],
                          type=r["type"], attributes=r.get("attributes", {}), weight=r.get("weight", 1.0),
                          evidence=r.get("evidence", [])) for r in rec["relationships"]]
            return nodes, edges

    def search_nodes(self, query: str, type: str | None = None, limit: int = 25) -> list[Node]:
        with self._driver.session() as session:
            cypher = "MATCH (e:Entity) WHERE toLower(e.label) CONTAINS toLower($q)"
            if type:
                cypher += " AND e.type = $type"
            cypher += " RETURN e LIMIT $limit"
            rows = session.run(cypher, q=query, type=type, limit=limit)
            return [Node(id=r["e"]["id"], type=r["e"]["type"], label=r["e"]["label"],
                         attributes=r["e"].get("attributes", {}),
                         source_documents=set(r["e"].get("source_documents", []))) for r in rows]

    def merge_nodes(self, keep_id: str, merge_id: str) -> None:
        with self._driver.session() as session:
            session.run(
                """
                MATCH (keep:Entity {id: $keep_id}), (merge:Entity {id: $merge_id})
                CALL apoc.refactor.mergeNodes([keep, merge], {properties: 'combine', mergeRels: true})
                YIELD node RETURN node
                """,
                keep_id=keep_id, merge_id=merge_id,
            )

    def to_networkx(self) -> nx.MultiDiGraph:
        """
        Pull the whole graph into NetworkX for analytics. Fine at the sizes
        a demo/pilot deployment sees; at true NCRB scale, swap the
        analytics module to call Neo4j GDS procedures directly instead of
        materializing the graph client-side (the call sites in
        app/analytics/* are the only place that would need to change).
        """
        g = nx.MultiDiGraph()
        for n in self.all_nodes():
            g.add_node(n.id, type=n.type, label=n.label, attributes=n.attributes,
                       source_documents=n.source_documents)
        for e in self.all_edges():
            g.add_edge(e.source, e.target, key=e.id, type=e.type, attributes=e.attributes,
                       weight=e.weight, evidence=e.evidence, _target=e.target)
        return g

    def remove_nodes(self, node_ids: list[str]) -> None:
        if not node_ids:
            return
        with self._driver.session() as session:
            session.run("MATCH (e:Entity) WHERE e.id IN $ids DETACH DELETE e", ids=node_ids)

    def clear(self) -> None:
        with self._driver.session() as session:
            session.run("MATCH (n:Entity) DETACH DELETE n")


class ScopedGraphStore(GraphStore):
    """
    KNOT6 Phase 1: investigation isolation, implemented as a decorator over
    any other GraphStore rather than a change to GraphStore/NetworkXGraphStore
    /Neo4jGraphStore themselves.

    Every node ID this wrapper writes is transparently namespaced with the
    owning investigation ("inv_<investigation_id>::<logical_id>") before
    being handed to the wrapped store, and every ID coming back out is
    stripped back to its logical (unprefixed) form -- so callers on either
    side of this class see exactly the plain entity IDs they always have.
    Concretely, this means `app/graph/graph_builder.py`,
    `app/resolution/entity_resolution.py`, `app/analytics/*.py` and
    `app/services/pipeline.py` needed **zero changes** for Phase 1: they are
    simply handed a `ScopedGraphStore(get_graph_store(), investigation_id)`
    instead of the raw store at the API layer (see `app/api/deps.py`), and
    every existing analytics/resolution/ingestion function keeps working
    unmodified because it never sees a namespaced ID.

    Because nothing ever creates an edge between two different investigations'
    namespaced IDs, `neighbors()`/path-finding naturally never traverses out
    of scope -- isolation falls out of the ID namespacing itself, not extra
    filtering logic layered on top of every read.

    `case_id` is intentionally *not* part of the graph-level scope in Phase 1
    (see docs/KNOT6_ARCHITECTURE.md): the isolation boundary the PS and
    Phase 1 both care about is the investigation, and entities legitimately
    recur across cases within one investigation (the same phone number
    showing up in two related cases of the same investigation is a feature,
    not a bug, per the original architecture doc's §9.2 "cross-case entity
    linking" note). Evidence rows still carry their own `case_id` in
    PostgreSQL for case-level bookkeeping.
    """

    def __init__(self, inner: GraphStore, investigation_id: str) -> None:
        if not investigation_id:
            raise ValueError("ScopedGraphStore requires a non-empty investigation_id.")
        self._inner = inner
        self.investigation_id = investigation_id
        self._prefix = f"inv_{investigation_id}::"

    # -- id (un)namespacing --------------------------------------------
    def _scope(self, node_id: str) -> str:
        return f"{self._prefix}{node_id}"

    def _unscope(self, physical_id: str) -> str:
        return physical_id[len(self._prefix):] if physical_id.startswith(self._prefix) else physical_id

    def _in_scope(self, physical_id: str) -> bool:
        return physical_id.startswith(self._prefix)

    def _unscope_node(self, node: Optional[Node]) -> Optional[Node]:
        if node is None:
            return None
        node.id = self._unscope(node.id)
        node.attributes.setdefault("_investigation_id", self.investigation_id)
        return node

    def _unscope_edge(self, edge: Edge) -> Edge:
        edge.source = self._unscope(edge.source)
        edge.target = self._unscope(edge.target)
        return edge

    # -- writes -----------------------------------------------------------
    def upsert_node(self, node_id: str, type: str, label: str, attributes: dict,
                     source_document: str | None = None) -> Node:
        node = self._inner.upsert_node(self._scope(node_id), type, label, attributes, source_document)
        return self._unscope_node(node)  # type: ignore[return-value]

    def upsert_edge(self, source: str, target: str, type: str, attributes: dict | None = None,
                     weight: float = 1.0, evidence: str | None = None) -> Edge:
        edge = self._inner.upsert_edge(self._scope(source), self._scope(target), type,
                                        attributes=attributes, weight=weight, evidence=evidence)
        return self._unscope_edge(edge)

    def record_edge_event(self, source: str, target: str, type: str, event: dict,
                           evidence: str | None = None) -> Edge:
        edge = self._inner.record_edge_event(self._scope(source), self._scope(target), type, event, evidence)
        return self._unscope_edge(edge)

    # -- reads --------------------------------------------------------------
    def get_node(self, node_id: str) -> Optional[Node]:
        return self._unscope_node(self._inner.get_node(self._scope(node_id)))

    def all_nodes(self) -> list[Node]:
        return [self._unscope_node(n) for n in self._inner.all_nodes() if self._in_scope(n.id)]  # type: ignore[misc]

    def all_edges(self) -> list[Edge]:
        return [self._unscope_edge(e) for e in self._inner.all_edges()
                if self._in_scope(e.source) and self._in_scope(e.target)]

    def neighbors(self, node_id: str, hops: int = 1) -> tuple[list[Node], list[Edge]]:
        nodes, edges = self._inner.neighbors(self._scope(node_id), hops=hops)
        return ([self._unscope_node(n) for n in nodes],  # type: ignore[misc]
                [self._unscope_edge(e) for e in edges])

    def search_nodes(self, query: str, type: str | None = None, limit: int = 25) -> list[Node]:
        # Over-fetch from the (potentially multi-investigation) inner store,
        # then filter to this investigation's namespace and trim. Fine at
        # prototype scale; a production Neo4j build would instead filter by
        # an indexed investigation_id property server-side.
        raw = self._inner.search_nodes(query, type=type, limit=max(limit * 10, 200))
        matched = [self._unscope_node(n) for n in raw if self._in_scope(n.id)]
        return matched[:limit]  # type: ignore[return-value]

    def merge_nodes(self, keep_id: str, merge_id: str) -> None:
        self._inner.merge_nodes(self._scope(keep_id), self._scope(merge_id))

    def remove_nodes(self, node_ids: list[str]) -> None:
        self._inner.remove_nodes([self._scope(n) for n in node_ids])

    def to_networkx(self) -> nx.MultiDiGraph:
        g = self._inner.to_networkx()
        sub = nx.MultiDiGraph()
        for n, d in g.nodes(data=True):
            if self._in_scope(n):
                sub.add_node(self._unscope(n), **d)
        for u, v, k, d in g.edges(keys=True, data=True):
            if self._in_scope(u) and self._in_scope(v):
                d = dict(d)
                d["_target"] = self._unscope(d.get("_target", v))
                sub.add_edge(self._unscope(u), self._unscope(v), key=k, **d)
        return sub

    def clear(self) -> None:
        """
        Delete every node (and touching edge) namespaced to this investigation
        only -- every other investigation sharing the same inner store is
        untouched. Built on `remove_nodes`, which each GraphStore backend
        implements as a real, targeted deletion (see that method's
        docstring), so this is safe on a live, multi-investigation store --
        unlike the pre-Phase-1 version of this method, which refused to run
        at all rather than risk clearing more than one investigation's data.
        Used by the demo-reseed path (`app/services/graph_recovery.py`) to
        restore Operation Nexus from its canonical source without disturbing
        any other investigation's graph.
        """
        physical_ids = [n.id for n in self._inner.all_nodes() if self._in_scope(n.id)]
        self._inner.remove_nodes(physical_ids)


@lru_cache
def get_graph_store() -> GraphStore:
    settings = get_settings()
    if settings.graph_backend == "neo4j":
        try:
            return Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        except Exception as exc:  # pragma: no cover - fallback path
            import logging
            logging.getLogger(__name__).warning(
                "Neo4j unreachable (%s); falling back to in-process NetworkX store.", exc
            )
            return NetworkXGraphStore()
    return NetworkXGraphStore()
