import type { EChartsOption } from "echarts";

import type { GraphPayload } from "./types";

const TYPE_COLORS: Record<string, string> = {
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

export interface BuildOptions {
  highlightNodeIds?: string[];
  searchNodeId?: string | null;
}

export function buildGraphOption(payload: GraphPayload, opts?: BuildOptions): EChartsOption {
  const highlightSet = new Set(opts?.highlightNodeIds ?? []);
  const searchNodeId: string | null | undefined = opts?.searchNodeId;

  const categories = Array.from(new Set(payload.nodes.map((node) => node.type))).map((type) => ({
    name: type,
    itemStyle: { color: TYPE_COLORS[type] ?? "#64748b" },
  }));

  return {
    color: categories.map((category) => category.itemStyle.color),
    tooltip: {
      trigger: "item",
      formatter: (params: unknown) => {
        const data = (
          params as {
            data?: {
              name?: string;
              type?: string;
              value?: number;
              _raw?: { validation_status?: string };
            };
          }
        ).data;
        if (!data?.name) {
          return "";
        }
        const tag = data._raw?.validation_status === "invalid" ? "【系统推断】" : "";
        return `${tag}${data.name}<br/>类型：${data.type ?? "关系"}<br/>置信度：${data.value ?? "-"}`;
      },
    },
    legend: {
      top: 8,
      left: 8,
      data: categories,
    },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        categories,
        force: {
          repulsion: 260,
          edgeLength: 130,
        },
        label: {
          show: true,
          position: "right",
          formatter: "{b}",
          fontSize: 12,
        },
        edgeLabel: {
          show: false,
          formatter: "{b}",
          fontSize: 11,
          color: "#475569",
        },
        lineStyle: {
          color: "#94a3b8",
          curveness: 0.16,
          width: 1.4,
        },
        emphasis: {
          focus: "adjacency",
          lineStyle: {
            width: 2.4,
          },
          edgeLabel: {
            show: true,
            formatter: "{b}",
            fontSize: 11,
          },
        },
        data: payload.nodes.map((node) => {
          const isHL = highlightSet.has(node.id);
          const isSN = searchNodeId === node.id;
          const sz = node.type === "APT_GROUP" ? 56 : node.type === "COUNTRY" ? 48 : 36;
          const dim = (highlightSet.size > 0 || searchNodeId) && !isHL && !isSN;
          return {
            id: node.id,
            name: node.name,
            type: node.type,
            value: Number(node.confidence.toFixed(2)),
            category: node.type,
            symbolSize: isSN ? Math.round(sz * 1.5) : sz,
            itemStyle: {
              color: TYPE_COLORS[node.type] ?? "#64748b",
              borderColor: isSN ? "#f59e0b" : isHL ? "#f59e0b" : "transparent",
              borderWidth: isSN ? 4 : isHL ? 3 : 0,
              shadowBlur: isSN ? 20 : 0,
              shadowColor: isSN ? "rgba(245,158,11,0.7)" : "transparent",
              opacity: dim ? 0.12 : 1,
            },
            label: {
              show: true,
              fontSize: isSN ? 16 : dim ? 10 : 12,
              color: isSN ? "#f59e0b" : "#172026",
              fontWeight: isSN ? 700 : 400,
            },
            _raw: node,
          };
        }),
        links: payload.edges.map((edge) => {
          const isSearched = !!searchNodeId;
          const pathEdge =
            (highlightSet.has(edge.source) && highlightSet.has(edge.target)) ||
            (isSearched && (edge.source === searchNodeId || edge.target === searchNodeId));
          const isInfer = edge.validation_status === "invalid";
          return {
            source: edge.source,
            target: edge.target,
            name: edge.label,
            lineStyle:
              highlightSet.size > 0 || isSearched
                ? { opacity: pathEdge ? 1 : 0.08 }
                : isInfer
                  ? { opacity: 0.4, type: "dashed" as const, color: "#9ca3af" }
                  : undefined,
            _raw: edge,
          };
        }),
      },
    ],
  };
}
