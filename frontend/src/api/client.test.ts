import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchGraph, fetchReport } from "./client";

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
});
