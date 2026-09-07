import { NavLink } from "react-router-dom";
import { useAuth } from "../store/auth";

const links = [
  { to: "/", label: "Dashboard", icon: "📊" },
  { to: "/graph", label: "Graph Explorer", icon: "🕸️" },
  { to: "/path", label: "Path Finder", icon: "🔗" },
  { to: "/ingest", label: "Ingest Data", icon: "📥" },
  { to: "/audit", label: "Audit Log", icon: "🛡️", adminOnly: true },
];

export default function Sidebar() {
  const { role, fullName, logout } = useAuth();
  return (
    <aside className="w-60 shrink-0 bg-panel border-r border-border h-screen sticky top-0 flex flex-col">
      <div className="p-5 border-b border-border">
        <div className="text-xl font-bold text-accent tracking-wide">PRAHARI</div>
        <div className="text-xs text-slate-400 mt-1">Criminal Network Analysis</div>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {links
          .filter((l) => !l.adminOnly || role === "admin")
          .map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive ? "bg-accent/15 text-accent" : "text-slate-300 hover:bg-panel2"
                }`
              }
            >
              <span>{l.icon}</span>
              {l.label}
            </NavLink>
          ))}
      </nav>
      <div className="p-4 border-t border-border text-xs text-slate-400">
        <div className="text-slate-200 font-medium">{fullName}</div>
        <div className="uppercase tracking-wide text-accent">{role}</div>
        <button onClick={logout} className="mt-2 text-slate-400 hover:text-alert transition-colors">
          Sign out
        </button>
      </div>
    </aside>
  );
}
