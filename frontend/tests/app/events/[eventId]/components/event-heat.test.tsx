// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ heat: vi.fn(), history: vi.fn() }));
vi.mock("@/api/shijian", () => ({
  getEventHeat: api.heat,
  listEventHeatHistory: api.history,
}));
import { EventHeat } from "@/app/events/[eventId]/components/event-heat";
import { heat } from "../../../../components/events/fixtures";
import { ApiRequestError } from "@/request";
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
describe("event source heat", () => {
  it("keeps the current heat readable when history fails and displays its error code with retry", async () => {
    api.heat.mockResolvedValue(heat());
    api.history
      .mockRejectedValueOnce(
        new ApiRequestError({
          kind: "http",
          code: "heat_history_unavailable",
          status: 503,
          message: "unavailable",
        }),
      )
      .mockResolvedValue({ items: [] });
    render(<EventHeat eventId="event" />);
    await screen.findByRole("heading", { name: "热度历史读取失败" });
    expect(screen.getByText("heat_history_unavailable · 503")).toBeTruthy();
    expect(
      screen.getByText(
        (_, node) =>
          node?.tagName === "P" && node.textContent === "48 小时热度 2.0",
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    await screen.findByText(/尚无当前修订的实际小时快照/);
    expect(api.history).toHaveBeenCalledTimes(2);
  });

  it("does not combine heat or history from a changed event revision", async () => {
    api.heat.mockResolvedValue({ ...heat(), event_revision: 2 });
    api.history.mockResolvedValue({ event_revision: 2, items: [heat()] });
    const loaded = vi.fn();
    render(
      <EventHeat eventId="event" eventRevision={1} onHeatLoaded={loaded} />,
    );
    await waitFor(() =>
      expect(screen.getAllByText("event_revision_conflict · 409")).toHaveLength(
        2,
      ),
    );
    expect(loaded).toHaveBeenCalledWith(null);
    expect(
      screen.queryByText(
        (_, node) =>
          node?.tagName === "P" && node.textContent === "48 小时热度 2.0",
      ),
    ).toBeNull();
    expect(document.querySelector('[data-slot="chart"]')).toBeNull();
  });

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
    expect(
      await screen.findByText(
        (_, node) =>
          node?.tagName === "P" && node.textContent === "48 小时热度 待确定",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        (_, node) =>
          node?.tagName === "P" && node.textContent === "互动热度 0.00",
      ),
    ).toBeTruthy();
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
    expect(
      await screen.findByText(
        (_, node) =>
          node?.tagName === "P" && node.textContent === "48 小时热度 18.5",
      ),
    ).toBeTruthy();
    expect(screen.getByText("趋势待确定")).toBeTruthy();
    expect(screen.getByText(/2 个参与者因新增或采集时钟不足/)).toBeTruthy();
    expect(screen.queryByText(/%/)).toBeNull();
  });
});
