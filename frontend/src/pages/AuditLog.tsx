import { useEffect, useState } from "react";
import { api, AuditEntry } from "../api/client";

export default function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/audit")
      .then((res) => setEntries(res.data))
      .catch(() => setError("Only admin accounts can view the audit log."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Audit Log</h1>
        <p className="text-slate-400 text-sm mt-1">
          Every ingest, merge, and analytics access — who did what, and when. Admin-only, per role
          policy.
        </p>
      </div>
      {loading && <div className="text-slate-400">Loading…</div>}
      {error && <div className="text-alert text-sm">{error}</div>}
      {!loading && !error && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-border">
                <th className="py-2 pr-4">Timestamp</th>
                <th className="py-2 pr-4">Actor</th>
                <th className="py-2 pr-4">Action</th>
                <th className="py-2 pr-4">Target</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-b border-border/50">
                  <td className="py-2 pr-4 text-slate-400 whitespace-nowrap">
                    {new Date(e.timestamp).toLocaleString()}
                  </td>
                  <td className="py-2 pr-4">{e.actor}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-accent">{e.action}</td>
                  <td className="py-2 pr-4 text-slate-400">{e.target ?? "—"}</td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-4 text-slate-500 text-center">
                    No activity recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
