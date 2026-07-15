// @vitest-environment jsdom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import type { ComponentType } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchEntitySearch } from "../api/client";
import type { GraphNode } from "../types";
import SearchBar from "./SearchBar";

vi.mock("../api/client", () => ({
  fetchEntitySearch: vi.fn(),
}));

const resultNode: GraphNode = {
  id: "apt_group:apt28",
  name: "APT28",
  type: "APT_GROUP",
  aliases: [],
  description: "",
  confidence: 1,
  source_count: 1,
  first_seen: null,
  last_seen: null,
  tags: [],
  evidence_ids: [],
};

type DesiredProps = {
  onSelect: (nodeId: string) => void;
  onClear: () => void;
};

const SearchBarUnderTest = SearchBar as ComponentType<DesiredProps>;

describe("实体搜索框", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(fetchEntitySearch).mockResolvedValue([resultNode]);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("搜索结果使用键盘可操作的按钮", async () => {
    const onSelect = vi.fn();
    render(<SearchBarUnderTest onSelect={onSelect} onClear={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "APT" },
    });
    await act(async () => {
      vi.advanceTimersByTime(250);
      await Promise.resolve();
    });

    const result = screen.getByRole("button", { name: /APT28.*APT_GROUP/ });
    fireEvent.click(result);

    expect(onSelect).toHaveBeenCalledWith("apt_group:apt28");
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe(
      "APT28",
    );
  });

  it("清空搜索输入时通知上层恢复组织图谱", () => {
    const onClear = vi.fn();
    render(<SearchBarUnderTest onSelect={vi.fn()} onClear={onClear} />);

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "APT28" } });
    fireEvent.change(input, { target: { value: "" } });

    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
