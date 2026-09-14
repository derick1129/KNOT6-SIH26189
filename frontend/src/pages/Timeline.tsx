import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, InvestigationTimeline, TimelineEvent } from "../api/client";
import { useInvestigation } from "../store/investigation";

const KIND_DOT: Record<string, string> = {
  CALL: "bg-warn", TRANSACTION: "bg-alert", PRESENCE: "bg-accent",
  EVIDENCE_UPLOADED: "bg-good", CASE_EVENT: "bg-slate-400", OTHER: "bg-slate-400",
};
const KIND_LABEL: Record<string, string> = {
  CALL: "Call", TRANSACTION: "Transaction", PRESENCE: "Presence / mention",
  EVIDENCE_UPLOADED: "Evidence", CASE_EVENT: "Case event", OTHER: "Other",
};
const KINDS = ["CALL", "TRANSACTION", "PRESENCE", "EVIDENCE_UPLOADED", "CASE_EVENT"];

/**
 * Full investigation timeline -- calls, transactions, dated document
 * relationships, evidence registration and case/investigation lifecycle
 * events, all aggregated server-side from real data
 * (GET /api/investigations/{id}/timeline, see app/services/timeline.py).
 * Relationships whose source carried no reliable date are listed
 * separately under "undated" rather than dropped or given a fabricated
 * timestamp.
 */
export default function Timeline() {
  const { currentId } = useInvestigation();
  const navigate = useNavigate();
  const [data, setData] = useState<InvestigationTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [kindFilter, setKindFilter] = useState<Set<string>>(new Set());
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [ascending, setAscending] = useState(true);
  const [showUndated, setShowUndated] = useState(false);

  useEffect(() => {
    if (!currentId) return;
    setLoading(true);
    const params: Record<string, any> = { ascending };
    if (kindFilter.size > 0) params.event_type = Array.from(kindFilter);
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    api.get(`/investigations/${currentId}/timeline`, { params }).then((res) => setData(res.data)).finally(() => setLoading(false));
  }, [currentId, kindFilter, dateFrom, dateTo, ascending]);

  function toggleKind(k: string) {
    setKindFilter((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });
  }

  const events = data?.events ?? [];
  const entityCount = useMemo(() => new Set(events.flatMap((e) => e.entities_involved)).size, [events]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display font-semibold">Timeline</h1>
        <p className="text-muted text-sm mt-1 max-w-2xl">
          Chronological reconstruction of this investigation — calls, transactions, dated document mentions,
          evidence registration and case events, in the order they occurred. Nothing here is invented: events
          without a reliable source date are listed separately below.
        </p>
      </div>

      <div className="card space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {KINDS.map((k) => (
            <button
              key={k}
              onClick={() => toggleKind(k)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors flex items-center gap-1.5 ${
                kindFilter.has(k) || kindFilter.size === 0
                  ? "border-accent/50 text-accent bg-accent/10"
                  : "border-border text-muted hover:border-borderStrong"
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${KIND_DOT[k]}`} />
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 items-center text-sm">
          <label className="flex items-center gap-1.5 text-muted text-xs">
            From <input type="date" className="knot-input py-1 text-xs" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="flex items-center gap-1.5 text-muted text-xs">
            To <input type="date" className="knot-input py-1 text-xs" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <button onClick={() => setAscending((a) => !a)} className="text-xs text-muted hover:text-slate-200">
            {ascending ? "↓ Newest last" : "↑ Newest first"} (click to reverse)
          </button>
          {data && (
            <span className="text-[11px] text-muted ml-auto">
              {data.total_events} event{data.total_events === 1 ? "" : "s"} · {entityCount} entities involved
            </span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="text-muted">Loading…</div>
      ) : events.length === 0 ? (
        <div className="card text-center py-14 text-muted text-sm">No timeline events match the current filters.</div>
      ) : (
        <div className="card">
          <div className="relative pl-6">
            <div className="absolute left-[7px] top-1 bottom-1 w-px bg-border" />
            <div className="space-y-5">
              {events.map((e) => (
                <EventRow key={e.id} event={e} navigate={navigate} />
              ))}
            </div>
          </div>
        </div>
      )}

      {data && data.undated_relations.length > 0 && (
        <div className="card">
          <button onClick={() => setShowUndated((s) => !s)} className="text-xs text-muted hover:text-slate-200 flex items-center gap-1.5">
            {showUndated ? "▾" : "▸"} {data.undated_relations.length} relationship{data.undated_relations.length === 1 ? "" : "s"} with no reliable date
          </button>
          {showUndated && (
            <div className="mt-3 space-y-1.5">
              {data.undated_relations.map((u) => (
                <div key={u.relationship_id} className="text-sm text-slate-300 border-b border-border/40 last:border-0 py-1.5">
                  {u.description}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// A graph-derived event's `evidence` list carries the raw ingestion
// document id (e.g. "demo-cdr", "SOCIAL-2") -- only ones actually uploaded
// through the Evidence pipeline are prefixed "evidence-<Evidence.id>" (see
// app/api/routes/evidence.py's `document_id`) and can be deep-linked to a
// real Evidence Vault row; the same convention
// app/services/investigation_search.py already uses. Anything else has no
// corresponding Evidence row to open.
function realEvidenceId(raw: string): string | null {
  return raw.startsWith("evidence-") ? raw.slice("evidence-".length) : null;
}

function EventRow({ event, navigate }: { event: TimelineEvent; navigate: (path: string) => void }) {
  return (
    <div className="relative">
      <div className={`absolute -left-[22px] top-1.5 w-2.5 h-2.5 rounded-full ${KIND_DOT[event.kind] ?? "bg-slate-400"}`} />
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <span className="text-sm text-slate-100 font-medium">{event.description}</span>
        <span className="text-[11px] text-muted font-mono shrink-0">{new Date(event.timestamp).toLocaleString()}</span>
      </div>
      <div className="text-[12px] text-muted mt-0.5 flex items-center gap-2 flex-wrap">
        <span className="badge bg-slate-400/10 text-slate-400">{KIND_LABEL[event.kind] ?? event.kind}</span>
        {event.entities_involved.length > 0 && (
          <button onClick={() => navigate(`/network?focus=${event.entities_involved[0]}`)} className="text-accent hover:underline">
            Open in graph
          </button>
        )}
        {event.kind === "EVIDENCE_UPLOADED" && event.evidence[0] && (
          <button onClick={() => navigate(`/evidence?evidence=${event.evidence[0]}`)} className="text-accent hover:underline">
            View evidence
          </button>
        )}
        {event.evidence.map((raw) => {
          const evId = realEvidenceId(raw);
          return evId ? (
            <button key={raw} onClick={() => navigate(`/evidence?evidence=${evId}`)} className="text-accent hover:underline">
              View evidence
            </button>
          ) : null;
        })}
      </div>
    </div>
  );
}
