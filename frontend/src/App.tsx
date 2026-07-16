import ReactECharts from "echarts-for-react";
import {
  Activity,
  Database,
  FileText,
  Maximize2,
  Minimize2,
  Network,
  RefreshCw,
  ShieldCheck,
  Upload,
  Radar,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  fetchGraph,
  fetchNeighbors,
  fetchReport,
  generateReport,
  fetchHealth,
} from "./api/client";
import { buildGraphOption } from "./graphOptions";
import type {
  Evidence,
  GraphEdge,
  GraphNode,
  GraphPayload,
  ReportPayload,
} from "./types";
import NodeDetail from "./components/NodeDetail";
import SearchBar from "./components/SearchBar";
import TechniqueFilter from "./components/TechniqueFilter";
import RegionFilter from "./components/RegionFilter";
import TimelineBar from "./components/TimelineBar";
import PathTracking from "./components/PathTracking";
import ReportPanel from "./components/ReportPanel";
import AnalysisPage from "./pages/AnalysisPage";
import PipelineModal from "./components/PipelineModal";
import CrawlerModal from "./components/CrawlerModal";

const TARGETS = ["APT28", "Lazarus", "Kimsuky"];

export function App() {
  const [target, setTarget] = useState(TARGETS[0]);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [searchGraph, setSearchGraph] = useState<GraphPayload | null>(null);
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [generating, setGenerating] = useState(false);
  const chartRef = useRef<any>(null);
  const chartInstanceRef = useRef<any>(null);
  const graphPanelRef = useRef<HTMLDivElement>(null);
  const [isGraphFullscreen, setIsGraphFullscreen] = useState(false);
  const [currentYear, setCurrentYear] = useState(2026);
  const [highlightNodeIds, setHighlightNodeIds] = useState<string[]>([]);
  const [searchNodeId, setSearchNodeId] = useState<string | null>(null);
  const [techniqueFilter, setTechniqueFilter] = useState("");
  const [legendFilter, setLegendFilter] = useState<string | null>(null);
  const [regionFilter, setRegionFilter] = useState("");
  const [page, setPage] = useState<"graph" | "analysis">("graph");
  const [pipelineOpen, setPipelineOpen] = useState(false);
  const [graphDepth, setGraphDepth] = useState<number>(2);
  const [graphDepthInput, setGraphDepthInput] = useState<string>("2");
  const [graphDepthError, setGraphDepthError] = useState<string | null>(null);
  const graphRequestRef = useRef<AbortController | null>(null);
  const selectedSearchNodeRef = useRef<string | null>(null);
  const [crawlerOpen, setCrawlerOpen] = useState(false);
  const [llmConfigured, setLlmConfigured] = useState(false);
  const neighborRequestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchHealth()
      .then((health) => setLlmConfigured(health.components.llm === "configured"))
      .catch(() => setLlmConfigured(false));
  }, []);
  const firstSentence = (text: string): string => {
    const match = text.match(/^.*?[。！？.!?]/);
    return match ? match[0] : text;
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsGraphFullscreen(document.fullscreenElement === graphPanelRef.current);
      chartInstanceRef.current?.resize();
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  const handleGraphFullscreen = useCallback(async () => {
    const graphPanel = graphPanelRef.current;
    if (!graphPanel) return;

    try {
      if (document.fullscreenElement === graphPanel) {
        await document.exitFullscreen();
      } else if (graphPanel.requestFullscreen) {
        await graphPanel.requestFullscreen();
      } else {
        setError("当前浏览器不支持全屏展示");
      }
    } catch {
      setError("无法切换图谱全屏，请检查浏览器权限");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    neighborRequestRef.current?.abort();
    neighborRequestRef.current = null;
    graphRequestRef.current?.abort();
    graphRequestRef.current = null;
    selectedSearchNodeRef.current = null;
    setSearchGraph(null);
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    setSearchNodeId(null);
    setRegionFilter("");
    setTechniqueFilter("");
    setLegendFilter(null);
    setGraphDepthError(null);

    const graphController = new AbortController();
    graphRequestRef.current = graphController;
    fetchGraph(target, graphDepth, { signal: graphController.signal })
      .then((graphPayload) => {
        if (cancelled) {
          return;
        }
        setGraph(graphPayload);
        setSelectedEvidence(graphPayload.evidence[0] ?? null);
      })
      .catch((cause: unknown) => {
        if (cancelled) {
          return;
        }
        setError(cause instanceof Error ? cause.message : "请求失败");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    fetchReport(target)
      .then((reportPayload) => {
        if (!cancelled) {
          setReport(reportPayload);
        }
      })
      .catch(() => {
        // 报告不存在时不阻断主流程
      });

    return () => {
      cancelled = true;
    };
  }, [target, reloadKey]);

  const filteredGraph = useMemo(() => {
    const activeGraph = searchGraph ?? graph;
    if (!activeGraph) return null;
    if (highlightNodeIds.length > 0) return activeGraph;
    let visible = activeGraph.nodes;
    if (currentYear < 2026) {
      visible = visible.filter((n) => {
        if (!n.first_seen) return true;
        const fy = parseInt(n.first_seen.split("-")[0], 10);
        if (Number.isNaN(fy)) return true;
        return fy <= currentYear;
      });
    }
    if (techniqueFilter) {
      const connectedIds = new Set([techniqueFilter]);
      activeGraph.edges.forEach((e) => {
        if (e.source === techniqueFilter) connectedIds.add(e.target);
        if (e.target === techniqueFilter) connectedIds.add(e.source);
      });
      visible = visible.filter((n) => connectedIds.has(n.id));
    }
    if (legendFilter) {
      const typeIds = new Set(
        activeGraph.nodes
          .filter((n) => n.type === legendFilter)
          .map((n) => n.id),
      );
      const connectedIds = new Set(typeIds);
      activeGraph.edges.forEach((e) => {
        if (typeIds.has(e.source)) connectedIds.add(e.target);
        if (typeIds.has(e.target)) connectedIds.add(e.source);
      });
      visible = visible.filter((n) => connectedIds.has(n.id));
    }
    if (regionFilter) {
      const connectedIds = new Set([regionFilter]);
      activeGraph.edges.forEach((e) => {
        if (e.source === regionFilter) connectedIds.add(e.target);
        if (e.target === regionFilter) connectedIds.add(e.source);
      });
      visible = visible.filter((n) => connectedIds.has(n.id));
    }
    const visibleIds = new Set(visible.map((n) => n.id));
    return {
      ...activeGraph,
      nodes: visible,
      edges: activeGraph.edges.filter(
        (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
      ),
    };
  }, [
    graph,
    searchGraph,
    currentYear,
    techniqueFilter,
    regionFilter,
    highlightNodeIds,
    legendFilter,
  ]);
  const countries = useMemo(
    () =>
      graph?.nodes
        .filter((n) => n.type === "COUNTRY")
        .map((n) => ({ id: n.id, name: n.name })) ?? [],
    [graph],
  );
  const techniqueOptions = useMemo(
    () =>
      graph?.nodes
        .filter((n) => n.type === "TECHNIQUE")
        .map((n) => ({ id: n.id, name: n.name })) ?? [],
    [graph],
  );
  const graphOption = useMemo(
    () =>
      filteredGraph
        ? buildGraphOption(filteredGraph, { highlightNodeIds, searchNodeId })
        : null,
    [filteredGraph, highlightNodeIds, searchNodeId],
  );

  const handleChartReady = useCallback((instance: any) => {
    chartInstanceRef.current = instance;
    instance.on("click", (params: any) => {
      if (params.dataType === "node") {
        const raw = params.data._raw as GraphNode | undefined;
        if (raw) setSelectedNode(raw);
        setSearchNodeId(null);
        setSelectedEdge(null);
      } else if (params.dataType === "edge") {
        const raw = params.data._raw as GraphEdge | undefined;
        if (raw) {
          setSelectedEdge(raw);
          setSelectedNode(null);
        }
      }
    });
    instance.on("legendselectchanged", (params: any) => {
      setLegendFilter((prev: string | null) =>
        prev === params.name ? null : params.name,
      );
      setTimeout(() => {
        const cats = instance.getOption().legend?.[0]?.data || [];
        cats.forEach((cat: any) => {
          instance.dispatchAction({
            type: "legendSelect",
            name: typeof cat === "string" ? cat : cat.name,
          });
        });
      }, 0);
    });
  }, []);

  const handleSearchSelect = useCallback(
    (nodeId: string, depth = graphDepth) => {
      selectedSearchNodeRef.current = nodeId;
      neighborRequestRef.current?.abort();
      const controller = new AbortController();
      neighborRequestRef.current = controller;
      setSearchNodeId(nodeId);
      setSelectedNode(null);
      setSelectedEdge(null);
      setError(null);
      fetchNeighbors(nodeId, depth, { signal: controller.signal })
        .then((payload) => {
          if (controller.signal.aborted || selectedSearchNodeRef.current !== nodeId) return;
          setSearchGraph(payload);
          setSelectedEvidence(payload.evidence[0] ?? null);
        })
        .catch((cause: unknown) => {
          if (controller.signal.aborted || selectedSearchNodeRef.current !== nodeId) return;
          setError(cause instanceof Error ? cause.message : "实体筛选失败");
        });
    },
    [graphDepth],
  );
  const handleSearchClear = useCallback(() => {
    selectedSearchNodeRef.current = null;
    neighborRequestRef.current?.abort();
    neighborRequestRef.current = null;
    setSearchGraph(null);
    setSearchNodeId(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    setSelectedEvidence(graph?.evidence[0] ?? null);
    setError(null);
  }, [graph]);
  const handleGraphDepthChange = useCallback(
    (value: string) => {
      setGraphDepthInput(value);
      if (value.trim() === "") {
        setGraphDepthError("请输入 1–20 的整数");
        return;
      }
      const parsed = Number(value);
      if (!Number.isInteger(parsed)) {
        setGraphDepthError("请输入 1–20 的整数");
        return;
      }
      const nextDepth = Math.min(20, Math.max(1, parsed));
      setGraphDepthInput(String(nextDepth));
      setGraphDepthError(null);
      setGraphDepth(nextDepth);
      if (selectedSearchNodeRef.current) {
        handleSearchSelect(selectedSearchNodeRef.current, nextDepth);
      } else {
        graphRequestRef.current?.abort();
        const controller = new AbortController();
        graphRequestRef.current = controller;
        setLoading(true);
        fetchGraph(target, nextDepth, { signal: controller.signal })
          .then((payload) => {
            if (controller.signal.aborted) return;
            setGraph(payload);
            setSelectedEvidence(payload.evidence[0] ?? null);
          })
          .catch((cause: unknown) => {
            if (!controller.signal.aborted) {
              setError(cause instanceof Error ? cause.message : "请求失败");
            }
          })
          .finally(() => {
            if (!controller.signal.aborted) setLoading(false);
          });
      }
    },
    [graphDepth, handleSearchSelect, target],
  );
  const handlePathFound = useCallback((ids: string[]) => {
    setHighlightNodeIds(ids);
    setSelectedNode(null);
  }, []);
  const handlePathClear = useCallback(() => {
    setHighlightNodeIds([]);
  }, []);
  const handleGenerateReport = useCallback(async (tgt: string) => {
    setGenerating(true);
    try {
      const reportPayload = await generateReport(tgt);
      setReport(reportPayload);
    } catch {
      // 生成失败不影响主流程
    } finally {
      setGenerating(false);
    }
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">ThreatGraph-OSINT</p>
          <h1>开源威胁情报知识图谱研判系统</h1>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={() => setReloadKey((value) => value + 1)}
        >
          <RefreshCw size={18} />
          <span>刷新</span>
        </button>
      </header>

      <section className="toolbar" aria-label="目标组织">
        <div className="segmented">
          {TARGETS.map((item) => (
            <button
              className={item === target ? "active" : ""}
              key={item}
              type="button"
              onClick={() => setTarget(item)}
            >
              <ShieldCheck size={16} />
              <span>{item}</span>
            </button>
          ))}
        </div>
        <SearchBar
          key={target}
          onSelect={handleSearchSelect}
          onClear={handleSearchClear}
        />
        <TechniqueFilter
          techniques={techniqueOptions}
          value={techniqueFilter}
          onChange={setTechniqueFilter}
        />
        <RegionFilter
          countries={countries}
          value={regionFilter}
          onChange={setRegionFilter}
        />
        <div className="toolbar-actions">
          <button
            type="button"
            onClick={() => setPipelineOpen(true)}
            style={{
              padding: "6px 12px",
              borderRadius: 8,
              border: "1px solid #d7dfdd",
              background: "#ffffff",
              cursor: "pointer",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <Upload size={16} />
            <span>导入文档</span>
          </button>
          <button
            className="toolbar-action toolbar-action-secondary"
            type="button"
            onClick={() => setCrawlerOpen(true)}
          >
            <Radar size={16} />
            <span>采集情报</span>
          </button>
        </div>
        <div className="status-strip">
          <span>
            <Database size={16} />
            SQLite
          </span>
          <span>
            <Network size={16} />
            graph.json
          </span>
          <span>
            <Activity size={16} />
            P0
          </span>
        </div>
      </section>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {(["graph", "analysis"] as const).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPage(p)}
            style={{
              padding: "6px 16px",
              borderRadius: 8,
              border: "1px solid #d7dfdd",
              background: page === p ? "#0f766e" : "#ffffff",
              color: page === p ? "#fff" : "#172026",
              cursor: "pointer",
              fontSize: 13,
              fontWeight: page === p ? 600 : 400,
            }}
          >
            {p === "graph" ? "知识图谱" : "行为分析"}
          </button>
        ))}
      </div>

      {error ? <div className="alert">{error}</div> : null}

      {page === "analysis" ? (
        <AnalysisPage target={target} />
      ) : (
        <>
          <section className="metrics-grid">
            <Metric label="实体" value={filteredGraph?.nodes.length ?? 0} />
            <Metric label="关系" value={filteredGraph?.edges.length ?? 0} />
            <Metric label="证据" value={filteredGraph?.evidence.length ?? 0} />
            <Metric label="目标" value={target} />
          </section>

          <section className="workbench">
            <div ref={graphPanelRef} className="graph-panel" style={{ position: "relative" }}>
              <div className="panel-heading">
                <h2>关系图谱</h2>
                <div className="graph-heading-actions">
                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                    <span>展示深度</span>
                    <input
                      aria-label="图谱展示深度"
                      type="number"
                      min={1}
                      max={20}
                      step={1}
                      value={graphDepthInput}
                      onChange={(event) => handleGraphDepthChange(event.target.value)}
                      style={{
                        width: 64,
                        padding: "4px 6px",
                        border: "1px solid #cbd5e1",
                        borderRadius: 6,
                      }}
                    />
                    {graphDepthError ? (
                      <span style={{ color: "#dc2626" }}>{graphDepthError}</span>
                    ) : null}
                  </label>
                  <button
                    aria-label={isGraphFullscreen ? "退出图谱全屏" : "全屏显示图谱"}
                    aria-pressed={isGraphFullscreen}
                    className="graph-fullscreen-button"
                    title={isGraphFullscreen ? "退出全屏" : "全屏显示"}
                    type="button"
                    onClick={handleGraphFullscreen}
                  >
                    {isGraphFullscreen ? (
                      <Minimize2 aria-hidden="true" size={18} />
                    ) : (
                      <Maximize2 aria-hidden="true" size={18} />
                    )}
                  </button>
                </div>
              </div>
              <div className="graph-canvas">
                {graphOption ? (
                  <ReactECharts
                    ref={chartRef}
                    className="chart"
                    option={graphOption}
                    onChartReady={handleChartReady}
                  />
                ) : null}
              </div>
              {selectedNode && (
                <>
                  <div
                    onClick={() => setSelectedNode(null)}
                    style={{
                      position: "absolute",
                      inset: 0,
                      background: "rgba(0,0,0,0.2)",
                      zIndex: 25,
                    }}
                  />
                  <NodeDetail
                    entityId={selectedNode?.id ?? null}
                    onClose={() => setSelectedNode(null)}
                  />
                </>
              )}
            </div>

            <aside className="side-panel">
              {selectedEdge ? (
                <>
                  <div className="panel-heading">
                    <h2>关系详情</h2>
                    <button
                      onClick={() => setSelectedEdge(null)}
                      style={{
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        color: "#64748b",
                        fontSize: 18,
                      }}
                    >
                      &times;
                    </button>
                  </div>
                  <div style={{ padding: 16, fontSize: 13, color: "#334155" }}>
                    <div style={{ marginBottom: 12 }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          borderRadius: 4,
                          background: "#0f766e",
                          color: "#fff",
                          fontWeight: 600,
                        }}
                      >
                        {selectedEdge.label}
                      </span>
                      <span
                        style={{
                          marginLeft: 8,
                          fontSize: 12,
                          color: "#64748b",
                        }}
                      >
                        {selectedEdge.type}
                      </span>
                      {selectedEdge.validation_status === "valid" ? (
                        <span
                          style={{
                            display: "inline-block",
                            marginLeft: 8,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: "#dcfce7",
                            color: "#166534",
                            fontSize: 11,
                            fontWeight: 600,
                          }}
                        >
                          证据事实
                        </span>
                      ) : (
                        <span
                          style={{
                            display: "inline-block",
                            marginLeft: 8,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: "#f1f5f9",
                            color: "#64748b",
                            fontSize: 11,
                            fontWeight: 600,
                          }}
                        >
                          系统推断
                        </span>
                      )}
                    </div>
                    <p>
                      置信度:{" "}
                      <strong style={{ color: "#172026" }}>
                        {selectedEdge.confidence}
                      </strong>
                    </p>
                    <p>
                      来源数: {selectedEdge.source_count} · 证据:{" "}
                      {selectedEdge.evidence_count} 条
                    </p>
                    <hr
                      style={{
                        border: "none",
                        borderTop: "1px solid #e2e8e6",
                        margin: "12px 0",
                      }}
                    />
                    <p style={{ color: "#64748b" }}>
                      {selectedEdge.source} → {selectedEdge.target}
                    </p>
                    <div style={{ marginTop: 12 }}>
                      {(selectedEdge.evidence_ids ?? []).map((evId, evIdx) => {
                        const e = filteredGraph?.evidence.find(
                          (ev) => ev.id === evId,
                        );
                        if (!e) return null;
                        return (
                          <div
                            key={e.id}
                            style={{
                              padding: 10,
                              marginBottom: 8,
                              border: "1px solid #e2e8e6",
                              borderRadius: 8,
                              background: "#f8faf9",
                            }}
                          >
                            <p style={{ margin: "0 0 4px", fontSize: 12 }}>
                              {e.text}
                            </p>
                            <a
                              href={e.source_url}
                              target="_blank"
                              rel="noreferrer"
                              style={{
                                fontSize: 11,
                                color: "#0f766e",
                                fontWeight: 600,
                              }}
                            >
                              {e.source_name}
                            </a>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="panel-heading">
                    <h2>证据链</h2>
                    <FileText size={18} />
                  </div>
                  <div className="evidence-list">
                    {filteredGraph?.evidence.map((item) => (
                      <div
                        className={
                          selectedEvidence?.id === item.id
                            ? "evidence-item active"
                            : "evidence-item"
                        }
                        key={item.id}
                        onClick={() => setSelectedEvidence(item)}
                      >
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {item.id}
                        </a>
                        <span>{firstSentence(item.text)}</span>
                      </div>
                    ))}
                  </div>
                  {selectedEvidence ? (
                    <div className="evidence-detail">
                      <p>{selectedEvidence.text}</p>
                    </div>
                  ) : null}
                </>
              )}
            </aside>
          </section>

          <PathTracking
            nodes={filteredGraph?.nodes ?? []}
            onPathFound={handlePathFound}
            onPathClear={handlePathClear}
          />
          <TimelineBar
            minYear={2004}
            maxYear={2026}
            currentYear={currentYear}
            onChange={setCurrentYear}
          />

          <ReportPanel
            graph={graph}
            report={report}
            target={target}
            onGenerate={handleGenerateReport}
            generating={generating}
          />
        </>
      )}
      <PipelineModal
        open={pipelineOpen}
        onClose={() => setPipelineOpen(false)}
        onSuccess={() => setReloadKey((v) => v + 1)}
      />
      <CrawlerModal
        open={crawlerOpen}
        target={target}
        llmConfigured={llmConfigured}
        onClose={() => setCrawlerOpen(false)}
        onSuccess={() => setReloadKey((value) => value + 1)}
      />
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
