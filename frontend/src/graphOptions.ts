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
}

export function buildGraphOption(
  payload: GraphPayload,
  opts?: BuildOptions,
): EChartsOption {
  const highlightSet = new Set(opts?.highlightNodeIds ?? []);

  const categories = Array.from(
    new Set(payload.nodes.map((node) => node.type)),
  ).map((type) => ({
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
        const tag =
          data._raw?.validation_status === "invalid" ? "【系统推断】" : "";
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
          show: true,
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
        },
        data: payload.nodes.map((node) => ({
          id: node.id,
          name: node.name,
          type: node.type,
          value: Number(node.confidence.toFixed(2)),
          category: node.type,
          symbolSize:
            node.type === "APT_GROUP" ? 56 : node.type === "COUNTRY" ? 48 : 36,
          itemStyle: {
            color: TYPE_COLORS[node.type] ?? "#64748b",
            borderColor: highlightSet.has(node.id) ? "#f59e0b" : "transparent",
            borderWidth: highlightSet.has(node.id) ? 3 : 0,
            opacity:
              highlightSet.size > 0 && !highlightSet.has(node.id) ? 0.25 : 1,
          },
          label: {
            show: true,
            fontSize:
              highlightSet.size > 0 && !highlightSet.has(node.id) ? 10 : 12,
            color: "#172026",
          },
          _raw: node,
        })),
        links: payload.edges.map((edge) => {
          const pathEdge =
            highlightSet.has(edge.source) && highlightSet.has(edge.target);
          const isInfer = edge.validation_status === "invalid";
          return {
            source: edge.source,
            target: edge.target,
            name: edge.label,
            lineStyle:
              highlightSet.size > 0
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
