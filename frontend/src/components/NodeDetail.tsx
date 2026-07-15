import { useState, useEffect } from "react";
import { fetchEntity } from "../api/client";
import type { EntityDetail } from "../types";

const TYPE_COLOR: Record<string, string> = {
  APT_GROUP: "#0f766e",
  MALWARE: "#be123c",
  TOOL: "#b45309",
  CVE: "#7c3aed",
  TECHNIQUE: "#0369a1",
  PERSON: "#db2777",
  COUNTRY: "#15803d",
  INDUSTRY: "#0d9488",
  CAMPAIGN: "#6d28d9",
  ORGANIZATION: "#4b5563",
};

interface NodeDetailProps {
  entityId: string | null;
  onClose: () => void;
}

export default function NodeDetail({ entityId, onClose }: NodeDetailProps) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);

  useEffect(() => {
    if (!entityId) { setDetail(null); return; }
    fetchEntity(entityId).then(setDetail).catch(() => setDetail(null));
  }, [entityId]);

  if (!detail) return null;

  const rows: [string, string][] = [
    ["名称", detail.name],
    ["别名", detail.aliases?.join(", ") || "-"],
    ["描述", detail.description || "-"],
    ["置信度", String(detail.confidence ?? "-")],
    ["来源数", String(detail.source_count ?? "-")],
    ["首次发现", detail.first_seen ?? "-"],
    ["最近活跃", detail.last_seen ?? "-"],
    ["标签", detail.tags?.join(", ") || "-"],
  ];

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        right: 0,
        width: 340,
        height: "100%",
        background: "#ffffff",
        borderLeft: "1px solid #d7dfdd",
        zIndex: 30,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 8,
          padding: 16,
          borderBottom: "1px solid #e2e8e6",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
            {detail.name}
          </h3>
          <span
            style={{
              display: "inline-block",
              marginTop: 4,
              fontSize: 11,
              padding: "2px 8px",
              borderRadius: 4,
              color: "#fff",
              background: TYPE_COLOR[detail.type] || "#64748b",
            }}
          >
            {detail.type}
          </span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "#64748b",
            fontSize: 20,
            cursor: "pointer",
            lineHeight: 1,
            padding: "0 4px",
          }}
        >
          &times;
        </button>
      </div>
      <div style={{ padding: 16, overflowY: "auto", flex: 1 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <td
                  style={{
                    padding: "6px 0",
                    borderBottom: "1px solid #e2e8e6",
                    fontSize: 13,
                    verticalAlign: "top",
                    color: "#64748b",
                    width: 80,
                    whiteSpace: "nowrap",
                    fontWeight: 500,
                  }}
                >
                  {k}
                </td>
                <td
                  style={{
                    padding: "6px 0",
                    borderBottom: "1px solid #e2e8e6",
                    fontSize: 13,
                    verticalAlign: "top",
                    color: "#172026",
                    wordBreak: "break-all",
                  }}
                >
                  {v}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
