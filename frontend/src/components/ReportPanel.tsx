import type { GraphPayload } from "../types";

interface ReportPanelProps {
  graph: GraphPayload | null;
  target: string;
}

export default function ReportPanel({ graph, target }: ReportPanelProps) {
  if (!graph) return null;

  const targetNode = graph.nodes.find((n) => n.name === target && n.type === "APT_GROUP");
  if (!targetNode) return null;

  const edgesByType: Record<string, { label: string; confidence: number; infer: boolean }[]> = {};
  graph.edges.forEach((e) => {
    const src = graph.nodes.find((n) => n.id === e.source)?.name ?? e.source;
    const dst = graph.nodes.find((n) => n.id === e.target)?.name ?? e.target;
    (edgesByType[e.type] ??= []).push({ label: `${src} → ${dst}`, confidence: e.confidence, infer: e.validation_status === "invalid" });
  });

  const typeCounts: Record<string, number> = {};
  graph.nodes.forEach((n) => { typeCounts[n.type] = (typeCounts[n.type] || 0) + 1; });

  const profile = [
    ["名称", targetNode.name],
    ["别名", targetNode.aliases?.join(", ") || "-"],
    ["描述", targetNode.description || "-"],
    ["置信度", targetNode.confidence != null ? String(targetNode.confidence) : "-"],
    ["来源数", targetNode.source_count != null ? String(targetNode.source_count) :"-"],
    ["首次发现", targetNode.first_seen ?? "-"],
    ["最近活跃", targetNode.last_seen ?? "-"],
  ];

  const stats = [
    ["节点", String(graph.nodes.length)],
    ["边", String(graph.edges.length)],
    ["证据", String(graph.evidence.length)],
    ...Object.entries(typeCounts).map(([t, c]) => [t, String(c)]),
  ];

  return (
    <section className="report-panel">
      <div className="panel-heading">
        <h2>{target} - 威胁分析报告</h2>
      </div>
      <div style={{ padding: 16, maxHeight: 400, overflowY: "auto", fontSize: 13 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 8px" }}>目标画像</h3>
        <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 20 }}>
          <tbody>
            {profile.map(([k, v]) => (
              <tr key={k}>
                <td style={{ padding: "4px 8px", color: "#64748b", width: 80, fontWeight: 500, borderBottom: "1px solid #e2e8e6" }}>{k}</td>
                <td style={{ padding: "4px 8px", color: "#172026", borderBottom: "1px solid #e2e8e6" }}>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 8px" }}>关键关系</h3>
        {Object.entries(edgesByType).map(([type, items]) => (
          <div key={type} style={{ marginBottom: 8 }}>
            <p style={{ fontSize: 12, color: "#64748b", fontWeight: 600, margin: "0 0 4px" }}>{type}</p>
            {items.map((item, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 8px", fontSize: 12, background: i % 2 === 0 ? "#f8faf9" : "transparent", borderRadius: 4, marginBottom: 2 }}>
                <span style={{ color: "#172026" }}>{item.label}</span>
                <span style={{ color: "#64748b", marginLeft: "auto" }}>
                  {item.infer ? <span style={{ color: "#94a3b8", fontStyle: "italic" }}>推断</span> : String(item.confidence)}
                </span>
              </div>
            ))}
          </div>
        ))}

        <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "16px 0 8px" }}>基础统计</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
          {stats.map(([k, v]) => (
            <div key={k} style={{ padding: "8px 10px", background: "#f8faf9", borderRadius: 6, border: "1px solid #e2e8e6" }}>
              <p style={{ margin: 0, fontSize: 11, color: "#64748b" }}>{k}</p>
              <p style={{ margin: "2px 0 0", fontSize: 16, fontWeight: 600, color: "#172026" }}>{v}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
