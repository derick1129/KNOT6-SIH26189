import { useEffect, useState } from "react";
import { api, IntelligenceSummary } from "../api/client";
import ChatPanel from "../components/ChatPanel";
import { useInvestigation } from "../store/investigation";

/**
 * ASK KNOT6 -- the standalone, full-page Investigation Copilot. Shares its
 * entire conversation implementation (including the guided starter
 * questions and "Continue exploring" follow-ups) with the embedded chat on
 * the Case Intelligence page (see ../components/ChatPanel.tsx) so the two
 * never silently drift into two different chat experiences; this page only
 * owns its own header.
 */
export default function AICopilot() {
  const { currentId, current } = useInvestigation();
  const [summary, setSummary] = useState<IntelligenceSummary | null>(null);

  useEffect(() => {
    if (!currentId) return;
    api.get(`/investigations/${currentId}/intelligence`).then((res) => setSummary(res.data));
  }, [currentId]);

  if (!currentId) {
    return <div className="card text-center py-16 text-muted">Choose an investigation to use the AI Copilot.</div>;
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-4">
        <div className="eyebrow mb-1">ASK KNOT6</div>
        <h1 className="text-2xl font-display font-semibold">Investigation Copilot</h1>
        <p className="text-muted text-sm mt-1">
          Grounded in {current?.name ?? "this investigation"}'s real graph, evidence and analytics — never a
          general-purpose chatbot. Every claim traces to retrieved data; evidence citations open the source directly.
        </p>
      </div>

      <ChatPanel variant="full" summary={summary} />
    </div>
  );
}
