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
      vi
        .fn()
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
        llmConfigured
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "流水线" })).toBeTruthy();
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
        llmConfigured
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
        llmConfigured
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
    expect(
      screen.getByText("发现 12 篇 · 清洗 10 篇 · 导入 8 篇"),
    ).toBeTruthy();
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(screen.queryByText("演示任务未调用后端接口")).toBeNull();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/crawl/runs"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("renders collecting progress from backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              success: true,
              data: { crawl_run_id: "crawl_test_002", status: "pending" },
            }),
            { status: 202 },
          ),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              success: true,
              data: {
                crawl_run_id: "crawl_test_002",
                keyword: "APT28",
                status: "running",
                progress: {
                  phase: "collecting",
                  current: 3,
                  total: 10,
                  target: "APT28",
                  source: "FreeBuf",
                  message: "正在采集",
                },
                pipeline: {
                  job_id: "job_pipe_002",
                  status: "running",
                  progress: {
                    phase: "building_graph",
                    current: 0,
                    total: 1,
                    percent: 40,
                    message: "正在写入 SQLite",
                    doc_id: "apt28_108",
                  },
                },
                events: [
                  {
                    sequence: 1,
                    level: "info",
                    phase: "pipeline_building_graph",
                    message: "正在写入 SQLite",
                    doc_id: "apt28_108",
                    source: "FreeBuf",
                    job_id: "job_pipe_002",
                    details: {},
                    created_at: "2026-07-17T12:00:00+08:00",
                  },
                ],
              },
            }),
            { status: 200 },
          ),
        ),
    );

    render(
      <CrawlerModal
        open
        target="APT28"
        llmConfigured
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "开始采集" }));

    await act(async () => {
      await Promise.resolve();
    });

    expect(
      screen.getByText("3/10 正在采集 目标：APT28 来源：FreeBuf"),
    ).toBeTruthy();
    expect(screen.getByText(/采集任务.*crawl_test_002/)).toBeTruthy();
    expect(screen.getByText(/子 Pipeline.*job_pipe_002/)).toBeTruthy();
    expect(screen.getByText("正在写入 SQLite")).toBeTruthy();
  });

  it("keeps the modal action disabled when LLM is not configured", () => {
    render(
      <CrawlerModal
        open
        target="APT28"
        llmConfigured={false}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    expect(screen.getByRole("status").textContent).toContain(
      "需要有效 LLM 配置",
    );
    expect(
      (screen.getByRole("button", { name: "开始采集" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
