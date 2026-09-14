import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./shell/AppShell";
import LandingPage from "./landing/LandingPage";
import AICopilot from "./pages/AICopilot";
import AuditIntegrity from "./pages/AuditIntegrity";
import CaseDetail from "./pages/CaseDetail";
import CaseIntelligence from "./pages/CaseIntelligence";
import Entities from "./pages/Entities";
import EvidenceVault from "./pages/EvidenceVault";
import FinancialIntelligence from "./pages/FinancialIntelligence";
import GeoIntelligence from "./pages/GeoIntelligence";
import HypothesisLab from "./pages/HypothesisLab";
import Ingestion from "./pages/Ingestion";
import InvestigationDetail from "./pages/InvestigationDetail";
import Investigations from "./pages/Investigations";
import Login from "./pages/Login";
import NetworkExplorer from "./pages/NetworkExplorer";
import Overview from "./pages/Overview";
import PathFinder from "./pages/PathFinder";
import Timeline from "./pages/Timeline";
import { useAuth } from "./store/auth";

function Protected({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return <AppShell>{children}</AppShell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<Login />} />

      <Route path="/overview" element={<Protected><Overview /></Protected>} />
      <Route path="/investigations" element={<Protected><Investigations /></Protected>} />
      <Route path="/investigations/:investigationId" element={<Protected><InvestigationDetail /></Protected>} />
      <Route path="/investigations/:investigationId/cases/:caseId" element={<Protected><CaseDetail /></Protected>} />
      <Route path="/intelligence" element={<Protected><CaseIntelligence /></Protected>} />
      <Route path="/network" element={<Protected><NetworkExplorer /></Protected>} />
      <Route path="/entities" element={<Protected><Entities /></Protected>} />
      <Route path="/timeline" element={<Protected><Timeline /></Protected>} />
      <Route path="/financial" element={<Protected><FinancialIntelligence /></Protected>} />
      <Route path="/geo" element={<Protected><GeoIntelligence /></Protected>} />
      <Route path="/evidence" element={<Protected><EvidenceVault /></Protected>} />
      <Route path="/hypothesis" element={<Protected><HypothesisLab /></Protected>} />
      <Route path="/copilot" element={<Protected><AICopilot /></Protected>} />
      <Route path="/audit" element={<Protected><AuditIntegrity /></Protected>} />
      <Route path="/path" element={<Protected><PathFinder /></Protected>} />
      <Route path="/ingest" element={<Protected><Ingestion /></Protected>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
