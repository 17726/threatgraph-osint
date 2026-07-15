import { useState, useEffect } from "react";
import { fetchAnalysis } from "../api/client";
import type { AnalysisResponse, MitreMapping, BehaviorPattern, InferredRelation } from "../types";

interface AnalysisPageProps {
  target: string;
}

export default function AnalysisPage({ target }: AnalysisPageProps) {
  const [mitre, setMitre] = useState<MitreMapping[]>([]);
  const [behavior, setBehavior] = useState<BehaviorPattern[]>([]);
  const [inferences, setInferences] = useState<InferredRelation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchAnalysis<AnalysisResponse>(target, "mitre").then((r) => setMitre(r.mappings ?? [])),
      fetchAnalysis<AnalysisResponse>(target, "behavior").then((r) =>
        setBehavior(r.patterns ?? []),
      ),
      fetchAnalysis<AnalysisResponse>(target, "inferences").then((r) =>
        setInferences(r.inferences ?? []),
      ),
    ])
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [target]);

  if (loading) return <p style={{ padding: 20, color: "#64748b" }}>加载中...</p>;

  const tacticMap: Record<string, MitreMapping[]> = {};
  mitre.forEach((m) => {
    const tactic = m.tactic || "其他";
    (tacticMap[tactic] ??= []).push(m);
  });

  return (
    <section className="report-panel" style={{ marginTop: 16 }}>
      <div className="panel-heading">
        <h2>{target} - 行为分析</h2>
      </div>
      <div style={{ padding: 16, maxHeight: 500, overflowY: "auto", fontSize: 13 }}>
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 8px" }}>
            MITRE ATT&CK 映射
          </h3>
          {mitre.length === 0 ? (
            <p style={{ color: "#94a3b8" }}>暂无数据</p>
          ) : (
            Object.entries(tacticMap).map(([tactic, items]) => (
              <div key={tactic} style={{ marginBottom: 8 }}>
                <p style={{ fontSize: 12, color: "#64748b", fontWeight: 600, margin: "0 0 4px" }}>
                  {tactic}
                </p>
                {items.map((m) => (
                  <div
                    key={m.mapping_id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      padding: "6px 10px",
                      background: "#f8faf9",
                      borderRadius: 6,
                      border: "1px solid #e2e8e6",
                      marginBottom: 2,
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 600, color: "#172026" }}>{m.technique_id}</span>
                      <span style={{ marginLeft: 8, color: "#475569" }}>{m.technique_name}</span>
                    </div>
                    <span style={{ color: "#64748b", fontSize: 12 }}>置信度: {m.confidence}</span>
                  </div>
                ))}
              </div>
            ))
          )}
        </div>

        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 8px" }}>
            行为模式
          </h3>
          {behavior.length === 0 ? (
            <p style={{ color: "#94a3b8" }}>暂无数据</p>
          ) : (
            behavior.map((p) => (
              <div
                key={p.pattern_id}
                style={{
                  padding: "10px 12px",
                  background: "#f8faf9",
                  borderRadius: 6,
                  border: "1px solid #e2e8e6",
                  marginBottom: 6,
                }}
              >
                <p style={{ margin: "0 0 4px", fontWeight: 600, color: "#0f766e", fontSize: 13 }}>
                  {p.stage}
                </p>
                <p style={{ margin: 0, color: "#475569", fontSize: 12 }}>{p.description}</p>
                <p style={{ margin: "4px 0 0", color: "#94a3b8", fontSize: 11 }}>
                  相关技术: {p.technique_ids?.join(", ") ?? "-"} | 置信度: {p.confidence}
                </p>
              </div>
            ))
          )}
        </div>

        <div>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "#0f766e", margin: "0 0 8px" }}>
            推断关系
          </h3>
          {inferences.length === 0 ? (
            <p style={{ color: "#94a3b8" }}>暂无数据</p>
          ) : (
            inferences.map((r) => (
              <div
                key={r.inferred_relation_id}
                style={{
                  padding: "6px 10px",
                  background: "#f8faf9",
                  borderRadius: 6,
                  border: "1px solid #e2e8e6",
                  marginBottom: 4,
                }}
              >
                <p style={{ margin: 0, fontSize: 12 }}>
                  <span style={{ color: "#64748b" }}>{r.type}</span> {r.source} → {r.target}{" "}
                  <span style={{ color: "#94a3b8", fontStyle: "italic" }}>({r.confidence})</span>
                </p>
                <p style={{ margin: "2px 0 0", fontSize: 11, color: "#94a3b8" }}>{r.rationale}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
