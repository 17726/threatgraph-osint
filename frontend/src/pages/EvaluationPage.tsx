import { MOCK_EVAL } from "../data/mockEval";
import type { EvalMetrics } from "../data/mockEval";

function pct(n: number) {
  return `${(n * 100).toFixed(0)}%`;
}

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div
      style={{
        padding: "14px",
        background: "#ffffff",
        border: "1px solid #d7dfdd",
        borderRadius: 8,
      }}
    >
      <p style={{ margin: "0 0 4px", fontSize: 12, color: "#64748b" }}>{label}</p>
      <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#172026" }}>{value}</p>
      {sub && <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>{sub}</p>}
    </div>
  );
}

export default function EvaluationPage() {
  const m: EvalMetrics = MOCK_EVAL;
  return (
    <section className="report-panel" style={{ marginTop: 16 }}>
      <div className="panel-heading">
        <h2>评测结果</h2>
      </div>
      <div style={{ padding: 16, fontSize: 13 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 12px" }}>
          实体抽取
        </h3>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 10,
            marginBottom: 24,
          }}
        >
          <MetricCard label="Precision" value={pct(m.entity_precision)} />
          <MetricCard label="Recall" value={pct(m.entity_recall)} />
          <MetricCard label="F1" value={pct(m.entity_f1)} />
        </div>

        <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 12px" }}>
          关系抽取
        </h3>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 10,
            marginBottom: 24,
          }}
        >
          <MetricCard label="Precision" value={pct(m.relation_precision)} />
          <MetricCard label="Recall" value={pct(m.relation_recall)} />
          <MetricCard label="F1" value={pct(m.relation_f1)} />
        </div>

        <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 12px" }}>
          测试集规模
        </h3>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 10,
            marginBottom: 24,
          }}
        >
          <MetricCard label="文档" value={String(m.test_docs)} />
          <MetricCard label="实体" value={String(m.test_entities)} />
          <MetricCard label="关系" value={String(m.test_relations)} />
        </div>

        <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 12px" }}>
          错误样例
        </h3>
        <div style={{ display: "grid", gap: 8 }}>
          {m.errors.map((e, i) => (
            <div
              key={i}
              style={{
                padding: "10px 12px",
                background: "#f8faf9",
                borderRadius: 6,
                border: "1px solid #e2e8e6",
              }}
            >
              <span
                style={{
                  display: "inline-block",
                  padding: "1px 6px",
                  borderRadius: 4,
                  background: "#fef2f2",
                  color: "#991b1b",
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                {e.type}
              </span>
              <p style={{ margin: "4px 0 0", fontSize: 13, color: "#334155" }}>{e.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
