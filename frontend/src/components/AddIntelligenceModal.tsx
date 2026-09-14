import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Case, EvidenceItem } from "../api/client";

/**
 * KNOT6 "Add Intelligence" workflow -- a thin, honest UI layer over the
 * existing, unmodified evidence pipeline
 * (`POST /investigations/{id}/cases/{id}/evidence`, see
 * backend/app/api/routes/evidence.py). No parallel implementation: every
 * file goes through the exact same upload -> extraction -> entity/relation
 * ingestion -> graph update path the Case Detail page's upload form already
 * uses. This just gives it a dashboard entry point, multi-file batching,
 * and a real per-file result summary instead of one file at a time buried
 * on a case page.
 */

const SOURCE_TYPES = [
  { value: "FIR", label: "FIR / Police Report" },
  { value: "POLICE_REPORT", label: "Police Report" },
  { value: "CDR", label: "Call Detail Records (CDR)" },
  { value: "FINANCIAL_TRANSACTION", label: "Financial Transactions" },
  { value: "SURVEILLANCE", label: "Surveillance Report" },
  { value: "SOCIAL_MEDIA", label: "Social Media" },
  { value: "CRIMINAL_HISTORY", label: "Criminal History Database" },
  { value: "INTELLIGENCE_REPORT", label: "Intelligence Report" },
  { value: "OTHER", label: "Other (metadata only)" },
];

const SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".csv", ".xlsx", ".json"];

function guessSourceType(filename: string): string {
  const ext = filename.slice(filename.lastIndexOf(".")).toLowerCase();
  if (ext === ".csv" || ext === ".xlsx") return "CDR";
  return "INTELLIGENCE_REPORT";
}

// Real pipeline stages (see evidence.py::_process), shown as a rotating
// caption while a file's single upload+process request is in flight --
// never a fake percentage, never a per-step checkmark we can't actually
// observe over one HTTP round trip.
const STAGE_CAPTIONS = [
  "Uploading file…",
  "Extracting content…",
  "Identifying entities…",
  "Resolving relationships…",
  "Updating investigation graph…",
];

type FileStatus = "pending" | "uploading" | "done" | "failed";

interface FileRow {
  id: string;
  file: File;
  sourceType: string;
  status: FileStatus;
  evidence?: EvidenceItem;
  error?: string;
}

function extOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i === -1 ? "" : name.slice(i).toLowerCase();
}

function StageCaption() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((v) => (v + 1) % STAGE_CAPTIONS.length), 900);
    return () => clearInterval(t);
  }, []);
  return <span>{STAGE_CAPTIONS[i]}</span>;
}

export default function AddIntelligenceModal({
  open,
  investigationId,
  investigationName,
  onClose,
  onCompleted,
}: {
  open: boolean;
  investigationId: string | null;
  investigationName?: string;
  onClose: () => void;
  onCompleted: () => void;
}) {
  const navigate = useNavigate();
  const [cases, setCases] = useState<Case[]>([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [caseId, setCaseId] = useState<string>("");
  const [files, setFiles] = useState<FileRow[]>([]);
  const [phase, setPhase] = useState<"select" | "uploading" | "summary">("select");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const hadAnySuccessRef = useRef(false);

  useEffect(() => {
    if (!open || !investigationId) return;
    setCasesLoading(true);
    api
      .get(`/investigations/${investigationId}/cases`)
      .then((res) => {
        const list: Case[] = res.data;
        setCases(list);
        setCaseId(list[0]?.id ?? "");
      })
      .finally(() => setCasesLoading(false));
  }, [open, investigationId]);

  // Reset transient state every time the modal is (re-)opened.
  useEffect(() => {
    if (open) {
      setFiles([]);
      setPhase("select");
      hadAnySuccessRef.current = false;
    }
  }, [open]);

  if (!open) return null;

  function addFiles(list: FileList | null) {
    if (!list) return;
    const next: FileRow[] = Array.from(list).map((file) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      sourceType: guessSourceType(file.name),
      status: "pending",
    }));
    setFiles((prev) => [...prev, ...next]);
  }

  function removeFile(id: string) {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }

  function setSourceType(id: string, sourceType: string) {
    setFiles((prev) => prev.map((f) => (f.id === id ? { ...f, sourceType } : f)));
  }

  async function startUpload() {
    if (!investigationId || !caseId || files.length === 0) return;
    setPhase("uploading");

    for (const row of files) {
      setFiles((prev) => prev.map((f) => (f.id === row.id ? { ...f, status: "uploading" } : f)));
      try {
        const form = new FormData();
        form.append("file", row.file);
        form.append("source_type", row.sourceType);
        form.append("description", "");
        const res = await api.post<EvidenceItem>(
          `/investigations/${investigationId}/cases/${caseId}/evidence`,
          form,
          { headers: { "Content-Type": "multipart/form-data" } }
        );
        const ev = res.data;
        const failed = ev.processing_status === "FAILED";
        if (!failed) hadAnySuccessRef.current = true;
        setFiles((prev) =>
          prev.map((f) =>
            f.id === row.id
              ? {
                  ...f,
                  status: failed ? "failed" : "done",
                  evidence: ev,
                  error: failed ? ev.processing_summary?.error ?? "Processing failed." : undefined,
                }
              : f
          )
        );
      } catch (err: any) {
        const message =
          err?.response?.data?.detail ??
          (err?.response?.status === 403
            ? "You do not have permission to upload evidence."
            : err?.message ?? "Upload failed.");
        setFiles((prev) => prev.map((f) => (f.id === row.id ? { ...f, status: "failed", error: message } : f)));
      }
    }

    setPhase("summary");
    if (hadAnySuccessRef.current) onCompleted();
  }

  function handleClose() {
    if (hadAnySuccessRef.current) onCompleted();
    onClose();
  }

  const selectedCase = cases.find((c) => c.id === caseId);
  const doneFiles = files.filter((f) => f.status === "done");
  const failedFiles = files.filter((f) => f.status === "failed");
  const totalEntities = doneFiles.reduce(
    (sum, f) =>
      sum + (f.evidence?.processing_summary?.entities_extracted ?? f.evidence?.processing_summary?.entities_created ?? 0),
    0
  );
  const totalRelations = doneFiles.reduce(
    (sum, f) =>
      sum + (f.evidence?.processing_summary?.relations_extracted ?? f.evidence?.processing_summary?.relations_created ?? 0),
    0
  );
  const entityTypeTotals: Record<string, number> = {};
  for (const f of doneFiles) {
    const types = f.evidence?.processing_summary?.entity_types as Record<string, number> | undefined;
    if (types) for (const [t, n] of Object.entries(types)) entityTypeTotals[t] = (entityTypeTotals[t] ?? 0) + n;
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[6vh] px-4" onClick={handleClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl max-h-[86vh] overflow-y-auto bg-panel border border-borderStrong rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-border">
          <div>
            <h2 className="text-lg font-display font-semibold text-slate-50">Add Intelligence</h2>
            <p className="text-xs text-muted mt-0.5">
              {investigationName ? `Scoped to ${investigationName}` : "Select an investigation first."}
            </p>
          </div>
          <button onClick={handleClose} className="text-muted hover:text-slate-100 text-xl leading-none">
            ×
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {!investigationId ? (
            <div className="text-sm text-muted">No investigation selected.</div>
          ) : phase === "summary" ? (
            <SummaryView
              doneCount={doneFiles.length}
              failedCount={failedFiles.length}
              totalEntities={totalEntities}
              totalRelations={totalRelations}
              entityTypeTotals={entityTypeTotals}
              files={files}
              onViewEvidence={() => {
                navigate("/evidence");
                handleClose();
              }}
              onOpenNetwork={() => {
                navigate("/network");
                handleClose();
              }}
              onViewEntities={() => {
                navigate("/entities");
                handleClose();
              }}
              onContinue={handleClose}
            />
          ) : (
            <>
              {/* Case selection -- evidence always attaches to a case, never uploaded globally. */}
              {casesLoading ? (
                <div className="text-sm text-muted">Loading cases…</div>
              ) : cases.length === 0 ? (
                <div className="text-sm text-alert bg-alert/10 border border-alert/30 rounded-lg px-3 py-2.5">
                  This investigation has no case yet. Create one from the{" "}
                  <a
                    href={`/investigations/${investigationId}`}
                    className="underline hover:text-alert/80"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(`/investigations/${investigationId}`);
                      handleClose();
                    }}
                  >
                    investigation page
                  </a>{" "}
                  before uploading evidence.
                </div>
              ) : (
                <div>
                  <label className="eyebrow">Case</label>
                  {cases.length === 1 ? (
                    <div className="mt-1.5 text-sm text-slate-200">
                      <span className="font-mono text-xs text-muted mr-2">{selectedCase?.case_number}</span>
                      {selectedCase?.title}
                    </div>
                  ) : (
                    <select
                      className="knot-input w-full mt-1.5"
                      value={caseId}
                      onChange={(e) => setCaseId(e.target.value)}
                      disabled={phase === "uploading"}
                    >
                      {cases.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.case_number} — {c.title}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              {/* Drop zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  addFiles(e.dataTransfer.files);
                }}
                onClick={() => inputRef.current?.click()}
                className={`rounded-xl border-2 border-dashed px-6 py-8 text-center cursor-pointer transition-colors ${
                  dragOver ? "border-accent bg-accent/5" : "border-border hover:border-borderStrong"
                }`}
              >
                <input
                  ref={inputRef}
                  type="file"
                  multiple
                  className="hidden"
                  accept={SUPPORTED_EXTENSIONS.join(",")}
                  onChange={(e) => {
                    addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
                <div className="text-sm text-slate-300">Drag files here, or click to browse</div>
                <div className="text-xs text-muted mt-1.5">Supported: PDF, DOCX, TXT, CSV, XLSX, JSON</div>
                <div className="text-[11px] text-muted mt-1">
                  A scanned/image-only PDF has no extractable text yet (OCR is not available) and will be
                  reported as failed, not silently skipped.
                </div>
              </div>

              {/* File list */}
              {files.length > 0 && (
                <div className="space-y-2">
                  {files.map((f) => (
                    <FileRowView
                      key={f.id}
                      row={f}
                      onRemove={() => removeFile(f.id)}
                      onSourceTypeChange={(v) => setSourceType(f.id, v)}
                    />
                  ))}
                </div>
              )}

              <div className="flex items-center justify-between pt-1">
                <span className="text-xs text-muted">
                  {files.length === 0
                    ? "No files selected."
                    : `${files.length} file${files.length === 1 ? "" : "s"} ready`}
                </span>
                <button
                  disabled={files.length === 0 || !caseId || phase === "uploading"}
                  onClick={startUpload}
                  className="knot-btn-primary"
                >
                  {phase === "uploading"
                    ? "Processing…"
                    : `Upload & Process${files.length > 1 ? ` ${files.length} files` : ""}`}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function FileRowView({
  row,
  onRemove,
  onSourceTypeChange,
}: {
  row: FileRow;
  onRemove: () => void;
  onSourceTypeChange: (v: string) => void;
}) {
  const ext = extOf(row.file.name).replace(".", "").toUpperCase();
  return (
    <div className="flex items-center gap-3 bg-panel2 border border-border rounded-lg px-3 py-2.5">
      <span className="text-[10px] font-mono text-muted border border-border rounded px-1.5 py-0.5 shrink-0">
        {ext || "?"}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-slate-100 truncate">{row.file.name}</div>
        <div className="text-[11px] text-muted mt-0.5">
          {(row.file.size / 1024).toFixed(1)} KB
          {row.status === "uploading" && (
            <>
              {" · "}
              <StageCaption />
            </>
          )}
          {row.status === "done" && (
            <span className="text-good">
              {" · Processed"}
              {row.evidence?.processing_summary?.entities_extracted != null &&
                ` — ${row.evidence.processing_summary.entities_extracted} entities, ${row.evidence.processing_summary.relations_extracted} relations`}
              {row.evidence?.processing_summary?.entities_created != null &&
                ` — ${row.evidence.processing_summary.entities_created} entities, ${row.evidence.processing_summary.relations_created} relations`}
            </span>
          )}
          {row.status === "failed" && <span className="text-alert">{" · Failed: "}{row.error}</span>}
        </div>
      </div>
      {row.status === "pending" && (
        <select
          className="knot-input text-xs py-1.5"
          value={row.sourceType}
          onChange={(e) => onSourceTypeChange(e.target.value)}
        >
          {SOURCE_TYPES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      )}
      {row.status === "pending" ? (
        <button onClick={onRemove} className="text-muted hover:text-alert text-sm shrink-0" title="Remove">
          ×
        </button>
      ) : (
        <span className="shrink-0 text-sm">
          {row.status === "uploading" && <span className="text-muted animate-pulse">⟳</span>}
          {row.status === "done" && <span className="text-good">✓</span>}
          {row.status === "failed" && <span className="text-alert">✕</span>}
        </span>
      )}
    </div>
  );
}

function SummaryView({
  doneCount,
  failedCount,
  totalEntities,
  totalRelations,
  entityTypeTotals,
  files,
  onViewEvidence,
  onOpenNetwork,
  onViewEntities,
  onContinue,
}: {
  doneCount: number;
  failedCount: number;
  totalEntities: number;
  totalRelations: number;
  entityTypeTotals: Record<string, number>;
  files: FileRow[];
  onViewEvidence: () => void;
  onOpenNetwork: () => void;
  onViewEntities: () => void;
  onContinue: () => void;
}) {
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold text-slate-100">
          {doneCount > 0 ? "Evidence processed" : "Processing failed"}
        </h3>
        <div className="mt-3 space-y-1.5">
          {files.map((f) => (
            <div key={f.id} className="flex items-center gap-2 text-sm">
              <span className={f.status === "done" ? "text-good" : "text-alert"}>
                {f.status === "done" ? "✓" : "✕"}
              </span>
              <span className="text-slate-200 truncate">{f.file.name}</span>
              <span className="text-muted text-xs">
                {f.status === "done" ? "Processed" : `Failed: ${f.error}`}
              </span>
            </div>
          ))}
        </div>
      </div>

      {doneCount > 0 && (
        <div className="rounded-lg bg-panel2 border border-border px-4 py-3.5 space-y-2">
          <div className="text-sm text-slate-200">
            <span className="mono-tabular font-medium text-slate-50">{totalEntities}</span> entities discovered
            {Object.keys(entityTypeTotals).length > 0 && (
              <span className="text-muted text-xs">
                {" "}
                ({Object.entries(entityTypeTotals)
                  .map(([t, n]) => `${n} ${t.toLowerCase().replace(/_/g, " ")}`)
                  .join(", ")})
              </span>
            )}
          </div>
          <div className="text-sm text-slate-200">
            <span className="mono-tabular font-medium text-slate-50">{totalRelations}</span> relationships
            discovered
          </div>
          <div className="text-xs text-good">Investigation graph updated.</div>
        </div>
      )}

      {failedCount > 0 && (
        <div className="text-xs text-alert">
          {failedCount} file{failedCount === 1 ? "" : "s"} failed to process — see reasons above. Nothing was
          fabricated or silently skipped; failed files are not part of the graph.
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap pt-1">
        <button onClick={onViewEvidence} className="knot-btn-ghost">
          View Evidence
        </button>
        <button onClick={onOpenNetwork} className="knot-btn-ghost">
          Open Network
        </button>
        <button onClick={onViewEntities} className="knot-btn-ghost">
          View Entities
        </button>
        <button onClick={onContinue} className="knot-btn-primary ml-auto">
          Continue Investigation
        </button>
      </div>
    </div>
  );
}
