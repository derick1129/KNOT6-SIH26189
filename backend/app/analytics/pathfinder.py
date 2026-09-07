"""
"How are these two suspects connected?" -- the single most common
investigator question a link chart answers. Shortest path is the
headline result; `all_paths_count` (bounded by a cutoff so it stays fast
on a dense graph) gives a sense of how *robustly* connected two people
are versus connected by one coincidental edge.
"""
from __future__ import annotations

import networkx as nx

from app.db.graph_store import GraphStore
from app.models.schemas import EntityOut, PathHop, PathResult, RelationOut


def find_path(store: GraphStore, source_id: str, target_id: str, max_hops: int = 6) -> PathResult:
    g = store.to_networkx()
    if source_id not in g or target_id not in g:
        return PathResult(source=source_id, target=target_id, found=False)

    undirected = g.to_undirected()
    if not nx.has_path(undirected, source_id, target_id):
        return PathResult(source=source_id, target=target_id, found=False)

    node_path = nx.shortest_path(undirected, source_id, target_id)
    hops: list[PathHop] = []
    for i, node_id in enumerate(node_path):
        node = store.get_node(node_id)
        if not node:
            continue
        via_relation = None
        if i > 0:
            prev_id = node_path[i - 1]
            edge_data = None
            if g.has_edge(prev_id, node_id):
                edge_data = list(g.get_edge_data(prev_id, node_id).items())[0]
            elif g.has_edge(node_id, prev_id):
                edge_data = list(g.get_edge_data(node_id, prev_id).items())[0]
            if edge_data:
                key, d = edge_data
                via_relation = RelationOut(id=key, source=prev_id, target=node_id, type=d.get("type", "RELATED"),
                                            attributes=d.get("attributes", {}), weight=d.get("weight", 1.0),
                                            evidence=d.get("evidence", []))
        hops.append(PathHop(
            entity=EntityOut(id=node.id, type=node.type, label=node.label, attributes=node.attributes,
                              source_count=len(node.source_documents)),
            via_relation=via_relation,
        ))

    all_paths_count = 0
    for _ in nx.all_simple_paths(undirected, source_id, target_id, cutoff=max_hops):
        all_paths_count += 1
        if all_paths_count >= 50:  # cap: this is a UI hint, not a full enumeration
            break

    return PathResult(source=source_id, target=target_id, found=True, hops=len(node_path) - 1,
                       path=hops, all_paths_count=all_paths_count)
