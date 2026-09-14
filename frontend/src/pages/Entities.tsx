import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Entity, ResolutionCandidate } from "../api/client";
import { useAuth } from "../store/auth";
import { useInvestigation } from "../store/investigation";

const TYPES = ["PERSON", "PHONE", "VEHICLE", "LOCATION", "ORGANIZATION", "FINANCIAL_ACCOUNT", "EVENT", "CASE"];
const TYPE_COLOR: Record<string, string> = {
  PERSON: "bg-accent/15 text-accent", PHONE: "bg-warn/15 text-warn", VEHICLE: "bg-purple-400/15 text-purple-300",
  LOCATION: "bg-good/15 text-good", ORGANIZATION: "bg-pink-400/15 text-pink-300",
  FINANCIAL_ACCOUNT: "bg-alert/15 text-alert", EVENT: "bg-slate-400/15 text-slate-300", CASE: "bg-slate-400/15 text-slate-300",
};

/**
 * A type-browsable roster over the same /api/entities/search endpoint the
 * Network Explorer's search box already uses -- the PS names "Entities" as
 * its own core area, so this gives it a dedicated home rather than folding
 * it entirely into graph search.
 */
export default function Entities() {
  const { currentId } = useInvestigation();
  const { role } = useAuth();
  const navigate = useNavigate();
  const [type, setType] = useState("PERSON");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<"browse" | "resolution">("browse");
  const canResolve = role === "analyst" || role === "admin";

  useEffect(() => {
    if (!currentId) return;
    setLoading(true);
    api
      .get("/entities/search", { params: { q: query || "a", type, investigation_id: currentId, limit: 60 } })
      .then((res) => setResults(res.data))
      .finally(() => setLoading(false));
  }, [currentId, type, query]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-display font-semibold">Entities</h1>
          <p className="text-muted text-sm mt-1">Browse every entity resolved into this investigation, by type.</p>
        </div>
        {canResolve && (
          <div className="flex gap-1.5">
            <button
              onClick={() => setTab("browse")}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                tab === "browse" ? "border-accent text-accent bg-accent/10" : "border-border text-muted hover:border-borderStrong"
              }`}
            >
              Browse
            </button>
            <button
              onClick={() => setTab("resolution")}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                tab === "resolution" ? "border-accent text-accent bg-accent/10" : "border-border text-muted hover:border-borderStrong"
              }`}
            >
              Resolution Review
            </button>
          </div>
        )}
      </div>

      {tab === "resolution" && canResolve ? (
        <ResolutionReview investigationId={currentId} />
      ) : (
      <>
      <div className="card flex flex-wrap gap-3 items-center">
        <div className="flex gap-1.5 flex-wrap">
          {TYPES.map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                type === t ? "border-accent text-accent bg-accent/10" : "border-border text-muted hover:border-borderStrong"
              }`}
            >
              {t.replace(/_/g, " ")}
            </button>
          ))}
        </div>
        <input
          className="knot-input flex-1 min-w-[180px]"
          placeholder="Filter by name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {results.map((e) => (
          <button
            key={e.id}
            onClick={() => navigate(`/network?focus=${e.id}`)}
            className="card text-left hover:border-accent/40 transition-colors"
          >
            <span className={`badge ${TYPE_COLOR[e.type] ?? "bg-slate-400/15"}`}>{e.type.replace(/_/g, " ")}</span>
            <div className="font-medium text-slate-100 mt-2 truncate">{e.label}</div>
            <div className="text-[11px] text-muted mt-1">{e.source_count} source document{e.source_count === 1 ? "" : "s"}</div>
          </button>
        ))}
        {!loading && results.length === 0 && (
          <div className="text-sm text-muted col-span-full py-8 text-center">
            No {type.replace(/_/g, " ").toLowerCase()} entities found{query ? ` matching "${query}"` : ""}.
          </div>
        )}
      </div>
      </>
      )}
    </div>
  );
}

const DECISION_STYLE: Record<string, string> = {
  AUTO_MERGE_ELIGIBLE: "bg-good/15 text-good",
  REVIEW_REQUIRED: "bg-warn/15 text-warn",
};

/**
 * Entity resolution review: surfaces the candidates
 * app/resolution/entity_resolution.py proposes (fuzzy name match +
 * corroborating shared connection), backed by the
 * entity_resolution_decisions table via /api/entities/resolution/decide --
 * approving performs the real merge, rejecting only records the decision so
 * the same pair stops resurfacing (see that endpoint's docstring). Never a
 * silent auto-merge: every decision here is an explicit analyst action.
 */
function ResolutionReview({ investigationId }: { investigationId: string | null }) {
  const [candidates, setCandidates] = useState<ResolutionCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  function load() {
    if (!investigationId) return;
    setLoading(true);
    api
      .get("/entities/resolution/candidates", { params: { investigation_id: investigationId, entity_type: "PERSON" } })
      .then((res) => setCandidates(res.data))
      .catch(() => setError("Unable to load resolution candidates (analyst/admin access required)."))
      .finally(() => setLoading(false));
  }

  useEffect(load, [investigationId]);

  function decide(c: ResolutionCandidate, decision: "APPROVED" | "REJECTED") {
    const key = `${c.keep_id}:${c.merge_id}`;
    setBusy(key);
    api
      .post(
        "/entities/resolution/decide",
        { keep_id: c.keep_id, merge_id: c.merge_id, decision, reason: decision === "APPROVED" ? "Analyst-confirmed match" : "Analyst-rejected match" },
        { params: { investigation_id: investigationId } }
      )
      .then(() => setCandidates((prev) => prev.filter((x) => x.keep_id !== c.keep_id || x.merge_id !== c.merge_id)))
      .finally(() => setBusy(null));
  }

  if (loading) return <div className="text-muted">Loading candidates…</div>;
  if (error) return <div className="text-alert text-sm">{error}</div>;

  return (
    <div className="space-y-3">
      <p className="text-muted text-sm max-w-2xl">
        Possible duplicate PERSON entities detected by name similarity plus a corroborating shared connection
        (phone, location, vehicle, or account). Nothing merges automatically — review each candidate.
      </p>
      {candidates.length === 0 ? (
        <div className="card text-center py-14 text-muted text-sm">No pending resolution candidates in this investigation.</div>
      ) : (
        candidates.map((c) => {
          const key = `${c.keep_id}:${c.merge_id}`;
          return (
            <div key={key} className="card space-y-3">
              <div className="flex items-start justify-between flex-wrap gap-2">
                <div>
                  <div className="text-sm text-slate-100">
                    <span className="font-medium">{c.keep_label}</span>
                    <span className="text-muted mx-2">↔</span>
                    <span className="font-medium">{c.merge_label}</span>
                  </div>
                  <div className="text-[11px] text-muted mt-1 font-mono">{c.confidence.toFixed(0)}% name similarity</div>
                </div>
                <span className={`badge ${DECISION_STYLE[c.decision_status]}`}>{c.decision_status.replace(/_/g, " ")}</span>
              </div>

              <ul className="text-[12px] text-slate-300 list-disc list-inside space-y-0.5">
                {c.matching_reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>

              <div className="text-[11px] text-muted">
                Sources: {c.keep_label} — {c.source_references.keep?.join(", ") || "none"} · {c.merge_label} —{" "}
                {c.source_references.merge?.join(", ") || "none"}
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => decide(c, "APPROVED")}
                  disabled={busy === key}
                  className="knot-btn-primary text-xs px-3 py-1.5 disabled:opacity-40"
                >
                  {busy === key ? "Working…" : "Approve Merge"}
                </button>
                <button
                  onClick={() => decide(c, "REJECTED")}
                  disabled={busy === key}
                  className="text-xs px-3 py-1.5 rounded-md border border-border hover:border-alert/50 hover:text-alert transition-colors disabled:opacity-40"
                >
                  Reject
                </button>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
