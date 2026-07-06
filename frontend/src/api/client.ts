import type { ApiResponse, GraphPayload, ReportPayload } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

export function fetchGraph(target: string): Promise<GraphPayload> {
  return getJson<GraphPayload>(`/graph?target=${encodeURIComponent(target)}&depth=2`);
}

export function fetchReport(target: string): Promise<ReportPayload> {
  return getJson<ReportPayload>(`/reports/${encodeURIComponent(target)}`);
}
