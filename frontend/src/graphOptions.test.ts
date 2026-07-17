import { describe, expect, it } from "vitest";

import * as graphOptions from "./graphOptions";
import type { GraphPayload } from "./types";

const payload: GraphPayload = {
  schema_version: "1.0",
  nodes: [
    {
      id: "apt_group:apt28",
      name: "APT28",
      type: "APT_GROUP",
      aliases: [],
      description: "",
      confidence: 0.96,
      source_count: 2,
      first_seen: null,
      last_seen: null,
      tags: [],
      evidence_ids: [],
    },
    {
      id: "malware:x-agent",
      name: "X-Agent",
      type: "MALWARE",
      aliases: [],
      description: "",
      confidence: 0.9,
      source_count: 1,
      first_seen: null,
      last_seen: null,
      tags: [],
      evidence_ids: [],
    },
  ],
  edges: [
    {
      id: "rel:apt28:uses:x-agent",
      source: "apt_group:apt28",
      target: "malware:x-agent",
      type: "USES",
      label: "使用",
      confidence: 0.91,
      source_count: 1,
      evidence_count: 1,
      first_seen: null,
      last_seen: null,
      validation_status: "valid",
      evidence_ids: [],
    },
  ],
  evidence: [],
};

describe("3D 图谱数据适配", () => {
  it("提供独立的 3D 数据构建函数", () => {
    expect(graphOptions).toHaveProperty("buildGraph3DData");
  });

  it("复制 API 数据并生成搜索高亮所需的三维样式", () => {
    const result = graphOptions.buildGraph3DData(payload, {
      searchNodeId: "apt_group:apt28",
    });

    expect(result.nodes).toHaveLength(2);
    expect(result.nodes[0]).not.toBe(payload.nodes[0]);
    expect(result.nodes[0]).toMatchObject({
      id: "apt_group:apt28",
      color: "#f59e0b",
      val: 18,
      _raw: payload.nodes[0],
    });
    expect(result.nodes[1]).toMatchObject({
      id: "malware:x-agent",
      color: "#cbd5e1",
      val: 6,
      _raw: payload.nodes[1],
    });
    expect(result.links[0]).toMatchObject({
      id: "rel:apt28:uses:x-agent",
      source: "apt_group:apt28",
      target: "malware:x-agent",
      name: "使用",
      color: "#f59e0b",
      width: 3,
      particles: 3,
      _raw: payload.edges[0],
    });
    expect(payload.nodes[0]).not.toHaveProperty("color");
    expect(payload.edges[0].source).toBe("apt_group:apt28");
  });
});

describe("2D 图谱漫游", () => {
  it("允许在图谱平移后的整块画布继续拖拽和缩放", () => {
    const option = graphOptions.buildGraphOption(payload);
    const series = Array.isArray(option.series) ? option.series[0] : option.series;

    expect(series).toMatchObject({
      type: "graph",
      roam: true,
      roamTrigger: "global",
    });
  });
});

describe("3D 点击聚焦", () => {
  it("强调点击主体和相邻关系并调暗无关节点", () => {
    const focusPayload: GraphPayload = {
      ...payload,
      nodes: [
        ...payload.nodes,
        {
          ...payload.nodes[1],
          id: "country:ukraine",
          name: "Ukraine",
          type: "COUNTRY",
        },
        {
          ...payload.nodes[1],
          id: "campaign:unrelated",
          name: "Unrelated",
          type: "CAMPAIGN",
        },
      ],
      edges: [
        ...payload.edges,
        {
          ...payload.edges[0],
          id: "rel:ukraine:unrelated",
          source: "country:ukraine",
          target: "campaign:unrelated",
        },
      ],
    };

    const result = graphOptions.buildGraph3DData(focusPayload, {
      focusNodeId: "apt_group:apt28",
    });

    expect(result.nodes[0].color).toBe("#f59e0b");
    expect(result.nodes[1].color).toBe("#be123c");
    expect(result.nodes[2].color).toBe("#cbd5e1");
    expect(result.links[0]).toMatchObject({ color: "#f59e0b", width: 3, particles: 3 });
    expect(result.links[1]).toMatchObject({ color: "#e2e8f0", width: 1.2, particles: 0 });
  });
});

describe("2D 图谱关系 tooltip", () => {
  it("映射关系类型、置信度和稳定标识", () => {
    const option = graphOptions.buildGraphOption(payload) as {
      series: Array<{
        links?: Array<Record<string, unknown>>;
      }>;
    };
    const relation = option.series[0].links?.[0];

    expect(relation).toMatchObject({
      id: "rel:apt28:uses:x-agent",
      name: "使用",
      type: "USES",
      value: 0.91,
      _raw: payload.edges[0],
    });
  });

  it("悬浮关系时显示真实类型和置信度", () => {
    const option = graphOptions.buildGraphOption(payload) as {
      tooltip: {
        formatter: (params: unknown) => string;
      };
    };
    const relation = {
      name: "攻击目标",
      type: "TARGETS",
      value: 0.95,
      _raw: { validation_status: "valid" },
    };

    const tooltip = option.tooltip.formatter({ data: relation });

    expect(tooltip).toBe("攻击目标<br/>类型：TARGETS<br/>置信度：0.95");
  });
});
