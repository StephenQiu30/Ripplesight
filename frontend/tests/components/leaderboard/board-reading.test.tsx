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
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe(
      "69.4",
    );
    expect(screen.queryByRole("columnheader", { name: "变化" })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "上下文" })).toBeNull();
    expect(screen.getByText("55%")).toBeTruthy();
    expect(screen.getByText("对证据变化敏感")).toBeTruthy();
    expect(screen.getByText("暂无公开价格")).toBeTruthy();
    expect(screen.getByText(/保留原排名/)).toBeTruthy();
    expect(
      screen
        .getByRole("checkbox", { name: "国内模型" })
        .getAttribute("aria-checked"),
    ).toBe("true");
    expect(screen.queryByText("¥0")).toBeNull();
  });

  it("renders a valid empty filter as an empty result with reset", () => {
    render(
      <BoardReading data={{ ...board, entries: [] }} domestic openWeights />,
    );
    expect(screen.getByText("当前筛选没有符合条件的模型")).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "当前筛选没有符合条件的模型",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "清除筛选" }).getAttribute("href"),
    ).toBe("/leaderboard");
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
