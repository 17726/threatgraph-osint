// @vitest-environment jsdom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CrawlerModal from "./CrawlerModal";

describe("CrawlerModal", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              success: true,
              data: { crawl_run_id: "crawl_test_001", status: "pending" },
            }),
            { status: 202 },
          ),
        )
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              success: true,
              data: {
                crawl_run_id: "crawl_test_001",
                keyword: "Lazarus",
                status: "succeeded",
                items_found: 12,
                items_promoted: 10,
                items_imported: 8,
                items_skipped: 2,
                items_failed: 0,
                document_ids: ["lazarus_001"],
                workspace_cleaned: true,
                error_message: null,
              },
            }),
            { status: 200 },
          ),
        ),
    );
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("renders the organization, sources, and filter controls", () => {
    render(
      <CrawlerModal
        open
        target="APT28"
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "采集情报" })).toBeTruthy();
    expect(
      (screen.getByRole("combobox", { name: "目标组织" }) as HTMLSelectElement)
        .value,
    ).toBe("APT28");
    expect((screen.getByLabelText("奇安信") as HTMLInputElement).checked).toBe(
      true,
    );
    expect(
      (
        screen.getByRole("checkbox", {
          name: "启用 LLM 相关性过滤",
        }) as HTMLInputElement
      ).checked,
    ).toBe(false);
    expect(screen.queryByText("COLLECT / DEMO MODE")).toBeNull();
    expect(screen.queryByText("bit 0")).toBeNull();
    expect(screen.queryByText("sources = 1")).toBeNull();
    expect(screen.queryByText("仅演示采集和导入流程")).toBeNull();
    expect(screen.queryByText("当前为交互演示")).toBeNull();
    expect(screen.queryByText("建议 1-20 篇，避免一次任务过重。")).toBeNull();
  });

  it("updates the selected sources when sources change", () => {
    render(
      <CrawlerModal
        open
        target="APT28"
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    fireEvent.click(screen.getAllByLabelText("FreeBuf")[0]);

    expect(
      (screen.getAllByLabelText("FreeBuf")[0] as HTMLInputElement).checked,
    ).toBe(true);
  });

  it("creates a task, polls backend, and shows real completion statistics", async () => {
    const onSuccess = vi.fn();
    render(
      <CrawlerModal
        open
        target="Lazarus"
        onClose={vi.fn()}
        onSuccess={onSuccess}
      />,
    );

    fireEvent.click(screen.getAllByRole("button", { name: "开始采集" })[0]);
    expect(screen.getByText("正在提交采集任务")).toBeTruthy();

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("采集任务完成")).toBeTruthy();
    expect(screen.getByText("发现 12 篇 · 清洗 10 篇 · 导入 8 篇")).toBeTruthy();
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(screen.queryByText("演示任务未调用后端接口")).toBeNull();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/crawl/runs"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});
