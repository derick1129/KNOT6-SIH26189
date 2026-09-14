import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../store/auth";

const DEMO_ACCOUNTS = [
  { role: "Admin", username: "admin", password: "admin123" },
  { role: "Investigator", username: "investigator", password: "investigator123" },
  { role: "Analyst", username: "analyst", password: "analyst123" },
  { role: "Viewer", username: "viewer", password: "viewer123" },
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
      navigate("/overview");
    } catch {
      setError("Invalid credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink px-4 knot-grid-bg">
      <div className="w-full max-w-sm">
        <Link to="/" className="block text-center mb-8">
          <div className="font-display text-3xl font-semibold text-slate-100 tracking-wide">KNOT6</div>
          <div className="text-sm text-muted mt-1">Investigation Intelligence Platform</div>
          <div className="text-xs text-slate-600 mt-1">SIH Problem Statement 26189</div>
        </Link>
        <form onSubmit={submit} className="card-elevated space-y-4">
          <div>
            <label className="eyebrow">Username</label>
            <input className="knot-input w-full mt-1.5" value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div>
            <label className="eyebrow">Password</label>
            <input type="password" className="knot-input w-full mt-1.5" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <div className="text-alert text-xs">{error}</div>}
          <button disabled={loading} className="knot-btn-primary w-full py-2.5">
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <div className="mt-5 text-xs text-muted text-center space-y-1">
          <div className="eyebrow mb-1.5">Demo accounts</div>
          {DEMO_ACCOUNTS.map((a) => (
            <div key={a.username}>
              {a.role}: <span className="text-slate-300 font-mono">{a.username}</span> /{" "}
              <span className="text-slate-300 font-mono">{a.password}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
