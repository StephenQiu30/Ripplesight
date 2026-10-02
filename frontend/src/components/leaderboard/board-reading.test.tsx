// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BoardReading } from "./board-reading";

afterEach(cleanup);

const run: HotKeyAPI.RunView = {
  id: "00000000-0000-4000-8000-000000000001",
  methodology_version: "2026.09-public-consensus-v15",
  generated_at: "2026-10-02T01:00:00Z",
  calculated_at: "2026-10-02T01:00:00Z",
  fingerprint: "fixed-evidence",
  fx: null,
};

const board: HotKeyAPI.BoardView = {
  run,
  board: {
    key: "overall",
    name: "综合榜",
    description: "固定预算的公开共识",
    how_to_read: "先看排名，再看证据。",
    source_count: 4,
    operator_count: 3,
    model_count: 12,
    solver_optimal: true,
    connected_components: 1,
    score_definition: "固定锚点支持指数",
    display_method: "kemeny-order-support-1.0",
    max_optimization_gap: 0,
    observed_weighted_agreement: 0.8,
  },
  tabs: [{ key: "overall", name: "综合榜", href: "/leaderboard" }],
  entries: [
    {
      rank: 7,
      score: 69.4,
      model: {
        slug: "fixed-model",
        name: "Fixed Model",
        provider: "测试运营方",
        released_at: null,
        brand: { src: null, monogram: "F" },
      },
      source_count: 4,
      operator_count: 3,
      coverage: 0.55,
      confidence: "LOW",
      stability: {
        from_rank: 3,
        to_rank: 10,
        fixed_from: 5,
        fixed_to: 9,
        scenarios: 8,
        sensitive: true,
        incomplete: 0,
        ordinal_rank: 8,
        unavailable: 2,
      },
      price: null,
      access: { domestic: true, weights_url: null },
    },
  ],
  filter_entries: [],
  pending: [],
};

describe("model leaderboard reading", () => {
  it("preserves the published rank after filtering and marks missing prices", () => {
    render(<BoardReading data={board} domestic openWeights={false} />);
    expect(
      screen.getByRole("link", { name: "Fixed Model" }).getAttribute("href"),
    ).toBe("/leaderboard/models/fixed-model");
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("55%")).toBeTruthy();
    expect(screen.getByText("对证据变化敏感")).toBeTruthy();
    expect(screen.getByText("暂无公开价格")).toBeTruthy();
    expect(screen.getByText(/保留原排名/)).toBeTruthy();
    expect(
      screen
        .getByRole("checkbox", { name: "国内模型" })
        .hasAttribute("checked"),
    ).toBe(true);
    expect(screen.queryByText("¥0")).toBeNull();
  });

  it("renders a valid empty filter as an empty result with reset", () => {
    render(
      <BoardReading data={{ ...board, entries: [] }} domestic openWeights />,
    );
    expect(screen.getByText("当前筛选没有符合条件的模型")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "清除筛选" }).getAttribute("href"),
    ).toBe("/leaderboard");
  });
});
