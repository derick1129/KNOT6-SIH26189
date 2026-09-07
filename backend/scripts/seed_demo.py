"""
Standalone CLI: run the demo dataset through the pipeline and print a
summary of what the analytics modules found. Useful for a quick sanity
check without starting the API server:

    cd backend
    python scripts/seed_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analytics.anomaly import run_all_detectors
from app.analytics.centrality import compute_influencers
from app.analytics.community import compute_communities
from app.db.graph_store import NetworkXGraphStore
from app.services.seed_demo import seed


def main() -> None:
    store = NetworkXGraphStore()
    summary = seed(store)

    print("=== Ingestion summary ===")
    for source, s in summary["structured"].items():
        print(f"  {source}: {s['entities_created']} entities, {s['relations_created']} relations, "
              f"{s['entities_merged']} auto-merged")
    print(f"  unstructured documents processed: {summary['documents']}")

    print(f"\n=== Graph size === {len(store.all_nodes())} nodes, {len(store.all_edges())} edges")

    print("\n=== Top influencers ===")
    for inf in compute_influencers(store, top_n=5):
        print(f"  #{inf.rank} {inf.entity.label} ({inf.entity.type}) "
              f"composite={inf.composite_score} degree={inf.degree_centrality} "
              f"betweenness={inf.betweenness_centrality} pagerank={inf.pagerank}")

    print("\n=== Communities ===")
    for c in compute_communities(store):
        print(f"  community {c.community_id}: {c.size} members, density={c.density} -> {c.label}")

    print("\n=== Anomalies ===")
    for a in run_all_detectors(store):
        print(f"  [{a.severity.upper()}] {a.type}: {a.description}")


if __name__ == "__main__":
    main()
