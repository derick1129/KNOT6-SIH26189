import { useMemo, useState } from "react";
import { Community, GraphData, InfluencerScore } from "../api/client";
import { TYPE_COLOR } from "./graphColors";

/**
 * KNOT6 Overview's "Analytical Intelligence" panel -- sits beside the
 * Investigation Map (see Overview.tsx) as one investigation-intelligence
 * module, not a bolted-on analytics widget.
 *
 * Deliberately zero new network requests: every view here is derived from
 * data Overview already fetches for the graph itself (`/api/graph`,
 * `/api/analytics/influencers`, `/api/analytics/communities`) -- so it
 * updates on exactly the same schedule the graph does (investigation
 * switch, or a refresh after Add Intelligence processes new evidence),
 * with no separate cache to go stale. No counts are invented here; an
 * empty/loading graph renders an empty/loading state, never a placeholder
 * chart.
 */

type View = "entities" | "relationships" | "communities" | "influencers";

const VIEW_LABELS: Record<View, string> = {
  entities: "Entity Distribution",
  relationships: "Relationship Types",
  communities: "Community Sizes",
  influencers: "Top Connected Entities",
};

const FALLBACK_COLOR = "#6B7A72"; // muted sage-grey, for a type/relation not in the shared palette

interface Bar {
  key: string;
  label: string;
  value: number;
  color: string;
}

function titleCase(s: string): string {
  return s.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function AnalyticalIntelligence({
  graph,
  influencers,
  communities,
}: {
  graph: GraphData | null;
  influencers: InfluencerScore[];
  communities: Community[];
}) {
  const [view, setView] = useState<View>("entities");

  const bars: Bar[] = useMemo(() => {
    if (!graph) return [];
    switch (view) {
      case "entities": {
        const counts = new Map<string, number>();
        for (const n of graph.nodes) counts.set(n.type, (counts.get(n.type) ?? 0) + 1);
        return Array.from(counts.entries())
          .map(([type, value]) => ({ key: type, label: titleCase(type), value, color: TYPE_COLOR[type] ?? FALLBACK_COLOR }))
          .sort((a, b) => b.value - a.value);
      }
      case "relationships": {
        const counts = new Map<string, number>();
        for (const e of graph.edges) counts.set(e.type, (counts.get(e.type) ?? 0) + 1);
        return Array.from(counts.entries())
          .map(([type, value]) => ({ key: type, label: titleCase(type), value, color: "#6FA98C" }))
          .sort((a, b) => b.value - a.value)
          .slice(0, 8);
      }
      case "communities": {
        return communities
          .map((c) => ({
            key: String(c.community_id),
            label: c.label || `Community ${c.community_id}`,
            value: c.size,
            color: "#6FA98C",
          }))
          .sort((a, b) => b.value - a.value)
          .slice(0, 8);
      }
      case "influencers": {
        return influencers.slice(0, 8).map((i) => ({
          key: i.entity.id,
          label: i.entity.label,
          value: i.composite_score,
          color: TYPE_COLOR[i.entity.type] ?? FALLBACK_COLOR,
        }));
      }
    }
  }, [view, graph, influencers, communities]);

  const max = Math.max(1, ...bars.map((b) => b.value));
  const isScore = view === "influencers";

  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <h2 className="text-[13px] font-semibold text-slate-200 tracking-wide uppercase">Analytical Intelligence</h2>
        <select
          className="knot-input text-xs py-1.5"
          value={view}
          onChange={(e) => setView(e.target.value as View)}
        >
          {(Object.keys(VIEW_LABELS) as View[]).map((v) => (
            <option key={v} value={v}>
              {VIEW_LABELS[v]}
            </option>
          ))}
        </select>
      </div>

      {graph === null ? (
        <div className="flex-1 flex items-center justify-center text-muted text-sm">Loading analytics…</div>
      ) : bars.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted text-sm text-center px-4">
          {view === "communities" && "No communities detected yet."}
          {view === "influencers" && "No ranked entities yet."}
          {(view === "entities" || view === "relationships") && "No data yet — ingest evidence to populate this."}
        </div>
      ) : (
        <div className="space-y-3">
          {bars.map((b) => (
            <div key={b.key} className="group">
              <div className="flex items-baseline justify-between gap-2 mb-1">
                <span className="text-xs text-slate-300 truncate" title={b.label}>
                  {b.label}
                </span>
                <span className="mono-tabular text-xs text-slate-100 font-medium shrink-0">
                  {isScore ? b.value.toFixed(3) : b.value}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-panel2 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${Math.max(4, (b.value / max) * 100)}%`, backgroundColor: b.color }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
