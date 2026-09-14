import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  api, Entity, EvidenceItem, HypothesisDetail, HypothesisEvidenceLink, HypothesisStatus, HypothesisSummary,
} from "../api/client";
import { useInvestigation } from "../store/investigation";

/**
 * Hypothesis Lab, now persisted (previously: real analysis, composed live
 * client-side, but nothing saved -- see app/db/models.py:Hypothesis's
 * docstring). A saved hypothesis's title/description/status/tagged
 * evidence/notes are real database rows; its analytical context (path,
 * centrality, community, signals, relevant timeline) is still recomputed
 * live on every open from the same unmodified analytics endpoints the
 * original client-side version called -- deliberately never frozen, so a
 * hypothesis reopened after new evidence arrives shows the current picture,
 * not a stale one. Framing stays strictly investigative: `assessment` below
 * is server-narrated text, never a guilt claim (see
 * app/services/hypothesis.py:narrate_assessment).
 */

const STATUSES: HypothesisStatus[] = ["OPEN", "UNDER_REVIEW", "SUPPORTED", "CONTRADICTED", "INCONCLUSIVE"];
const STATUS_STYLE: Record<HypothesisStatus, string> = {
  OPEN: "bg-slate-400/15 text-slate-300",
  UNDER_REVIEW: "bg-warn/15 text-warn",
  SUPPORTED: "bg-good/15 text-good",
  CONTRADICTED: "bg-alert/15 text-alert",
  INCONCLUSIVE: "bg-accent/15 text-accent",
};

function EntityPicker({ label, onPick, picked, investigationId }: {
  label: string; onPick: (e: Entity | null) => void; picked: Entity | null; investigationId: string | null;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Entity[]>([]);

  useEffect(() => {
    if (!investigationId || query.trim().length < 2) return setResults([]);
    const t = setTimeout(() => {
      api.get("/entities/search", { params: { q: query, investigation_id: investigationId } }).then((res) => setResults(res.data));
    }, 250);
    return () => clearTimeout(t);
  }, [query, investigationId]);

  return (
    <div className="flex-1 min-w-[200px]">
      <label className="eyebrow">{label}</label>
      {picked ? (
        <div className="mt-1.5 flex items-center justify-between knot-input">
          <span>{picked.label} <span className="text-muted text-xs">· {picked.type}</span></span>
          <button className="text-muted hover:text-alert" onClick={() => { onPick(null); setQuery(""); }}>✕</button>
        </div>
      ) : (
        <>
          <input className="knot-input w-full mt-1.5" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search entity…" />
          {results.length > 0 && (
            <div className="mt-1 border border-border rounded-lg overflow-hidden bg-panel relative z-10">
              {results.map((r) => (
                <button key={r.id} className="w-full text-left px-3 py-2 text-sm hover:bg-panel2"
                  onClick={() => { onPick(r); setResults([]); }}>
                  {r.label} <span className="text-muted text-xs">· {r.type}</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function EvidenceTagRow({ link, onRemove }: { link: HypothesisEvidenceLink; onRemove: () => void }) {
  return (
    <div className="flex items-start justify-between gap-2 py-1.5 border-b border-border/40 last:border-0">
      <div className="min-w-0">
        <div className="text-sm text-slate-200 truncate">{link.evidence?.original_filename ?? "(evidence removed)"}</div>
        {link.note && <div className="text-[11px] text-muted mt-0.5">{link.note}</div>}
      </div>
      <button onClick={onRemove} className="text-muted hover:text-alert text-xs shrink-0">Remove</button>
    </div>
  );
}

export default function HypothesisLab() {
  const { currentId } = useInvestigation();
  const [searchParams] = useSearchParams();
  const [hypotheses, setHypotheses] = useState<HypothesisSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<HypothesisDetail | null>(null);
  const [mode, setMode] = useState<"list" | "create">("list");
  const [loadingDetail, setLoadingDetail] = useState(false);

  // create form
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [subject, setSubject] = useState<Entity | null>(null);
  const [target, setTarget] = useState<Entity | null>(null);
  const [creating, setCreating] = useState(false);

  // evidence tagging
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [tagEvidenceId, setTagEvidenceId] = useState("");
  const [tagRelation, setTagRelation] = useState<"SUPPORTING" | "CONTRADICTING">("SUPPORTING");
  const [tagNote, setTagNote] = useState("");
  const [tagging, setTagging] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [addingNote, setAddingNote] = useState(false);

  function loadList() {
    if (!currentId) return;
    api.get(`/investigations/${currentId}/hypotheses`).then((res) => setHypotheses(res.data));
  }
  useEffect(loadList, [currentId]);

  // Deep-link support: /hypothesis?open=<id> (used by search results and
  // the AI Copilot's OPEN_HYPOTHESIS action) -- open that hypothesis
  // directly instead of leaving the investigator to find it in the list.
  useEffect(() => {
    const openId = searchParams.get("open");
    if (openId) selectHypothesis(openId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    if (currentId) api.get(`/investigations/${currentId}/evidence`).then((res) => setEvidenceList(res.data));
  }, [currentId]);

  function loadDetail(id: string) {
    setLoadingDetail(true);
    api.get(`/hypotheses/${id}`).then((res) => setDetail(res.data)).finally(() => setLoadingDetail(false));
  }

  function selectHypothesis(id: string) {
    setSelectedId(id);
    setMode("list");
    loadDetail(id);
  }

  async function createHypothesis() {
    if (!currentId || !title.trim()) return;
    setCreating(true);
    try {
      const res = await api.post(`/investigations/${currentId}/hypotheses`, {
        title: title.trim(), description, subject_entity_id: subject?.id ?? null, target_entity_id: target?.id ?? null,
      });
      setTitle(""); setDescription(""); setSubject(null); setTarget(null);
      loadList();
      selectHypothesis(res.data.id);
      setDetail(res.data);
    } finally {
      setCreating(false);
    }
  }

  async function changeStatus(status: HypothesisStatus) {
    if (!detail) return;
    const res = await api.patch(`/hypotheses/${detail.id}`, { status });
    setDetail(res.data);
    loadList();
  }

  async function submitEvidenceTag() {
    if (!detail || !tagEvidenceId) return;
    setTagging(true);
    try {
      await api.post(`/hypotheses/${detail.id}/evidence`, {
        evidence_id: tagEvidenceId, relationship_type: tagRelation, note: tagNote,
      });
      setTagEvidenceId(""); setTagNote("");
      loadDetail(detail.id);
      loadList();
    } finally {
      setTagging(false);
    }
  }

  async function removeEvidenceTag(linkId: string) {
    if (!detail) return;
    await api.delete(`/hypotheses/${detail.id}/evidence/${linkId}`);
    loadDetail(detail.id);
    loadList();
  }

  async function submitNote() {
    if (!detail || !noteText.trim()) return;
    setAddingNote(true);
    try {
      await api.post(`/hypotheses/${detail.id}/notes`, { text: noteText.trim() });
      setNoteText("");
      loadDetail(detail.id);
    } finally {
      setAddingNote(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-display font-semibold">Hypothesis Lab</h1>
          <p className="text-muted text-sm mt-1 max-w-2xl">
            Test and track an investigative hypothesis — e.g. "Could this entity be a bridge between two networks?" —
            against real path, centrality, community and evidence data. Every output is an investigative lead for a
            human to verify, never a determination of guilt.
          </p>
        </div>
        <button
          onClick={() => { setMode("create"); setSelectedId(null); setDetail(null); }}
          className="knot-btn-primary text-sm shrink-0"
        >
          + New Hypothesis
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4">
        {/* --- Saved hypotheses list --- */}
        <aside className="card p-0 overflow-hidden h-fit">
          <div className="px-3 py-2.5 border-b border-border text-[11px] uppercase tracking-wide text-muted">
            Saved hypotheses ({hypotheses.length})
          </div>
          {hypotheses.length === 0 ? (
            <div className="px-3 py-6 text-sm text-muted text-center">None yet.</div>
          ) : (
            <div className="max-h-[520px] overflow-y-auto">
              {hypotheses.map((h) => (
                <button
                  key={h.id}
                  onClick={() => selectHypothesis(h.id)}
                  className={`w-full text-left px-3 py-2.5 border-b border-border/40 last:border-0 hover:bg-panel2/60 transition-colors ${
                    selectedId === h.id ? "bg-accent/10" : ""
                  }`}
                >
                  <div className="text-sm text-slate-100 truncate">{h.title}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`badge text-[10px] ${STATUS_STYLE[h.status]}`}>{h.status.replace("_", " ")}</span>
                    <span className="text-[10px] text-muted">
                      {h.supporting_count}✓ / {h.contradicting_count}✗
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </aside>

        {/* --- Main panel: create form or hypothesis detail --- */}
        <main className="space-y-4">
          {mode === "create" && (
            <div className="card space-y-3">
              <span className="eyebrow">New hypothesis</span>
              <input
                className="knot-input w-full"
                placeholder='e.g. "Entity A may be coordinating with Entity B"'
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
              <textarea
                className="knot-input w-full min-h-[70px]"
                placeholder="Describe the hypothesis in more detail (optional)…"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <div className="flex gap-4 flex-wrap items-end">
                <EntityPicker label="Subject entity" onPick={setSubject} picked={subject} investigationId={currentId} />
                <EntityPicker label="Possible target (optional)" onPick={setTarget} picked={target} investigationId={currentId} />
              </div>
              <p className="text-[11px] text-muted">
                Subject/target entities let the Lab compute live path, centrality and community context for this
                hypothesis every time it's opened.
              </p>
              <div className="flex gap-2">
                <button disabled={!title.trim() || creating} onClick={createHypothesis} className="knot-btn-primary disabled:opacity-40">
                  {creating ? "Saving…" : "Save Hypothesis"}
                </button>
                <button onClick={() => setMode("list")} className="text-sm text-muted hover:text-slate-200">Cancel</button>
              </div>
            </div>
          )}

          {mode === "list" && !detail && !loadingDetail && (
            <div className="card text-center py-14 text-muted text-sm">
              Select a saved hypothesis on the left, or create a new one.
            </div>
          )}

          {loadingDetail && <div className="text-muted">Loading…</div>}

          {mode === "list" && detail && !loadingDetail && (
            <div className="space-y-4">
              <div className="card space-y-3">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <span className="eyebrow">Hypothesis</span>
                    <h2 className="text-lg font-medium text-slate-100 mt-1">{detail.title}</h2>
                    {detail.description && <p className="text-sm text-muted mt-1 max-w-xl">{detail.description}</p>}
                  </div>
                  <select
                    className="knot-input text-xs"
                    value={detail.status}
                    onChange={(e) => changeStatus(e.target.value as HypothesisStatus)}
                  >
                    {STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
                  </select>
                </div>
                <div className={`text-sm px-3 py-2 rounded-md border ${STATUS_STYLE[detail.status]} border-current/20`}>
                  {detail.assessment}
                </div>
              </div>

              {/* Supporting / contradicting evidence */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="card">
                  <span className="eyebrow text-good">Supporting evidence ({detail.supporting_evidence.length})</span>
                  <div className="mt-2">
                    {detail.supporting_evidence.length === 0 && <p className="text-muted text-sm">None tagged yet.</p>}
                    {detail.supporting_evidence.map((l) => (
                      <EvidenceTagRow key={l.id} link={l} onRemove={() => removeEvidenceTag(l.id)} />
                    ))}
                  </div>
                </div>
                <div className="card">
                  <span className="eyebrow text-alert">Contradicting evidence ({detail.contradicting_evidence.length})</span>
                  <div className="mt-2">
                    {detail.contradicting_evidence.length === 0 && <p className="text-muted text-sm">None tagged yet.</p>}
                    {detail.contradicting_evidence.map((l) => (
                      <EvidenceTagRow key={l.id} link={l} onRemove={() => removeEvidenceTag(l.id)} />
                    ))}
                  </div>
                </div>
              </div>

              {/* Tag new evidence */}
              <div className="card space-y-2">
                <span className="eyebrow">Tag evidence</span>
                <div className="flex gap-2 flex-wrap items-center">
                  <select className="knot-input text-sm flex-1 min-w-[180px]" value={tagEvidenceId} onChange={(e) => setTagEvidenceId(e.target.value)}>
                    <option value="">Select evidence…</option>
                    {evidenceList.map((e) => <option key={e.id} value={e.id}>{e.original_filename}</option>)}
                  </select>
                  <select className="knot-input text-sm" value={tagRelation} onChange={(e) => setTagRelation(e.target.value as "SUPPORTING" | "CONTRADICTING")}>
                    <option value="SUPPORTING">Supporting</option>
                    <option value="CONTRADICTING">Contradicting</option>
                  </select>
                </div>
                <input className="knot-input w-full text-sm" placeholder="Note (optional)…" value={tagNote} onChange={(e) => setTagNote(e.target.value)} />
                <button disabled={!tagEvidenceId || tagging} onClick={submitEvidenceTag} className="knot-btn-primary text-sm disabled:opacity-40">
                  {tagging ? "Tagging…" : "Tag Evidence"}
                </button>
                {evidenceList.length === 0 && (
                  <p className="text-[11px] text-muted">No evidence registered in this investigation yet.</p>
                )}
              </div>

              {/* Analytical context (live-computed) */}
              <div className="card space-y-3">
                <span className="eyebrow">Analytical context (live)</span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                  {detail.analytical_context.subject_influencer && (
                    <div>
                      <span className="text-muted text-xs">Subject betweenness centrality</span>
                      <div className="text-slate-200">{detail.analytical_context.subject_influencer.betweenness_centrality.toFixed(3)}</div>
                    </div>
                  )}
                  {detail.analytical_context.same_community !== null && (
                    <div>
                      <span className="text-muted text-xs">Same detected community</span>
                      <div className="text-slate-200">{detail.analytical_context.same_community ? "Yes" : "No — different communities, yet connected"}</div>
                    </div>
                  )}
                </div>
                {detail.analytical_context.path?.found && (
                  <div>
                    <span className="text-muted text-xs">Evidentiary path</span>
                    <div className="flex items-center flex-wrap gap-2 mt-2">
                      {detail.analytical_context.path.path.map((hop, i) => (
                        <div key={hop.entity.id} className="flex items-center gap-2">
                          {i > 0 && <span className="text-muted text-xs">→ {hop.via_relation?.type}</span>}
                          <div className="knot-input py-1.5 px-2.5 text-xs">{hop.entity.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {detail.analytical_context.relevant_signals.length > 0 && (
                  <div>
                    <span className="text-muted text-xs">Relevant investigative signals</span>
                    <div className="mt-1 space-y-1">
                      {detail.analytical_context.relevant_signals.map((s) => (
                        <p key={s.id} className="text-sm text-slate-300">▸ {s.description}</p>
                      ))}
                    </div>
                  </div>
                )}
                {!detail.analytical_context.subject_entity && (
                  <p className="text-muted text-sm">No subject entity linked — analytical context unavailable.</p>
                )}
              </div>

              {/* Investigator notes */}
              <div className="card space-y-2">
                <span className="eyebrow">Investigator notes ({detail.notes.length})</span>
                {detail.notes.map((n) => (
                  <div key={n.id} className="text-sm text-slate-200 border-b border-border/40 last:border-0 py-1.5">
                    <span className="text-muted text-[11px]">{n.author} · {new Date(n.created_at).toLocaleString()}</span>
                    <p>{n.text}</p>
                  </div>
                ))}
                <div className="flex gap-2">
                  <input className="knot-input flex-1 text-sm" placeholder="Add a note…" value={noteText} onChange={(e) => setNoteText(e.target.value)} />
                  <button disabled={!noteText.trim() || addingNote} onClick={submitNote} className="knot-btn-primary text-sm disabled:opacity-40">
                    {addingNote ? "Adding…" : "Add"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
