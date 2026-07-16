// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchEntitySearch, fetchGraph, fetchNeighbors, fetchReport } from "./api/client";
import { App } from "./App";
import type { GraphNode, GraphPayload, ReportPayload } from "./types";

vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="graph-canvas" />,
}));

vi.mock("./api/client", () => ({
  fetchEntitySearch: vi.fn(),
  fetchGraph: vi.fn(),
  fetchNeighbors: vi.fn(),
  fetchReport: vi.fn(),
  generateReport: vi.fn(),
  fetchPath: vi.fn(),
  fetchAnalysis: vi.fn(),
  fetchEntity: vi.fn(),
  runPipeline: vi.fn(),
}));

const node = (id: string): GraphNode => ({
  id,
  name: id,
  type: "MALWARE",
  aliases: [],
  description: "",
  confidence: 1,
  source_count: 1,
  first_seen: null,
  last_seen: null,
  tags: [],
  evidence_ids: [],
});

const graph = (...ids: string[]): GraphPayload => ({
  schema_version: "1.0",
  nodes: ids.map(node),
  edges: [],
  evidence: [],
});

const report: ReportPayload = {
  target_group: "APT28",
  title: "APT28",
  markdown: "",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

function entityMetric(): HTMLElement {
  const label = screen.getByText("实体");
  const metric = label.closest(".metric");
  if (!metric) throw new Error("未找到实体指标");
  return metric as HTMLElement;
}

describe("实体一跳筛选", () => {
  beforeEach(() => {
    vi.mocked(fetchGraph).mockResolvedValue(graph("base-1", "base-2", "base-3"));
    vi.mocked(fetchReport).mockResolvedValue(report);
    vi.mocked(fetchEntitySearch).mockResolvedValue([node("entity:first"), node("entity:second")]);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("快速连续选择时只接受最后一次邻居响应", async () => {
    const first = deferred<GraphPayload>();
    const second = deferred<GraphPayload>();
    vi.mocked(fetchNeighbors).mockImplementation((entityId: string) =>
      entityId === "entity:first" ? first.promise : second.promise,
    );
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    const input = screen.getByRole("textbox", { name: "搜索实体" });
    fireEvent.change(input, { target: { value: "entity" } });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 260));
    });
    fireEvent.click(screen.getByRole("button", { name: /entity:first/ }));
    fireEvent.change(input, { target: { value: "entity" } });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 260));
    });
    fireEvent.click(screen.getByRole("button", { name: /entity:second/ }));

    await act(async () => second.resolve(graph("second-only")));
    expect(entityMetric().textContent).toContain("1");

    await act(async () => first.resolve(graph("stale-1", "stale-2")));
    expect(entityMetric().textContent).toContain("1");
  });

  it("清空搜索后恢复当前组织图谱", async () => {
    vi.mocked(fetchNeighbors).mockResolvedValue(graph("neighbor-only"));
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    const input = screen.getByRole("textbox", { name: "搜索实体" });
    fireEvent.change(input, { target: { value: "entity" } });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 260));
    });
    fireEvent.click(screen.getByRole("button", { name: /entity:first/ }));
    await waitFor(() => expect(entityMetric().textContent).toContain("1"));

    fireEvent.change(input, { target: { value: "" } });

    expect(entityMetric().textContent).toContain("3");
  });

  it("切换目标组织时取消一跳请求并清除旧筛选", async () => {
    vi.mocked(fetchNeighbors).mockResolvedValue(graph("neighbor-only"));
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    const input = screen.getByRole("textbox", { name: "搜索实体" });
    fireEvent.change(input, { target: { value: "entity" } });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 260));
    });
    fireEvent.click(screen.getByRole("button", { name: /entity:first/ }));
    await waitFor(() => expect(entityMetric().textContent).toContain("1"));
    const requestOptions = vi.mocked(fetchNeighbors).mock.calls[0]?.[1];

    fireEvent.click(screen.getByRole("button", { name: "Lazarus" }));

    await waitFor(() => expect(entityMetric().textContent).toContain("3"));
    expect(requestOptions?.signal?.aborted).toBe(true);
    expect((screen.getByRole("textbox", { name: "搜索实体" }) as HTMLInputElement).value).toBe("");
  });
});
