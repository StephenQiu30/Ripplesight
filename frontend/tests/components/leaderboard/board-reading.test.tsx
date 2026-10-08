// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BoardReading } from "@/components/leaderboard/board-reading";

afterEach(cleanup);

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { board } from "./fixtures";

describe("model leaderboard reading", () => {
  it("preserves the published rank after filtering and marks missing prices", () => {
    render(<BoardReading data={board} domestic openWeights={false} />);
    expect(
      screen
        .getAllByRole("link", { name: "Fixed Model" })[0]
        .getAttribute("href"),
    ).toBe("/leaderboard/models/fixed-model");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(
      screen.getByRole("heading", { level: 1, name: "模型榜" }),
    ).toBeTruthy();
    expect(screen.getByText("07")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe(
      "69.4",
    );
    expect(screen.getByRole("columnheader", { name: "变化" })).toBeTruthy();
    expect(screen.getByTitle("暂无上期排名对比").textContent).toBe("—");
    expect(screen.queryByRole("columnheader", { name: "上下文" })).toBeNull();
    expect(screen.queryByText("官方价格")).toBeNull();
    expect(screen.getByRole("heading", { name: "本周变化" })).toBeTruthy();
    expect(screen.queryByText("¥0")).toBeNull();
  });

  it("does not fabricate a ranking for an empty applied filter", () => {
    render(
      <BoardReading data={{ ...board, entries: [] }} domestic openWeights />,
    );
    expect(
      screen.getByRole("status", { name: "暂无可展示的已发布模型" }),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(
      screen.getByRole("radio", { name: "开源" }).getAttribute("aria-checked"),
    ).toBe("true");
  });
  it("renders an unfiltered empty publication without a fake ranking", () => {
    render(
      <BoardReading
        data={{ ...board, entries: [] }}
        domestic={false}
        openWeights={false}
      />,
    );
    expect(
      screen.getByRole("status", { name: "暂无可展示的已发布模型" }),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(
      screen.getByRole("heading", { level: 2, name: "暂无可展示的已发布模型" }),
    ).toBeTruthy();
  });
});
