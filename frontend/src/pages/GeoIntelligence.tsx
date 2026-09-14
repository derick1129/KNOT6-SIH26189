import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Entity, GraphData, TimelineEvent } from "../api/client";
import { useInvestigation } from "../store/investigation";

/**
 * Honest partial implementation: `LOCATION` entities are real graph data
 * (see app/graph/schema.py). A map view needs geographic coordinates, which
 * neither the demo dataset nor any ingestion loader in this codebase
 * carries yet (verified by inspection -- see docs/KNOT6_IMPLEMENTATION_
 * ROADMAP.md Phase 5) -- rather than fabricate coordinates, this screen
 * says so plainly and instead gives real substance per location: which
 * entities appear there, what relationships connect them, and when
 * (chronologically, from the same timeline aggregation the Timeline page
 * uses) -- all real data, composed from existing endpoints.
 */
export default function GeoIntelligence() {
  const { currentId } = useInvestigation();
  const navigate = useNavigate();
  const [locations, setLocations] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Entity | null>(null);
  const [neighborhood, setNeighborhood] = useState<GraphData | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    if (!currentId) return;
    setLoading(true);
    api
      .get("/entities/search", { params: { q: "a", type: "LOCATION", investigation_id: currentId, limit: 100 } })
      .then((res) => setLocations(res.data))
      .finally(() => setLoading(false));
  }, [currentId]);

  function openLocation(loc: Entity) {
    if (!currentId) return;
    setSelected(loc);
    setDetailLoading(true);
    Promise.all([
      api.get(`/graph/neighborhood/${loc.id}`, { params: { investigation_id: currentId, hops: 1 } }),
      api.get(`/investigations/${currentId}/timeline`, { params: { entity_id: loc.id, ascending: false } }),
    ])
      .then(([g, t]) => {
        setNeighborhood(g.data);
        setTimeline(t.data.events);
      })
      .finally(() => setDetailLoading(false));
  }

  const relatedEntities = neighborhood?.nodes.filter((n) => n.id !== selected?.id) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display font-semibold">Geo Intelligence</h1>
        <p className="text-muted text-sm mt-1 max-w-2xl">
          Locations resolved into this investigation's graph, with the entities, relationships and chronology
          associated with each. Map-based visualization requires geographic coordinates the data model doesn't
          carry yet — plainly labeled below rather than approximated.
        </p>
      </div>

      <div className="card border-warn/30 bg-warn/5 text-xs text-slate-300 flex items-start gap-2">
        <span className="text-warn mt-0.5">△</span>
        <span>Coordinates unavailable — no location entity in this investigation carries latitude/longitude, and
          none is fabricated here. Everything below (entities, relationships, chronology) is real graph data.</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
        <div className="space-y-2">
          {loading ? (
            <div className="text-muted text-sm">Loading…</div>
          ) : locations.length === 0 ? (
            <div className="card text-center py-10 text-muted text-sm">No location entities in this investigation yet.</div>
          ) : (
            locations.map((loc) => (
              <button
                key={loc.id}
                onClick={() => openLocation(loc)}
                className={`card w-full text-left hover:border-accent/40 transition-colors ${selected?.id === loc.id ? "border-accent/50 bg-accent/5" : ""}`}
              >
                <span className="badge bg-good/15 text-good">LOCATION</span>
                <div className="font-medium text-slate-100 mt-2">{loc.label}</div>
                <div className="text-[11px] text-muted mt-1">{loc.source_count} source document{loc.source_count === 1 ? "" : "s"}</div>
              </button>
            ))
          )}
        </div>

        <div>
          {!selected ? (
            <div className="card text-center py-16 text-muted text-sm">Select a location to see its entities, relationships and chronology.</div>
          ) : detailLoading ? (
            <div className="text-muted text-sm">Loading…</div>
          ) : (
            <div className="space-y-4">
              <div className="card">
                <span className="eyebrow">Entities appearing at {selected.label}</span>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {relatedEntities.length === 0 ? (
                    <p className="text-muted text-sm">No connected entities recorded.</p>
                  ) : (
                    relatedEntities.map((e) => (
                      <button key={e.id} onClick={() => navigate(`/network?focus=${e.id}`)} className="knot-input py-1.5 px-2.5 text-xs hover:border-accent/40">
                        {e.label} <span className="text-muted">· {e.type.replace(/_/g, " ")}</span>
                      </button>
                    ))
                  )}
                </div>
              </div>

              <div className="card">
                <span className="eyebrow">Chronological appearances</span>
                <div className="mt-2 space-y-1.5 max-h-[320px] overflow-y-auto">
                  {timeline.length === 0 ? (
                    <p className="text-muted text-sm">No dated events recorded for this location.</p>
                  ) : (
                    timeline.map((t) => (
                      <div key={t.id} className="flex items-baseline justify-between gap-3 text-sm border-b border-border/40 last:border-0 py-1.5">
                        <span className="text-slate-200">{t.description}</span>
                        <span className="text-[11px] text-muted font-mono shrink-0">{new Date(t.timestamp).toLocaleDateString()}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <button onClick={() => navigate(`/network?focus=${selected.id}`)} className="text-xs text-accent hover:underline">
                Open {selected.label} in Network Explorer →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
