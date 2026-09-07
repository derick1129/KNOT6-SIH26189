"""
Community detection: cluster the network into probable gangs / cells /
syndicate sub-groups using the Louvain method (modularity maximization).

Why Louvain specifically: it needs no prior knowledge of how many groups
exist (unlike k-means-style clustering), runs near-linearly so it stays
usable as the graph grows to thousands of entities, and its output
(a hard partition) maps directly onto the investigative question
"which suspects likely belong to the same operating cell" -- which is
what the Participants/Problem-statements-style grouping in the PS asks
for ("build relationship maps... identify... networks").
"""
from __future__ import annotations

import networkx as nx

try:
    import community as community_louvain  # python-louvain
except ImportError:  # pragma: no cover
    community_louvain = None

from app.db.graph_store import GraphStore
from app.models.schemas import Community, EntityOut


def compute_communities(store: GraphStore, min_size: int = 2) -> list[Community]:
    g = store.to_networkx()
    if g.number_of_nodes() < 2:
        return []

    simple = nx.Graph()
    for n, d in g.nodes(data=True):
        simple.add_node(n, **d)
    for u, v, d in g.edges(data=True):
        w = d.get("weight", 1.0)
        if simple.has_edge(u, v):
            simple[u][v]["weight"] += w
        else:
            simple.add_edge(u, v, weight=w)

    if simple.number_of_edges() == 0:
        return []

    if community_louvain is not None:
        partition = community_louvain.best_partition(simple, weight="weight", random_state=42)
    else:  # pragma: no cover - fallback if python-louvain isn't installed
        partition = {n: i for i, comp in enumerate(nx.connected_components(simple)) for n in comp}

    groups: dict[int, list[str]] = {}
    for node_id, comm_id in partition.items():
        groups.setdefault(comm_id, []).append(node_id)

    results = []
    for comm_id, members in groups.items():
        if len(members) < min_size:
            continue
        sub = simple.subgraph(members)
        possible_edges = len(members) * (len(members) - 1) / 2
        density = round(sub.number_of_edges() / possible_edges, 3) if possible_edges else 0.0

        entities = []
        for m in members:
            node = store.get_node(m)
            if node:
                entities.append(EntityOut(id=node.id, type=node.type, label=node.label,
                                           attributes=node.attributes, source_count=len(node.source_documents)))
        entities.sort(key=lambda e: e.label)
        label_sample = ", ".join(e.label for e in entities[:3])
        results.append(Community(
            community_id=comm_id, size=len(members), members=entities, density=density,
            label=f"Cluster ({label_sample}{'…' if len(entities) > 3 else ''})",
        ))

    results.sort(key=lambda c: c.size, reverse=True)
    return results
