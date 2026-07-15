import type {
  ApiResponse,
  GraphEdge,
  GraphNode,
  GraphPayload,
  ReportPayload,
  EntityDetail,
} from "../types";
import { getMockGraph, getMockReport } from "../data/mockPayload";

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

type GraphFilters = {
  target?: string;
  entity_types?: string[];
  entity_ids?: string[];
  relation_types?: string[];
  tags?: string[];
  source_types?: string[];
  languages?: string[];
  first_seen_from?: string;
  last_seen_to?: string;
  min_confidence?: number;
  depth?: number;
  limit?: number;
};

export function buildGraphQuery(
  target: string,
  techniqueFilter = "",
  regionFilter = "",
): { target: string; filters: GraphFilters } {
  const entity_ids = [techniqueFilter, regionFilter].filter(Boolean);
  return {
    target,
    filters: entity_ids.length ? { entity_ids } : {},
  };
}

export function fetchGraph(target: string, filters: GraphFilters = {}): Promise<GraphPayload> {
  const params = new URLSearchParams({ target: filters.target ?? target, depth: String(filters.depth ?? 0) });
  for (const key of ["entity_types", "entity_ids", "relation_types", "tags", "source_types", "languages"] as const) {
    const values = filters[key];
    if (values?.length) params.set(key, values.join(","));
  }
  for (const key of ["first_seen_from", "last_seen_to"] as const) {
    const value = filters[key];
    if (value) params.set(key, value);
  }
  for (const key of ["min_confidence", "limit"] as const) {
    const value = filters[key];
    if (value !== undefined) params.set(key, String(value));
  }

  return getJson<GraphPayload>(`/graph?${params.toString()}`).catch((error: unknown) => {
    const hasFilters = Object.entries(filters).some(([key, value]) => key !== "depth" && value !== undefined);
    if (target === "APT28" && !hasFilters) {
      return getMockGraph(target);
    }
    throw error;
  });
}

export function fetchReport(target: string): Promise<ReportPayload> {
  const url = `/reports/${encodeURIComponent(target)}`;

  return getJson<ReportPayload>(url).catch(() => getMockReport(target));
}

export function generateReport(target: string): Promise<ReportPayload> {
  const url = `/reports/${encodeURIComponent(target)}/generate`;

  return fetch(`${API_BASE_URL}${url}`, { method: "POST" }).then(
    (response) => {
      if (!response.ok) {
        throw new Error(`报告生成失败：${response.status}`);
      }
      return response.json().then((payload: ApiResponse<ReportPayload>) => payload.data);
    },
  );
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


export function fetchNeighbors(entity: string): Promise<GraphPayload> {
  return fetchGraph(entity, { depth: 1 });
}

export function fetchEntitySearch(query: string): Promise<GraphNode[]> {
  return getJson<GraphNode[]>(`/entities/search?q=${encodeURIComponent(query)}`);
}


export function fetchEntity(id: string): Promise<EntityDetail> {
  return getJson<EntityDetail>(`/entities/${encodeURIComponent(id)}`);
}

export interface PipelineResult {
  job_id: string;
  status: string;
  doc_id?: string;
  run_id?: string;
  chunks?: number;
  extracted_entities?: number;
  extracted_relations?: number;
  canonical_entities?: number;
  canonical_relations?: number;
  evidence?: number;
  behavior_patterns?: number;
}

export interface PipelineStatus {
  job_id: string;
  status: string;
  doc_id?: string;
  target_group?: string;
  steps?: string[];
  current_step?: string | null;
  failed_step?: string | null;
  error?: string | null;
  result?: Record<string, unknown> | null;
  started_at?: string;
  finished_at?: string;
}

async function pollPipelineStatus(
  jobId: string,
  maxWaitMs = 120_000,
  intervalMs = 2000,
): Promise<PipelineResult> {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${API_BASE_URL}/pipeline/status/${jobId}`);
    if (!res.ok) {
      throw new Error(`查询 Pipeline 状态失败: ${res.status}`);
    }
    const body = (await res.json()) as ApiResponse<PipelineStatus>;
    const job = body.data;
    if (job.status === "succeeded") {
      // 从 result 中提取 extract 步骤的 summary 字段
      const stepResults = (job.result ?? {}) as Record<string, unknown>;
      const extractResult = stepResults["extract"] as Record<string, unknown> | undefined;
      const summary = extractResult?.summary as Record<string, unknown> | undefined;
      return {
        job_id: job.job_id,
        status: job.status,
        canonical_entities: (summary?.canonical_entities ?? 0) as number,
        canonical_relations: (summary?.canonical_relations ?? 0) as number,
        evidence: (summary?.evidence ?? 0) as number,
        behavior_patterns: (summary?.behavior_patterns ?? 0) as number,
        extracted_entities: (summary?.extracted_entities ?? 0) as number,
        extracted_relations: (summary?.extracted_relations ?? 0) as number,
      };
    }
    if (job.status === "failed") {
      throw new Error(job.error || "Pipeline 运行失败");
    }
    // pending / running → 继续轮询
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("Pipeline 执行超时");
}

export async function runPipeline(
  document: File,
): Promise<PipelineResult> {
  const payload = JSON.parse(await document.text()) as Record<string, unknown>;
  const response = await fetch(`${API_BASE_URL}/documents/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Pipeline 运行失败: ${response.status}`);
  }
  const result = (await response.json()) as ApiResponse<{ job_id?: string } & Record<string, unknown>>;
  const jobId = result.data?.job_id;
  if (!jobId) {
    // 重复导入，没有创建新任务
    return { job_id: "", status: "skipped" };
  }
  return pollPipelineStatus(jobId);
}
