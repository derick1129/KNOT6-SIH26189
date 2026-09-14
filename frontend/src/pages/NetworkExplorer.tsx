import { lazy, Suspense, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, Community, Entity, GraphData, InfluencerScore } from "../api/client";
import EntityIntelPanel from "../components/EntityIntelPanel";
import { useInvestigation } from "../store/investigation";

const NetworkGraph3D = lazy(() => import("../components/NetworkGraph3D"));

const TYPES = ["", "PERSON", "PHONE", "VEHICLE", "LOCATION", "ORGANIZATION", "FINANCIAL_ACCOUNT"];

export default function NetworkExplorer() {
  const { currentId } = useInvestigation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [graph, setGraph] = useState<GraphData>({ nodes: [], edges: [] });
  const [influencers, setInfluencers] = useState<InfluencerScore[]>([]);
  const [communities, setCommunities] = useState<Community[]>([]);
  const [selected, setSelected] = useState<Entity | null>(null);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [results, setResults] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);

  const loadFullGraph = () => {
    if (!currentId) return;
    setLoading(true);
    Promise.all([
      api.get("/graph", { params: { investigation_id: currentId } }),
      api.get("/analytics/influencers", { params: { investigation_id: currentId, top_n: 25 } }),
      api.get("/analytics/communities", { params: { investigation_id: currentId } }),
    ])
      .then(([g, inf, comm]) => {
        setGraph(g.data);
        setInfluencers(inf.data);
        setCommunities(comm.data);
      })
      .finally(() => setLoading(false));
  };

  useEffect(loadFullGraph, [currentId]);

  // Deep-link support: /network?focus=<entityId> (used by the command palette).
  useEffect(() => {
    const focus = searchParams.get("focus");
    if (!focus || !currentId || graph.nodes.length === 0) return;
    const entity = graph.nodes.find((n) => n.id === focus);
    if (entity) setSelected(entity);
  }, [searchParams, currentId, graph.nodes]);

  useEffect(() => {
    if (!currentId || query.trim().length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .get("/entities/search", { params: { q: query, type: typeFilter || undefined, investigation_id: currentId } })
        .then((res) => setResults(res.data));
    }, 250);
    return () => clearTimeout(t);
  }, [query, typeFilter, currentId]);

  const focusEntity = (entity: Entity) => {
    setSelected(entity);
    setResults([]);
    setQuery("");
    setSearchParams({});
  };

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] gap-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-display font-semibold">Network Explorer</h1>
          <p className="text-muted text-sm mt-1">
            Rotate, zoom, and select any entity to focus its neighborhood and open its intelligence dossier.
          </p>
        </div>
        <button onClick={loadFullGraph} className="knot-btn-ghost">↺ Reset view</button>
      </div>

      <div className="card flex flex-wrap gap-3 items-center">
        <input
          className="knot-input flex-1 min-w-[220px]"
          placeholder="Search a person, phone, vehicle, location…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select className="knot-input" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          {TYPES.map((t) => <option key={t} value={t}>{t || "All types"}</option>)}
        </select>
        {results.length > 0 && (
          <div className="w-full flex flex-wrap gap-2">
            {results.map((r) => (
              <button key={r.id} onClick={() => focusEntity(r)} className="knot-btn-ghost">
                {r.label} <span className="text-muted">· {r.type}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-4 items-start flex-1 min-h-0">
        {loading ? (
          <div className="card flex-1 min-w-0 h-full flex items-center justify-center text-muted">Loading graph…</div>
        ) : (
          <div className="flex-1 min-w-0 h-full">
            <Suspense fallback={<div className="card h-full flex items-center justify-center text-muted">Loading 3D renderer…</div>}>
              <NetworkGraph3D data={graph} focusId={selected?.id} onNodeClick={setSelected} height={600} />
            </Suspense>
          </div>
        )}
        <EntityIntelPanel
          entity={selected}
          graph={graph}
          influencers={influencers}
          communities={communities}
          onClose={() => setSelected(null)}
          onFocusEntity={focusEntity}
        />
      </div>
    </div>
  );
}
