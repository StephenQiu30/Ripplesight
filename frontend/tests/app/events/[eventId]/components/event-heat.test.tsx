// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ heat: vi.fn(), history: vi.fn() }));
vi.mock("@/api/shijian", () => ({
  getEventHeat: api.heat,
  listEventHeatHistory: api.history,
}));
import { EventHeat } from "@/app/events/[eventId]/components/event-heat";
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
describe("event source heat", () => {
  it("keeps unknown source heat distinct from a known zero interaction score", async () => {
    api.heat.mockResolvedValue({
      heat: 0,
      participant_count: 0,
      editorial_participant_count: 0,
      signal_participant_count: 0,
      trend: "unknown",
      trend_pct: null,
      complete: false,
      uncomparable_participant_count: 0,
      badges: [],
      roster: [],
      eligible: false,
      formula_version: "attention-v1",
      interaction: { score: 0, rising_state: "insufficient" },
    });
    api.history.mockResolvedValue({ items: [] });
    render(<EventHeat eventId="fixed-event" />);
    expect(await screen.findByText("48 小时热度 待确定")).toBeTruthy();
    expect(screen.getByText("互动热度 0.00")).toBeTruthy();
    expect(screen.getByText(/真实历史样本不足/)).toBeTruthy();
    expect(api.heat).toHaveBeenCalledWith(
      { event_id: "fixed-event" },
      expect.anything(),
    );
    expect(api.history).toHaveBeenCalledWith(
      { event_id: "fixed-event", limit: 48 },
      expect.anything(),
    );
  });
  it("shows coverage and cohort exclusions without manufacturing a trend percentage", async () => {
    api.heat.mockResolvedValue({
      heat: 18.5,
      participant_count: 2,
      editorial_participant_count: 1,
      signal_participant_count: 1,
      trend: "unknown",
      trend_pct: null,
      complete: false,
      uncomparable_participant_count: 2,
      badges: ["new"],
      roster: [],
      eligible: true,
      formula_version: "attention-v1",
      interaction: null,
    });
    api.history.mockResolvedValue({ items: [] });
    render(<EventHeat eventId="event" />);
    expect(await screen.findByText("48 小时热度 18.5")).toBeTruthy();
    expect(screen.getByText("趋势待确定")).toBeTruthy();
    expect(screen.getByText(/2 个参与者因新增或采集时钟不足/)).toBeTruthy();
    expect(screen.queryByText(/%/)).toBeNull();
  });
});
