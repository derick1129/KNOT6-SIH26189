import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../store/auth";

const DEMO_ACCOUNTS = [
  { role: "Admin", username: "admin", password: "admin123" },
  { role: "Investigator", username: "investigator", password: "investigator123" },
  { role: "Analyst", username: "analyst", password: "analyst123" },
];

export default function Login() {
  const [username, setUsername] = useState("investigator");
  const [password, setPassword] = useState("investigator123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api.post("/auth/login", { username, password });
      login(res.data.access_token, res.data.role, res.data.full_name);
      navigate("/");
    } catch {
      setError("Invalid credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-3xl font-bold text-accent tracking-wide">PRAHARI</div>
          <div className="text-sm text-slate-400 mt-1">
            AI-Powered Criminal Network Analysis System
          </div>
          <div className="text-xs text-slate-600 mt-1">SIH Problem Statement 26189 · NCRB, MHA</div>
        </div>
        <form onSubmit={submit} className="card space-y-4">
          <div>
            <label className="text-xs text-slate-400">Username</label>
            <input
              className="w-full mt-1 bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-slate-400">Password</label>
            <input
              type="password"
              className="w-full mt-1 bg-panel2 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && <div className="text-alert text-xs">{error}</div>}
          <button
            disabled={loading}
            className="w-full bg-accent text-ink font-semibold rounded-lg py-2 text-sm hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <div className="mt-4 text-xs text-slate-500 text-center space-y-1">
          <div>Demo accounts:</div>
          {DEMO_ACCOUNTS.map((a) => (
            <div key={a.username}>
              {a.role}: <span className="text-slate-300">{a.username}</span> /{" "}
              <span className="text-slate-300">{a.password}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
