import axios from "axios";

export const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("prahari_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem("prahari_token");
      if (window.location.pathname !== "/login") window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// --- typed shapes (mirrors backend/app/models/schemas.py) -----------------

export interface Entity {
  id: string;
  type: string;
  label: string;
  attributes: Record<string, any>;
  risk_score: number;
  source_count: number;
}

export interface Relation {
  id: string;
  source: string;
  target: string;
  type: string;
  attributes: Record<string, any>;
  weight: number;
  evidence: string[];
}

export interface GraphData {
  nodes: Entity[];
  edges: Relation[];
}

export interface InfluencerScore {
  entity: Entity;
  degree_centrality: number;
  betweenness_centrality: number;
  pagerank: number;
  composite_score: number;
  rank: number;
}

export interface Community {
  community_id: number;
  size: number;
  members: Entity[];
  density: number;
  label: string;
}

export interface AnomalyFlag {
  id: string;
  type: string;
  severity: "low" | "medium" | "high";
  description: string;
  entities_involved: string[];
  evidence: Record<string, any>;
  detected_at: string;
}

export interface DashboardSummary {
  total_entities: number;
  total_relations: number;
  total_persons: number;
  total_cases: number;
  top_influencers: InfluencerScore[];
  community_count: number;
  open_anomalies: number;
  recent_anomalies: AnomalyFlag[];
}

export interface PathResult {
  source: string;
  target: string;
  found: boolean;
  hops: number;
  path: { entity: Entity; via_relation: Relation | null }[];
  all_paths_count: number;
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  target: string | null;
  details: Record<string, any>;
}
