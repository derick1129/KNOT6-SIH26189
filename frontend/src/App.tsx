import { Navigate, Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import AuditLog from "./pages/AuditLog";
import Dashboard from "./pages/Dashboard";
import GraphExplorer from "./pages/GraphExplorer";
import Ingestion from "./pages/Ingestion";
import Login from "./pages/Login";
import PathFinder from "./pages/PathFinder";
import { useAuth } from "./store/auth";

function Protected({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1 p-8 max-w-[1400px]">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <Protected>
            <Shell>
              <Dashboard />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/graph"
        element={
          <Protected>
            <Shell>
              <GraphExplorer />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/path"
        element={
          <Protected>
            <Shell>
              <PathFinder />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/ingest"
        element={
          <Protected>
            <Shell>
              <Ingestion />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/audit"
        element={
          <Protected>
            <Shell>
              <AuditLog />
            </Shell>
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
