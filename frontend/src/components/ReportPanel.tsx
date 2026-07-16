import { useState } from "react";
import { Sparkles } from "lucide-react";
import type { GraphPayload, ReportPayload, ReportSection } from "../types";

interface ReportPanelProps {
  graph: GraphPayload | null;
  report: ReportPayload | null;
  target: string;
  onGenerate?: (target: string) => void;
  generating?: boolean;
}

const SECTION_ICONS: Record<string, string> = {
  profile: "📋",
  behavior_patterns: "⚡",
  network: "🔗",
  timeline: "📅",
  threat_assessment: "🛡️",
};

export default function ReportPanel({
  graph,
  report,
  target,
  onGenerate,
  generating,
}: ReportPanelProps) {
  const [activeSection, setActiveSection] = useState<string>("profile");
  const [reportMode, setReportMode] = useState<"sections" | "full">("sections");

  // 如果有结构化报告章节，使用结构化展示
  if (report?.sections && report.sections.length > 0) {
    const sections = report.sections.sort((a, b) => a.sort_order - b.sort_order);
    const current = sections.find((s) => s.section_type === activeSection) ?? sections[0];

    return (
      <section className="report-panel">
        <div className="panel-heading">
          <h2>{report.title}</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {report.generated_at && (
              <span style={{ fontSize: 11, color: "#94a3b8" }}>
                {new Date(report.generated_at).toLocaleString("zh-CN")}
              </span>
            )}
            {onGenerate && (
              <button
                type="button"
                disabled={generating}
                onClick={() => onGenerate(target)}
                style={{
                  padding: "4px 10px",
                  borderRadius: 6,
                  border: "1px solid #0f766e",
                  background: generating ? "#e2e8e6" : "#0f766e",
                  cursor: generating ? "not-allowed" : "pointer",
                  fontSize: 12,
                  color: generating ? "#94a3b8" : "#fff",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                <Sparkles size={14} />
                {generating ? "生成中..." : "生成智能报告"}
              </button>
            )}
            <button
              type="button"
              onClick={() => setReportMode(reportMode === "sections" ? "full" : "sections")}
              style={{
                padding: "4px 10px",
                borderRadius: 6,
                border: "1px solid #d7dfdd",
                background: "#f8faf9",
                cursor: "pointer",
                fontSize: 12,
                color: "#172026",
              }}
            >
              {reportMode === "sections" ? "完整报告" : "章节模式"}
            </button>
          </div>
        </div>

        {reportMode === "full" ? (
          <div
            className="report-markdown"
            style={{ padding: 16, maxHeight: 500, overflowY: "auto", fontSize: 13 }}
          >
            <div
              style={{ lineHeight: 1.8, whiteSpace: "pre-wrap" }}
              dangerouslySetInnerHTML={{ __html: renderMarkdown(report.markdown) }}
            />
          </div>
        ) : (
          <>
            <div
              style={{
                display: "flex",
                borderBottom: "1px solid #e2e8e6",
                overflowX: "auto",
              }}
            >
              {sections.map((section) => (
                <button
                  key={section.section_type}
                  type="button"
                  onClick={() => setActiveSection(section.section_type)}
                  style={{
                    padding: "8px 14px",
                    border: "none",
                    borderBottom:
                      activeSection === section.section_type
                        ? "2px solid #0f766e"
                        : "2px solid transparent",
                    background: "transparent",
                    cursor: "pointer",
                    fontSize: 12,
                    fontWeight: activeSection === section.section_type ? 600 : 400,
                    color: activeSection === section.section_type ? "#0f766e" : "#64748b",
                    whiteSpace: "nowrap",
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  <span>{SECTION_ICONS[section.section_type] ?? "📄"}</span>
                  <span>{section.title}</span>
                </button>
              ))}
            </div>

            <div
              className="report-section-content"
              style={{ padding: 16, maxHeight: 400, overflowY: "auto", fontSize: 13 }}
            >
              <h3
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: "#0f766e",
                  margin: "0 0 12px",
                }}
              >
                {SECTION_ICONS[current.section_type] ?? "📄"} {current.title}
              </h3>

              <div
                style={{ lineHeight: 1.8, whiteSpace: "pre-wrap" }}
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(current.markdown),
                }}
              />

              {current.evidence_ids.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <details>
                    <summary
                      style={{
                        fontSize: 12,
                        color: "#64748b",
                        cursor: "pointer",
                        fontWeight: 600,
                      }}
                    >
                      引用证据（{current.evidence_ids.length} 条）
                    </summary>
                    <div style={{ marginTop: 8 }}>
                      {current.evidence_ids.map((eid) => (
                        <div
                          key={eid}
                          style={{
                            padding: "6px 10px",
                            background: "#f8faf9",
                            borderRadius: 6,
                            border: "1px solid #e2e8e6",
                            marginBottom: 6,
                            fontSize: 12,
                            color: "#475569",
                          }}
                        >
                          {eid}
                        </div>
                      ))}
                    </div>
                  </details>
                </div>
              )}
            </div>
          </>
        )}
      </section>
    );
  }

  // 降级：使用图谱数据生成基础报告
  const targetNode = graph?.nodes?.find((n) => n.name === target && n.type === "APT_GROUP");

  const edgesByType: Record<string, { label: string; confidence: number; infer: boolean }[]> = {};
  const typeCounts: Record<string, number> = {};
  if (graph) {
    graph.edges.forEach((e) => {
      const src = graph.nodes.find((n) => n.id === e.source)?.name ?? e.source;
      const dst = graph.nodes.find((n) => n.id === e.target)?.name ?? e.target;
      (edgesByType[e.type] ??= []).push({
        label: `${src} → ${dst}`,
        confidence: e.confidence,
        infer: e.validation_status === "invalid",
      });
    });
    graph.nodes.forEach((n) => {
      typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
    });
  }

  const profile = targetNode
    ? [
        ["名称", targetNode.name],
        ["别名", targetNode.aliases?.join(", ") || "-"],
        ["描述", targetNode.description || "-"],
        ["置信度", targetNode.confidence != null ? String(targetNode.confidence) : "-"],
        ["来源数", targetNode.source_count != null ? String(targetNode.source_count) : "-"],
        ["首次发现", targetNode.first_seen ?? "-"],
        ["最近活跃", targetNode.last_seen ?? "-"],
      ]
    : [];

  const stats = graph
    ? [
        ["节点", String(graph.nodes.length)],
        ["边", String(graph.edges.length)],
        ["证据", String(graph.evidence.length)],
        ...Object.entries(typeCounts).map(([t, c]) => [t, String(c)]),
      ]
    : [];

  return (
    <section className="report-panel">
      <div className="panel-heading">
        <h2>{target || "报告"} - 威胁分析报告</h2>
        {onGenerate && (
          <button
            type="button"
            disabled={generating}
            onClick={() => onGenerate(target)}
            style={{
              padding: "4px 10px",
              borderRadius: 6,
              border: "1px solid #0f766e",
              background: generating ? "#e2e8e6" : "#0f766e",
              cursor: generating ? "not-allowed" : "pointer",
              fontSize: 12,
              color: generating ? "#94a3b8" : "#fff",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <Sparkles size={14} />
            {generating ? "生成中..." : "生成智能报告"}
          </button>
        )}
      </div>
      {targetNode ? (
        <div style={{ padding: 16, maxHeight: 400, overflowY: "auto", fontSize: 13 }}>
          <h3
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: "#0f766e",
              margin: "0 0 8px",
            }}
          >
            目标画像
          </h3>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              marginBottom: 20,
            }}
          >
            <tbody>
              {profile.map(([k, v]) => (
                <tr key={k}>
                  <td
                    style={{
                      padding: "4px 8px",
                      color: "#64748b",
                      width: 80,
                      fontWeight: 500,
                      borderBottom: "1px solid #e2e8e6",
                    }}
                  >
                    {k}
                  </td>
                  <td
                    style={{
                      padding: "4px 8px",
                      color: "#172026",
                      borderBottom: "1px solid #e2e8e6",
                    }}
                  >
                    {v}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: "#0f766e",
              margin: "0 0 8px",
            }}
          >
            关键关系
          </h3>
          {Object.entries(edgesByType).map(([type, items]) => (
            <div key={type} style={{ marginBottom: 8 }}>
              <p
                style={{
                  fontSize: 12,
                  color: "#64748b",
                  fontWeight: 600,
                  margin: "0 0 4px",
                }}
              >
                {type}
              </p>
              {items.map((item, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 8px",
                    fontSize: 12,
                    background: i % 2 === 0 ? "#f8faf9" : "transparent",
                    borderRadius: 4,
                    marginBottom: 2,
                  }}
                >
                  <span style={{ color: "#172026" }}>{item.label}</span>
                  <span style={{ color: "#64748b", marginLeft: "auto" }}>
                    {item.infer ? (
                      <span style={{ color: "#94a3b8", fontStyle: "italic" }}>推断</span>
                    ) : (
                      String(item.confidence)
                    )}
                  </span>
                </div>
              ))}
            </div>
          ))}

          <h3
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: "#0f766e",
              margin: "16px 0 8px",
            }}
          >
            基础统计
          </h3>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 8,
            }}
          >
            {stats.map(([k, v]) => (
              <div
                key={k}
                style={{
                  padding: "8px 10px",
                  background: "#f8faf9",
                  borderRadius: 6,
                  border: "1px solid #e2e8e6",
                }}
              >
                <p style={{ margin: 0, fontSize: 11, color: "#64748b" }}>{k}</p>
                <p
                  style={{
                    margin: "2px 0 0",
                    fontSize: 16,
                    fontWeight: 600,
                    color: "#172026",
                  }}
                >
                  {v}
                </p>
              </div>
            ))}
          </div>
        </div>
      ) : graph ? (
        <div style={{ padding: 16, fontSize: 13, color: "#64748b" }}>
          暂无目标实体的图谱数据，请先通过管道导入数据或搜索实体。
        </div>
      ) : null}
    </section>
  );
}

/** 简单的 Markdown 转 HTML 渲染 */
function renderMarkdown(md: string): string {
  let html = md
    // 表格（处理前后空白、对齐标记 `:---`）
    .replace(/\s*\|(.+)\|\s*\n\s*\|[-:| ]+\|\s*\n((?:\s*\|.+\|\s*\n)*)/g, (_match, header: string, body: string) => {
      const headers = header
        .split("|")
        .map((h: string) => `<th>${h.trim()}</th>`)
        .join("");
      const rows = body
        .trim()
        .split("\n")
        .map((row: string) => {
          const cells = row
            .split("|")
            .map((c: string) => `<td>${c.trim()}</td>`)
            .join("");
          return `<tr>${cells}</tr>`;
        })
        .join("");
      return `<table style="width:100%;border-collapse:collapse;margin:8px 0;font-size:12px">
          <thead><tr>${headers}</tr></thead>
          <tbody>${rows}</tbody>
        </table>`;
    })
    // 标题 (####)
    .replace(/^#### (.+)$/gm, '<h4 style="margin:12px 0 6px;color:#0f766e;">$1</h4>')
    // 标题 (###)
    .replace(/^### (.+)$/gm, '<h3 style="margin:14px 0 8px;color:#0f766e;">$1</h3>')
    // 粗体
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // 列表
    .replace(/^- (.+)$/gm, '<li style="margin:2px 0">$1</li>')
    .replace(/((?:<li[^>]*>.*<\/li>\n?)+)/g, '<ul style="padding-left:20px;margin:6px 0">$1</ul>')
    // 有序列表
    .replace(/^(\d+)\. (.+)$/gm, '<li value="$1" style="margin:2px 0">$2</li>')
    // 空行转段落间距
    .replace(/\n\n/g, "</p><p style='margin:8px 0'>")
    // 换行
    .replace(/\n/g, "<br/>");

  return `<p style="margin:0">${html}</p>`;
}
