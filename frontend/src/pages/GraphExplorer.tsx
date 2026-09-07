import { useEffect, useState } from "react";
import { api, Entity, GraphData } from "../api/client";
import EntityPanel from "../components/EntityPanel";
import GraphView from "../components/GraphView";

const TYPES = ["", "PERSON", "PHONE", "VEHICLE", "LOCATION", "ORGANIZATION", "FINANCIAL_ACCOUNT"];

export default function GraphExplorer() {
  const [graph, setGraph] = useState<GraphData>({ nodes: [], edges: [] });
  const [selected, setSelected] = useState<Entity | null>(null);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [results, setResults] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);

  const loadFullGraph = () => {
    setLoading(true);
    api.get("/graph").then((res) => setGraph(res.data)).finally(() => setLoading(false));
  };

  useEffect(loadFullGraph, []);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .get("/entities/search", { params: { q: query, type: typeFilter || undefined } })
        .then((res) => setResults(res.data));
    }, 250);
    return () => clearTimeout(t);
  }, [query, typeFilter]);

  const focusEntity = async (entity: Entity) => {
    setSelected(entity);
    const res = await api.get(`/graph/neighborhood/${entity.id}`, { params: { hops: 2 } });
    setGraph(res.data);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">Graph Explorer</h1>
          <p className="text-slate-400 text-sm mt-1">
            Search an entity to see its 2-hop neighborhood, or browse the whole network.
          </p>
        </div>
        <button onClick={loadFullGraph} className="text-xs px-3 py-1.5 rounded-lg border border-border text-slate-300 hover:border-accent hover:text-accent">
          ↺ Reset to full graph
        </button>
      </div>

      <div className="card flex flex-wrap gap-3 items-center">
        <input
          className="flex-1 min-w-[220px] bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
          placeholder="Search a person, phone, vehicle, location…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className="bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          {TYPES.map((t) => (
            <option key={t} value={t}>
              {t || "All types"}
            </option>
          ))}
        </select>
        {results.length > 0 && (
          <div className="w-full flex flex-wrap gap-2">
            {results.map((r) => (
              <button
                key={r.id}
                onClick={() => focusEntity(r)}
                className="text-xs px-3 py-1.5 rounded-full bg-panel2 border border-border hover:border-accent hover:text-accent"
              >
                {r.label} <span className="text-slate-500">· {r.type}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-4 items-start">
        {loading ? (
          <div className="card flex-1 h-[560px] flex items-center justify-center text-slate-400">
            Loading graph…
          </div>
        ) : (
          <div className="flex-1">
            <GraphView
              data={graph}
              onNodeClick={(n) => setSelected(n)}
              highlightIds={selected ? new Set([selected.id]) : undefined}
            />
          </div>
        )}
        <EntityPanel entity={selected} onClose={() => setSelected(null)} />
      </div>
    </div>
  );
}
