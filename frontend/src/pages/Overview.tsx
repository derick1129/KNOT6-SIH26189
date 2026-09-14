import { lazy, Suspense, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { AnomalyFlag, api, Community, DashboardSummary, Entity, GraphData, InfluencerScore } from "../api/client";
import { useInvestigation } from "../store/investigation";
import { useAuth } from "../store/auth";
import AnalyticalIntelligence from "../components/AnalyticalIntelligence";

const NetworkGraph3D = lazy(() => import("../components/NetworkGraph3D"));
const AddIntelligenceModal = lazy(() => import("../components/AddIntelligenceModal"));

// Compact by default -- the graph only grows to (near) full viewport when
// the investigator explicitly opens Fullscreen (see `fullscreenGraph`
// below). Network Explorer (/network) is completely unaffected -- it keeps
// its own, unrelated full-size rendering.
const COMPACT_MAP_HEIGHT = 380;

// Mirrors the backend's evidence-upload write gate
// (`_WRITE_ROLES` in app/api/routes/evidence.py) -- a viewer never sees the
// control, and the backend enforces the same restriction independently, so
// hiding it here is a UX courtesy, not the actual authorization boundary.
const CAN_UPLOAD_ROLES = new Set(["investigator", "analyst", "admin"]);

const SEVERITY_TONE: Record<string, string> = { high: "text-alert", medium: "text-warn", low: "text-muted" };

/**
 * KNOT6 Overview: three stacked areas, not a dashboard of cards --
 * investigation identity, one dominant "investigation map" (the graph),
 * and a quiet list of investigative signals. Answers "what investigation
 * am I looking at / what's important / what's happening / where can I
 * continue" within a few seconds, per the visual-identity brief -- every
 * number and signal below comes from the same real backend analytics
 * endpoints Network Explorer already uses (nothing invented for the sake
 * of a nicer-looking dashboard).
 */
export default function Overview() {
  const { currentId, current } = useInvestigation();
  const { role } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [fullscreenGraph, setFullscreenGraph] = useState(false);
  const [fsHeight, setFsHeight] = useState(() => Math.max(360, window.innerHeight - 140));
  // Bumped after a successful upload so newly-ingested entities/relations
  // and refreshed analytics show up without a manual reload -- the graph
  // store itself updates in real time; this just re-triggers this page's
  // existing fetches against it.
  const [refreshToken, setRefreshToken] = useState(0);
  // Real backend analytics -- the exact same endpoints Network Explorer
  // already uses -- so the Overview graph can show real importance/
  // community structure instead of 59 equally-weighted dots. See
  // components/graphIntelligence.ts for how these get turned into node
  // sizing, glyph/label selection, and spatial clustering.
  const [influencers, setInfluencers] = useState<InfluencerScore[]>([]);
  const [communities, setCommunities] = useState<Community[]>([]);

  useEffect(() => {
    if (!currentId) return;
    setLoading(true);
    api.get("/analytics/dashboard", { params: { investigation_id: currentId } })
      .then((res) => setData(res.data))
      .finally(() => setLoading(false));
  }, [currentId, refreshToken]);

  useEffect(() => {
    if (!currentId) return;
    setGraph(null);
    Promise.all([
      api.get("/graph", { params: { investigation_id: currentId } }),
      api.get("/analytics/influencers", { params: { investigation_id: currentId, top_n: 25 } }),
      api.get("/analytics/communities", { params: { investigation_id: currentId } }),
    ]).then(([g, inf, comm]) => {
      setGraph(g.data);
      setInfluencers(inf.data);
      setCommunities(comm.data);
    });
  }, [currentId, refreshToken]);

  // Fullscreen Investigation Map: Esc closes it, and its height tracks the
  // viewport while open. Doesn't navigate away from Overview -- purely a
  // local overlay toggle over data this page already has in memory.
  useEffect(() => {
    if (!fullscreenGraph) return;
    const onResize = () => setFsHeight(Math.max(360, window.innerHeight - 140));
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreenGraph(false);
    };
    onResize();
    window.addEventListener("resize", onResize);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("keydown", onKey);
    };
  }, [fullscreenGraph]);

  if (!currentId) return <EmptyState />;
  if (loading) return <div className="text-muted">Loading overview…</div>;
  if (!data) return <div className="text-alert">Could not load the investigation overview.</div>;

  return (
    <div className="space-y-10">
      {/* Investigation identity */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="eyebrow mb-1">{current?.status ?? "ACTIVE"} INVESTIGATION</div>
          <h1 className="text-3xl md:text-4xl font-display font-semibold text-slate-50">
            {current?.name ?? "Investigation Overview"}
          </h1>
        </div>
        {role && CAN_UPLOAD_ROLES.has(role) && (
          <button onClick={() => setShowUpload(true)} className="knot-btn-primary shrink-0">
            + Add Intelligence
          </button>
        )}
      </div>
      <div>
        <p className="text-sm mt-3 text-slate-300">
          <Link to="/entities" className="hover:text-accent transition-colors">
            <span className="mono-tabular text-slate-100 font-medium">{data.total_entities}</span> entities
          </Link>
          {" · "}
          <Link to="/network" className="hover:text-accent transition-colors">
            <span className="mono-tabular text-slate-100 font-medium">{data.total_relations}</span> relationships
          </Link>
          {" · "}
          <a href="#signals" className="hover:text-accent transition-colors">
            <span className={`mono-tabular font-medium ${data.open_anomalies > 0 ? "text-warn" : "text-slate-100"}`}>
              {data.open_anomalies}
            </span>{" "}
            signals
          </a>
          {" · "}
          <span className="mono-tabular text-slate-100 font-medium">{data.total_persons}</span> persons of interest
        </p>
      </div>

      {/* Investigation Map + Analytical Intelligence -- one investigation-
          intelligence module: the real graph (60%) beside a real analytics
          read on the same data (40%). Stacks vertically below `lg`. */}
      <div className="flex flex-col lg:flex-row gap-6 items-stretch">
        <div className="w-full lg:w-[60%] min-w-0">
          <div className="flex items-center justify-between mb-3 gap-3">
            <div>
              <h2 className="text-[13px] font-semibold text-slate-200 tracking-wide uppercase">Investigation Map</h2>
              <p className="text-xs text-muted mt-0.5">
                The most relevant entities and their connections · hover to identify · click to explore further
              </p>
            </div>
            {graph !== null && graph.nodes.length > 0 && (
              <button
                onClick={() => setFullscreenGraph(true)}
                className="knot-btn-ghost shrink-0"
                title="Expand the Investigation Map"
              >
                Fullscreen ⛶
              </button>
            )}
          </div>

          {graph === null ? (
            <div className="card flex items-center justify-center text-muted text-sm" style={{ height: COMPACT_MAP_HEIGHT }}>
              Loading map…
            </div>
          ) : graph.nodes.length === 0 ? (
            <div
              className="card flex items-center justify-center text-muted text-sm text-center px-8"
              style={{ height: COMPACT_MAP_HEIGHT }}
            >
              No entities yet — ingest evidence to populate this investigation's graph.
            </div>
          ) : fullscreenGraph ? (
            <div className="card flex items-center justify-center text-muted text-sm" style={{ height: COMPACT_MAP_HEIGHT }}>
              Investigation Map is expanded — press Esc or Exit Fullscreen to return.
            </div>
          ) : (
            <Suspense
              fallback={
                <div className="card flex items-center justify-center text-muted text-sm" style={{ height: COMPACT_MAP_HEIGHT }}>
                  Loading map renderer…
                </div>
              }
            >
              <NetworkGraph3D
                data={graph}
                height={COMPACT_MAP_HEIGHT}
                showZoomControls
                simplified
                influencers={influencers}
                communities={communities}
                onNodeClick={(entity: Entity) => navigate(`/network?focus=${entity.id}`)}
              />
            </Suspense>
          )}
        </div>

        <div className="w-full lg:w-[40%] min-w-0">
          <AnalyticalIntelligence graph={graph} influencers={influencers} communities={communities} />
        </div>
      </div>

      {/* Fullscreen Investigation Map overlay -- same graph, same data, same
          interactions; only its presentation grows. Never navigates away
          from Overview, so closing it lands exactly back here. */}
      {fullscreenGraph && graph !== null && graph.nodes.length > 0 && (
        <div className="fixed inset-0 z-[100] bg-ink flex flex-col p-4 md:p-6">
          <div className="flex items-center justify-between mb-3 shrink-0">
            <div>
              <h2 className="text-[13px] font-semibold text-slate-200 tracking-wide uppercase">Investigation Map</h2>
              <p className="text-xs text-muted mt-0.5">{current?.name ?? "Investigation"}</p>
            </div>
            <button onClick={() => setFullscreenGraph(false)} className="knot-btn-ghost" title="Exit fullscreen (Esc)">
              Exit Fullscreen ✕
            </button>
          </div>
          <div className="flex-1 min-h-0">
            <Suspense fallback={<div className="h-full flex items-center justify-center text-muted text-sm">Loading map renderer…</div>}>
              <NetworkGraph3D
                data={graph}
                height={fsHeight}
                showZoomControls
                simplified
                expanded
                influencers={influencers}
                communities={communities}
                onNodeClick={(entity: Entity) => navigate(`/network?focus=${entity.id}`)}
              />
            </Suspense>
          </div>
        </div>
      )}

      {/* Investigative Signals -- typography and whitespace, not cards */}
      <section id="signals" className="scroll-mt-6 max-w-2xl">
        <div className="flex items-baseline justify-between mb-1">
          <h2 className="text-[13px] font-semibold text-slate-200 tracking-wide uppercase">Investigative Signals</h2>
          <Link to="/network" className="text-xs text-accent hover:underline shrink-0">
            View all →
          </Link>
        </div>
        <div className="divide-y divide-border/60">
          {data.recent_anomalies.map((a) => (
            <SignalRow key={a.id} anomaly={a} />
          ))}
          {data.recent_anomalies.length === 0 && (
            <div className="text-sm text-muted py-4">No unusual patterns detected in the current graph.</div>
          )}
        </div>
      </section>

      {role && CAN_UPLOAD_ROLES.has(role) && (
        <Suspense fallback={null}>
          <AddIntelligenceModal
            open={showUpload}
            investigationId={currentId}
            investigationName={current?.name}
            onClose={() => setShowUpload(false)}
            onCompleted={() => setRefreshToken((t) => t + 1)}
          />
        </Suspense>
      )}
    </div>
  );
}

function SignalRow({ anomaly }: { anomaly: AnomalyFlag }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-3">
      <div className="min-w-0">
        <div className={`text-sm font-medium ${SEVERITY_TONE[anomaly.severity] ?? "text-slate-200"}`}>
          {titleCase(anomaly.type)}
        </div>
        <div className="text-xs text-muted mt-0.5">{anomaly.description}</div>
      </div>
      <div className="text-[11px] text-muted shrink-0 whitespace-nowrap">{timeAgo(anomaly.detected_at)}</div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card text-center py-16">
      <h2 className="text-lg font-display font-semibold text-slate-100">No investigation selected</h2>
      <p className="text-muted text-sm mt-2 max-w-sm mx-auto">
        Choose or create an investigation to see its overview.
      </p>
      <Link to="/investigations" className="knot-btn-primary inline-block mt-5">Go to Investigations</Link>
    </div>
  );
}

function titleCase(s: string): string {
  return s.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}
