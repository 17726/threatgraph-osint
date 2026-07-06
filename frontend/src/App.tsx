import ReactECharts from "echarts-for-react";
import { Activity, Database, FileText, Network, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { fetchGraph, fetchReport } from "./api/client";
import { buildGraphOption } from "./graphOptions";
import type { Evidence, GraphPayload, ReportPayload } from "./types";

const TARGETS = ["APT28", "Lazarus", "Kimsuky"];

export function App() {
  const [target, setTarget] = useState(TARGETS[0]);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([fetchGraph(target), fetchReport(target)])
      .then(([graphPayload, reportPayload]) => {
        if (cancelled) {
          return;
        }
        setGraph(graphPayload);
        setReport(reportPayload);
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

  const graphOption = useMemo(() => (graph ? buildGraphOption(graph) : null), [graph]);

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

      {error ? <div className="alert">{error}</div> : null}

      <section className="metrics-grid">
        <Metric label="实体" value={graph?.nodes.length ?? 0} />
        <Metric label="关系" value={graph?.edges.length ?? 0} />
        <Metric label="证据" value={graph?.evidence.length ?? 0} />
        <Metric label="目标" value={target} />
      </section>

      <section className="workbench">
        <div className="graph-panel">
          <div className="panel-heading">
            <h2>关系图谱</h2>
            <span>{loading ? "加载中" : "已加载"}</span>
          </div>
          <div className="graph-canvas">
            {graphOption ? <ReactECharts className="chart" option={graphOption} /> : null}
          </div>
        </div>

        <aside className="side-panel">
          <div className="panel-heading">
            <h2>证据链</h2>
            <FileText size={18} />
          </div>
          <div className="evidence-list">
            {graph?.evidence.map((item) => (
              <button
                className={
                  selectedEvidence?.id === item.id ? "evidence-item active" : "evidence-item"
                }
                key={item.id}
                type="button"
                onClick={() => setSelectedEvidence(item)}
              >
                <strong>{item.id}</strong>
                <span>{item.text}</span>
              </button>
            ))}
          </div>
          {selectedEvidence ? (
            <div className="evidence-detail">
              <p>{selectedEvidence.text}</p>
              <a href={selectedEvidence.source_url} target="_blank" rel="noreferrer">
                来源链接
              </a>
            </div>
          ) : null}
        </aside>
      </section>

      <section className="report-panel">
        <div className="panel-heading">
          <h2>{report?.title ?? "威胁情报分析报告"}</h2>
          <span>Markdown</span>
        </div>
        <pre>{report?.markdown ?? ""}</pre>
      </section>
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
