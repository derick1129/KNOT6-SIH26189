import { useState } from "react";
import { api } from "../api/client";

const TEXT_SOURCES = [
  { value: "fir", label: "FIR / Police Report" },
  { value: "surveillance", label: "Surveillance Report" },
  { value: "intel_report", label: "Intelligence Report" },
];

const CSV_SOURCES = [
  { value: "cdr", label: "Call Detail Records (CDR)" },
  { value: "financial", label: "Financial Transactions" },
  { value: "criminal_history", label: "Criminal History Database" },
];

function TextIngestForm() {
  const [sourceType, setSourceType] = useState("fir");
  const [documentId, setDocumentId] = useState("");
  const [text, setText] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      const res = await api.post("/ingest/text", {
        source_type: sourceType,
        document_id: documentId || `${sourceType}-${Date.now()}`,
        text,
      });
      setResult(res.data);
      setText("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card space-y-3">
      <h2 className="font-semibold">Unstructured Report (NLP extraction)</h2>
      <div className="flex gap-3 flex-wrap">
        <select
          className="bg-panel2 border border-border rounded-lg px-3 py-2 text-sm"
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value)}
        >
          {TEXT_SOURCES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <input
          className="flex-1 min-w-[200px] bg-panel2 border border-border rounded-lg px-3 py-2 text-sm"
          placeholder="Document ID (optional)"
          value={documentId}
          onChange={(e) => setDocumentId(e.target.value)}
        />
      </div>
      <textarea
        className="w-full h-40 bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
        placeholder="Paste the FIR narrative / surveillance note / intelligence summary text here…"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <button
        disabled={!text.trim() || loading}
        onClick={submit}
        className="bg-accent text-ink font-semibold rounded-lg px-5 py-2 text-sm disabled:opacity-40"
      >
        {loading ? "Extracting…" : "Extract & Add to Graph"}
      </button>
      {result && (
        <div className="text-xs text-good bg-good/10 border border-good/30 rounded-lg px-3 py-2">
          Extracted {result.entities_extracted} entities and {result.relations_extracted} relations from{" "}
          {result.document_id}.
        </div>
      )}
    </div>
  );
}

function CsvIngestForm() {
  const [sourceType, setSourceType] = useState("cdr");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.post(`/ingest/csv/${sourceType}`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
      setFile(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card space-y-3">
      <h2 className="font-semibold">Structured Records (CSV)</h2>
      <select
        className="bg-panel2 border border-border rounded-lg px-3 py-2 text-sm"
        value={sourceType}
        onChange={(e) => setSourceType(e.target.value)}
      >
        {CSV_SOURCES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
      <input
        type="file"
        accept=".csv"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="text-sm text-slate-300"
      />
      <button
        disabled={!file || loading}
        onClick={submit}
        className="bg-accent text-ink font-semibold rounded-lg px-5 py-2 text-sm disabled:opacity-40"
      >
        {loading ? "Processing…" : "Upload & Build Graph"}
      </button>
      {result && (
        <div className="text-xs text-good bg-good/10 border border-good/30 rounded-lg px-3 py-2">
          Processed {result.records_processed} records → {result.entities_created} entities,{" "}
          {result.relations_created} relations ({result.entities_merged} auto-merged as duplicates).
        </div>
      )}
    </div>
  );
}

export default function Ingestion() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Ingest Data</h1>
        <p className="text-slate-400 text-sm mt-1">
          Every source named in the problem statement feeds the same graph. Structured sources (CDR,
          financial, criminal history) map directly to entities; unstructured reports go through the NLP
          extraction pipeline first.
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TextIngestForm />
        <CsvIngestForm />
      </div>
    </div>
  );
}
