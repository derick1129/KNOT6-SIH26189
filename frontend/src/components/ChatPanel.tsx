import { useEffect, useRef, useState } from "react";
import { api, ConversationTurn, CopilotAction, CopilotCitation, IntelligenceSummary } from "../api/client";
import { useCopilotNavigation } from "./copilotActions";
import { buildFollowUps, buildPrimaryStarters, buildStarterCategories } from "./copilotSuggestions";
import { useInvestigation } from "../store/investigation";

const CITATION_RE = /\[(EV-[0-9a-fA-F]{6,10})\]/g;

interface Turn {
  id: string;
  question: string;
  answer: string;
  citations: CopilotCitation[];
  actions: CopilotAction[];
  mode: "llm" | "deterministic";
}

function citationCode(citation: CopilotCitation): string {
  const m = citation.label.match(/\(([^)]+)\)\s*$/);
  return m ? m[1] : citation.evidence_id;
}

/** Renders an answer's plain text, turning any `[EV-xxxxxxxx]` token into a
 * clickable citation pill that opens the corresponding Evidence Vault item
 * -- never a fabricated reference, since the backend already stripped
 * anything not in `citations` before this ever reaches the browser. Works
 * identically whether the answer came from the LLM or the deterministic
 * answerer -- both format citation tags the same way (see
 * backend/app/copilot/context_builder.py's `evidence_code`). */
function AnswerText({ answer, citations, onCite }: { answer: string; citations: CopilotCitation[]; onCite: (c: CopilotCitation) => void }) {
  const byCode = new Map(citations.map((c) => [citationCode(c), c]));
  const parts: (string | CopilotCitation)[] = [];
  let last = 0;
  for (const m of answer.matchAll(CITATION_RE)) {
    const cite = byCode.get(m[1]);
    if (!cite) continue;
    parts.push(answer.slice(last, m.index));
    parts.push(cite);
    last = (m.index ?? 0) + m[0].length;
  }
  parts.push(answer.slice(last));

  return (
    <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-line">
      {parts.map((p, i) =>
        typeof p === "string" ? (
          <span key={i}>{p}</span>
        ) : (
          <button
            key={i}
            onClick={() => onCite(p)}
            className="inline-flex items-center mx-0.5 px-1.5 py-0.5 rounded bg-accent/15 text-accent text-[11px] font-mono hover:bg-accent/25 transition-colors align-baseline"
          >
            {citationCode(p)}
          </button>
        )
      )}
    </p>
  );
}

/** "Clear conversation?" confirmation -- reuses the same overlay pattern as
 * AddIntelligenceModal.tsx. Deliberately explicit that only chat memory is
 * affected, never investigation data (see ChatPanel's docstring below). */
function ClearConversationDialog({ onCancel, onConfirm, clearing }: { onCancel: () => void; onConfirm: () => void; clearing: boolean }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center px-4" onClick={onCancel}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-sm bg-panel border border-borderStrong rounded-2xl shadow-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-display font-semibold text-slate-50">Clear conversation?</h3>
        <p className="text-sm text-muted mt-2 leading-relaxed">
          This only clears the current Copilot conversation. Investigation data will not be affected.
        </p>
        <div className="flex items-center justify-end gap-2 mt-5">
          <button onClick={onCancel} className="knot-btn-ghost" disabled={clearing}>
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={clearing}
            className="text-xs px-3 py-1.5 rounded-lg bg-alert/15 text-alert border border-alert/30 hover:bg-alert/25 transition-colors disabled:opacity-40"
          >
            {clearing ? "Clearing…" : "Clear conversation"}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * KNOT6 Case Intelligence 2.0: the shared "ASK KNOT6" conversation
 * implementation -- embedded (dominant, primary) on the Case Intelligence
 * page and reused (full page) by the standalone `/copilot` route, so the
 * two never silently drift into two different chat experiences. Every
 * answer traces to this investigation's real graph/evidence/timeline/
 * analytics (see backend/app/copilot/copilot.py); when the answer came from
 * the deterministic (no-LLM) path, a small badge says so -- never presented
 * as if it were AI-generated prose it isn't.
 *
 * Investigation Assistant UX: the empty state and per-answer "Continue
 * exploring" chips (frontend/src/components/copilotSuggestions.ts) guide
 * the investigator toward question shapes the deterministic answerer
 * actually handles, rather than leaving a bare "ask anything" box -- but
 * every suggestion is sent through the exact same `ask()` call below as
 * anything typed by hand. Nothing here is a canned response.
 */
export default function ChatPanel({
  variant,
  summary,
}: {
  variant: "embedded" | "full";
  summary: IntelligenceSummary | null;
}) {
  const { currentId, current } = useInvestigation();
  const nav = useCopilotNavigation();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [showMoreQuestions, setShowMoreQuestions] = useState(false);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!currentId) return;
    setLoadingHistory(true);
    setUnavailable(null);
    api
      .get(`/investigations/${currentId}/conversations`)
      .then((res: { data: ConversationTurn[] }) => {
        setTurns(
          res.data.map((t) => ({
            id: t.id, question: t.question, answer: t.answer, citations: t.citations, actions: t.actions,
            mode: t.mode,
          }))
        );
      })
      .finally(() => setLoadingHistory(false));
  }, [currentId]);

  useEffect(() => {
    // `block: "nearest"` keeps this confined to the chat box's own scroll
    // container -- without it, the default `block: "center"` can drag the
    // whole page down to center the bottom of a fixed-height embedded chat
    // panel in the viewport, which is jarring when the chat is only one
    // section of a taller page (see the embedded variant on Case Intelligence).
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns, asking]);

  const ask = async (q: string) => {
    const text = q.trim();
    if (!text || !currentId || asking) return;
    setAsking(true);
    setQuestion("");
    setUnavailable(null);
    setError(null);
    try {
      const res = await api.post(`/investigations/${currentId}/copilot`, { question: text });
      const body = res.data;
      if (!body.available) {
        setUnavailable(body.answer);
        return;
      }
      setTurns((prev) => [
        ...prev,
        { id: body.turn_id ?? String(prev.length), question: text, answer: body.answer, citations: body.citations, actions: body.actions, mode: body.mode },
      ]);
    } catch (err: any) {
      // A real request failure (network/5xx/403) -- distinct from
      // `unavailable` (a normal 200 response saying no AI provider is
      // configured). Never silently drop the question with no feedback.
      setError(
        err?.response?.status === 403
          ? "You do not have permission to use the AI Copilot in this investigation."
          : "Could not reach KNOT6. Please check your connection and try again."
      );
      setQuestion(text); // give the investigator their question back to retry
    } finally {
      setAsking(false);
    }
  };

  const clearConversation = async () => {
    if (!currentId) return;
    setClearing(true);
    try {
      await api.delete(`/investigations/${currentId}/conversations`);
      setTurns([]);
      setUnavailable(null);
      setError(null);
      setShowMoreQuestions(false);
      setConfirmingClear(false);
    } catch {
      setError("Could not clear the conversation. Please try again.");
      setConfirmingClear(false);
    } finally {
      setClearing(false);
    }
  };

  if (!currentId) {
    return <div className="card text-center py-16 text-muted">Choose an investigation to use the AI Copilot.</div>;
  }

  const heightClass = variant === "embedded" ? "h-[460px]" : "h-[calc(100vh-7rem)] max-w-4xl mx-auto";
  const primaryStarters = buildPrimaryStarters(summary);
  const starterCategories = buildStarterCategories(summary);
  const lastTurn = turns[turns.length - 1];
  const followUps = lastTurn && !asking ? buildFollowUps(lastTurn.question, lastTurn.actions) : [];

  return (
    <div className={`flex flex-col ${heightClass}`}>
      <div className="flex items-center justify-between mb-2 px-0.5">
        {/* Omitted (not just empty-styled) while the empty state is showing --
            its own "KNOT6 AI / Investigation Assistant" heading already
            labels the panel there, ~30px below; keeping this eyebrow too
            would repeat "Investigation Assistant" twice in one glance. The
            span still renders so `justify-between` keeps Clear conversation
            pinned right either way. */}
        <span className="eyebrow">{turns.length > 0 ? "Investigation Assistant" : ""}</span>
        <button
          onClick={() => setConfirmingClear(true)}
          disabled={turns.length === 0 || asking}
          className="text-xs text-muted hover:text-alert transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Clear conversation
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto card space-y-5 mb-4">
        {loadingHistory ? (
          <div className="text-muted text-sm">Loading conversation…</div>
        ) : turns.length === 0 ? (
          <div className="py-4 max-w-xl mx-auto text-center">
            <div className="eyebrow mb-1">KNOT6 AI</div>
            <h2 className="text-xl font-display font-semibold text-slate-50">Investigation Assistant</h2>
            <p className="text-sm text-muted mt-2 mb-6">
              Explore this investigation through evidence, entities, relationships and activity.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
              {primaryStarters.map((q) => (
                <button key={q} onClick={() => ask(q)} className="knot-input text-left text-sm text-slate-300 hover:border-accent hover:text-slate-100 transition-colors">
                  {q}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowMoreQuestions((v) => !v)}
              className="mt-4 text-xs text-accent hover:underline"
            >
              {showMoreQuestions ? "Fewer questions ▴" : "More questions ▾"}
            </button>
            {showMoreQuestions && (
              <div className="mt-4 space-y-4 text-left">
                {starterCategories.map((c) => (
                  <div key={c.title}>
                    <div className="text-[11px] uppercase tracking-wide text-muted mb-1.5">{c.title}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {c.questions.map((q) => (
                        <button key={q} onClick={() => ask(q)} className="knot-btn-ghost">
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          turns.map((t, i) => (
            <div key={t.id} className="space-y-2">
              <div className="text-sm text-slate-400">
                <span className="eyebrow mr-2">Investigator</span>
                {t.question}
              </div>
              <div className="bg-panel2/60 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="eyebrow text-accent">KNOT6</span>
                  {t.mode === "deterministic" ? (
                    <span className="text-[10px] text-muted uppercase tracking-wide">Answered from investigation data</span>
                  ) : (
                    <span
                      className="text-[10px] uppercase tracking-wide text-accent flex items-center gap-1"
                      title="Generated by an AI provider, grounded only in this investigation's retrieved data"
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-accent inline-block" />
                      KNOT6 AI · Grounded in investigation evidence
                    </span>
                  )}
                </div>
                <AnswerText answer={t.answer} citations={t.citations} onCite={nav.openCitation} />
                {t.actions.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-3">
                    {t.actions.map((a, ai) => (
                      <button key={ai} onClick={() => nav.runAction(a)} className="knot-btn-ghost">
                        {a.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {i === turns.length - 1 && followUps.length > 0 && (
                <div className="pt-1">
                  <div className="text-[11px] uppercase tracking-wide text-muted mb-1.5">Continue exploring</div>
                  <div className="flex flex-wrap gap-1.5">
                    {followUps.map((f, fi) => (
                      <button
                        key={fi}
                        onClick={() => (f.kind === "ask" ? ask(f.question) : nav.runAction(f.action))}
                        className="knot-btn-ghost"
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
        {asking && <div className="text-sm text-muted">Reviewing investigation data…</div>}
        {unavailable && (
          <div className="card border-warn/30 bg-warn/[0.06]">
            <span className="eyebrow text-warn">AI reasoning not available</span>
            <p className="text-sm text-slate-300 mt-1.5">{unavailable}</p>
          </div>
        )}
        {error && (
          <div className="card border-alert/30 bg-alert/[0.06]">
            <p className="text-sm text-slate-200 font-medium">Unable to retrieve investigation intelligence.</p>
            <p className="text-xs text-muted mt-1">{error}</p>
            <button onClick={() => ask(question)} className="knot-btn-ghost mt-3">
              Try again
            </button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="card p-0 flex items-center gap-2">
        <input
          className="flex-1 bg-transparent px-4 py-3 text-sm outline-none placeholder:text-muted"
          placeholder={`Ask about entities, evidence, connections or timeline in ${current?.name ?? "this investigation"}...`}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(question)}
          disabled={asking}
        />
        <button onClick={() => ask(question)} disabled={!question.trim() || asking} className="knot-btn-primary mr-2 shrink-0">
          Ask
        </button>
      </div>

      {confirmingClear && (
        <ClearConversationDialog
          onCancel={() => setConfirmingClear(false)}
          onConfirm={clearConversation}
          clearing={clearing}
        />
      )}
    </div>
  );
}
