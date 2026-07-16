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
