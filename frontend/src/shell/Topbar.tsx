import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../store/auth";
import { useInvestigation } from "../store/investigation";

/**
 * Persistent top strip: hamburger (toggles the overlay nav drawer -- see
 * Sidebar.tsx/AppShell.tsx), the KNOT6 identity, the investigation
 * switcher, global search (opens CommandPalette), and the account chip.
 * This is the one piece of chrome that's always present regardless of
 * whether the drawer is open, so closing it never leaves the app feeling
 * unbranded or lost.
 */
export default function Topbar({ navOpen, onToggleNav }: { navOpen: boolean; onToggleNav: () => void }) {
  const { investigations, currentId, setCurrentId } = useInvestigation();
  const { fullName, role, logout } = useAuth();
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const navigate = useNavigate();
  const isMac = typeof navigator !== "undefined" && /Mac/.test(navigator.platform);
  const initials = (fullName ?? "?")
    .split(" ")
    .map((s) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <header className="h-16 shrink-0 border-b border-border bg-ink/80 backdrop-blur sticky top-0 z-20 flex items-center gap-4 px-6">
      <button
        onClick={onToggleNav}
        aria-label={navOpen ? "Close navigation" : "Open navigation"}
        aria-pressed={navOpen}
        className="w-9 h-9 -ml-1 rounded-lg flex items-center justify-center text-slate-300 hover:text-accent hover:bg-panel2 transition-colors shrink-0"
      >
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="w-[18px] h-[18px]">
          <path d="M3 6h14M3 10h14M3 14h14" />
        </svg>
      </button>

      <div className="flex items-baseline gap-2 shrink-0">
        <span className="font-display font-semibold text-[15px] tracking-wide text-slate-100">KNOT6</span>
        <span className="text-[11px] text-muted hidden sm:inline">Investigation Intelligence</span>
      </div>

      <div className="w-px h-5 bg-border hidden md:block" />

      <div className="relative hidden md:block">
        <button
          onClick={() => setSwitcherOpen((v) => !v)}
          className="flex items-center gap-2 text-sm text-slate-300 hover:text-accent transition-colors"
        >
          <span className="truncate max-w-[200px]">
            {investigations.find((i) => i.id === currentId)?.name ?? "Select investigation"}
          </span>
          <span className="text-muted text-xs">▾</span>
        </button>
        {switcherOpen && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setSwitcherOpen(false)} />
            <div className="absolute left-0 top-8 z-40 w-72 bg-panel border border-borderStrong rounded-xl shadow-2xl p-1.5">
              {investigations.map((inv) => (
                <button
                  key={inv.id}
                  onClick={() => {
                    setCurrentId(inv.id);
                    setSwitcherOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center justify-between ${
                    inv.id === currentId ? "bg-accent/10 text-accent" : "text-slate-300 hover:bg-panel2"
                  }`}
                >
                  <span className="truncate">{inv.name}</span>
                  <span className="text-[10px] text-muted">{inv.case_count} cases</span>
                </button>
              ))}
              <div className="border-t border-border mt-1 pt-1">
                <button
                  onClick={() => {
                    setSwitcherOpen(false);
                    navigate("/investigations");
                  }}
                  className="w-full text-left px-3 py-2 rounded-lg text-sm text-accent hover:bg-panel2"
                >
                  Manage investigations →
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="flex-1" />

      <button
        onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
        className="flex items-center gap-2 knot-input text-muted text-xs w-full max-w-md justify-between hover:border-accent/50"
      >
        <span className="flex items-center gap-2 truncate">
          <span>⌕</span> Search people, phone numbers, accounts, locations…
        </span>
        <kbd className="text-[10px] border border-border rounded px-1.5 py-0.5 shrink-0">{isMac ? "⌘K" : "Ctrl K"}</kbd>
      </button>

      <div className="flex-1" />

      <div className="relative shrink-0">
        <button
          onClick={() => setProfileOpen((v) => !v)}
          className="flex items-center gap-2.5 pl-1 pr-2 py-1 rounded-lg hover:bg-panel2 transition-colors"
        >
          <span className="w-8 h-8 rounded-full bg-accent/15 text-accent flex items-center justify-center text-[11px] font-mono font-semibold shrink-0">
            {initials}
          </span>
          <span className="text-left hidden lg:block">
            <span className="block text-[13px] text-slate-200 leading-tight">{fullName}</span>
            <span className="block text-[10px] uppercase tracking-wide text-muted leading-tight">{role}</span>
          </span>
          <span className="text-muted text-xs hidden lg:inline">▾</span>
        </button>
        {profileOpen && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setProfileOpen(false)} />
            <div className="absolute right-0 top-11 z-40 w-48 bg-panel border border-borderStrong rounded-xl shadow-2xl p-1.5">
              <div className="px-3 py-2 text-xs text-muted border-b border-border mb-1">
                Signed in as <span className="text-slate-200">{fullName}</span>
              </div>
              <button
                onClick={logout}
                className="w-full text-left px-3 py-2 rounded-lg text-sm text-alert hover:bg-panel2"
              >
                Sign out
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  );
}
