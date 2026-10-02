// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { ModelReading } from "@/app/leaderboard/models/[slug]/components/model-reading";

afterEach(cleanup);

it("labels historical evidence and separates excluded and unmeasured sources", () => {
  const data: HotKeyAPI.ModelDetailView = {
    run: {
      id: "00000000-0000-4000-8000-000000000001",
      methodology_version: "2026.09-public-consensus-v15",
      generated_at: "2026-09-30T01:00:00Z",
      calculated_at: null,
      fingerprint: "historical",
      fx: null,
    },
    historical: true,
    model: {
      slug: "fixed-model",
      name: "Fixed Model",
      provider: null,
      released_at: null,
      brand: { src: null, monogram: "F" },
    },
    context_window_tokens: null,
    weights_url: null,
    price: null,
    overall: {
      key: "overall",
      name: "综合榜",
      rank: 7,
      score: 69.4,
      source_count: 4,
      on_board: true,
    },
    overall_stability: null,
    categories: [],
    metric_count: 1,
    evidence: [
      {
        key: "coding",
        name: "编程",
        items: [
          {
            unit: "test",
            source_key: "livebench",
            source_name: "LiveBench",
            official_url: "https://livebench.ai",
            protocol: "protocol-1",
            snapshot_id: "00000000-0000-4000-8000-000000000002",
            raw_score: 0.7,
            display: "70%",
            source_rank: 3,
            source_model_name: "Fixed Model (high)",
            configuration_key: "high",
            configuration_label: "high",
            selection_reason: "代表配置",
            upstream_at: null,
            verified_at: "2026-09-30T01:00:00Z",
            measured_at: null,
            carried_forward: true,
            components: {},
          },
        ],
      },
    ],
    excluded: [
      { key: "excluded", name: "配置被排除的来源", reason: "非基础模型配置" },
    ],
    unmeasured: [{ key: "unmeasured", name: "未测评的来源" }],
    comparisons: [],
  };
  render(<ModelReading data={data} />);
  expect(screen.getByText(/历史发布轮次/)).toBeTruthy();
  expect(screen.getByText("同协议沿用")).toBeTruthy();
  expect(screen.getByText("非基础模型配置")).toBeTruthy();
  expect(screen.getByText("未测评的来源")).toBeTruthy();
  expect(screen.getByText("暂无公开价格")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "LiveBench" }).getAttribute("href"),
  ).toBe("/leaderboard/sources/livebench");
});
