import type { ApiResponse } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export type CrawlRunRequest = {
  keyword: string;
  limit: number;
  sources: number;
  filter: boolean;
};

export type CrawlRunStats = {
  crawl_run_id: string;
  keyword: string;
  status: "pending" | "running" | "succeeded" | "partial_success" | "failed";
  items_found: number;
  items_promoted: number;
  items_imported: number;
  items_skipped: number;
  items_failed: number;
  items_pipeline_succeeded: number;
  items_pipeline_failed: number;
  document_ids: string[];
  workspace_cleaned: boolean;
  error_message: string | null;
  artifact_path?: string | null;
  artifact_error?: string | null;
  filter_summary?: {
    total: number;
    kept: number;
    discarded: number;
    errors: number;
    warnings: Array<{ doc_id: string; warning: string }>;
    failed_documents: Array<{
      doc_id: string;
      reason: string;
      message: string;
    }>;
  } | null;
  pipeline?: {
    job_id: string;
    status: "pending" | "running" | "succeeded" | "failed";
    progress?: PipelineProgress;
  } | null;
  events?: CrawlRunEvent[];
  progress?: {
    phase:
      | "pending"
      | "collecting"
      | "validating"
      | "importing"
      | "pipeline"
      | "completed"
      | "partial_success"
      | "failed";
    current: number;
    total: number;
    target: string;
    source: string | null;
    message: string;
    doc_id?: string | null;
    job_id?: string | null;
    percent?: number;
  };
};

export type PipelineProgress = {
  phase: string;
  current: number;
  total: number;
  percent: number;
  message: string;
  doc_id?: string | null;
  updated_at?: string;
};

export type CrawlRunEvent = {
  sequence: number;
  level: "info" | "warning" | "error";
  phase: string;
  message: string;
  doc_id?: string | null;
  source?: string | null;
  job_id?: string | null;
  details?: Record<string, unknown>;
  created_at: string;
};

async function parseResponse<T>(
  response: Response,
  message: string,
): Promise<T> {
  const payload = (await response.json()) as ApiResponse<T> & {
    error?: { message?: string };
  };
  if (!response.ok || payload.success !== true) {
    throw new Error(payload.error?.message ?? `${message}: ${response.status}`);
  }
  return payload.data;
}

export async function createCrawlRun(
  payload: CrawlRunRequest,
  options: { signal?: AbortSignal } = {},
): Promise<CrawlRunStats> {
  const response = await fetch(`${API_BASE_URL}/crawl/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: options.signal,
  });
  return parseResponse<CrawlRunStats>(response, "创建采集任务失败");
}

export async function fetchCrawlRun(
  runId: string,
  options: { signal?: AbortSignal } = {},
): Promise<CrawlRunStats> {
  const response = await fetch(
    `${API_BASE_URL}/crawl/runs/${encodeURIComponent(runId)}`,
    {
      signal: options.signal,
    },
  );
  return parseResponse<CrawlRunStats>(response, "查询采集任务失败");
}
