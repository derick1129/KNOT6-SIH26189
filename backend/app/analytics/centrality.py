"""
Key-influencer detection: "who matters" in the network, answered with
three complementary centrality measures rather than one, because each
catches a different investigative role:

  - Degree centrality      -> who has the most direct contacts (a hub /
                               well-connected operator)
  - Betweenness centrality -> who sits *between* clusters that otherwise
                               wouldn't talk -- often the courier,
                               fixer, or intermediary bridging two gangs
                               or a financier separate from the muscle
  - PageRank                -> who is connected to *other important*
                               people, not just many people -- surfaces
                               the person several hops removed who a
                               naive degree count would miss entirely

`composite_score` blends all three (equal weight by default) into one
ranked list, which is what the dashboard's "Top Influencers" panel shows;
the individual scores stay available so an investigator can see *why*
someone ranks highly (hub vs. bridge vs. well-connected-to-the-connected).
"""
from __future__ import annotations

import networkx as nx

from app.db.graph_store import GraphStore
from app.graph import schema
from app.models.schemas import EntityOut, InfluencerScore


def _to_simple_undirected_weighted(g: nx.MultiDiGraph) -> nx.Graph:
    simple = nx.Graph()
    for n, d in g.nodes(data=True):
        simple.add_node(n, **d)
    for u, v, d in g.edges(data=True):
        w = d.get("weight", 1.0)
        if simple.has_edge(u, v):
            simple[u][v]["weight"] += w
        else:
            simple.add_edge(u, v, weight=w)
    return simple


def compute_influencers(store: GraphStore, top_n: int = 10,
                         actor_types: tuple[str, ...] = (schema.PERSON, schema.ORGANIZATION)) -> list[InfluencerScore]:
    g = store.to_networkx()
    if g.number_of_nodes() == 0:
        return []
    simple = _to_simple_undirected_weighted(g)

    degree = nx.degree_centrality(simple)
    try:
        betweenness = nx.betweenness_centrality(simple, weight="weight", normalized=True)
    except Exception:
        betweenness = {n: 0.0 for n in simple.nodes}
    try:
        pagerank = nx.pagerank(g, weight="weight")
    except Exception:
        pagerank = {n: 0.0 for n in simple.nodes}

    scored = []
    for node_id in simple.nodes:
        node = store.get_node(node_id)
        if not node or node.type not in actor_types:
            continue
        d, b, p = degree.get(node_id, 0.0), betweenness.get(node_id, 0.0), pagerank.get(node_id, 0.0)
        composite = round((d + b + p) / 3, 4)
        scored.append((composite, d, b, p, node))

    scored.sort(key=lambda t: t[0], reverse=True)
    results = []
    for rank, (composite, d, b, p, node) in enumerate(scored[:top_n], start=1):
        results.append(InfluencerScore(
            entity=EntityOut(id=node.id, type=node.type, label=node.label, attributes=node.attributes,
                              source_count=len(node.source_documents)),
            degree_centrality=round(d, 4), betweenness_centrality=round(b, 4), pagerank=round(p, 4),
            composite_score=composite, rank=rank,
        ))
    return results
