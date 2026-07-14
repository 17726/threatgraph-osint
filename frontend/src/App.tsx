import ReactECharts from "echarts-for-react";
import {
  Activity,
  Database,
  FileText,
  Network,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchGraph } from "./api/client";
import { buildGraphOption } from "./graphOptions";
import type { Evidence, GraphEdge, GraphNode, GraphPayload } from "./types";
import NodeDetail from "./components/NodeDetail";
import SearchBar from "./components/SearchBar";
import TimelineBar from "./components/TimelineBar";
import PathTracking from "./components/PathTracking";
import ReportPanel from "./components/ReportPanel";
import AnalysisPage from "./pages/AnalysisPage";
import EvaluationPage from "./pages/EvaluationPage";

const TARGETS = ["APT28", "Lazarus", "Kimsuky"];

export function App() {
  const [target, setTarget] = useState(TARGETS[0]);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const chartRef = useRef<any>(null);
  const chartInstanceRef = useRef<any>(null);
  const [currentYear, setCurrentYear] = useState(2026);
  const [highlightNodeIds, setHighlightNodeIds] = useState<string[]>([]);
  const [searchNodeId, setSearchNodeId] = useState<string | null>(null);
  const [page, setPage] = useState<"graph" | "analysis" | "evaluation">(
    "graph",
  );
  const firstSentence = (text: string): string => {
    const match = text.match(/^.*?[。！？.!?]/);
    return match ? match[0] : text;
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    setSearchNodeId(null);

    fetchGraph(target)
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

    return () => {
      cancelled = true;
    };
  }, [target, reloadKey]);

  const filteredGraph = useMemo(() => {
    if (!graph) return null;
    if (highlightNodeIds.length > 0) return graph;
    if (currentYear >= 2026) return graph;
    const activeIds = new Set(
      graph.nodes
        .filter((n) => {
        if (!n.first_seen) return true;
        const fy = parseInt(n.first_seen.split("-")[0], 10);
        if (Number.isNaN(fy)) return true;
        return fy <= currentYear;
      })
      .map((n) => n.id),
    );
    return {
      ...graph,
      nodes: graph.nodes.filter((n) => activeIds.has(n.id)),
      edges: graph.edges.filter(
        (e) => activeIds.has(e.source) && activeIds.has(e.target),
      ),
    };
  }, [graph, currentYear, highlightNodeIds]);
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
  }, []);

  const handleSearchSelect = useCallback(
    (nodeId: string) => {
      const instance = chartInstanceRef.current;
      if (!instance || !filteredGraph) return;
      const idx = filteredGraph.nodes.findIndex((n) => n.id === nodeId);
      if (idx >= 0) {
        setSearchNodeId(nodeId);
        // 重置视图并居中到目标节点
        instance.dispatchAction({ type: "restore" });
        try {
          const opt = instance.getOption();
          const node = opt.series?.[0]?.data?.[idx];
          if (node && typeof node.x === "number" && typeof node.y === "number") {
            instance.setOption({ series: [{ center: [node.x, node.y], zoom: 1.8 }] });
          }
        } catch (_) { /* 忽略坐标读取失败 */ }
        instance.dispatchAction({
          type: "focusNodeAdjacency",
          seriesIndex: 0,
          dataIndex: idx,
        });
      }
    },
    [filteredGraph],
  );
  const handlePathFound = useCallback((ids: string[]) => {
    setHighlightNodeIds(ids);
    setSelectedNode(null);
  }, []);
  const handlePathClear = useCallback(() => {
    setHighlightNodeIds([]);
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
          onSelect={handleSearchSelect}
        />
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
        {(["graph", "analysis", "evaluation"] as const).map((p) => (
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
            {p === "graph"
              ? "知识图谱"
              : p === "analysis"
                ? "行为分析"
                : "评测结果"}
          </button>
        ))}
      </div>

      {error ? <div className="alert">{error}</div> : null}

      {page === "analysis" ? (
        <AnalysisPage target={target} />
      ) : page === "evaluation" ? (
        <EvaluationPage />
      ) : (
        <>
          <section className="metrics-grid">
            <Metric label="实体" value={filteredGraph?.nodes.length ?? 0} />
            <Metric label="关系" value={filteredGraph?.edges.length ?? 0} />
            <Metric label="证据" value={graph?.evidence.length ?? 0} />
            <Metric label="目标" value={target} />
          </section>

          <section className="workbench">
            <div className="graph-panel" style={{ position: "relative" }}>
              <div className="panel-heading">
                <h2>关系图谱</h2>
                <span>{loading ? "加载中" : "已加载"}</span>
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
                        const e = graph?.evidence.find((ev) => ev.id === evId);
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
                        );})}
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
                    {graph?.evidence.map((item) => (
                      <div
                      className={
                        selectedEvidence?.id === item.id
                          ? "evidence-item active"
                          : "evidence-item"
                      }
                      key={item.id}
                      onClick={() => setSelectedEvidence(item)}
                    >
                      <a href={item.source_url} target="_blank" rel="noreferrer">{item.id}</a>
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

          <ReportPanel target={target} />
        </>
      )}
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
