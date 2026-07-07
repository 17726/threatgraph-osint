import type { GraphPayload } from "../types";

interface AnalysisPageProps {
  graph: GraphPayload | null;
  target: string;
}

export default function AnalysisPage({ graph, target }: AnalysisPageProps) {
  if (!graph) return <p style={{ padding: 20, color: "#64748b" }}>加载中...</p>;

  const techniques = graph.nodes.filter((n) => n.type === "TECHNIQUE");
  const tacticMap: Record<string, string[]> = {};
  techniques.forEach((t) => {
    const tactic = t.tags?.[0] || "其他";
    (tacticMap[tactic] ??= []).push(t.name);
  });

  const targetEdges = graph.edges.filter((e) => e.type === "TARGETS");
  const targetNames = [...new Set(targetEdges.map((e) => {
    const n = graph.nodes.find((n) => n.id === (e.target === `apt_group:${target.toLowerCase()}` ? e.source : e.target));
    return n?.name ?? e.target;
  }))];

  const inferenceEdges = graph.edges.filter((e) => e.validation_status === "invalid");

  const usedTTPs = graph.edges
    .filter((e) => e.type === "USES")
    .map((e) => {
      const tn = graph.nodes.find((n) => n.id === e.target);
      return { name: tn?.name ?? e.target, confidence: e.confidence };
    });

  return (
    <section className="report-panel" style={{ marginTop: 16 }}>
      <div className="panel-heading"><h2>{target} - 行为分析</h2></div>
      <div style={{ padding: 16, maxHeight: 500, overflowY: "auto", fontSize: 13 }}>
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 8px" }}>MITRE ATT&CK 技术</h3>
          {Object.entries(tacticMap).map(([tactic, names]) => (
            <div key={tactic} style={{ marginBottom: 8 }}>
              <p style={{ fontSize: 12, color: "#64748b", fontWeight: 600, margin: "0 0 4px" }}>{tactic}</p>
              {names.map((name) => (
                <div key={name} style={{ padding: "4px 8px", fontSize: 12, background: "#f8faf9", borderRadius: 4, marginBottom: 2 }}>
                  <span>{name}</span>
                </div>
              ))}
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 8px" }}>使用技术</h3>
          {usedTTPs.length === 0 ? <p style={{ color: "#94a3b8" }}>无</p> : (
            <div style={{ display: "grid", gap: 6 }}>
              {usedTTPs.map((t, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 10px", background: "#f8faf9", borderRadius: 6, border: "1px solid #e2e8e6" }}>
                  <span>{t.name}</span>
                  <span style={{ color: "#64748b" }}>{t.confidence}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 8px" }}>目标偏好</h3>
          {targetNames.length === 0 ? <p style={{ color: "#94a3b8" }}>无</p> : targetNames.map((n) => (
            <div key={n} style={{ padding: "4px 8px", fontSize: 12, background: "#f8faf9", borderRadius: 4, marginBottom: 2 }}>
              <span>{n}</span>
            </div>
          ))}
        </div>

        <div>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 8px" }}>推断关系</h3>
          {inferenceEdges.length === 0 ? <p style={{ color: "#94a3b8" }}>无</p> : inferenceEdges.map((e) => {
            const src = graph.nodes.find((n) => n.id === e.source)?.name ?? e.source;
            const dst = graph.nodes.find((n) => n.id === e.target)?.name ?? e.target;
            return (
              <div key={e.id} style={{ padding: "6px 10px", background: "#f8faf9", borderRadius: 6, border: "1px solid #e2e8e6", marginBottom: 4 }}>
                <p style={{ margin: 0, fontSize: 12 }}><span style={{ color: "#64748b" }}>{e.label}</span> {src} → {dst} <span style={{ color: "#94a3b8", fontStyle: "italic" }}>({e.confidence})</span></p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
