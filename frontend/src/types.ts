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
  section_type: "profile" | "behavior_patterns" | "network" | "timeline" | "threat_assessment";
  title: string;
  markdown: string;
  evidence_ids: string[];
  analysis_refs: string[];
  graph_refs: {
    node_ids: string[];
    edge_ids: string[];
  };
  sort_order: number;
};
