import React, { createContext, useContext, useEffect, useState } from "react";

interface AuthState {
  token: string | null;
  role: string | null;
  fullName: string | null;
  login: (token: string, role: string, fullName: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("prahari_token"));
  const [role, setRole] = useState<string | null>(() => localStorage.getItem("prahari_role"));
  const [fullName, setFullName] = useState<string | null>(() => localStorage.getItem("prahari_name"));

  useEffect(() => {
    if (token) localStorage.setItem("prahari_token", token);
    else localStorage.removeItem("prahari_token");
  }, [token]);

  const login = (t: string, r: string, n: string) => {
    setToken(t);
    setRole(r);
    setFullName(n);
    localStorage.setItem("prahari_token", t);
    localStorage.setItem("prahari_role", r);
    localStorage.setItem("prahari_name", n);
  };

  const logout = () => {
    setToken(null);
    setRole(null);
    setFullName(null);
    localStorage.removeItem("prahari_token");
    localStorage.removeItem("prahari_role");
    localStorage.removeItem("prahari_name");
  };

  return (
    <AuthContext.Provider value={{ token, role, fullName, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
