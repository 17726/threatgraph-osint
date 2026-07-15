import { afterEach, describe, expect, it, vi } from "vitest";

import { buildGraphQuery, fetchGraph, fetchReport, runPipeline } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("runPipeline", () => {
  it("提交文档后轮询等待后台流水线完成", async () => {
    let callCount = 0;
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/documents/import")) {
        callCount++;
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: { job_id: "job-1", status: "pending" },
          }),
        };
      }
      if (url.includes("/pipeline/status")) {
        callCount++;
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: {
              job_id: "job-1",
              status: "succeeded",
              result: {
                extract: {
                  summary: {
                    canonical_entities: 10,
                    canonical_relations: 5,
                    evidence: 12,
                    behavior_patterns: 3,
                    extracted_entities: 15,
                    extracted_relations: 7,
                  },
                },
              },
            },
          }),
        };
      }
      return { ok: false };
    });
    vi.stubGlobal("fetch", fetchMock);
    const document = new File([JSON.stringify({ doc_id: "apt28_001" })], "apt28_001.json", {
      type: "application/json",
    });

    const result = await runPipeline(document);

    expect(result.status).toBe("succeeded");
    expect(result.canonical_entities).toBe(10);
    expect(result.canonical_relations).toBe(5);
    expect(result.evidence).toBe(12);
    // 验证 POST 和 GET 都被调用了
    expect(callCount).toBeGreaterThanOrEqual(2);
  });

  it("导入重复文档时跳过流水线", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { doc_id: "apt28_001", status: "skipped" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const document = new File([JSON.stringify({ doc_id: "apt28_001" })], "apt28_001.json");
    const result = await runPipeline(document);
    expect(result.status).toBe("skipped");
  });
});

describe("fetchGraph", () => {
  it("将图谱过滤条件传递给后端查询", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { schema_version: "1.0", nodes: [], edges: [], evidence: [] },
        timestamp: "2026-01-01T00:00:00Z",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchGraph("APT28", {
      entity_types: ["TECHNIQUE", "COUNTRY"],
      relation_types: ["USES"],
      tags: ["apt"],
      source_types: ["news"],
      languages: ["en"],
      first_seen_from: "2015-01-01",
      last_seen_to: "2026-01-01",
      min_confidence: 0.8,
      depth: 2,
      limit: 100,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(
        "/api/v1/graph?target=APT28&depth=2&entity_types=TECHNIQUE%2CCOUNTRY&relation_types=USES&tags=apt&source_types=news&languages=en&first_seen_from=2015-01-01&last_seen_to=2026-01-01&min_confidence=0.8&limit=100",
      ),
    );
  });

  it("默认演示目标无过滤条件请求失败时抛出错误", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("后端不可用"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchGraph("APT28")).rejects.toThrow("后端不可用");
  });

  it("带过滤条件请求失败时抛出错误而不是回退到 mock", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("后端不可用")));

    await expect(fetchGraph("APT28", { entity_types: ["TECHNIQUE"] })).rejects.toThrow("后端不可用");
  });

  it("地区筛选保留组织 target 且不发送未知后端字段", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { schema_version: "1.0", nodes: [], edges: [], evidence: [] },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const query = buildGraphQuery("APT28", "", "Ukraine");
    await fetchGraph(query.target, query.filters);

    expect(fetchMock).toHaveBeenCalledWith(expect.not.stringContaining("region="));
  });

  it("非默认目标请求失败时抛出错误而不是回退到 mock", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("后端不可用")));

    await expect(fetchGraph("Lazarus")).rejects.toThrow("后端不可用");
  });

  it("将技术和地区筛选映射为实体 ID 过滤并保留组织 target", () => {
    expect(buildGraphQuery("APT28", "technique:t1566", "country:ukraine")).toEqual({
      target: "APT28",
      filters: { entity_ids: ["technique:t1566", "country:ukraine"] },
    });
    expect(buildGraphQuery("APT28", "TECHNIQUE", "")).toEqual({
      target: "APT28",
      filters: { entity_ids: ["TECHNIQUE"] },
    });
    expect(buildGraphQuery("APT28", "", "Ukraine")).toEqual({
      target: "APT28",
      filters: { entity_ids: ["Ukraine"] },
    });
    expect(buildGraphQuery("APT28", "", "")).toEqual({
      target: "APT28",
      filters: {},
    });
  });

  it("图谱请求失败时向上抛出错误，不返回 Mock 数据", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("后端不可用")));

    await expect(fetchGraph("APT28")).rejects.toThrow("后端不可用");
  });

  it("报告请求失败时向上抛出错误，不返回 Mock 数据", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("后端不可用")));

    await expect(fetchReport("APT28")).rejects.toThrow("后端不可用");
  });
});
