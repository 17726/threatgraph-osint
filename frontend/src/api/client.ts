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
  const url = `/graph?target=${encodeURIComponent(target)}&depth=2`;
  
  if (import.meta.env.DEV) {
    return getJson<GraphPayload>(url).catch(() => getMockGraph(target));
  }
  
  return getJson<GraphPayload>(url);
}

export function fetchReport(target: string): Promise<ReportPayload> {
  const url = `/reports/${encodeURIComponent(target)}`;
  
  if (import.meta.env.DEV) {
    return getJson<ReportPayload>(url).catch(() => getMockReport(target));
  }
  
  return getJson<ReportPayload>(url);
}

export function fetchPath(source: string, target: string): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  const url = `/graph/path?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`;
  
  if (import.meta.env.DEV) {
    return getJson<{ nodes: GraphNode[]; edges: GraphEdge[] }>(url)
      .catch(() => ({ nodes: [], edges: [] }));
  }
  
  return getJson<{ nodes: GraphNode[]; edges: GraphEdge[] }>(url);
}