// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchEntitySearch, fetchGraph, fetchNeighbors, fetchReport } from "./api/client";
import { App } from "./App";
import type { GraphNode, GraphPayload, ReportPayload } from "./types";

const forceGraphMocks = vi.hoisted(() => ({
  cameraPosition: vi.fn(),
  zoomToFit: vi.fn(),
}));

vi.mock("echarts-for-react", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  return {
    default: function MockECharts({ option, onChartReady }: { option: any; onChartReady?: any }) {
      const clickHandlerRef = React.useRef<((params: any) => void) | null>(null);
      React.useEffect(() => {
        onChartReady?.({
          on: (event: string, handler: (params: any) => void) => {
            if (event === "click") clickHandlerRef.current = handler;
          },
          resize: vi.fn(),
        });
      }, [onChartReady]);
      const firstNode = option?.series?.[0]?.data?.[0];
      return (
        <div data-testid="graph-canvas">
          <button
            type="button"
            onClick={() =>
              clickHandlerRef.current?.({ dataType: "node", data: { _raw: firstNode?._raw } })
            }
          >
            模拟选择 2D 节点
          </button>
        </div>
      );
    },
  };
});

vi.mock("react-force-graph-3d", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  return {
    default: React.forwardRef(function MockForceGraph(
      props: {
        graphData: { nodes: unknown[]; links: unknown[] };
        onNodeClick: (node: unknown) => void;
        onLinkClick: (link: unknown) => void;
        onBackgroundClick?: () => void;
        onEngineStop?: () => void;
        backgroundColor?: string;
        nodeRelSize?: number;
      },
      ref,
    ) {
      React.useImperativeHandle(ref, () => ({
        cameraPosition: forceGraphMocks.cameraPosition,
        zoomToFit: forceGraphMocks.zoomToFit,
      }));
      return (
        <div
          data-testid="graph-3d-canvas"
          data-background-color={props.backgroundColor}
          data-node-rel-size={props.nodeRelSize}
          data-first-node-color={(props.graphData.nodes[0] as { color?: string })?.color}
          data-second-node-color={(props.graphData.nodes[1] as { color?: string })?.color}
          data-first-link-color={(props.graphData.links[0] as { color?: string })?.color}
          data-first-link-width={(props.graphData.links[0] as { width?: number })?.width}
        >
          <button type="button" onClick={() => props.onNodeClick(props.graphData.nodes[0])}>
            模拟选择 3D 节点
          </button>
          <button type="button" onClick={() => props.onLinkClick(props.graphData.links[0])}>
            模拟选择 3D 关系
          </button>
          <button type="button" onClick={() => props.onEngineStop?.()}>
            模拟 3D 布局完成
          </button>
          <button type="button" onClick={() => props.onBackgroundClick?.()}>
            模拟点击 3D 空白
          </button>
        </div>
      );
    }),
  };
});

vi.mock("./components/NodeDetail", () => ({
  default: ({ entityId }: { entityId: string | null }) => (
    <div data-testid="node-detail">{entityId}</div>
  ),
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

const node = (id: string, type = "MALWARE"): GraphNode => ({
  id,
  name: id,
  type,
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
  nodes: ids.map((id) => node(id)),
  edges: [],
  evidence: [],
});

const graphWithRelation = (): GraphPayload => ({
  ...graph("apt_group:apt28", "malware:x-agent"),
  edges: [
    {
      id: "rel:apt28:uses:x-agent",
      source: "apt_group:apt28",
      target: "malware:x-agent",
      type: "USES",
      label: "使用",
      confidence: 0.91,
      source_count: 1,
      evidence_count: 0,
      first_seen: null,
      last_seen: null,
      validation_status: "valid",
      evidence_ids: [],
    },
  ],
});

const graphWithTypes = (): GraphPayload => ({
  ...graph("apt_group:apt28", "malware:x-agent", "country:ukraine"),
  nodes: [
    node("apt_group:apt28", "APT_GROUP"),
    node("malware:x-agent", "MALWARE"),
    node("country:ukraine", "COUNTRY"),
  ],
  edges: [
    {
      id: "rel:apt28:uses:x-agent",
      source: "apt_group:apt28",
      target: "malware:x-agent",
      type: "USES",
      label: "使用",
      confidence: 0.91,
      source_count: 1,
      evidence_count: 0,
      first_seen: null,
      last_seen: null,
      validation_status: "valid",
      evidence_ids: [],
    },
  ],
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

  it("默认显示 2D 图谱并支持切换 3D 后再切回", async () => {
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    const twoDimensionalButton = screen.getByRole("button", { name: "2D 视图" });
    const threeDimensionalButton = screen.getByRole("button", { name: "3D 视图" });

    expect(twoDimensionalButton.getAttribute("aria-pressed")).toBe("true");
    expect(threeDimensionalButton.getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByTestId("graph-canvas")).toBeTruthy();

    fireEvent.click(threeDimensionalButton);
    expect(threeDimensionalButton.getAttribute("aria-pressed")).toBe("true");
    const graph3DCanvas = await screen.findByTestId("graph-3d-canvas");
    expect(graph3DCanvas.getAttribute("data-background-color")).toBe("#ffffff");
    expect(graph3DCanvas.getAttribute("data-node-rel-size")).toBe("3.5");
    expect(screen.getByRole("button", { name: "模拟选择 3D 节点" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "模拟 3D 布局完成" }));
    expect(forceGraphMocks.cameraPosition).toHaveBeenCalledWith(
      { x: 0, y: 0, z: 360 },
      { x: 0, y: 0, z: 0 },
      600,
    );
    fireEvent.click(twoDimensionalButton);
    expect(twoDimensionalButton.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("graph-canvas")).toBeTruthy();
  });

  it("在 3D 视图选择节点时复用实体详情", async () => {
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    fireEvent.click(screen.getByRole("button", { name: "3D 视图" }));
    fireEvent.click(await screen.findByRole("button", { name: "模拟选择 3D 节点" }));

    expect(screen.getByTestId("node-detail").textContent).toBe("base-1");
  });

  it("在全屏 3D 视图选择关系时高亮关系并显示可见详情", async () => {
    let fullscreenElement: Element | null = null;
    const requestFullscreen = vi.fn(function (this: HTMLElement) {
      fullscreenElement = this;
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
    vi.mocked(fetchGraph).mockResolvedValue(graphWithRelation());
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("2"));

    fireEvent.click(screen.getByRole("button", { name: "全屏显示图谱" }));
    await waitFor(() => expect(requestFullscreen).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "3D 视图" }));
    fireEvent.click(await screen.findByRole("button", { name: "模拟选择 3D 关系" }));

    const graph3DCanvas = screen.getByTestId("graph-3d-canvas");
    expect(graph3DCanvas.getAttribute("data-first-link-color")).toBe("#f59e0b");
    expect(graph3DCanvas.getAttribute("data-first-link-width")).toBe("4");
    expect(screen.getByTestId("graph-edge-detail-fullscreen")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "关系详情" })).toBeTruthy();
    expect(screen.getByText("使用")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "模拟点击 3D 空白" }));
    expect(screen.queryByTestId("graph-edge-detail-fullscreen")).toBeNull();
    expect(screen.getByTestId("graph-3d-canvas").getAttribute("data-first-link-color")).toBe(
      "#94a3b8",
    );
  });

  it("2D 和 3D 共用类型标签筛选并可通过全部一次清除", async () => {
    vi.mocked(fetchGraph).mockResolvedValue(graphWithTypes());
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    const allTypesButton = screen.getByRole("button", { name: "显示全部类型" });
    const aptGroupButton = screen.getByRole("button", { name: "筛选类型 APT_GROUP" });
    expect(allTypesButton.getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(aptGroupButton);
    expect(aptGroupButton.getAttribute("aria-pressed")).toBe("true");
    expect(entityMetric().textContent).toContain("2");

    fireEvent.click(screen.getByRole("button", { name: "3D 视图" }));
    expect(screen.getByRole("button", { name: "筛选类型 APT_GROUP" })).toBeTruthy();
    expect(entityMetric().textContent).toContain("2");

    fireEvent.click(allTypesButton);
    expect(allTypesButton.getAttribute("aria-pressed")).toBe("true");
    expect(entityMetric().textContent).toContain("3");
  });

  it("点击 3D 节点后聚焦主体并可通过空白画布清除", async () => {
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    fireEvent.click(screen.getByRole("button", { name: "3D 视图" }));
    let graph3DCanvas = await screen.findByTestId("graph-3d-canvas");
    expect(graph3DCanvas.getAttribute("data-first-node-color")).toBe("#be123c");

    fireEvent.click(screen.getByRole("button", { name: "模拟选择 3D 节点" }));
    await waitFor(() => {
      graph3DCanvas = screen.getByTestId("graph-3d-canvas");
      expect(graph3DCanvas.getAttribute("data-first-node-color")).toBe("#f59e0b");
      expect(graph3DCanvas.getAttribute("data-second-node-color")).toBe("#cbd5e1");
    });

    fireEvent.click(screen.getByRole("button", { name: "模拟点击 3D 空白" }));
    await waitFor(() =>
      expect(screen.getByTestId("graph-3d-canvas").getAttribute("data-first-node-color")).toBe(
        "#be123c",
      ),
    );
  });

  it("2D 节点选择不会在切换 3D 时自动触发聚焦", async () => {
    render(<App />);
    await waitFor(() => expect(entityMetric().textContent).toContain("3"));

    fireEvent.click(screen.getByRole("button", { name: "模拟选择 2D 节点" }));
    fireEvent.click(screen.getByRole("button", { name: "3D 视图" }));

    expect(
      (await screen.findByTestId("graph-3d-canvas")).getAttribute("data-first-node-color"),
    ).toBe("#be123c");
  });
});
