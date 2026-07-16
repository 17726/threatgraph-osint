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
  status: "pending" | "running" | "succeeded" | "failed";
  items_found: number;
  items_promoted: number;
  items_imported: number;
  items_skipped: number;
  items_failed: number;
  document_ids: string[];
  workspace_cleaned: boolean;
  error_message: string | null;
};

async function parseResponse<T>(response: Response, message: string): Promise<T> {
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
  const response = await fetch(`${API_BASE_URL}/crawl/runs/${encodeURIComponent(runId)}`, {
    signal: options.signal,
  });
  return parseResponse<CrawlRunStats>(response, "查询采集任务失败");
}
