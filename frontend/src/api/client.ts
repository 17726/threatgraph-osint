import type { ApiResponse, GraphEdge, GraphNode, GraphPayload, ReportPayload } from "../types";
import { getMockGraph, getMockReport } from "../data/mockPayload";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

export function fetchGraph(target: string): Promise<GraphPayload> {
  return getJson<GraphPayload>(`/graph?target=${encodeURIComponent(target)}&depth=2`)
    .catch(() => getMockGraph(target));
}

export function fetchReport(target: string): Promise<ReportPayload> {
  return getJson<ReportPayload>(`/reports/${encodeURIComponent(target)}`)
    .catch(() => getMockReport(target));
}

export function fetchPath(source: string, target: string): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  return getJson<{ nodes: GraphNode[]; edges: GraphEdge[] }>(`/graph/path?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`)
    .catch(() => ({ nodes: [], edges: [] }));
}
