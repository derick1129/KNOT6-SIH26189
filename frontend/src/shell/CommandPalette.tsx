import { Command } from "cmdk";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Entity } from "../api/client";
import { useInvestigation } from "../store/investigation";

const TYPE_ICON: Record<string, string> = {
  PERSON: "◈", PHONE: "☎", VEHICLE: "▲", LOCATION: "◎", ORGANIZATION: "▣",
  FINANCIAL_ACCOUNT: "$", EVENT: "◆", CASE: "▤",
};

const NAV_SHORTCUTS = [
  { label: "Overview", to: "/overview" },
  { label: "Investigations", to: "/investigations" },
  { label: "Network Explorer", to: "/network" },
  { label: "Entities", to: "/entities" },
  { label: "Timeline", to: "/timeline" },
  { label: "Financial Intelligence", to: "/financial" },
  { label: "Geo Intelligence", to: "/geo" },
  { label: "Evidence Vault", to: "/evidence" },
  { label: "Hypothesis Lab", to: "/hypothesis" },
  { label: "AI Copilot", to: "/copilot" },
  { label: "Audit & Integrity", to: "/audit" },
];

/**
 * Global ⌘K / Ctrl+K command palette: fast navigation + entity search
 * across the active investigation via the existing /api/entities/search
 * endpoint. No new backend surface -- a UI composition over what Phase 1
 * already exposes.
 */
export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Entity[]>([]);
  const navigate = useNavigate();
  const { currentId } = useInvestigation();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (!open || !currentId || query.trim().length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .get("/entities/search", { params: { q: query, investigation_id: currentId, limit: 8 } })
        .then((res) => setResults(res.data))
        .catch(() => setResults([]));
    }, 200);
    return () => clearTimeout(t);
  }, [query, open, currentId]);

  if (!open) return null;

  const goTo = (path: string) => {
    navigate(path);
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[14vh]" onClick={() => setOpen(false)}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <Command
        shouldFilter={false}
        className="relative w-full max-w-xl bg-panel border border-borderStrong rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 border-b border-border">
          <span className="text-muted">⌕</span>
          <Command.Input
            autoFocus
            value={query}
            onValueChange={setQuery}
            placeholder="Search people, phones, vehicles, locations… or jump to a workspace"
            className="w-full bg-transparent py-3.5 text-sm outline-none text-slate-100 placeholder:text-muted"
          />
          <kbd className="text-[10px] text-muted border border-border rounded px-1.5 py-0.5">ESC</kbd>
        </div>
        <Command.List className="max-h-[60vh] overflow-y-auto p-2">
          <Command.Empty className="px-3 py-6 text-center text-sm text-muted">
            {currentId ? "No matches." : "Select an investigation first."}
          </Command.Empty>

          {results.length > 0 && (
            <Command.Group heading="Entities" className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted">
              {results.map((r) => (
                <Command.Item
                  key={r.id}
                  onSelect={() => goTo(`/network?focus=${r.id}`)}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm cursor-pointer aria-selected:bg-panel2 aria-selected:text-accent"
                >
                  <span className="text-accent w-4 text-center">{TYPE_ICON[r.type] ?? "•"}</span>
                  <span className="flex-1">{r.label}</span>
                  <span className="text-[10px] text-muted">{r.type}</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {query.trim().length < 2 && (
            <Command.Group heading="Go to" className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted">
              {NAV_SHORTCUTS.map((n) => (
                <Command.Item
                  key={n.to}
                  onSelect={() => goTo(n.to)}
                  className="px-3 py-2 rounded-lg text-sm cursor-pointer aria-selected:bg-panel2 aria-selected:text-accent"
                >
                  {n.label}
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </div>
  );
}
