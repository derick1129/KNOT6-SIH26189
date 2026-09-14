import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, Case, Investigation } from "../api/client";

const STATUS_STYLE: Record<string, string> = {
  OPEN: "bg-good/20 text-good",
  UNDER_REVIEW: "bg-warn/20 text-warn",
  CLOSED: "bg-slate-400/20 text-slate-300",
  ARCHIVED: "bg-slate-400/20 text-slate-300",
};

const PRIORITY_STYLE: Record<string, string> = {
  LOW: "text-slate-400",
  MEDIUM: "text-warn",
  HIGH: "text-alert",
  CRITICAL: "text-alert font-bold",
};

export default function InvestigationDetail() {
  const { investigationId } = useParams<{ investigationId: string }>();
  const navigate = useNavigate();
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [caseNumber, setCaseNumber] = useState("");
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    if (!investigationId) return;
    setLoading(true);
    Promise.all([
      api.get(`/investigations/${investigationId}`),
      api.get(`/investigations/${investigationId}/cases`),
    ])
      .then(([inv, cs]) => {
        setInvestigation(inv.data);
        setCases(cs.data);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [investigationId]);

  const submit = async () => {
    if (!caseNumber.trim() || !title.trim()) return;
    setSubmitting(true);
    try {
      await api.post(`/investigations/${investigationId}/cases`, { case_number: caseNumber, title });
      setCaseNumber("");
      setTitle("");
      setCreating(false);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="text-slate-400">Loading…</div>;
  if (!investigation) return <div className="text-alert">Investigation not found.</div>;

  return (
    <div className="space-y-6">
      <div>
        <Link to="/investigations" className="text-xs text-accent hover:underline">
          ← All investigations
        </Link>
        <div className="flex items-center justify-between flex-wrap gap-3 mt-2">
          <div>
            <h1 className="text-2xl font-bold">{investigation.name}</h1>
            <p className="text-slate-400 text-sm mt-1">{investigation.description || "No description."}</p>
          </div>
          <button
            onClick={() => setCreating((c) => !c)}
            className="text-xs px-3 py-1.5 rounded-lg border border-border text-slate-300 hover:border-accent hover:text-accent"
          >
            {creating ? "Cancel" : "+ New Case"}
          </button>
        </div>
      </div>

      {creating && (
        <div className="card space-y-3">
          <div className="flex gap-3 flex-wrap">
            <input
              className="flex-1 min-w-[160px] bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
              placeholder="Case number (e.g. CASE-002)"
              value={caseNumber}
              onChange={(e) => setCaseNumber(e.target.value)}
            />
            <input
              className="flex-[2] min-w-[220px] bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <button
            disabled={!caseNumber.trim() || !title.trim() || submitting}
            onClick={submit}
            className="bg-accent text-ink font-semibold rounded-lg px-5 py-2 text-sm disabled:opacity-40"
          >
            {submitting ? "Creating…" : "Create Case"}
          </button>
        </div>
      )}

      <div className="space-y-2">
        {cases.map((c) => (
          <button
            key={c.id}
            onClick={() => navigate(`/investigations/${investigationId}/cases/${c.id}`)}
            className="card w-full text-left flex items-center justify-between hover:border-accent transition-colors"
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-slate-500">{c.case_number}</span>
                <span className="font-medium">{c.title}</span>
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {c.evidence_count} evidence item{c.evidence_count === 1 ? "" : "s"} · created by {c.created_by}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={`text-xs ${PRIORITY_STYLE[c.priority] ?? ""}`}>{c.priority}</span>
              <span className={`badge ${STATUS_STYLE[c.status] ?? "bg-slate-400/20"}`}>{c.status}</span>
            </div>
          </button>
        ))}
        {cases.length === 0 && <div className="text-sm text-slate-500">No cases yet in this investigation.</div>}
      </div>
    </div>
  );
}
