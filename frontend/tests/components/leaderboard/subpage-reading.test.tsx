// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SourcesReading } from "@/app/leaderboard/sources/components/sources-reading";
import { SourceReading } from "@/app/leaderboard/sources/[sourceKey]/components/source-reading";
import { RulesReading } from "@/app/leaderboard/rules/components/rules-reading";

const source: HotKeyAPI.SourceSummaryView = {
  key: "test",
  name: "测试来源",
  status: "ranked",
  operator: "测试机构",
  description: "测试来源说明",
  brand: { src: null, monogram: "T" },
  weight: 0.25,
  family_key: "test",
  category_key: "coding",
  collected: false,
};
const detail: HotKeyAPI.SourceDetailView = {
  run: null,
  source,
  full_name: "来源完整名称",
  area: null,
  official_url: "https://example.com/source",
  what: "测量说明",
  usage: "使用说明",
  limits: "限制说明",
  license: "测试许可",
  attribution: "测试署名",
  upstream_at: null,
  synced_at: null,
  collected: false,
  system_rows: false,
  rows: [],
  rows_note: null,
};
const rules: HotKeyAPI.RulesView = {
  run: null,
  methodology_version: "test-version",
  score_definition: "固定锚点支持指数",
  display_method: "test-display",
  tie_policy: "test-tie",
  budgets: [],
  anchors: [],
  configuration_policy: "test-config",
  carry_forward_days: 3,
  release_window_months: 6,
};
afterEach(cleanup);

function expectPageTitle(title: string) {
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(screen.getByRole("heading", { level: 1, name: title })).toBeTruthy();
}

it("renders source coverage without suggesting an uncollected registry is live", () => {
  render(
    <SourcesReading
      data={{
        run: null,
        groups: [
          {
            key: "coding",
            name: "编程证据",
            blurb: "分组说明",
            sources: [source],
          },
        ],
      }}
    />,
  );
  expectPageTitle("评测来源与覆盖");
  expect(screen.getByText("本轮无证据")).toBeTruthy();
  expect(screen.getByText("25.0%")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "测试来源" }).getAttribute("href"),
  ).toBe("/leaderboard/sources/test");
});

it("renders empty source directories and empty groups explicitly", () => {
  const { rerender } = render(
    <SourcesReading data={{ run: null, groups: [] }} />,
  );
  expect(
    screen.getByRole("status", { name: "暂无可展示的评测来源" }),
  ).toBeTruthy();
  expectPageTitle("评测来源与覆盖");
  expect(
    screen.getByRole("heading", { level: 2, name: "暂无可展示的评测来源" }),
  ).toBeTruthy();
  rerender(
    <SourcesReading
      data={{
        run: null,
        groups: [
          { key: "coding", name: "编程证据", blurb: "分组说明", sources: [] },
        ],
      }}
    />,
  );
  expectPageTitle("评测来源与覆盖");
  expect(screen.getByText("该分组暂无已注册来源。")).toBeTruthy();
});

it("distinguishes an uncollected source from withheld public rows", () => {
  const { rerender } = render(<SourceReading data={detail} />);
  expect(
    screen.getByRole("status", { name: "尚未采集该来源的合资格证据" }),
  ).toBeTruthy();
  expectPageTitle("来源完整名称");
  expect(
    screen.getByRole("heading", {
      level: 2,
      name: "尚未采集该来源的合资格证据",
    }),
  ).toBeTruthy();
  expect(screen.getByText(/测试许可/)).toBeTruthy();
  expect(screen.getByText(/测试署名/)).toBeTruthy();
  rerender(<SourceReading data={{ ...detail, collected: true }} />);
  expectPageTitle("来源完整名称");
  expect(
    screen.getByRole("heading", {
      level: 2,
      name: "该来源不提供可公开展示的逐行明细",
    }),
  ).toBeTruthy();
  expect(
    screen.getByRole("status", { name: "该来源不提供可公开展示的逐行明细" }),
  ).toBeTruthy();
});

it("retains original source rank, exclusions and system-configuration warnings", () => {
  render(
    <SourceReading
      data={{
        ...detail,
        system_rows: true,
        collected: true,
        rows: [
          {
            source_model_name: "测试配置",
            source_rank: 7,
            model_slug: "test-model",
            provider: "测试机构",
            display: "70%",
            configuration_label: "high",
            excluded: "非基础配置",
          },
        ],
      }}
    />,
  );
  expectPageTitle("来源完整名称");
  expect(screen.getByRole("table")).toBeTruthy();
  expect(screen.getByText("7")).toBeTruthy();
  expect(screen.getByText("70%")).toBeTruthy();
  expect(
    screen.getByText(/仅供参考，不能直接当作基础模型能力排名/),
  ).toBeTruthy();
  expect(screen.getByText("排除：非基础配置")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "测试配置" }).getAttribute("href"),
  ).toBe("/leaderboard/models/test-model");
});

it("handles missing budgets, anchors and optional thresholds without inventing numbers", () => {
  render(<RulesReading data={rules} />);
  expectPageTitle("计算规则与证据边界");
  expect(screen.getByText("暂无公开预算配置。")).toBeTruthy();
  expect(screen.getByText("暂无公开锚点配置。")).toBeTruthy();
  expect(screen.queryByText(/综合榜至少/)).toBeNull();
  expect(screen.queryByText(/分类榜至少/)).toBeNull();
});

it("maps actual budgets and publication thresholds to the rules table", () => {
  render(
    <RulesReading
      data={{
        ...rules,
        budgets: [
          { key: "coding", name: "编程", weight: 0.4, sources: ["test"] },
        ],
        anchors: ["anchor-1"],
        overall_minimum_models: 10,
        overall_minimum_anchors: 2,
        category_minimum_models: 3,
        category_minimum_anchors: 1,
      }}
    />,
  );
  expectPageTitle("计算规则与证据边界");
  expect(screen.getByText("40%")).toBeTruthy();
  expect(screen.getByText("anchor-1")).toBeTruthy();
  expect(screen.getByText(/综合榜至少 10 个模型、2 个固定锚点/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "test" }).getAttribute("href")).toBe(
    "/leaderboard/sources/test",
  );
});
