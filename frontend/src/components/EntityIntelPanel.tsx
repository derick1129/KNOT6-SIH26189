import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { Community, Entity, GraphData, InfluencerScore } from "../api/client";

const TYPE_LABEL: Record<string, string> = {
  PERSON: "Person", PHONE: "Phone", VEHICLE: "Vehicle", LOCATION: "Location",
  ORGANIZATION: "Organization", FINANCIAL_ACCOUNT: "Financial Account", EVENT: "Event", CASE: "Case",
};

interface Props {
  entity: Entity | null;
  graph: GraphData;
  influencers: InfluencerScore[];
  communities: Community[];
  onClose: () => void;
  onFocusEntity: (e: Entity) => void;
}

/**
 * The signature "why does this entity matter" dossier. Every number here is
 * computed from data the existing analytics endpoints already return
 * (`app/analytics/centrality.py`, `community.py`) plus the currently loaded
 * neighborhood -- nothing is fabricated. Where the PS's fuller vision (case
 * links, per-entity timeline) needs backend support Phase 1 doesn't have
 * yet, that section says so plainly instead of inventing numbers.
 */
export default function EntityIntelPanel({ entity, graph, influencers, communities, onClose, onFocusEntity }: Props) {
  const navigate = useNavigate();
  const [showWhy, setShowWhy] = useState(true);

  if (!entity) {
    return (
      <aside className="w-[340px] shrink-0 card flex items-center justify-center text-center">
        <p className="text-sm text-muted max-w-[200px]">
          Select an entity in the graph to open its intelligence dossier.
        </p>
      </aside>
    );
  }

  const connectedEdges = graph.edges.filter((e) => e.source === entity.id || e.target === entity.id);
  const connectedIds = new Set(connectedEdges.map((e) => (e.source === entity.id ? e.target : e.source)));
  const connectedEntities = graph.nodes.filter((n) => connectedIds.has(n.id));

  const influencer = influencers.find((i) => i.entity.id === entity.id);
  const community = communities.find((c) => c.members.some((m) => m.id === entity.id));

  const evidenceIds = Array.from(new Set(connectedEdges.flatMap((e) => e.evidence))).slice(0, 8);

  // Relevance: a 0-100 read of the composite centrality score when this
  // entity ranks among the investigation's influencers; otherwise a
  // connection-count-based floor. Explicitly *not* a "criminal probability"
  // -- see KNOT6_PROJECT_SPECIFICATION.pdf's guardrails.
  const relevance = influencer
    ? Math.round(Math.min(100, influencer.composite_score * 260))
    : Math.min(60, connectedEntities.length * 8);

  return (
    <aside className="w-[340px] shrink-0 flex flex-col gap-3">
      <div className="card">
        <div className="flex items-start justify-between gap-2">
          <div>
            <span className="badge bg-accent/15 text-accent">{TYPE_LABEL[entity.type] ?? entity.type}</span>
            <h2 className="text-lg font-display font-semibold text-slate-50 mt-2 break-words leading-tight">
              {entity.label}
            </h2>
          </div>
          <button onClick={onClose} className="text-muted hover:text-slate-200 text-sm">✕</button>
        </div>

        <div className="mt-4">
          <div className="flex items-baseline justify-between">
            <span className="eyebrow">Investigation Relevance</span>
            <span className="font-mono text-2xl font-semibold text-accent">{relevance}</span>
          </div>
          <div className="h-1.5 bg-panel2 rounded-full mt-2 overflow-hidden">
            <div className="h-full bg-accent rounded-full transition-all" style={{ width: `${relevance}%` }} />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 mt-4 text-center">
          <Metric label="Sources" value={entity.source_count} />
          <Metric label="Connections" value={connectedEntities.length} />
          <Metric label="Communities" value={community ? 1 : 0} />
        </div>
      </div>

      <div className="card">
        <button
          onClick={() => setShowWhy((v) => !v)}
          className="w-full flex items-center justify-between text-left"
        >
          <span className="eyebrow">Why this entity matters</span>
          <span className="text-muted text-xs">{showWhy ? "−" : "+"}</span>
        </button>
        {showWhy && (
          <div className="mt-3 space-y-2 text-[13px] text-slate-300 leading-relaxed">
            {influencer ? (
              <>
                <Reason>
                  Ranked <b className="text-slate-100">#{influencer.rank}</b> by composite influence in this
                  investigation.
                </Reason>
                <Reason>
                  Betweenness centrality of <b className="text-slate-100">{influencer.betweenness_centrality.toFixed(3)}</b> —
                  sits between clusters that otherwise wouldn't connect.
                </Reason>
                <Reason>
                  Direct degree centrality <b className="text-slate-100">{influencer.degree_centrality.toFixed(3)}</b> across{" "}
                  {connectedEntities.length} connection{connectedEntities.length === 1 ? "" : "s"}.
                </Reason>
                {community && (
                  <Reason>
                    Member of a detected community of <b className="text-slate-100">{community.size}</b> entities
                    (density {community.density}).
                  </Reason>
                )}
              </>
            ) : (
              <Reason>
                Corroborated by <b className="text-slate-100">{entity.source_count}</b> source document
                {entity.source_count === 1 ? "" : "s"} with <b className="text-slate-100">{connectedEntities.length}</b> direct
                connection{connectedEntities.length === 1 ? "" : "s"} in the current graph. Not currently ranked among
                the investigation's top influencers.
              </Reason>
            )}
            <p className="text-[11px] text-muted pt-1 border-t border-border mt-2">
              This is an investigative signal, not a determination of guilt — every figure above traces to graph
              structure and cited source documents for a human investigator to verify.
            </p>
          </div>
        )}
      </div>

      <div className="card flex-1 min-h-0 flex flex-col">
        <span className="eyebrow">Connected entities</span>
        <div className="mt-2 space-y-1 overflow-y-auto flex-1">
          {connectedEntities.slice(0, 20).map((c) => (
            <button
              key={c.id}
              onClick={() => onFocusEntity(c)}
              className="w-full flex items-center justify-between text-left px-2 py-1.5 rounded-lg text-[13px] hover:bg-panel2 transition-colors"
            >
              <span className="truncate text-slate-200">{c.label}</span>
              <span className="text-[10px] text-muted shrink-0 ml-2">{TYPE_LABEL[c.type] ?? c.type}</span>
            </button>
          ))}
          {connectedEntities.length === 0 && <div className="text-xs text-muted py-2">No direct connections loaded.</div>}
        </div>
      </div>

      {evidenceIds.length > 0 && (
        <div className="card">
          <span className="eyebrow">Relevant evidence</span>
          <div className="mt-2 space-y-1">
            {evidenceIds.map((id) => (
              <div key={id} className="font-mono text-[11px] text-slate-400 truncate">· {id}</div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <button onClick={() => navigate("/path")} className="knot-btn-ghost flex-1 text-center">
          Trace Connections
        </button>
        <button onClick={() => setShowWhy(true)} className="knot-btn-ghost flex-1 text-center">
          Explain
        </button>
      </div>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-panel2 rounded-lg py-2">
      <div className="font-mono text-base font-semibold text-slate-100">{value}</div>
      <div className="text-[10px] text-muted mt-0.5 uppercase tracking-wide">{label}</div>
    </div>
  );
}

function Reason({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="text-accent mt-0.5">▸</span>
      <span>{children}</span>
    </div>
  );
}
