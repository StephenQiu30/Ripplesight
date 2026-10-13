// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import {
  HeatHistory,
  heatTrendLabel,
} from "@/components/publication/heat-history";
import { HistoryCurve } from "@/components/ui/history-curve";

afterEach(cleanup);
const heatHistory: HotKeyAPI.PublicHeatHistory = {
  state: "available",
  event_revision: 2,
  snapshot_at: "2026-10-06T08:30:00Z",
  formula_version: "attention-v1-48h-halflife24h",
  trend: { state: "insufficient_data", reason: "source_changed" },
  points: Array.from({ length: 48 }, (_, index) => ({
    window_end: new Date(
      Date.parse("2026-10-06T08:00:00Z") - (47 - index) * 3600000,
    ).toISOString(),
    value: index > 42 ? index - 40 : null,
    computed_at: index > 42 ? "2026-10-06T08:10:00Z" : null,
    reason: index > 42 ? null : "missing",
    segment_key: index < 46 ? "a" : "b",
    participant_count: index > 42 ? 2 : null,
  })),
};
it("draws only consecutive same-cohort lines and exposes an auditable disclosure", () => {
  const { container } = render(<HeatHistory history={heatHistory} />);
  expect(screen.getByText(/5\/48个有效小时记录/)).toBeTruthy();
  expect(screen.getByText(/来源口径变化，不可直接比较/)).toBeTruthy();
  expect(container.querySelectorAll("circle")).toHaveLength(5);
  expect(container.querySelectorAll("line")).toHaveLength(3);
  const trigger = screen.getByRole("button", { name: "查看历史依据" });
  expect(trigger.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(trigger);
  expect(trigger.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByRole("table", { name: "小时热度计算依据" })).toBeTruthy();
  expect(screen.getAllByRole("row")).toHaveLength(49);
  expect(screen.getByText(/计算时间不代表窗口截止时已知/)).toBeTruthy();
});
it("retains missing and recomputed states without a fabricated flat curve", () => {
  const { container, rerender } = render(
    <HeatHistory
      history={{
        ...heatHistory,
        state: "insufficient_data",
        reason: "recomputed",
        points: heatHistory.points.map((point) => ({
          ...point,
          value: null,
          reason: "recomputed",
        })),
        trend: { state: "insufficient_data", reason: "recomputed" },
      }}
    />,
  );
  expect(container.querySelector("svg")).toBeNull();
  expect(screen.getByText(/0\/48个有效小时/)).toBeTruthy();
  rerender(<HeatHistory />);
  expect(screen.getByText("历史依据未返回")).toBeTruthy();
});
it("breaks gaps even with unchanged segment hashes and a fixed hourly spacing", () => {
  const { container } = render(
    <HistoryCurve
      label="gapped"
      points={[
        { at: "2026-10-06T01:00:00Z", value: 1, segment: "a" },
        { at: "2026-10-06T02:00:00Z", value: null, segment: "a" },
        { at: "2026-10-06T03:00:00Z", value: 3, segment: "a" },
        { at: "2026-10-06T05:00:00Z", value: 4, segment: "a" },
      ]}
    />,
  );
  expect(container.querySelectorAll("line")).toHaveLength(0);
  expect(
    heatTrendLabel({ state: "unavailable", reason: "not_public" }),
  ).toContain("依据不可用");
});
