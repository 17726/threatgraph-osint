import type {
  ApiResponse,
  GraphEdge,
  GraphNode,
  GraphPayload,
  ReportPayload,
  EntityDetail,
} from "../types";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

type PathResult = { nodes: GraphNode[]; edges: GraphEdge[] };

type PathApiPayload =
  | PathResult
  | {
      paths?: Array<PathResult>;
    };

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

export function fetchGraph(target: string): Promise<GraphPayload> {
  const url = `/graph?target=${encodeURIComponent(target)}&depth=2`;

  return getJson<GraphPayload>(url);
}

export function fetchReport(target: string): Promise<ReportPayload> {
  const url = `/reports/${encodeURIComponent(target)}`;

  return getJson<ReportPayload>(url);
}

export function generateReport(target: string): Promise<ReportPayload> {
  const url = `/reports/${encodeURIComponent(target)}/generate`;

  return fetch(`${API_BASE_URL}${url}`, { method: "POST" }).then((response) => {
    if (!response.ok) {
      throw new Error(`报告生成失败：${response.status}`);
    }
    return response
      .json()
      .then((payload: ApiResponse<ReportPayload>) => payload.data);
  });
}

export async function fetchPath(
  source: string,
  target: string,
): Promise<PathResult> {
  const url = `/graph/path?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`;
  try {
    const payload = await getJson<PathApiPayload>(url);
    if ("nodes" in payload && "edges" in payload) return payload;
    return payload.paths?.[0] ?? { nodes: [], edges: [] };
  } catch {
    return { nodes: [], edges: [] };
  }
}

export async function fetchAnalysis<T = unknown>(
  target: string,
  type: "behavior" | "mitre" | "inferences" | "threat-assessment",
): Promise<T> {
  return getJson<T>("/analysis/" + encodeURIComponent(target) + "/" + type);
}

export function fetchEntitySearch(query: string): Promise<GraphNode[]> {
  return getJson<GraphNode[]>(
    `/entities/search?q=${encodeURIComponent(query)}`,
  );
}

export function fetchEntity(id: string): Promise<EntityDetail> {
  return getJson<EntityDetail>(`/entities/${encodeURIComponent(id)}`);
}

export interface PipelineResult {
  doc_id: string;
  run_id: string;
  chunks: number;
  extracted_entities: number;
  extracted_relations: number;
  canonical_entities: number;
  canonical_relations: number;
  evidence: number;
  behavior_patterns: number;
}

export async function runPipeline(document: File): Promise<PipelineResult> {
  const formData = new FormData();
  formData.append("document", document);

  const response = await fetch(`${API_BASE_URL}/pipeline/run`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`Pipeline 运行失败: ${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<PipelineResult>;
  return payload.data;
}
