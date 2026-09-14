import { useState } from "react";
import CommandPalette from "./CommandPalette";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

/**
 * Sidebar is an overlay drawer, hidden by default -- it does NOT reserve
 * permanent horizontal space in the layout (see Sidebar.tsx). Open/close
 * state lives here since both Topbar (the hamburger trigger) and Sidebar
 * itself need it.
 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="min-h-screen bg-ink">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex-1 min-w-0 flex flex-col min-h-screen">
        <Topbar navOpen={navOpen} onToggleNav={() => setNavOpen((v) => !v)} />
        <main className="flex-1 min-w-0 p-8 max-w-[1600px] w-full mx-auto">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
