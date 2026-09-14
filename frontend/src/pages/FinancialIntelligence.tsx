import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, FinancialIntelligence as FinancialData, GraphData } from "../api/client";
import { useInvestigation } from "../store/investigation";

const NetworkGraph3D = lazy(() => import("../components/NetworkGraph3D"));

/**
 * Financial Intelligence: account summaries, real transaction totals,
 * major counterparties and circular-flow detection now come from
 * GET /api/investigations/{id}/financial (app/services/financial.py) --
 * computed once server-side from actual TRANSACTED_WITH event amounts,
 * rather than recomputed here from generic edge `weight` (which was never
 * a currency figure). The 3D graph below is still a client-side rendering
 * concern only, built from the same accounts/counterparties the backend
 * already identified -- not a second source of financial truth.
 */
export default function FinancialIntelligence() {
  const { currentId } = useInvestigation();
  const navigate = useNavigate();
  const [data, setData] = useState<FinancialData | null>(null);
  const [graph, setGraph] = useState<GraphData>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!currentId) return;
    setLoading(true);
    Promise.all([
      api.get(`/investigations/${currentId}/financial`),
      api.get("/graph", { params: { investigation_id: currentId } }),
    ])
      .then(([f, g]) => {
        setData(f.data);
        setGraph(g.data);
      })
      .finally(() => setLoading(false));
  }, [currentId]);

  const financialGraph = useMemo<GraphData>(() => {
    if (!data) return { nodes: [], edges: [] };
    const accountIds = new Set(data.accounts.map((a) => a.account.id));
    const edges = graph.edges.filter((e) => e.type === "TRANSACTED_WITH" && accountIds.has(e.source) && accountIds.has(e.target));
    const touchedIds = new Set(edges.flatMap((e) => [e.source, e.target]));
    return { nodes: graph.nodes.filter((n) => touchedIds.has(n.id)), edges };
  }, [graph, data]);

  const currency = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display font-semibold">Financial Intelligence</h1>
        <p className="text-muted text-sm mt-1">
          Account-level transaction totals, major counterparties, and layering/circular-flow patterns already
          flagged by the anomaly engine — computed from real recorded transaction amounts.
        </p>
      </div>

      {loading ? (
        <div className="text-muted">Loading…</div>
      ) : !data || data.accounts.length === 0 ? (
        <div className="card text-center py-14 text-muted text-sm">No financial-account activity in this investigation yet.</div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Accounts" value={data.accounts.length} />
            <Stat label="Transactions" value={data.transaction_count} />
            <Stat label="Total flow" value={currency(data.total_outbound)} isCurrency />
            <Stat label="Circular flows flagged" value={data.circular_flows.length} tone={data.circular_flows.length > 0 ? "alert" : "good"} />
          </div>

          <Suspense fallback={<div className="card h-[420px] flex items-center justify-center text-muted">Loading 3D renderer…</div>}>
            <NetworkGraph3D data={financialGraph} height={420} />
          </Suspense>

          {data.circular_flows.length > 0 && (
            <div className="card">
              <span className="eyebrow text-alert">Circular / pass-through transactions</span>
              <div className="mt-3 space-y-2">
                {data.circular_flows.map((c, i) => (
                  <div key={i} className="border border-alert/40 bg-alert/10 rounded-lg px-3 py-2 text-xs text-slate-200">
                    {c.description}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="card overflow-x-auto p-0">
            <div className="px-4 py-2.5 border-b border-border text-[11px] uppercase tracking-wide text-muted">
              Account summary
            </div>
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="text-left text-muted text-[11px] uppercase tracking-wide border-b border-border">
                  <th className="py-2 px-4">Account</th>
                  <th className="py-2 px-4">Holder</th>
                  <th className="py-2 px-4">Transactions</th>
                  <th className="py-2 px-4">Inbound</th>
                  <th className="py-2 px-4">Outbound</th>
                </tr>
              </thead>
              <tbody>
                {data.accounts.map((a) => (
                  <tr key={a.account.id} className="border-b border-border/50 last:border-0 hover:bg-panel2/60 transition-colors cursor-pointer"
                      onClick={() => navigate(`/network?focus=${a.account.id}`)}>
                    <td className="py-2.5 px-4 text-slate-100 font-medium">{a.account.label}</td>
                    <td className="py-2.5 px-4 text-slate-300">{a.holder_entities.map((h) => h.label).join(", ") || "—"}</td>
                    <td className="py-2.5 px-4 text-muted">{a.transaction_count}</td>
                    <td className="py-2.5 px-4 text-good font-mono">{currency(a.total_inbound)}</td>
                    <td className="py-2.5 px-4 text-alert font-mono">{currency(a.total_outbound)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.major_counterparties.length > 0 && (
            <div className="card">
              <span className="eyebrow">Major counterparties</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {data.major_counterparties.map((c) => (
                  <button key={c.account.id} onClick={() => navigate(`/network?focus=${c.account.id}`)}
                          className="knot-input py-1.5 px-2.5 text-xs hover:border-accent/40">
                    {c.account.label} · {currency(c.total_amount)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {data.transaction_timeline.length > 0 && (
            <div className="card">
              <span className="eyebrow">Transaction timeline</span>
              <div className="mt-2 space-y-1.5 max-h-[280px] overflow-y-auto">
                {data.transaction_timeline.map((t) => (
                  <div key={t.id} className="flex items-baseline justify-between gap-3 text-sm border-b border-border/40 last:border-0 py-1.5">
                    <span className="text-slate-200">{t.description}</span>
                    <span className="text-[11px] text-muted font-mono shrink-0">{new Date(t.timestamp).toLocaleDateString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value, tone = "default", isCurrency = false }: {
  label: string; value: number | string; tone?: "default" | "alert" | "good"; isCurrency?: boolean;
}) {
  const toneClass = tone === "alert" ? "text-alert" : tone === "good" ? "text-good" : "text-slate-100";
  return (
    <div className="card">
      <div className="eyebrow">{label}</div>
      <div className={`font-mono text-xl font-semibold mt-1 ${toneClass}`}>{isCurrency ? `₹${value}` : value}</div>
    </div>
  );
}
