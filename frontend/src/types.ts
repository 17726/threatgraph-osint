export type ApiResponse<T> = {
  success: boolean;
  data: T;
  timestamp: string;
};

export type GraphNode = {
  id: string;
  name: string;
  type: string;
  aliases: string[];
  description: string;
  confidence: number;
  source_count: number;
  first_seen: string | null;
  last_seen: string | null;
  tags: string[];
  evidence_ids: string[];
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
  confidence: number;
  source_count: number;
  evidence_count: number;
  first_seen: string | null;
  last_seen: string | null;
  validation_status: "valid" | "invalid";
  evidence_ids: string[];
};

export type Evidence = {
  id: string;
  doc_id: string;
  chunk_id: string | null;
  entity_id: string | null;
  relation_id: string | null;
  text: string;
  evidence_type: "direct_quote" | "summary" | "inference_support";
  quote_start: number | null;
  quote_end: number | null;
  source_url: string;
  source_type: string;
  source_name: string;
  published_at: string | null;
  retrieved_at: string | null;
  source_reliability: string;
  language: "zh" | "en";
};

export type GraphPayload = {
  schema_version: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  evidence: Evidence[];
};

export type ReportPayload = {
  target_group: string;
  title: string;
  markdown: string;
  generated_at?: string;
  sections?: ReportSection[];
};

export type ReportSection = {
  section_id: string;
  section_type: string;
  title: string;
  markdown: string;
  evidence_ids: string[];
  analysis_refs: string[];
  graph_refs: Record<string, unknown>;
  sort_order: number;
};

export type MitreMapping = {
  mapping_id: string;
  target_group: string;
  technique_id: string;
  technique_name: string;
  tactic: string;
  attack_stage: string;
  confidence: number;
  evidence_ids: string[];
};

export type BehaviorPattern = {
  pattern_id: string;
  target_group: string;
  stage: string;
  description: string;
  technique_ids: string[];
  relation_ids: string[];
  evidence_ids: string[];
  confidence: number;
};

export type InferredRelation = {
  inferred_relation_id: string;
  source: string;
  source_name?: string;
  target: string;
  target_name?: string;
  type: string;
  rationale: string;
  confidence: number;
  status: string;
  evidence_ids: string[];
};

export type EntityDetail = GraphNode & {
  evidence_count: number;
  evidence: Evidence[];
  relations: {
    relation_id: string;
    source: string;
    target: string;
    type: string;
    label: string;
  }[];
};

export type AnalysisResponse = {
  target_group: string;
  patterns?: BehaviorPattern[];
  mappings?: MitreMapping[];
  inferences?: InferredRelation[];
};

export type ThreatAssessment = {
  target_group: string;
  risk_level: string;
  risk_score: number;
  rationale: string;
  recommendations: string[];
  evidence_ids: string[];
};
