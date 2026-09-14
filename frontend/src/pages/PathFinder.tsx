import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, Entity, PathResult } from "../api/client";
import { useInvestigation } from "../store/investigation";

function EntitySearchBox({
  label,
  onPick,
  investigationId,
  picked: pickedProp,
}: {
  label: string;
  onPick: (e: Entity) => void;
  investigationId: string | null;
  picked?: Entity | null;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Entity[]>([]);
  const [picked, setPicked] = useState<Entity | null>(null);

  // Deep-link support: a caller (e.g. the AI Copilot's "Show Path" action)
  // can hand this box an already-resolved entity instead of requiring the
  // investigator to search for it again.
  useEffect(() => {
    if (pickedProp !== undefined) setPicked(pickedProp);
  }, [pickedProp]);

  useEffect(() => {
    if (!investigationId || query.trim().length < 2) return setResults([]);
    const t = setTimeout(() => {
      api
        .get("/entities/search", { params: { q: query, investigation_id: investigationId } })
        .then((res) => setResults(res.data));
    }, 250);
    return () => clearTimeout(t);
  }, [query, investigationId]);

  return (
    <div className="flex-1">
      <label className="text-xs text-slate-400">{label}</label>
      {picked ? (
        <div className="mt-1 flex items-center justify-between bg-panel2 border border-accent/50 rounded-lg px-3 py-2 text-sm">
          <span>
            {picked.label} <span className="text-slate-500 text-xs">· {picked.type}</span>
          </span>
          <button
            className="text-slate-500 hover:text-alert"
            onClick={() => {
              setPicked(null);
              setQuery("");
            }}
          >
            ✕
          </button>
        </div>
      ) : (
        <>
          <input
            className="w-full mt-1 bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search entity…"
          />
          {results.length > 0 && (
            <div className="mt-1 border border-border rounded-lg overflow-hidden">
              {results.map((r) => (
                <button
                  key={r.id}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-panel2"
                  onClick={() => {
                    setPicked(r);
                    onPick(r);
                    setResults([]);
                  }}
                >
                  {r.label} <span className="text-slate-500 text-xs">· {r.type}</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function PathFinder() {
  const { currentId } = useInvestigation();
  const [searchParams] = useSearchParams();
  const [source, setSource] = useState<Entity | null>(null);
  const [target, setTarget] = useState<Entity | null>(null);
  const [result, setResult] = useState<PathResult | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async (sourceEntity?: Entity, targetEntity?: Entity) => {
    const s = sourceEntity ?? source;
    const t = targetEntity ?? target;
    if (!s || !t) return;
    setLoading(true);
    try {
      const res = await api.get("/graph/path", {
        params: { source: s.id, target: t.id, investigation_id: currentId },
      });
      setResult(res.data);
    } finally {
      setLoading(false);
    }
  };

  // Deep-link support: /path?source=<id>&target=<id> (used by the AI
  // Copilot's "Show Path" action and Key Relationships' "Open Graph").
  // Resolves both ids to real entities via the existing lookup endpoint,
  // then auto-runs the same path query a manual search would trigger.
  useEffect(() => {
    const sourceId = searchParams.get("source");
    const targetId = searchParams.get("target");
    if (!sourceId || !targetId || !currentId) return;
    Promise.all([
      api.get(`/entities/${sourceId}`, { params: { investigation_id: currentId } }),
      api.get(`/entities/${targetId}`, { params: { investigation_id: currentId } }),
    ]).then(([s, t]) => {
      setSource(s.data);
      setTarget(t.data);
      run(s.data, t.data);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, currentId]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Connection Path Finder</h1>
        <p className="text-slate-400 text-sm mt-1">
          "How are these two suspects connected?" — the shortest evidentiary chain between any two
          entities in the network.
        </p>
      </div>

      <div className="card flex gap-4 items-end flex-wrap">
        <EntitySearchBox label="From" onPick={setSource} investigationId={currentId} picked={source} />
        <EntitySearchBox label="To" onPick={setTarget} investigationId={currentId} picked={target} />
        <button
          disabled={!source || !target || loading}
          onClick={() => run()}
          className="bg-accent text-ink font-semibold rounded-lg px-5 py-2 text-sm disabled:opacity-40"
        >
          {loading ? "Searching…" : "Find Path"}
        </button>
      </div>

      {result && (
        <div className="card">
          {!result.found ? (
            <div className="text-slate-400 text-sm">No connection found within the current graph.</div>
          ) : (
            <>
              <div className="text-sm text-slate-400 mb-4">
                Shortest path: <span className="text-slate-100 font-semibold">{result.hops} hop(s)</span> ·{" "}
                {result.all_paths_count} distinct path(s) found overall
                {result.all_paths_count >= 50 ? "+" : ""}
              </div>
              <div className="flex items-center flex-wrap gap-2">
                {result.path.map((hop, i) => (
                  <div key={hop.entity.id} className="flex items-center gap-2">
                    {i > 0 && (
                      <div className="flex flex-col items-center text-[10px] text-slate-500 px-1">
                        <span>→</span>
                        <span>{hop.via_relation?.type ?? ""}</span>
                      </div>
                    )}
                    <div className="bg-panel2 border border-border rounded-lg px-3 py-2 text-sm text-center">
                      <div className="font-medium">{hop.entity.label}</div>
                      <div className="text-[10px] text-slate-500">{hop.entity.type}</div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
