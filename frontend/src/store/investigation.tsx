import React, { createContext, useContext, useEffect, useState } from "react";
import { api, Investigation } from "../api/client";
import { useAuth } from "./auth";

interface InvestigationState {
  investigations: Investigation[];
  currentId: string | null;
  current: Investigation | null;
  loading: boolean;
  setCurrentId: (id: string) => void;
  refresh: () => void;
}

const InvestigationContext = createContext<InvestigationState | null>(null);

/**
 * KNOT6 Phase 1: which investigation the rest of the app is scoped to.
 *
 * Defaults to the first investigation returned by the API (in practice,
 * the auto-seeded "Operation Nexus" demo investigation) so every existing
 * screen keeps working out of the box without the user having to pick
 * anything first -- see the Investigations page for explicit switching.
 */
export function InvestigationProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(
    () => localStorage.getItem("knot6_investigation_id")
  );
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    if (!token) return;
    setLoading(true);
    api
      .get("/investigations")
      .then((res) => {
        const list: Investigation[] = res.data;
        setInvestigations(list);
        setCurrentId((prev) => {
          if (prev && list.some((i) => i.id === prev)) return prev;
          return list[0]?.id ?? null;
        });
      })
      .finally(() => setLoading(false));
  };

  useEffect(refresh, [token]);

  useEffect(() => {
    if (currentId) localStorage.setItem("knot6_investigation_id", currentId);
  }, [currentId]);

  const current = investigations.find((i) => i.id === currentId) ?? null;

  return (
    <InvestigationContext.Provider value={{ investigations, currentId, current, loading, setCurrentId, refresh }}>
      {children}
    </InvestigationContext.Provider>
  );
}

export function useInvestigation() {
  const ctx = useContext(InvestigationContext);
  if (!ctx) throw new Error("useInvestigation must be used within InvestigationProvider");
  return ctx;
}
