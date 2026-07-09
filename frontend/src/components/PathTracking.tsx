import { useEffect, useState, useMemo } from "react";
import { fetchPath } from "../api/client";
import type { GraphNode } from "../types";

interface PathTrackingProps {
  nodes: GraphNode[];
  onPathFound: (nodeIds: string[]) => void;
  onPathClear: () => void;
}

export default function PathTracking({
  nodes,
  onPathFound,
  onPathClear,
}: PathTrackingProps) {
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [traversing, setTraversing] = useState(false);

  const nodeIds = useMemo(() => new Set(nodes.map((n) => n.id)), [nodes]);

  useEffect(() => {
    setFromId((prev) => (prev && nodeIds.has(prev) ? prev : ""));
    setToId((prev) => (prev && nodeIds.has(prev) ? prev : ""));
  }, [nodeIds]);

  const handleTrace = async () => {
    if (!fromId || !toId || fromId === toId) {
      alert("请选择两个不同的节点");
      return;
    }
    try {
      setTraversing(true);
      const result = await fetchPath(fromId, toId);
      if (!result.nodes || result.nodes.length === 0) {
        alert("未找到路径，路径追踪需要后端支持");
        return;
      }
      const ids = result.nodes.map((n) => n.id);
      onPathFound(ids);
    } catch {
      alert("路径追踪失败");
    } finally {
      setTraversing(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 20px",
        background: "#ffffff",
        borderTop: "1px solid #d7dfdd",
        flexShrink: 0,
        fontSize: 12,
        color: "#64748b",
      }}
    >
      <span>路径追踪:</span>
      <select
        value={fromId}
        disabled={traversing}
        onChange={(e) => setFromId(e.target.value)}
        style={{
          padding: "4px 8px",
          background: "#ffffff",
          border: "1px solid #d7dfdd",
          borderRadius: 4,
          color: "#172026",
          fontSize: 12,
          outline: "none",
          maxWidth: 180,
        }}
      >
        <option value="">起点</option>
        {nodes.map((n) => (
          <option key={n.id} value={n.id}>
            {n.name}
          </option>
        ))}
      </select>
      <span style={{ color: "#0f766e", fontWeight: 700 }}>→</span>
      <select
        value={toId}
        disabled={traversing}
        onChange={(e) => setToId(e.target.value)}
        style={{
          padding: "4px 8px",
          background: "#ffffff",
          border: "1px solid #d7dfdd",
          borderRadius: 4,
          color: "#172026",
          fontSize: 12,
          outline: "none",
          maxWidth: 180,
        }}
      >
        <option value="">终点</option>
        {nodes.map((n) => (
          <option key={n.id} value={n.id}>
            {n.name}
          </option>
        ))}
      </select>
      <button
        onClick={handleTrace}
        disabled={traversing}
        style={{
          padding: "4px 12px",
          opacity: traversing ? 0.5 : 1,
          cursor: traversing ? "not-allowed" : "pointer",
          background: "#f4f7f6",
          border: "1px solid #d7dfdd",
          borderRadius: 8,
          color: "#172026",
          fontSize: 12,
        }}
      >
        {traversing ? "追踪中..." : "追踪"}
      </button>
      <button
        onClick={onPathClear}
        style={{
          padding: "4px 12px",
          cursor: "pointer",
          background: "#f4f7f6",
          border: "1px solid #d7dfdd",
          borderRadius: 8,
          color: "#172026",
          fontSize: 12,
        }}
      >
        清除
      </button>
    </div>
  );
}
