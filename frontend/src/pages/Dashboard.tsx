import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, DashboardSummary } from "../api/client";
import StatCard from "../components/StatCard";

const SEVERITY_STYLE: Record<string, string> = {
  high: "border-alert/40 bg-alert/10 text-alert",
  medium: "border-warn/40 bg-warn/10 text-warn",
  low: "border-slate-500/40 bg-slate-500/10 text-slate-300",
};

export default function Dashboard() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/analytics/dashboard").then((res) => setData(res.data)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-slate-400">Loading dashboard…</div>;
  if (!data) return <div className="text-alert">Could not load dashboard.</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Investigation Overview</h1>
        <p className="text-slate-400 text-sm mt-1">
          Unified view across FIRs, CDRs, financial records, surveillance, social media and criminal
          history.
        </p>
      </div>

      <div className="flex flex-wrap gap-4">
        <StatCard label="Total Entities" value={data.total_entities} />
        <StatCard label="Total Relationships" value={data.total_relations} />
        <StatCard label="Persons of Interest" value={data.total_persons} />
        <StatCard label="Detected Clusters" value={data.community_count} />
        <StatCard
          label="Open Anomalies"
          value={data.open_anomalies}
          tone={data.open_anomalies > 0 ? "alert" : "good"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <div className="flex justify-between items-center mb-3">
            <h2 className="font-semibold">Top Influencers</h2>
            <Link to="/graph" className="text-xs text-accent hover:underline">
              Explore graph →
            </Link>
          </div>
          <div className="space-y-2">
            {data.top_influencers.map((inf) => (
              <div key={inf.entity.id} className="flex items-center justify-between text-sm border-b border-border/60 pb-2 last:border-0">
                <div className="flex items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-accent/20 text-accent flex items-center justify-center text-xs font-bold">
                    {inf.rank}
                  </span>
                  <div>
                    <div className="text-slate-100">{inf.entity.label}</div>
                    <div className="text-xs text-slate-500">{inf.entity.type}</div>
                  </div>
                </div>
                <div className="text-right text-xs text-slate-400">
                  <div>composite {inf.composite_score.toFixed(3)}</div>
                  <div>betweenness {inf.betweenness_centrality.toFixed(3)}</div>
                </div>
              </div>
            ))}
            {data.top_influencers.length === 0 && (
              <div className="text-sm text-slate-500">No entities yet — ingest data to populate this view.</div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="flex justify-between items-center mb-3">
            <h2 className="font-semibold">Recent Suspicious Patterns</h2>
            <span className="text-xs text-slate-500">{data.open_anomalies} total</span>
          </div>
          <div className="space-y-2">
            {data.recent_anomalies.map((a) => (
              <div key={a.id} className={`border rounded-lg px-3 py-2 text-xs ${SEVERITY_STYLE[a.severity]}`}>
                <div className="font-semibold uppercase tracking-wide">{a.type.replace(/_/g, " ")}</div>
                <div className="text-slate-300 mt-1">{a.description}</div>
              </div>
            ))}
            {data.recent_anomalies.length === 0 && (
              <div className="text-sm text-slate-500">No anomalies detected in the current dataset.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
