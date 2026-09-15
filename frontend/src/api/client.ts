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

// --- KNOT6 Phase 1: Investigations / Cases / Evidence ----------------------

export interface Investigation {
  id: string;
  name: string;
  description: string;
  status: "ACTIVE" | "ARCHIVED" | "CLOSED";
  // True only for the bundled "Operation Nexus" demo investigation --
  // new intelligence uploads into it are refused server-side (409), see
  // backend/app/services/evidence_processing.py::ensure_not_demo_protected.
  is_demo_seed: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
  case_count: number;
}

export interface Case {
  id: string;
  investigation_id: string;
  case_number: string;
  title: string;
  description: string;
  status: "OPEN" | "UNDER_REVIEW" | "CLOSED" | "ARCHIVED";
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  created_by: string;
  created_at: string;
  updated_at: string;
  evidence_count: number;
}

export interface EvidenceItem {
  id: string;
  investigation_id: string;
  case_id: string;
  filename: string;
  original_filename: string;
  source_type: string;
  mime_type: string;
  file_size: number;
  uploaded_by: string;
  uploaded_at: string;
  processing_status: "UPLOADED" | "PROCESSING" | "PROCESSED" | "FAILED";
  description: string;
  processing_summary: Record<string, any>;
  sha256_hash: string;
}

// --- KNOT6 Phase 4: Evidence Integrity + tamper-evident audit chain -------

export interface EvidenceIntegrityVerify {
  evidence_id: string;
  status: "VALID" | "INTEGRITY_VIOLATION" | "UNAVAILABLE";
  stored_hash: string;
  computed_hash: string | null;
  checked_at: string;
  message: string;
}

export interface AuditChainVerify {
  status: "VALID" | "INTEGRITY_VIOLATION" | "EMPTY";
  entries_checked: number;
  first_broken_entry_id: string | null;
  first_broken_seq: number | null;
  message: string;
  checked_at: string;
}

// --- Entity resolution: candidate review, wired to entity_resolution_decisions

export interface ResolutionCandidate {
  keep_id: string;
  merge_id: string;
  keep_label: string;
  merge_label: string;
  confidence: number;
  matching_reasons: string[];
  source_references: Record<string, string[]>;
  decision_status: "AUTO_MERGE_ELIGIBLE" | "REVIEW_REQUIRED";
}

export interface ResolutionDecision {
  id: string;
  investigation_id: string;
  keep_id: string;
  merge_id: string;
  decision: "APPROVED" | "REJECTED";
  reason: string;
  decided_by: string;
  decided_at: string;
}

// --- Case Intelligence: deterministic summary, search, copilot ------------

export interface KeyEntity {
  entity: Entity;
  connections: number;
  relevance_label: string;
  relevance_score: number;
}

export interface KeyRelationship {
  source: Entity;
  target: Entity;
  type: string;
  description: string;
  evidence: string[];
}

export interface RecentDevelopment {
  id: string;
  kind: string;
  description: string;
  timestamp: string;
  target: string | null;
}

export interface OpenSignal {
  id: string;
  type: string;
  severity: "low" | "medium" | "high";
  description: string;
  entities_involved: string[];
  primary_entity_id: string | null;
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  kind: "CALL" | "TRANSACTION" | "PRESENCE" | "EVIDENCE_UPLOADED" | "CASE_EVENT" | "OTHER";
  title: string;
  description: string;
  entities_involved: string[];
  relationship_ids: string[];
  evidence: string[];
  source: string;
  metadata: Record<string, any>;
}

export interface UndatedRelation {
  relationship_id: string;
  type: string | null;
  description: string;
  entities_involved: string[];
  evidence: string[];
}

export interface InvestigationTimeline {
  investigation_id: string;
  events: TimelineEvent[];
  undated_relations: UndatedRelation[];
  total_events: number;
}

// --- Financial Intelligence backend aggregation ---------------------------

export interface FinancialAccount {
  account: Entity;
  holder_entities: Entity[];
  transaction_count: number;
  total_inbound: number;
  total_outbound: number;
  counterparty_count: number;
}

export interface Counterparty {
  account: Entity;
  transaction_count: number;
  total_amount: number;
}

export interface CircularFlow {
  account_ids: string[];
  account_labels: string[];
  description: string;
  evidence: string[];
}

export interface FinancialIntelligence {
  investigation_id: string;
  accounts: FinancialAccount[];
  transaction_count: number;
  total_inbound: number;
  total_outbound: number;
  major_counterparties: Counterparty[];
  transaction_timeline: TimelineEvent[];
  suspicious_patterns: AnomalyFlag[];
  circular_flows: CircularFlow[];
  relevant_evidence: string[];
}

export interface EvidenceSummary {
  total: number;
  processed: number;
  pending: number;
  failed: number;
  integrity_verified: number | null;
  recent: EvidenceItem[];
}

export interface InvestigatorNote {
  id: string;
  author: string;
  text: string;
  created_at: string;
}

export interface InvestigatorNotes {
  available: boolean;
  notes: InvestigatorNote[];
  message: string | null;
}

export interface CaseBrief {
  summary: string;
  total_entities: number;
  total_relations: number;
  cross_domain_entities: number;
  open_signal_count: number;
  domains: string[];
}

export interface IntelligenceSummary {
  investigation_id: string;
  case_brief: CaseBrief;
  key_entities: KeyEntity[];
  key_relationships: KeyRelationship[];
  recent_developments: RecentDevelopment[];
  open_signals: OpenSignal[];
  evidence_summary: EvidenceSummary;
  timeline_summary: TimelineEvent[];
  investigator_notes: InvestigatorNotes;
}

export interface SearchHypothesisHit {
  id: string;
  title: string;
  status: string;
  supporting_count: number;
  contradicting_count: number;
}

export interface SearchResults {
  query: string;
  entities: { entity: Entity; connections: number }[];
  related_entities: Entity[];
  relationships: { relationship: KeyRelationship }[];
  evidence: { evidence: EvidenceItem }[];
  timeline: { event: TimelineEvent }[];
  signals: OpenSignal[];
  conversation: { turn_id: string; question: string; created_at: string }[];
  hypotheses: SearchHypothesisHit[];
}

export interface CopilotCitation {
  evidence_id: string;
  label: string;
}

export interface CopilotAction {
  type: "OPEN_ENTITY" | "OPEN_GRAPH" | "VIEW_EVIDENCE" | "VIEW_TIMELINE" | "SHOW_PATH"
      | "OPEN_HYPOTHESIS" | "OPEN_FINANCIAL" | "OPEN_GEO";
  label: string;
  entity_id: string | null;
  target_entity_id: string | null;
  evidence_id: string | null;
  hypothesis_id?: string | null;
}

export interface CopilotResponse {
  available: boolean;
  answer: string;
  citations: CopilotCitation[];
  actions: CopilotAction[];
  context_entity_ids: string[];
  turn_id: string | null;
  mode: "llm" | "deterministic";
}

export interface ConversationTurn {
  id: string;
  investigation_id: string;
  username: string;
  question: string;
  answer: string;
  citations: CopilotCitation[];
  actions: CopilotAction[];
  created_at: string;
  mode: "llm" | "deterministic";
}

// --- KNOT6 Case Intelligence 2.0: investigation activity / resume --------

export interface ActivityIn {
  activity_type: string;
  target_type?: string | null;
  target_id?: string | null;
  target_label?: string | null;
  extra?: Record<string, any>;
}

export interface ResumePoint {
  available: boolean;
  description: string;
  activity_type: string | null;
  timestamp: string | null;
  action: CopilotAction | null;
}

// --- Hypothesis Lab persistence -------------------------------------------

export type HypothesisStatus = "OPEN" | "UNDER_REVIEW" | "SUPPORTED" | "CONTRADICTED" | "INCONCLUSIVE";

export interface HypothesisSummary {
  id: string;
  investigation_id: string;
  case_id: string | null;
  title: string;
  description: string;
  status: HypothesisStatus;
  subject_entity_id: string | null;
  target_entity_id: string | null;
  related_entity_ids: string[];
  supporting_count: number;
  contradicting_count: number;
  note_count: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface HypothesisNote {
  id: string;
  author: string;
  text: string;
  created_at: string;
}

export interface HypothesisEvidenceLink {
  id: string;
  hypothesis_id: string;
  evidence_id: string;
  relationship_type: "SUPPORTING" | "CONTRADICTING";
  note: string;
  created_by: string;
  created_at: string;
  evidence: EvidenceItem | null;
}

export interface HypothesisAnalyticalContext {
  subject_entity: Entity | null;
  target_entity: Entity | null;
  subject_influencer: InfluencerScore | null;
  target_influencer: InfluencerScore | null;
  same_community: boolean | null;
  path: PathResult | null;
  relevant_signals: AnomalyFlag[];
  relevant_timeline: TimelineEvent[];
}

export interface HypothesisDetail extends HypothesisSummary {
  notes: HypothesisNote[];
  supporting_evidence: HypothesisEvidenceLink[];
  contradicting_evidence: HypothesisEvidenceLink[];
  related_entities: Entity[];
  analytical_context: HypothesisAnalyticalContext;
  assessment: string;
}
