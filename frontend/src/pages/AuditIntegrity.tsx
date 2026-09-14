import { useEffect, useState } from "react";
import { api, AuditChainVerify, AuditEntry } from "../api/client";

const ACTION_STYLE = (action: string) => {
  if (action.startsWith("LOGIN")) return "text-slate-400";
  if (action.startsWith("CREATE") || action.startsWith("UPLOAD")) return "text-good";
  if (action.startsWith("ARCHIVE") || action.startsWith("CLOSE")) return "text-warn";
  if (action.startsWith("MERGE")) return "text-accent";
  if (action.startsWith("VERIFY")) return "text-accent";
  return "text-slate-300";
};

/**
 * Admin-only accountability trail. Real, persistent data
 * (`audit_entries` in PostgreSQL/SQLite), now hash-chained (Phase 4): each
 * row's `entry_hash` commits to the row before it, so "Verify Chain
 * Integrity" below re-derives every hash from its stored content and
 * reports the first row (if any) whose stored hash no longer matches --
 * see app/services/integrity.py for the exact formula. This is a clean,
 * self-contained tamper-evidence abstraction, not a claim of a production
 * Hyperledger Fabric deployment (see the module's docstring).
 */
export default function AuditIntegrity() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [chain, setChain] = useState<AuditChainVerify | null>(null);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    api.get("/audit").then((res) => setEntries(res.data)).catch(() => setError("Only admin accounts can view the audit trail.")).finally(() => setLoading(false));
  }, []);

  function verifyChain() {
    setVerifying(true);
    api
      .get("/audit/verify")
      .then((res) => setChain(res.data))
      .catch(() =>
        setChain({
          status: "INTEGRITY_VIOLATION", entries_checked: 0, first_broken_entry_id: null, first_broken_seq: null,
          message: "Verification request failed (admin access required).", checked_at: new Date().toISOString(),
        })
      )
      .finally(() => setVerifying(false));
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-display font-semibold">Audit &amp; Integrity</h1>
          <p className="text-muted text-sm mt-1">Who did what, and when — every ingest, merge and investigation action.</p>
        </div>
        <button
          onClick={verifyChain}
          disabled={verifying}
          className="text-sm px-3 py-1.5 rounded-md border border-border hover:border-accent/50 hover:text-accent transition-colors disabled:opacity-50"
        >
          {verifying ? "Verifying chain…" : "Verify Chain Integrity"}
        </button>
      </div>

      {chain && (
        <div
          className={`card text-xs flex items-start gap-2 ${
            chain.status === "VALID" ? "border-good/30 bg-good/5 text-good" : "border-alert/30 bg-alert/5 text-alert"
          }`}
        >
          <span className="mt-0.5">{chain.status === "VALID" ? "✓" : "⚠"}</span>
          <div>
            <div className="font-semibold">{chain.status === "VALID" ? "VALID — no tampering detected" : "INTEGRITY VIOLATION"}</div>
            <div className="text-slate-300 mt-0.5">{chain.message}</div>
            {chain.first_broken_seq != null && (
              <div className="text-slate-400 mt-0.5 font-mono">Broken at sequence {chain.first_broken_seq} (entry {chain.first_broken_entry_id})</div>
            )}
          </div>
        </div>
      )}

      {loading && <div className="text-muted">Loading…</div>}
      {error && <div className="text-alert text-sm">{error}</div>}

      {!loading && !error && (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm min-w-[720px]">
            <thead>
              <tr className="text-left text-muted text-[11px] uppercase tracking-wide border-b border-border">
                <th className="py-3 px-4">Timestamp</th>
                <th className="py-3 px-4">Actor</th>
                <th className="py-3 px-4">Action</th>
                <th className="py-3 px-4">Target</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-b border-border/50 last:border-0 hover:bg-panel2/60 transition-colors">
                  <td className="py-2.5 px-4 text-muted font-mono text-xs whitespace-nowrap">{new Date(e.timestamp).toLocaleString()}</td>
                  <td className="py-2.5 px-4 text-slate-200">{e.actor}</td>
                  <td className={`py-2.5 px-4 font-mono text-xs ${ACTION_STYLE(e.action)}`}>{e.action}</td>
                  <td className="py-2.5 px-4 text-muted font-mono text-xs truncate max-w-[220px]">{e.target ?? "—"}</td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr><td colSpan={4} className="py-8 text-muted text-center">No activity recorded yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
