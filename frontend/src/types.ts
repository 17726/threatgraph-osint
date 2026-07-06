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
  evidence_ids: string[];
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
  confidence: number;
  evidence_ids: string[];
};

export type Evidence = {
  id: string;
  doc_id: string;
  chunk_id: string | null;
  entity_id: string | null;
  relation_id: string | null;
  text: string;
  source_url: string;
  language: "zh" | "en";
};

export type GraphPayload = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  evidence: Evidence[];
};

export type ReportPayload = {
  target_group: string;
  title: string;
  markdown: string;
};
