import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Case, EvidenceItem } from "../api/client";

const SOURCE_TYPES = [
  "FIR", "POLICE_REPORT", "CDR", "FINANCIAL_TRANSACTION", "SURVEILLANCE",
  "SOCIAL_MEDIA", "CRIMINAL_HISTORY", "INTELLIGENCE_REPORT", "OTHER",
];

const STATUS_STYLE: Record<string, string> = {
  UPLOADED: "bg-slate-400/20 text-slate-300",
  PROCESSING: "bg-warn/20 text-warn",
  PROCESSED: "bg-good/20 text-good",
  FAILED: "bg-alert/20 text-alert",
};

function UploadForm({ investigationId, caseId, onUploaded }: { investigationId: string; caseId: string; onUploaded: () => void }) {
  const [sourceType, setSourceType] = useState("FIR");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("source_type", sourceType);
      form.append("description", description);
      await api.post(`/investigations/${investigationId}/cases/${caseId}/evidence`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setFile(null);
      setDescription("");
      onUploaded();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card space-y-3">
      <h2 className="font-semibold">Register Evidence</h2>
      <div className="flex gap-3 flex-wrap">
        <select
          className="bg-panel2 border border-border rounded-lg px-3 py-2 text-sm"
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value)}
        >
          {SOURCE_TYPES.map((t) => (
            <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
          ))}
        </select>
        <input
          className="flex-1 min-w-[200px] bg-panel2 border border-border rounded-lg px-3 py-2 text-sm"
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm text-slate-300" />
      <button
        disabled={!file || loading}
        onClick={submit}
        className="bg-accent text-ink font-semibold rounded-lg px-5 py-2 text-sm disabled:opacity-40"
      >
        {loading ? "Uploading & processing…" : "Upload & Register"}
      </button>
      <p className="text-xs text-slate-500">
        Text sources (FIR, police report, surveillance, social media, intel reports) accept TXT, PDF, DOCX or
        JSON and go through NLP extraction. CDR, financial and criminal-history sources accept CSV, XLSX or
        JSON and are parsed as structured records. A scanned PDF with no extractable text, or a corrupt/malformed
        file, is reported as failed with the real reason — never silently treated as processed.
      </p>
    </div>
  );
}

export default function CaseDetail() {
  const { investigationId, caseId } = useParams<{ investigationId: string; caseId: string }>();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    if (!investigationId || !caseId) return;
    setLoading(true);
    Promise.all([
      api.get(`/investigations/${investigationId}/cases/${caseId}`),
      api.get(`/investigations/${investigationId}/cases/${caseId}/evidence`),
    ])
      .then(([c, ev]) => {
        setCaseData(c.data);
        setEvidence(ev.data);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [investigationId, caseId]);

  if (loading) return <div className="text-slate-400">Loading…</div>;
  if (!caseData) return <div className="text-alert">Case not found.</div>;

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/investigations/${investigationId}`} className="text-xs text-accent hover:underline">
          ← {caseData.investigation_id ? "Back to investigation" : "Back"}
        </Link>
        <h1 className="text-2xl font-bold mt-2">
          <span className="text-slate-500 font-mono text-lg mr-2">{caseData.case_number}</span>
          {caseData.title}
        </h1>
        <p className="text-slate-400 text-sm mt-1">{caseData.description || "No description."}</p>
      </div>

      {investigationId && caseId && (
        <UploadForm investigationId={investigationId} caseId={caseId} onUploaded={load} />
      )}

      <div className="card">
        <h2 className="font-semibold mb-3">Evidence ({evidence.length})</h2>
        <div className="space-y-2">
          {evidence.map((ev) => (
            <div key={ev.id} className="flex items-center justify-between border-b border-border/60 pb-2 last:border-0 text-sm">
              <div>
                <div className="text-slate-100">{ev.original_filename}</div>
                <div className="text-xs text-slate-500">
                  {ev.source_type.replace(/_/g, " ")} · {(ev.file_size / 1024).toFixed(1)} KB · uploaded by{" "}
                  {ev.uploaded_by}
                  {ev.processing_summary?.entities_extracted != null &&
                    ` · ${ev.processing_summary.entities_extracted} entities, ${ev.processing_summary.relations_extracted} relations`}
                  {ev.processing_summary?.entities_created != null &&
                    ` · ${ev.processing_summary.entities_created} entities, ${ev.processing_summary.relations_created} relations`}
                </div>
                {ev.processing_status === "FAILED" && ev.processing_summary?.error && (
                  <div className="text-xs text-alert mt-1">{ev.processing_summary.error}</div>
                )}
              </div>
              <span className={`badge ${STATUS_STYLE[ev.processing_status] ?? "bg-slate-400/20"}`}>
                {ev.processing_status}
              </span>
            </div>
          ))}
          {evidence.length === 0 && <div className="text-sm text-slate-500">No evidence registered yet.</div>}
        </div>
      </div>
    </div>
  );
}
