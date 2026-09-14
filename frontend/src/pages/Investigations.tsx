import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useInvestigation } from "../store/investigation";

const STATUS_STYLE: Record<string, string> = {
  ACTIVE: "bg-good/20 text-good",
  ARCHIVED: "bg-slate-400/20 text-slate-300",
  CLOSED: "bg-alert/20 text-alert",
};

export default function Investigations() {
  const { investigations, currentId, setCurrentId, loading, refresh } = useInvestigation();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      const res = await api.post("/investigations", { name, description });
      setName("");
      setDescription("");
      setCreating(false);
      refresh();
      setCurrentId(res.data.id);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">Investigations</h1>
          <p className="text-slate-400 text-sm mt-1">
            Every case, source document and graph entity belongs to exactly one investigation.
          </p>
        </div>
        <button
          onClick={() => setCreating((c) => !c)}
          className="text-xs px-3 py-1.5 rounded-lg border border-border text-slate-300 hover:border-accent hover:text-accent"
        >
          {creating ? "Cancel" : "+ New Investigation"}
        </button>
      </div>

      {creating && (
        <div className="card space-y-3">
          <input
            className="w-full bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            placeholder="Investigation name (e.g. Operation Nexus)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <textarea
            className="w-full h-20 bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <button
            disabled={!name.trim() || submitting}
            onClick={submit}
            className="bg-accent text-ink font-semibold rounded-lg px-5 py-2 text-sm disabled:opacity-40"
          >
            {submitting ? "Creating…" : "Create Investigation"}
          </button>
        </div>
      )}

      {loading && <div className="text-slate-400">Loading…</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {investigations.map((inv) => (
          <Link
            key={inv.id}
            to={`/investigations/${inv.id}`}
            onClick={() => setCurrentId(inv.id)}
            className={`card block hover:border-accent transition-colors ${inv.id === currentId ? "border-accent" : ""}`}
          >
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-semibold">{inv.name}</h3>
              <span className={`badge ${STATUS_STYLE[inv.status] ?? "bg-slate-400/20"}`}>{inv.status}</span>
            </div>
            <p className="text-xs text-slate-400 mt-2 line-clamp-2">{inv.description || "No description."}</p>
            <div className="text-xs text-slate-500 mt-3">
              {inv.case_count} case{inv.case_count === 1 ? "" : "s"} · created by {inv.created_by}
            </div>
            {inv.id === currentId && (
              <div className="text-[10px] text-accent mt-2 uppercase tracking-wide">Currently active</div>
            )}
          </Link>
        ))}
        {!loading && investigations.length === 0 && (
          <div className="text-sm text-slate-500">No investigations yet — create one to get started.</div>
        )}
      </div>
    </div>
  );
}
