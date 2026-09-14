import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Case, IntelligenceSummary, SearchResults } from "../api/client";
import ChatPanel from "../components/ChatPanel";
import { useCopilotNavigation } from "../components/copilotActions";
import ResumePanel from "../components/ResumePanel";
import { useInvestigation } from "../store/investigation";

const TYPE_LABEL: Record<string, string> = {
  PERSON: "Person", PHONE: "Phone", VEHICLE: "Vehicle", LOCATION: "Location",
  ORGANIZATION: "Organization", FINANCIAL_ACCOUNT: "Financial Account", EVENT: "Event", CASE: "Case",
};

const SEVERITY_TONE: Record<string, string> = { high: "text-alert", medium: "text-warn", low: "text-muted" };

/**
 * KNOT6 Case Intelligence 2.0 -- chat-first. The investigator's first three
 * seconds on this page answer: what investigation is this, where did I
 * leave off, and how do I ask KNOT6 about it -- in that order. Search,
 * signals, entity/relationship counts and everything else the old
 * dashboard-of-cards layout surfaced up front are still here, but
 * demoted to supporting context: KNOT6 now *tells* the investigator what's
 * going on conversationally (via ChatPanel, grounded in
 * backend/app/copilot/copilot.py) rather than making them read a wall of
 * stat cards to find out.
 */
export default function CaseIntelligence() {
  const { currentId, current } = useInvestigation();
  const nav = useCopilotNavigation();
  const [summary, setSummary] = useState<IntelligenceSummary | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);

  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResults | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    if (!currentId) return;
    setLoading(true);
    Promise.all([
      api.get(`/investigations/${currentId}/intelligence`),
      api.get(`/investigations/${currentId}/cases`),
    ])
      .then(([s, c]) => {
        setSummary(s.data);
        setCases(c.data);
      })
      .finally(() => setLoading(false));
  }, [currentId]);

  useEffect(() => {
    if (!currentId || query.trim().length < 2) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    const t = setTimeout(() => {
      api
        .get(`/investigations/${currentId}/search`, { params: { q: query } })
        .then((res) => {
          setSearchResults(res.data);
          nav.recordSearch(query.trim());
        })
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(t);
  }, [query, currentId]);

  if (!currentId) return <EmptyState />;
  if (loading) return <div className="text-muted">Loading case intelligence…</div>;
  if (!summary) return <div className="text-alert">Could not load Case Intelligence for this investigation.</div>;

  const isSearching = searchOpen && query.trim().length >= 2;

  return (
    <div className="space-y-6">
      {/* Investigation identity -- compact */}
      <div>
        <div className="eyebrow mb-1">CASE INTELLIGENCE</div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="text-2xl md:text-3xl font-display font-semibold text-slate-50">
            {current?.name ?? "Investigation"}
          </h1>
          {cases[0] && <span className="font-mono text-xs text-muted">{cases[0].case_number}</span>}
        </div>
      </div>

      {/* Continue where you left off */}
      <ResumePanel />

      {/* ASK KNOT6 -- dominant */}
      <div>
        <div className="flex items-baseline justify-between mb-3">
          <div>
            <div className="eyebrow mb-1">Ask KNOT6</div>
            <p className="text-muted text-sm">Explore this investigation through evidence, entities, relationships and activity.</p>
          </div>
          <Link to="/copilot" className="text-xs text-accent hover:underline shrink-0">
            Open full conversation →
          </Link>
        </div>
        <ChatPanel variant="embedded" summary={summary} />
      </div>

      {/* Investigation Status -- secondary, plain text, not a dashboard */}
      <StatusStrip summary={summary} />

      {/* Search -- kept, visually secondary, distinct from Ask KNOT6 */}
      <div>
        <button
          onClick={() => setSearchOpen((v) => !v)}
          className="text-xs text-muted hover:text-slate-200 transition-colors flex items-center gap-1.5"
        >
          <span>⌕</span> Search this investigation (people, accounts, phones, evidence…)
          <span className="text-[10px]">{searchOpen ? "▴" : "▾"}</span>
        </button>
        {searchOpen && (
          <div className="mt-2 space-y-4">
            <input
              autoFocus
              className="knot-input w-full max-w-md text-sm"
              placeholder="Suresh Yadav, ACC1001, 9876543210, circular transaction…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {isSearching && <SearchPanel results={searchResults} loading={searching} nav={nav} />}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusStrip({ summary }: { summary: IntelligenceSummary }) {
  const b = summary.case_brief;
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm py-2">
      <span className="eyebrow shrink-0">Investigation Status</span>
      <Stat value={b.total_entities} label="entities" />
      <Divider />
      <Stat value={b.total_relations} label="relationships" />
      <Divider />
      <Stat value={b.open_signal_count} label="signals requiring review" tone={b.open_signal_count > 0 ? "text-warn" : undefined} />
      <Divider />
      <Stat value={b.cross_domain_entities} label="cross-domain entities" />
      {b.domains.length > 0 && (
        <>
          <Divider />
          <span className="text-muted capitalize">{b.domains.join(" · ")}</span>
        </>
      )}
    </div>
  );
}

function Stat({ value, label, tone }: { value: number; label: string; tone?: string }) {
  return (
    <span className="text-muted">
      <span className={`font-mono font-semibold ${tone ?? "text-slate-200"}`}>{value}</span> {label}
    </span>
  );
}

function Divider() {
  return <span className="w-px h-3 bg-border shrink-0" />;
}

function SearchPanel({
  results,
  loading,
  nav,
}: {
  results: SearchResults | null;
  loading: boolean;
  nav: ReturnType<typeof useCopilotNavigation>;
}) {
  if (loading && !results) return <div className="text-muted text-sm">Searching…</div>;
  if (!results) return null;

  const empty =
    results.entities.length === 0 && results.evidence.length === 0 && results.timeline.length === 0 &&
    results.relationships.length === 0 && results.signals.length === 0 && results.conversation.length === 0 &&
    results.hypotheses.length === 0;

  if (empty) {
    return <div className="card text-center py-10 text-sm text-muted">No results for "{results.query}" in this investigation.</div>;
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {results.entities.length > 0 && (
        <div className="card">
          <SectionHeader title="Entities" />
          <div className="space-y-1">
            {results.entities.map((hit) => (
              <button key={hit.entity.id} onClick={() => nav.openEntity(hit.entity.id, hit.entity.label)}
                className="w-full flex items-center justify-between text-left px-2 py-1.5 rounded-lg hover:bg-panel2 transition-colors">
                <span className="text-sm text-slate-100">{hit.entity.label}</span>
                <span className="text-[11px] text-muted">{TYPE_LABEL[hit.entity.type] ?? hit.entity.type} · {hit.connections} conn.</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {results.related_entities.length > 0 && (
        <div className="card">
          <SectionHeader title="Related Entities" />
          <div className="flex flex-wrap gap-1.5">
            {results.related_entities.map((e) => (
              <button key={e.id} onClick={() => nav.openEntity(e.id, e.label)} className="knot-btn-ghost">
                {e.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {results.relationships.length > 0 && (
        <div className="card">
          <SectionHeader title="Relationships" />
          <div className="space-y-1">
            {results.relationships.map((hit, i) => (
              <button key={i} onClick={() => nav.openPath(hit.relationship.source.id, hit.relationship.target.id, hit.relationship.source.label, hit.relationship.target.label)}
                className="w-full flex items-center justify-between gap-2 text-left px-2 py-1.5 rounded-lg hover:bg-panel2 transition-colors">
                <span className="text-sm text-slate-200 truncate">
                  {hit.relationship.source.label} <span className="text-accent text-[11px]">{hit.relationship.description}</span>{" "}
                  {hit.relationship.target.label}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {results.evidence.length > 0 && (
        <div className="card">
          <SectionHeader title="Evidence" />
          <div className="space-y-1">
            {results.evidence.map((hit) => (
              <button key={hit.evidence.id} onClick={() => nav.openEvidence(hit.evidence.id, hit.evidence.original_filename)}
                className="w-full flex items-center justify-between text-left px-2 py-1.5 rounded-lg hover:bg-panel2 transition-colors">
                <span className="text-sm text-slate-100 truncate">{hit.evidence.original_filename}</span>
                <span className="text-[11px] text-muted shrink-0">{hit.evidence.source_type.replace(/_/g, " ")}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {results.timeline.length > 0 && (
        <div className="card">
          <SectionHeader title="Timeline" />
          <div className="space-y-1.5">
            {results.timeline.map((hit) => (
              <div key={hit.event.id} className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-slate-200 truncate">{hit.event.description}</span>
                <span className="text-[10px] text-muted font-mono shrink-0">{new Date(hit.event.timestamp).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {results.signals.length > 0 && (
        <div className="card">
          <SectionHeader title="Signals" />
          <div className="space-y-1.5">
            {results.signals.map((s) => (
              <div key={s.id} className="text-sm">
                <span className={SEVERITY_TONE[s.severity] ?? "text-slate-200"}>{titleCase(s.type)}</span>
                <span className="text-muted text-[11px]"> — {s.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {results.conversation.length > 0 && (
        <div className="card">
          <SectionHeader title="Conversation" action={<Link to="/copilot" className="text-xs text-accent hover:underline">Ask KNOT6 →</Link>} />
          <div className="space-y-1.5">
            {results.conversation.map((c) => (
              <div key={c.turn_id} className="text-sm text-slate-200">"{c.question}"</div>
            ))}
          </div>
        </div>
      )}

      {results.hypotheses.length > 0 && (
        <div className="card">
          <SectionHeader title="Hypotheses" />
          <div className="space-y-1">
            {results.hypotheses.map((h) => (
              <Link key={h.id} to={`/hypothesis?open=${h.id}`}
                className="flex items-center justify-between gap-2 text-left px-2 py-1.5 rounded-lg hover:bg-panel2 transition-colors">
                <span className="text-sm text-slate-100 truncate">{h.title}</span>
                <span className="text-[11px] text-muted shrink-0">
                  {h.status.replace(/_/g, " ")} · {h.supporting_count}✓/{h.contradicting_count}✗
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between mb-3">
      <h2 className="text-[13px] font-semibold text-slate-200 tracking-wide uppercase">{title}</h2>
      {action}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card text-center py-16">
      <h2 className="text-lg font-display font-semibold text-slate-100">No investigation selected</h2>
      <p className="text-muted text-sm mt-2 max-w-sm mx-auto">Choose or create an investigation to see its Case Intelligence briefing.</p>
      <Link to="/investigations" className="knot-btn-primary inline-block mt-5">Go to Investigations</Link>
    </div>
  );
}

function titleCase(s: string): string {
  return s.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
