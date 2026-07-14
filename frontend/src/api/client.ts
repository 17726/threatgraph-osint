import type {
  ApiResponse,
  GraphEdge,
  GraphNode,
  GraphPayload,
  ReportPayload,
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

export function generateReport(target: string): Promise<ReportPayload> {
  const url = `/reports/${encodeURIComponent(target)}/generate`;

  if (import.meta.env.DEV) {
    return postJson<ReportPayload>(url).catch(() => getMockReport(target));
  }

  return postJson<ReportPayload>(url);
}

async function postJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

export async function fetchPath(
  source: string,
  target: string,
): Promise<PathResult> {
  const url = `/graph/path?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`;
  const payload = await getJson<PathApiPayload>(url);

  if ("nodes" in payload && "edges" in payload) {
    return payload;
  }

  return payload.paths?.[0] ?? { nodes: [], edges: [] };
}
