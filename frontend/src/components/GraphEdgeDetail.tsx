import type { Evidence, GraphEdge } from "../types";

interface GraphEdgeDetailProps {
  edge: GraphEdge;
  evidence: Evidence[];
  onClose: () => void;
}

export default function GraphEdgeDetail({ edge, evidence, onClose }: GraphEdgeDetailProps) {
  return (
    <>
      <div className="panel-heading">
        <h2>关系详情</h2>
        <button
          aria-label="关闭关系详情"
          type="button"
          onClick={onClose}
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
            {edge.label}
          </span>
          <span style={{ marginLeft: 8, fontSize: 12, color: "#64748b" }}>{edge.type}</span>
          <span
            style={{
              display: "inline-block",
              marginLeft: 8,
              padding: "2px 6px",
              borderRadius: 4,
              background: edge.validation_status === "valid" ? "#dcfce7" : "#f1f5f9",
              color: edge.validation_status === "valid" ? "#166534" : "#64748b",
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            {edge.validation_status === "valid" ? "证据事实" : "系统推断"}
          </span>
        </div>
        <p>
          置信度: <strong style={{ color: "#172026" }}>{edge.confidence}</strong>
        </p>
        <p>
          来源数: {edge.source_count} · 证据: {edge.evidence_count} 条
        </p>
        <hr style={{ border: "none", borderTop: "1px solid #e2e8e6", margin: "12px 0" }} />
        <p style={{ color: "#64748b" }}>
          {edge.source} → {edge.target}
        </p>
        <div style={{ marginTop: 12 }}>
          {(edge.evidence_ids ?? []).map((evidenceId) => {
            const item = evidence.find((candidate) => candidate.id === evidenceId);
            if (!item) return null;
            return (
              <div
                key={item.id}
                style={{
                  padding: 10,
                  marginBottom: 8,
                  border: "1px solid #e2e8e6",
                  borderRadius: 8,
                  background: "#f8faf9",
                }}
              >
                <p style={{ margin: "0 0 4px", fontSize: 12 }}>{item.text}</p>
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ fontSize: 11, color: "#0f766e", fontWeight: 600 }}
                >
                  {item.source_name}
                </a>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
