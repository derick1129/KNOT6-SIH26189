import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, EvidenceIntegrityVerify, EvidenceItem } from "../api/client";
import { useInvestigation } from "../store/investigation";

const STATUS_STYLE: Record<string, string> = {
  UPLOADED: "bg-slate-400/15 text-slate-300",
  PROCESSING: "bg-warn/15 text-warn",
  PROCESSED: "bg-good/15 text-good",
  FAILED: "bg-alert/15 text-alert",
};

const INTEGRITY_STYLE: Record<string, string> = {
  VALID: "bg-good/15 text-good",
  INTEGRITY_VIOLATION: "bg-alert/15 text-alert",
  UNAVAILABLE: "bg-slate-400/15 text-slate-400",
  CHECKING: "bg-slate-400/15 text-slate-400 animate-pulse",
};

/**
 * Investigation-wide Evidence Vault. Real metadata from Phase 1's `evidence`
 * table. Phase 4: every item now carries the SHA-256 hash computed at
 * upload time (`Evidence.sha256_hash`), and "Verify" re-hashes the file
 * currently on disk against it on demand
 * (`POST /api/evidence/{id}/verify-integrity`) -- never a fabricated
 * checkmark, and never auto-run for every row on page load (that would
 * silently re-read every stored file on every visit to this screen).
 */
export default function EvidenceVault() {
  const { currentId } = useInvestigation();
  const [searchParams] = useSearchParams();
  const highlightId = searchParams.get("evidence");
  const highlightRef = useRef<HTMLTableRowElement | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState("");
  const [integrity, setIntegrity] = useState<Record<string, EvidenceIntegrityVerify | "CHECKING">>({});

  useEffect(() => {
    if (!currentId) return;
    setLoading(true);
    api.get(`/investigations/${currentId}/evidence`).then((res) => setEvidence(res.data)).finally(() => setLoading(false));
  }, [currentId]);

  function verifyIntegrity(evidenceId: string) {
    setIntegrity((prev) => ({ ...prev, [evidenceId]: "CHECKING" }));
    api
      .post(`/evidence/${evidenceId}/verify-integrity`)
      .then((res) => setIntegrity((prev) => ({ ...prev, [evidenceId]: res.data })))
      .catch(() =>
        setIntegrity((prev) => ({
          ...prev,
          [evidenceId]: {
            evidence_id: evidenceId, status: "UNAVAILABLE", stored_hash: "", computed_hash: null,
            checked_at: new Date().toISOString(), message: "Verification request failed.",
          },
        }))
      );
  }

  // Deep-link support: /evidence?evidence=<id> (used by the AI Copilot's
  // citations and "View Evidence" action) -- scrolls to and highlights the
  // referenced row instead of leaving the investigator to find it manually.
  useEffect(() => {
    if (highlightId && !loading) highlightRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightId, loading, evidence]);

  const filtered = sourceFilter ? evidence.filter((e) => e.source_type === sourceFilter) : evidence;
  const sourceTypes = Array.from(new Set(evidence.map((e) => e.source_type)));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-display font-semibold">Evidence Vault</h1>
          <p className="text-muted text-sm mt-1">
            Every source document registered into this investigation, with provenance and processing status.
          </p>
        </div>
        {sourceTypes.length > 0 && (
          <select className="knot-input" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
            <option value="">All source types</option>
            {sourceTypes.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
          </select>
        )}
      </div>

      {loading ? (
        <div className="text-muted">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="card text-center py-14 text-muted text-sm">
          No evidence registered yet — upload evidence from a case's detail page.
        </div>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm min-w-[860px]">
            <thead>
              <tr className="text-left text-muted text-[11px] uppercase tracking-wide border-b border-border">
                <th className="py-3 px-4">Evidence</th>
                <th className="py-3 px-4">Source</th>
                <th className="py-3 px-4">Uploader</th>
                <th className="py-3 px-4">Registered</th>
                <th className="py-3 px-4">Processing</th>
                <th className="py-3 px-4">Integrity</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr
                  key={e.id}
                  ref={e.id === highlightId ? highlightRef : undefined}
                  className={`border-b border-border/50 last:border-0 hover:bg-panel2/60 transition-colors ${
                    e.id === highlightId ? "bg-accent/10 ring-1 ring-inset ring-accent/40" : ""
                  }`}
                >
                  <td className="py-3 px-4">
                    <div className="text-slate-100 font-medium">{e.original_filename}</div>
                    <div className="font-mono text-[10px] text-muted mt-0.5">{e.id}</div>
                  </td>
                  <td className="py-3 px-4 text-slate-300">{e.source_type.replace(/_/g, " ")}</td>
                  <td className="py-3 px-4 text-slate-300">{e.uploaded_by}</td>
                  <td className="py-3 px-4 text-muted font-mono text-xs whitespace-nowrap">
                    {new Date(e.uploaded_at).toLocaleString()}
                  </td>
                  <td className="py-3 px-4">
                    <span className={`badge ${STATUS_STYLE[e.processing_status]}`}>{e.processing_status}</span>
                  </td>
                  <td className="py-3 px-4">
                    {!e.sha256_hash ? (
                      <span className="text-[11px] text-muted">No reference hash</span>
                    ) : (
                      <div className="space-y-1">
                        <div className="font-mono text-[10px] text-muted" title={e.sha256_hash}>
                          {e.sha256_hash.slice(0, 12)}…
                        </div>
                        {integrity[e.id] && integrity[e.id] !== "CHECKING" ? (
                          <span
                            className={`badge ${INTEGRITY_STYLE[(integrity[e.id] as EvidenceIntegrityVerify).status]}`}
                            title={(integrity[e.id] as EvidenceIntegrityVerify).message}
                          >
                            {(integrity[e.id] as EvidenceIntegrityVerify).status === "VALID" ? "VALID" : "VIOLATION"}
                          </span>
                        ) : (
                          <button
                            onClick={() => verifyIntegrity(e.id)}
                            disabled={integrity[e.id] === "CHECKING"}
                            className="text-[11px] text-accent hover:underline disabled:opacity-50"
                          >
                            {integrity[e.id] === "CHECKING" ? "Verifying…" : "Verify Integrity"}
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
