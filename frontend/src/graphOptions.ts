import type { EChartsOption } from "echarts";

import type { GraphPayload } from "./types";

const TYPE_COLORS: Record<string, string> = {
  APT_GROUP: "#0f766e",
  TECHNIQUE: "#b45309",
  MALWARE: "#be123c",
  TARGET: "#4f46e5",
  ORGANIZATION: "#0369a1",
};

export function buildGraphOption(payload: GraphPayload): EChartsOption {
  const categories = Array.from(new Set(payload.nodes.map((node) => node.type))).map((type) => ({
    name: type,
    itemStyle: {
      color: TYPE_COLORS[type] ?? "#64748b",
    },
  }));

  return {
    color: categories.map((category) => category.itemStyle.color),
    tooltip: {
      trigger: "item",
      formatter: (params: unknown) => {
        const data = (params as { data?: { name?: string; type?: string; value?: number } }).data;
        if (!data?.name) {
          return "";
        }
        return `${data.name}<br/>类型：${data.type ?? "关系"}<br/>置信度：${data.value ?? "-"}`;
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
          symbolSize: node.type === "APT_GROUP" ? 56 : 42,
          itemStyle: {
            color: TYPE_COLORS[node.type] ?? "#64748b",
          },
        })),
        links: payload.edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          name: edge.label,
        })),
      },
    ],
  };
}
