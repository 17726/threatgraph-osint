import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchGraph, fetchReport, runPipeline } from "./client";

describe("API 客户端", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("图谱请求失败时向上抛出错误，不返回 Mock 数据", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("后端不可用")));

    await expect(fetchGraph("APT28")).rejects.toThrow("后端不可用");
  });

  it("报告请求失败时向上抛出错误，不返回 Mock 数据", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("后端不可用")));

    await expect(fetchReport("APT28")).rejects.toThrow("后端不可用");
  });

  it("导入文档后轮询后台流水线直到完成", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/documents/import")) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: { doc_id: "apt28_001", job_id: "job-1", status: "imported" },
          }),
        };
      }
      if (url.includes("/pipeline/status/job-1")) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: {
              job_id: "job-1",
              status: "succeeded",
              result: {
                canonical_entities: 10,
                canonical_relations: 5,
                evidence: 12,
                behavior_patterns: 3,
                extracted_entities: 15,
                extracted_relations: 7,
              },
            },
          }),
        };
      }
      throw new Error(`未预期请求: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const document = new File(
      [JSON.stringify({ doc_id: "apt28_001" })],
      "apt28_001.json",
      { type: "application/json" },
    );

    const result = await runPipeline(document, { intervalMs: 0 });

    expect(result.status).toBe("succeeded");
    expect(result.canonical_entities).toBe(10);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
