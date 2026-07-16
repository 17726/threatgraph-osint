import type {
  ApiResponse,
  GraphEdge,
  GraphNode,
  GraphPayload,
  ReportPayload,
  EntityDetail,
} from "../types";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export type HealthPayload = {
  status: string;
  components: { llm: string };
};

type PathResult = { nodes: GraphNode[]; edges: GraphEdge[] };

type PathApiPayload =
  | PathResult
  | {
      paths?: Array<PathResult>;
    };

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

export function fetchGraph(target: string): Promise<GraphPayload> {
  const url = `/graph?target=${encodeURIComponent(target)}`;

  return getJson<GraphPayload>(url);
}

export function fetchHealth(): Promise<HealthPayload> {
  return getJson<HealthPayload>("/health");
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
    return response.json().then((payload: ApiResponse<ReportPayload>) => payload.data);
  });
}

export async function fetchPath(source: string, target: string): Promise<PathResult> {
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

export function fetchNeighbors(
  entityId: string,
  options: { signal?: AbortSignal } = {},
): Promise<GraphPayload> {
  return getJson<GraphPayload>(`/graph/neighbors?entity_id=${encodeURIComponent(entityId)}`, {
    signal: options.signal,
  });
}

export function fetchEntitySearch(query: string): Promise<GraphNode[]> {
  return getJson<GraphNode[]>(`/entities/search?q=${encodeURIComponent(query)}`);
}

export function fetchEntity(id: string): Promise<EntityDetail> {
  return getJson<EntityDetail>(`/entities/${encodeURIComponent(id)}`);
}

export interface PipelineResult {
  job_id?: string;
  status?: string;
  doc_id?: string;
  run_id?: string;
  chunks?: number;
  extracted_entities?: number;
  extracted_relations?: number;
  canonical_entities?: number;
  canonical_relations?: number;
  evidence?: number;
  behavior_patterns?: number;
  skipped?: boolean;
  summaries?: Array<{
    extracted_entities: number;
    extracted_relations: number;
    canonical_entities: number;
    canonical_relations: number;
    evidence: number;
  }>;
}

export type ExtractionMode = "reviewed" | "live";

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

export interface PipelineRunOptions {
  maxWaitMs?: number;
  intervalMs?: number;
  extractionMode?: ExtractionMode;
  signal?: AbortSignal;
  onStatus?: (status: "importing" | "pending" | "running") => void;
}

type ApiErrorPayload = {
  success: false;
  error?: {
    code?: string;
    message?: string;
  };
};

async function responseData<T>(response: Response, fallbackMessage: string): Promise<T> {
  let payload: ApiResponse<T> | ApiErrorPayload | null = null;
  try {
    payload = (await response.json()) as ApiResponse<T> | ApiErrorPayload;
  } catch {
    // 非 JSON 错误仍使用包含状态码的兜底消息。
  }
  if (!response.ok || !payload || payload.success !== true) {
    const message = payload && "error" in payload ? payload.error?.message : undefined;
    throw new Error(message || `${fallbackMessage}: ${response.status}`);
  }
  return payload.data;
}

function abortError(): DOMException {
  return new DOMException("操作已取消", "AbortError");
}

function abortableDelay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      signal?.removeEventListener("abort", handleAbort);
      resolve();
    }, milliseconds);
    const handleAbort = () => {
      clearTimeout(timeout);
      reject(abortError());
    };
    signal?.addEventListener("abort", handleAbort, { once: true });
  });
}

function pipelineSummary(result: Record<string, unknown>): Record<string, unknown> {
  const summaries = result.summaries;
  if (Array.isArray(summaries) && summaries.length > 0) {
    return summaries[0] as Record<string, unknown>;
  }
  const extract = result.extract as Record<string, unknown> | undefined;
  return (extract?.summary ?? result) as Record<string, unknown>;
}

async function pollPipelineStatus(
  jobId: string,
  options: PipelineRunOptions = {},
): Promise<PipelineResult> {
  const deadline = Date.now() + (options.maxWaitMs ?? 120_000);
  const intervalMs = options.intervalMs ?? 2000;
  while (Date.now() < deadline) {
    if (options.signal?.aborted) throw abortError();
    const response = await fetch(`${API_BASE_URL}/pipeline/status/${jobId}`, {
      signal: options.signal,
    });
    const job = await responseData<PipelineStatus>(response, "查询 Pipeline 状态失败");
    if (job.status === "succeeded") {
      const result = (job.result ?? {}) as Record<string, unknown>;
      const summary = pipelineSummary(result);
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
    options.onStatus?.(job.status === "running" ? "running" : "pending");
    await abortableDelay(intervalMs, options.signal);
  }
  throw new Error("Pipeline 执行超时");
}

export async function runPipeline(
  document: File,
  options: PipelineRunOptions = {},
): Promise<PipelineResult> {
  let documentPayload: Record<string, unknown>;
  try {
    documentPayload = JSON.parse(await document.text()) as Record<string, unknown>;
  } catch {
    throw new Error("文档不是有效的 JSON");
  }

  options.onStatus?.("importing");
  const importResponse = await fetch(`${API_BASE_URL}/documents/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(documentPayload),
    signal: options.signal,
  });
  const imported = await responseData<{
    doc_id: string;
    status: string;
  }>(importResponse, "文档导入失败");

  const pipelineResponse = await fetch(`${API_BASE_URL}/pipeline/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doc_id: imported.doc_id,
      extraction_mode: options.extractionMode ?? "reviewed",
    }),
    signal: options.signal,
  });
  const job = await responseData<PipelineStatus>(pipelineResponse, "Pipeline 提交失败");
  options.onStatus?.(job.status === "running" ? "running" : "pending");
  const result = await pollPipelineStatus(job.job_id, options);
  return { ...result, doc_id: imported.doc_id };
}
