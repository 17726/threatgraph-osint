import { useState, useEffect } from "react";
import { fetchReport } from "../api/client";
import type { ReportPayload } from "../types";

interface ReportPanelProps {
  target: string;
}

const CARD_ORDER = ["目标画像", "关联统计", "目标偏好", "行为模式", "MITRE ATT&CK 技术映射", "关键关系"];

function parseMarkdown(md: string) {
  const sections: { title: string; lines: string[] }[] = [];
  const footer: string[] = [];
  let currentTitle = "";
  let currentLines: string[] = [];

  for (const line of md.split("\n")) {
    if (line.trim() === "---") continue;

    const isQuote = line.trim().startsWith("> ");
    const h2 = line.match(/^## (.+)/);

    if (isQuote) {
      footer.push(line.trim().slice(2));
    } else if (h2) {
      if (currentTitle) sections.push({ title: currentTitle, lines: currentLines });
      currentTitle = h2[1].trim();
      currentLines = [];
    } else if (currentTitle) {
      currentLines.push(line);
    }
  }
  if (currentTitle) sections.push({ title: currentTitle, lines: currentLines });

  sections.sort((a, b) => {
    const ia = CARD_ORDER.indexOf(a.title);
    const ib = CARD_ORDER.indexOf(b.title);
    return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
  });

  return { sections, footer };
}

function renderLine(line: string, index: number) {
  const trimmed = line.trim();
  if (!trimmed) return null;

  const h3 = trimmed.match(/^### (.+)/);
  if (h3) {
    return <h4 key={index} style={{ margin: "12px 0 6px", fontSize: 13, fontWeight: 600, color: "#0f766e" }}>{h3[1]}</h4>;
  }

  if (trimmed.startsWith("- ")) {
    const content = trimmed.slice(2);
    const parts = content.split(/\*\*(.*?)\*\*/g);
    return (
      <div key={index} style={{ padding: "4px 8px", fontSize: 12, color: "#334155", display: "flex", gap: 6, alignItems: "baseline" }}>
        <span style={{ color: "#0f766e", fontWeight: 700 }}>•</span>
        {parts.map((part, i) =>
          i % 2 === 1
            ? <span key={i} style={{ fontWeight: 600, color: "#172026" }}>{part}</span>
            : <span key={i}>{part}</span>
        )}
      </div>
    );
  }

  return <p key={index} style={{ margin: "4px 0", fontSize: 12, color: "#475569", lineHeight: 1.6 }}>{trimmed}</p>;
}

function getCardBackground(title: string): string {
  const colors: Record<string, string> = {
    "目标画像": "#f0fdf4",
    "关联统计": "#eff6ff",
    "目标偏好": "#fef2f2",
    "行为模式": "#f8fafc",
    "MITRE ATT&CK 技术映射": "#f5f3ff",
    "关键关系": "#fff7ed",
  };
  return colors[title] ?? "#f8faf9";
}

export default function ReportPanel({ target }: ReportPanelProps) {
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchReport(target).then(setReport).catch(() => {}).finally(() => setLoading(false));
  }, [target]);

  if (loading) return <section className="report-panel"><p style={{ padding: 16, color: "#64748b", fontSize: 13 }}>加载报告...</p></section>;
  if (!report) return null;

  const { sections, footer } = parseMarkdown(report.markdown);

  return (
    <section className="report-panel">
      <div className="panel-heading">
        <h2>{report.title}</h2>
      </div>
      <div style={{ padding: "12px 16px", maxHeight: 420, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
        {sections.map((section) => (
          <div
            key={section.title}
            style={{
              background: getCardBackground(section.title),
              borderRadius: 8,
              border: "1px solid #e2e8e6",
              padding: "10px 12px",
            }}
          >
            <h3 style={{ margin: "0 0 6px", fontSize: 14, fontWeight: 600, color: "#0f766e" }}>
              {section.title}
            </h3>
            {section.lines.map((line, i) => renderLine(line, i))}
          </div>
        ))}
        {footer.length > 0 && (
          <div style={{ textAlign: "center", fontSize: 11, color: "#94a3b8", lineHeight: 1.6, padding: "4px 0" }}>
            {footer.map((f, i) => <p key={i} style={{ margin: 0 }}>{f}</p>)}
          </div>
        )}
      </div>
    </section>
  );
}