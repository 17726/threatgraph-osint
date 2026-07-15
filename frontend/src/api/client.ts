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
  current_step?: string | null;
  failed_step?: string | null;
  error?: string | null;
  result?: Record<string, unknown> | null;
}

interface PipelineRunOptions {
  maxWaitMs?: number;
  intervalMs?: number;
}

async function pollPipelineStatus(
  jobId: string,
  options: PipelineRunOptions = {},
): Promise<PipelineResult> {
  const deadline = Date.now() + (options.maxWaitMs ?? 120_000);
  const intervalMs = options.intervalMs ?? 2000;
  while (Date.now() < deadline) {
    const response = await fetch(`${API_BASE_URL}/pipeline/status/${jobId}`);
    if (!response.ok) {
      throw new Error(`查询 Pipeline 状态失败: ${response.status}`);
    }
    const payload = (await response.json()) as ApiResponse<PipelineStatus>;
    const job = payload.data;
    if (job.status === "succeeded") {
      const result = (job.result ?? {}) as Record<string, unknown>;
      const extract = result.extract as Record<string, unknown> | undefined;
      const summary = (extract?.summary ?? result) as Record<string, unknown>;
      return {
        job_id: job.job_id,
        status: job.status,
        canonical_entities: (summary.canonical_entities ?? 0) as number,
        canonical_relations: (summary.canonical_relations ?? 0) as number,
        evidence: (summary.evidence ?? 0) as number,
        behavior_patterns: (summary.behavior_patterns ?? 0) as number,
        extracted_entities: (summary.extracted_entities ?? 0) as number,
        extracted_relations: (summary.extracted_relations ?? 0) as number,
      };
    }
    if (job.status === "failed") {
      throw new Error(job.error || "Pipeline 运行失败");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Pipeline 执行超时");
}

export async function runPipeline(
  document: File,
  options: PipelineRunOptions = {},
): Promise<PipelineResult> {
  const documentPayload = JSON.parse(await document.text()) as Record<
    string,
    unknown
  >;

  const response = await fetch(`${API_BASE_URL}/documents/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(documentPayload),
  });
  if (!response.ok) {
    throw new Error(`Pipeline 运行失败: ${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<{
    doc_id: string;
    job_id?: string;
    status: string;
  }>;
  if (!payload.data.job_id) {
    return { job_id: "", status: "skipped" };
  }
  return pollPipelineStatus(payload.data.job_id, options);
}
