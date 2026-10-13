// @vitest-environment happy-dom
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { NegativeSurge } from "@/components/publication/negative-surge";
import { readableHomeReading } from "@/app/components/home-format";
import { negativeSurge } from "../../app/components/home-fixtures";

afterEach(cleanup);

it("shows server decision, exact policy, two denominators and an evidence link", () => {
  render(<NegativeSurge surge={negativeSurge} />);
  expect(screen.getAllByText("达到报道负面突增规则")).toHaveLength(2);
  expect(screen.getByText(/可判定 1\/1 个公开事件/)).toBeTruthy();
  expect(screen.getByText(/当前24小时：有效 10\/10 · 负面 8/)).toBeTruthy();
  expect(screen.getByText(/前一24小时：有效 10\/10 · 负面 2/)).toBeTruthy();
  expect(
    screen.getByText(/占比变化 60 个百分点 · 负面数量变化 6 条/),
  ).toBeTruthy();
  expect(screen.getByText(/controlled-visual-only/)).toBeTruthy();
  expect(screen.getByText(/比例差 0.2/)).toBeTruthy();
  expect(
    screen
      .getByRole("link", { name: negativeSurge.events[0].title })
      .getAttribute("href"),
  ).toBe(negativeSurge.events[0].reading_url);
});

it.each([
  [
    "not_configured",
    "判定规则未配置，真实阈值待校准",
    "rule_not_configured",
    "尚未配置经过校准的规则",
  ],
  [
    "insufficient_data",
    "数据不足，暂不可判定",
    "previous_empty",
    "前一24小时没有基线样本",
  ],
  ["unavailable", "判定依据不可用", "evidence_conflict", "报道依据存在冲突"],
  [
    "not_triggered",
    "未达到突增规则",
    "ratio_increase_below_threshold",
    "整体负面占比增幅未达阈值",
  ],
] as const)(
  "distinguishes %s and gives concrete reasons",
  (state, label, reason, detail) => {
    const event = {
      ...negativeSurge.events[0],
      state,
      reasons: [reason],
      ratio_increase: null,
      negative_count_increase: null,
    };
    render(
      <NegativeSurge
        surge={{
          ...negativeSurge,
          state,
          rule: state === "not_configured" ? null : negativeSurge.rule,
          events: [event],
        }}
      />,
    );
    expect(screen.getAllByText(label)).toHaveLength(2);
    expect(screen.getByText(detail)).toBeTruthy();
    expect(screen.queryByText(/占比变化/)).toBeNull();
  },
);

it("retains unknown total for partial assessment and does not turn missing data into clear", () => {
  const { rerender } = render(
    <NegativeSurge
      surge={{ ...negativeSurge, total_events: 3, insufficient_count: 2 }}
    />,
  );
  expect(screen.getByText(/全站突增总数未知/)).toBeTruthy();
  rerender(<NegativeSurge />);
  expect(screen.getByText("暂无后端判定依据，当前状态未知")).toBeTruthy();
  expect(screen.queryByText(/已判定触发/)).toBeNull();
  rerender(
    <NegativeSurge
      surge={{
        ...negativeSurge,
        state: "empty",
        total_events: 0,
        evaluated_events: 0,
        triggered_count: 0,
        events: [],
      }}
    />,
  );
  expect(screen.getByText("暂无可公开判定的事件")).toBeTruthy();
});

it.each([403, 503])("removes stale decisions and links on %s", (status) => {
  render(<NegativeSurge surge={negativeSurge} failure={{ status }} />);
  expect(screen.queryByRole("link")).toBeNull();
  expect(screen.queryByText(/已判定触发/)).toBeNull();
  expect(
    screen.getByText(
      status === 403
        ? "无权读取负面突增判定"
        : "负面突增判定读取失败，请重新加载事件",
    ),
  ).toBeTruthy();
  const safe = readableHomeReading({
    stories: [],
    editions: [],
    unavailable: [],
    negativeSurge,
    failures: { stories: { status } },
  });
  expect(safe.negativeSurge).toBeUndefined();
});

it("expands the bounded server list through a keyboard-operable button", () => {
  render(
    <NegativeSurge
      surge={{
        ...negativeSurge,
        total_events: 7,
        events: Array.from({ length: 7 }, (_, index) => ({
          ...negativeSurge.events[0],
          event_id: String(index),
        })),
      }}
    />,
  );
  expect(screen.getAllByRole("link")).toHaveLength(5);
  fireEvent.click(screen.getByRole("button", { name: "展开更多判定事件" }));
  expect(screen.getAllByRole("link")).toHaveLength(7);
});
