import { CopilotAction, IntelligenceSummary } from "../api/client";

/**
 * KNOT6 Case Intelligence: deterministic question suggestions for the
 * Investigation Assistant -- both the starter-state categories and the
 * per-answer "Continue exploring" follow-ups. No LLM involved anywhere in
 * this file (per the brief: guide the investigator toward useful questions
 * without pretending to be a free-form chatbot).
 *
 * A follow-up is either `kind: "ask"` -- clicking it sends the question
 * through ChatPanel's normal `ask()` call, the exact same backend/app/
 * copilot/copilot.py flow a typed question goes through, never a canned
 * answer -- or `kind: "action"`, which reuses a real CopilotAction the
 * backend already returned for the turn (see copilotActions.ts's
 * `runAction`), so a follow-up never points at navigation that doesn't
 * actually exist.
 *
 * Every static "ask" question below was verified against a real
 * investigation (Operation Nexus) to actually resolve through the
 * deterministic answerer (backend/app/copilot/deterministic_answerer.py)
 * rather than land on the honest-but-unhelpful "AI reasoning is not
 * configured" fallback -- a suggestion that reliably dead-ends is worse
 * than not suggesting it.
 */

export interface StarterCategory {
  title: string;
  questions: string[];
}

/** The categorized "more questions" menu. Entity-specific items substitute
 * a real top entity from this investigation's own intelligence summary
 * when one exists, so they're never generic placeholder text. */
export function buildStarterCategories(summary: IntelligenceSummary | null): StarterCategory[] {
  const top = summary?.key_entities?.[0]?.entity;

  return [
    {
      title: "Case Overview",
      questions: [
        "What is happening in this investigation?",
        "Give me a case summary",
        "What are the key entities?",
        "Where did I leave off?",
      ],
    },
    {
      title: "Network",
      questions: [
        "Show the most relevant entities",
        "Which entities are most connected?",
        "Which entities span multiple domains?",
        top ? `Show ${top.label}'s connections` : "Show the most connected entities in this network",
      ],
    },
    {
      title: "Evidence & Timeline",
      questions: [
        "What evidence do we have?",
        "What happened recently?",
        "What happened around 14 August?",
        "What evidence supports the current signals?",
      ],
    },
    {
      title: "Analysis",
      questions: [
        "What unusual patterns have been detected?",
        "What investigative signals need review?",
        "What unusual financial activity has been detected?",
        "What unusual communication patterns have been detected?",
      ],
    },
  ];
}

/** 4-6 primary suggestions shown directly in the empty state, one drawn
 * from each category so the first screen isn't overloaded -- the full
 * categorized menu (buildStarterCategories) sits behind "More questions"
 * (per the brief: "do not overload the interface"). */
export function buildPrimaryStarters(summary: IntelligenceSummary | null): string[] {
  const categories = buildStarterCategories(summary);
  return [
    categories[0].questions[0], // What is happening in this investigation?
    categories[0].questions[2], // What are the key entities?
    categories[1].questions[0], // Show the most relevant entities
    categories[2].questions[0], // What evidence do we have?
    categories[3].questions[0], // What unusual patterns have been detected?
    categories[3].questions[2], // What unusual financial activity...
  ];
}

export type FollowUpSuggestion =
  | { kind: "ask"; label: string; question: string }
  | { kind: "action"; label: string; action: CopilotAction };

const FINANCIAL_PHRASES = ["financial", "transaction", "account", "money", "payment"];
const TEMPORAL_PHRASES = ["what happened", "around", " date", "august", "timeline", "when did"];

/**
 * "Continue exploring" chips after an answer -- deterministic, derived only
 * from the question just asked and the real CopilotAction list the backend
 * already returned for it. Mirrors the same lightweight keyword
 * classification backend/app/copilot/deterministic_answerer.py itself
 * uses, but only to pick suggestion text/ordering -- never to answer
 * anything, so this is not a second conversation-memory or retrieval
 * system.
 */
export function buildFollowUps(question: string, actions: CopilotAction[]): FollowUpSuggestion[] {
  const q = question.toLowerCase();
  const entityAction = actions.find((a) => a.type === "OPEN_ENTITY");
  const graphAction = actions.find((a) => a.type === "OPEN_GRAPH");
  const evidenceAction = actions.find((a) => a.type === "VIEW_EVIDENCE");
  const timelineAction = actions.find((a) => a.type === "VIEW_TIMELINE");
  const financialAction = actions.find((a) => a.type === "OPEN_FINANCIAL");
  const label = entityAction?.label.replace(/^Open /, "");

  const isFinancial = FINANCIAL_PHRASES.some((p) => q.includes(p));
  const isTemporal = TEMPORAL_PHRASES.some((p) => q.includes(p));

  const out: FollowUpSuggestion[] = [];
  const askEvidence = (): FollowUpSuggestion =>
    evidenceAction
      ? { kind: "action", label: "View evidence", action: evidenceAction }
      : { kind: "ask", label: "What evidence supports this?", question: "What evidence supports this?" };

  if (isFinancial && label) {
    out.push({ kind: "ask", label: "Show the transaction path", question: `Show the transaction path for ${label}` });
    out.push({ kind: "ask", label: "Which accounts are involved?", question: `Which accounts are involved with ${label}?` });
    out.push(askEvidence());
    if (financialAction) out.push({ kind: "action", label: financialAction.label, action: financialAction });
    return out;
  }

  if (isTemporal && label) {
    out.push({ kind: "ask", label: "What happened around this date?", question: `What happened around this date involving ${label}?` });
    out.push({ kind: "ask", label: "Which entities were involved?", question: `Which entities were involved with ${label} at that time?` });
    out.push({ kind: "ask", label: "Show related evidence", question: `What evidence mentions ${label}?` });
    if (timelineAction) out.push({ kind: "action", label: timelineAction.label, action: timelineAction });
    return out;
  }

  if (label) {
    // Generic entity-focused turn ("Why is X important?", "Who is X connected to?").
    out.push(graphAction
      ? { kind: "action", label: "Show connections", action: graphAction }
      : { kind: "ask", label: "Show connections", question: `Show ${label}'s connections` });
    // isFinancial/isTemporal already returned above, so this branch only
    // runs for a plain entity-focused turn ("Why is X important?" etc).
    out.push({ kind: "ask", label: "Financial connections", question: `What are ${label}'s financial connections?` });
    out.push(askEvidence());
    if (entityAction) out.push({ kind: "action", label: entityAction.label, action: entityAction });
    return out.slice(0, 4);
  }

  return out;
}
