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
  fetchHealth: vi.fn(() =>
    Promise.resolve({
      status: "healthy",
      components: { llm: "configured" },
    }),
  ),
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
    vi.mocked(fetchNeighbors).mockImplementation((entityId: string) => {
      if (entityId === "entity:first") return first.promise;
      if (entityId === "entity:second") return second.promise;
      throw new Error(`意外的实体请求: ${entityId}`);
    });
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
    const requestOptions = vi.mocked(fetchNeighbors).mock.calls[0]?.[2];

    fireEvent.click(screen.getByRole("button", { name: "Lazarus" }));

    await waitFor(() => expect(entityMetric().textContent).toContain("3"));
    expect(requestOptions?.signal?.aborted).toBe(true);
    expect((screen.getByRole("textbox", { name: "搜索实体" }) as HTMLInputElement).value).toBe("");
  });

  it("使用纯图标按钮进入和退出图谱全屏", async () => {
    let fullscreenElement: Element | null = null;
    const requestFullscreen = vi.fn(function (this: HTMLElement) {
      fullscreenElement = this;
      document.dispatchEvent(new Event("fullscreenchange"));
      return Promise.resolve();
    });
    const exitFullscreen = vi.fn(() => {
      fullscreenElement = null;
      document.dispatchEvent(new Event("fullscreenchange"));
      return Promise.resolve();
    });
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      get: () => fullscreenElement,
    });
    Object.defineProperty(HTMLElement.prototype, "requestFullscreen", {
      configurable: true,
      value: requestFullscreen,
    });
    Object.defineProperty(document, "exitFullscreen", {
      configurable: true,
      value: exitFullscreen,
    });

    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    const enterButton = screen.getByRole("button", { name: "全屏显示图谱" });
    expect(enterButton.textContent).toBe("");

    fireEvent.click(enterButton);
    await waitFor(() => expect(requestFullscreen).toHaveBeenCalledTimes(1));
    expect(requestFullscreen.mock.instances[0]).toBe(enterButton.closest(".graph-panel"));

    const exitButton = screen.getByRole("button", { name: "退出图谱全屏" });
    fireEvent.click(exitButton);
    await waitFor(() => expect(exitFullscreen).toHaveBeenCalledTimes(1));
  });

  it("图谱标题栏不显示冗余加载状态", async () => {
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    expect(screen.queryByText(/^(加载中|已加载)$/)).toBeNull();
  });
});
