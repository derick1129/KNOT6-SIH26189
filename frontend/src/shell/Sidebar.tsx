import { useEffect } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../store/auth";
import { useInvestigation } from "../store/investigation";

const PRIMARY = [
  { to: "/overview", label: "Overview", icon: IconGrid },
  { to: "/investigations", label: "Investigations", icon: IconFolder },
  { to: "/intelligence", label: "Case Intelligence", icon: IconBrief },
  { to: "/network", label: "Network Explorer", icon: IconGraph },
  { to: "/entities", label: "Entities", icon: IconTag },
  { to: "/timeline", label: "Timeline", icon: IconClock },
  { to: "/financial", label: "Financial Intelligence", icon: IconCurrency },
  { to: "/geo", label: "Geo Intelligence", icon: IconMap },
  { to: "/evidence", label: "Evidence Vault", icon: IconVault },
  { to: "/hypothesis", label: "Hypothesis Lab", icon: IconFlask },
  { to: "/copilot", label: "AI Copilot", icon: IconSpark },
  { to: "/audit", label: "Audit & Integrity", icon: IconShield, adminOnly: true },
];

const TOOLS = [
  { to: "/path", label: "Path Finder" },
  { to: "/ingest", label: "Quick Ingest" },
];

/**
 * Overlay navigation drawer -- hidden by default, no permanent width
 * reservation in the app layout (AppShell just stacks Topbar+content full
 * width). Opened by Topbar's hamburger button; closes on backdrop click,
 * Escape, or picking a destination.
 */
export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { role, fullName, logout } = useAuth();
  const { current } = useInvestigation();

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  return (
    <>
      {/* Backdrop -- only present (and interactive) while open, so it never
          intercepts clicks on the dashboard when closed. */}
      <div
        className={`fixed inset-0 bg-black/50 z-40 transition-opacity duration-300 ${
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onClose}
        aria-hidden
      />

      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 bg-ink2 border-r border-border flex flex-col
          transform transition-transform duration-300 ease-out
          ${open ? "translate-x-0" : "-translate-x-full"}`}
        aria-hidden={!open}
      >
        <div className="px-5 py-5 border-b border-border flex items-center justify-between">
          <div>
            <div className="font-display font-semibold text-lg tracking-wide text-slate-100">KNOT6</div>
            <div className="text-[11px] text-muted mt-0.5">Investigation Intelligence</div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close navigation"
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:text-slate-100 hover:bg-panel2 transition-colors"
          >
            <IconClose className="w-4 h-4" />
          </button>
        </div>

        {current && (
          <div className="px-5 py-3 border-b border-border">
            <div className="eyebrow">Active investigation</div>
            <div className="text-sm text-slate-200 truncate mt-0.5" title={current.name}>
              {current.name}
            </div>
          </div>
        )}

        <nav className="flex-1 overflow-y-auto p-3 space-y-0.5">
          {PRIMARY.filter((l) => !l.adminOnly || role === "admin").map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] transition-colors ${
                  isActive ? "bg-accent/10 text-accent" : "text-slate-300 hover:bg-panel2 hover:text-slate-100"
                }`
              }
            >
              <l.icon className="w-4 h-4 shrink-0" />
              {l.label}
            </NavLink>
          ))}

          <div className="eyebrow px-3 pt-4 pb-1">Tools</div>
          {TOOLS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] transition-colors ${
                  isActive ? "bg-accent/10 text-accent" : "text-slate-400 hover:bg-panel2 hover:text-slate-100"
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-border text-xs">
          <div className="text-slate-200 font-medium">{fullName}</div>
          <div className="uppercase tracking-wide text-accent text-[10px] mt-0.5">{role}</div>
          <button onClick={logout} className="mt-2 text-muted hover:text-alert transition-colors">
            Sign out
          </button>
        </div>
      </aside>
    </>
  );
}

/* Minimal inline icon set -- no icon-library dependency for a handful of
   simple strokes; keeps the bundle small and every glyph visually
   consistent (1.5px stroke, 20px viewbox). */
function IconBase({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
      {children}
    </svg>
  );
}
function IconGrid(p: any) { return <IconBase {...p}><rect x="2.5" y="2.5" width="6" height="6" rx="1"/><rect x="11.5" y="2.5" width="6" height="6" rx="1"/><rect x="2.5" y="11.5" width="6" height="6" rx="1"/><rect x="11.5" y="11.5" width="6" height="6" rx="1"/></IconBase>; }
function IconFolder(p: any) { return <IconBase {...p}><path d="M2.5 5.5a1 1 0 0 1 1-1h4l1.5 2h7.5a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-13a1 1 0 0 1-1-1z"/></IconBase>; }
function IconBrief(p: any) { return <IconBase {...p}><rect x="3" y="6" width="14" height="10" rx="1.5"/><path d="M7.5 6V4.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V6"/><path d="M3 10.5h14"/></IconBase>; }
function IconGraph(p: any) { return <IconBase {...p}><circle cx="5" cy="5" r="1.8"/><circle cx="15" cy="6" r="1.8"/><circle cx="9" cy="14" r="1.8"/><circle cx="16" cy="14" r="1.8"/><path d="M6.5 6.2 8 12.5M13.5 6.7 10.3 13"/></IconBase>; }
function IconTag(p: any) { return <IconBase {...p}><path d="M3 10.5 9.5 4H16v6.5L9.5 17z"/><circle cx="12.5" cy="7.5" r="1"/></IconBase>; }
function IconClock(p: any) { return <IconBase {...p}><circle cx="10" cy="10" r="7"/><path d="M10 6v4l3 2"/></IconBase>; }
function IconCurrency(p: any) { return <IconBase {...p}><circle cx="10" cy="10" r="7"/><path d="M10 6.5v7M12.2 8a2.2 2.2 0 0 0-2.2-1.2c-1.4 0-2.2.7-2.2 1.6 0 2.2 4.4 1 4.4 3.2 0 .9-.8 1.6-2.2 1.6a2.2 2.2 0 0 1-2.2-1.2"/></IconBase>; }
function IconMap(p: any) { return <IconBase {...p}><path d="M7 3.5 3 5v11.5l4-1.5 6 1.5 4-1.5V4l-4 1.5-6-1.5Z"/><path d="M7 3.5v11.5M13 5v11.5"/></IconBase>; }
function IconVault(p: any) { return <IconBase {...p}><rect x="3" y="3" width="14" height="14" rx="2"/><circle cx="10" cy="10" r="3"/><path d="M10 8.5v3"/></IconBase>; }
function IconFlask(p: any) { return <IconBase {...p}><path d="M8 3h4M8.5 3v5L4.8 15a1.4 1.4 0 0 0 1.2 2h8a1.4 1.4 0 0 0 1.2-2L11.5 8V3"/></IconBase>; }
function IconSpark(p: any) { return <IconBase {...p}><path d="M10 2.5c.6 3 2 4.4 5 5-3 .6-4.4 2-5 5-.6-3-2-4.4-5-5 3-.6 4.4-2 5-5Z"/></IconBase>; }
function IconShield(p: any) { return <IconBase {...p}><path d="M10 2.5 16 5v5c0 4-2.6 6.6-6 7.5C6.6 16.6 4 14 4 10V5z"/><path d="M7.5 10 9.3 11.8 12.8 8.2"/></IconBase>; }
function IconClose(p: any) { return <IconBase {...p}><path d="M5 5l10 10M15 5 5 15"/></IconBase>; }
