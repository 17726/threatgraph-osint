import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchGraph, fetchReport, runPipeline } from "./client";

describe("API 客户端", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("图谱请求失败时向上抛出错误，不返回 Mock 数据", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("后端不可用")));

    await expect(fetchGraph("APT28", 2)).rejects.toThrow("后端不可用");
  });

  it("图谱请求携带展示深度", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { schema_version: "1.0", nodes: [], edges: [], evidence: [] },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await fetchGraph("APT28", 4);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/graph\?target=APT28&depth=4$/),
      { signal: undefined },
    );
  });

  it("报告请求失败时向上抛出错误，不返回 Mock 数据", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("后端不可用")));

    await expect(fetchReport("APT28")).rejects.toThrow("后端不可用");
  });

  it("一跳查询调用语义明确的 neighbors 接口", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: { schema_version: "1.0", nodes: [], edges: [], evidence: [] },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = (await import("./client")) as typeof import("./client") & {
      fetchNeighbors?: (
        entityId: string,
        depth: number,
        options?: { signal?: AbortSignal },
      ) => Promise<unknown>;
    };

    expect(client.fetchNeighbors).toBeTypeOf("function");
    const controller = new AbortController();
    await client.fetchNeighbors?.("technique:t1566", 3, {
      signal: controller.signal,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(
        /\/api\/v1\/graph\/neighbors\?entity_id=technique%3At1566&depth=3$/,
      ),
      { signal: controller.signal },
    );
  });

  it("导入文档后显式提交后台流水线并轮询直到完成", async () => {
    const onProgress = vi.fn();
    const fetchMock = vi
      .fn()
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/documents/import")) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              data: { doc_id: "apt28_001", status: "imported" },
            }),
          };
        }
        if (url.includes("/pipeline/run")) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              data: { job_id: "job-1", status: "pending" },
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
                progress: {
                  phase: "completed",
                  current: 1,
                  total: 1,
                  percent: 100,
                  message: "流水线执行完成",
                  doc_id: "apt28_001",
                  updated_at: "2026-07-17T12:00:00+08:00",
                },
                events: [
                  {
                    job_id: "job-1",
                    sequence: 1,
                    level: "info",
                    phase: "completed",
                    message: "流水线执行完成",
                    current: 1,
                    total: 1,
                    doc_id: "apt28_001",
                    details: {},
                    created_at: "2026-07-17T12:00:00+08:00",
                  },
                ],
                result: {
                  doc_ids: ["apt28_001"],
                  summaries: [
                    {
                      canonical_entities: 10,
                      canonical_relations: 5,
                      evidence: 12,
                      behavior_patterns: 3,
                      extracted_entities: 15,
                      extracted_relations: 7,
                    },
                  ],
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
      {
        type: "application/json",
      },
    );

    const result = await runPipeline(document, {
      extractionMode: "reviewed",
      intervalMs: 0,
      onProgress,
    });

    expect(result.status).toBe("succeeded");
    expect(result.canonical_entities).toBe(10);
    expect(onProgress).toHaveBeenCalledWith(
      expect.objectContaining({
        job_id: "job-1",
        status: "succeeded",
        progress: expect.objectContaining({ percent: 100 }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const pipelineRequest = fetchMock.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(String(pipelineRequest.body))).toEqual({
      doc_id: "apt28_001",
      extraction_mode: "reviewed",
    });
  });

  it("重复文档仍可显式重新运行流水线", async () => {
    const requestedUrls: string[] = [];
    const fetchMock = vi
      .fn()
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        requestedUrls.push(url);
        if (url.includes("/documents/import")) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              data: { doc_id: "apt28_001", status: "skipped" },
            }),
          };
        }
        if (url.includes("/pipeline/run")) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              data: { job_id: "job-2", status: "pending" },
            }),
          };
        }
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: { job_id: "job-2", status: "succeeded", result: {} },
          }),
        };
      });
    vi.stubGlobal("fetch", fetchMock);
    const document = new File(
      [JSON.stringify({ doc_id: "apt28_001" })],
      "apt28_001.json",
    );

    await runPipeline(document, { intervalMs: 0 });

    expect(requestedUrls.some((url) => url.includes("/pipeline/run"))).toBe(
      true,
    );
  });

  it("导入失败时显示后端统一错误消息", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({
          success: false,
          error: {
            code: "ERR_VALIDATION",
            message: "content_hash 与正文不一致",
          },
        }),
      }),
    );
    const document = new File(["{}"], "invalid.json");

    await expect(runPipeline(document)).rejects.toThrow(
      "content_hash 与正文不一致",
    );
  });

  it("取消信号会终止状态轮询", async () => {
    const controller = new AbortController();
    let statusCalls = 0;
    const fetchMock = vi
      .fn()
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/documents/import")) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              data: { doc_id: "apt28_001", status: "imported" },
            }),
          };
        }
        if (url.includes("/pipeline/run")) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              data: { job_id: "job-3", status: "pending" },
            }),
          };
        }
        statusCalls += 1;
        controller.abort();
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: { job_id: "job-3", status: "running", result: {} },
          }),
        };
      });
    vi.stubGlobal("fetch", fetchMock);
    const document = new File(
      [JSON.stringify({ doc_id: "apt28_001" })],
      "apt28_001.json",
    );

    await expect(
      runPipeline(document, {
        intervalMs: 0,
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(statusCalls).toBe(1);
  });
});
