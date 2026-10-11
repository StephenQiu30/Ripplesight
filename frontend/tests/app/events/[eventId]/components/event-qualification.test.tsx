// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { EventQualification } from "@/app/events/[eventId]/components/event-qualification";
import { heat } from "../../../../components/events/fixtures";

const current = (): HotKeyAPI.EventAttentionView => ({
  ...heat("2026-10-11T18:00:00+08:00"),
  formula_version: "attention-v1-48h-halflife24h",
});
afterEach(cleanup);

describe("current 48 hour ranking qualification receipt", () => {
  it("explains the server-qualified window, minimums and grouping without treating participation as corroboration", () => {
    render(<EventQualification data={current()} />);
    expect(screen.getByText("满足当前48小时热榜条件")).toBeTruthy();
    expect(screen.getByText("服务端资格回执：满足")).toBeTruthy();
    expect(screen.getByText(/实际 2 个 \/ 至少 2 个/)).toBeTruthy();
    expect(screen.getByText(/实际 1 个 \/ 至少 1 个/)).toBeTruthy();
    expect(
      [...document.querySelectorAll("time")].map((node) => node.dateTime),
    ).toEqual(["2026-10-09T10:00:00.000Z", "2026-10-11T10:00:00.000Z"]);
    expect(
      screen.getByText(/起点不计入，终点计入；未来材料不计入/),
    ).toBeTruthy();
    expect(screen.getByText(/优先按来源组，其次按主体/)).toBeTruthy();
    expect(
      screen.getByText(/参与者不等于帖子数、作者数或独立事实确认/),
    ).toBeTruthy();
    expect(
      screen.getByText(/不替代24小时相关帖、作者和新事实统计/),
    ).toBeTruthy();
    expect(screen.queryByText(/未满足原因/)).toBeNull();
  });

  it.each([
    { participants: 1, editorial: 1, signal: 0, reason: "去重参与者不足2个" },
    { participants: 2, editorial: 0, signal: 2, reason: "缺少编辑参与者" },
    {
      participants: 0,
      editorial: 0,
      signal: 0,
      reason: "去重参与者不足2个；缺少编辑参与者",
    },
  ])(
    "explains only the missing conditions: $reason",
    ({ participants, editorial, signal, reason }) => {
      render(
        <EventQualification
          data={{
            ...current(),
            eligible: false,
            participant_count: participants,
            editorial_participant_count: editorial,
            signal_participant_count: signal,
          }}
        />,
      );
      expect(screen.getByText("尚未满足当前48小时热榜条件")).toBeTruthy();
      expect(screen.getByText(`未满足原因：${reason}。`)).toBeTruthy();
      expect(screen.queryByText("资格说明待确定")).toBeNull();
    },
  );

  it.each([
    { formula_version: undefined },
    { formula_version: "attention-v2-future" },
    { window_end: "not-a-time" },
    { window_end: "2026-10-11T10:00:00" },
    { participant_count: -1 },
    { participant_count: 1.5 },
    { editorial_participant_count: 3 },
    { signal_participant_count: NaN },
    { participant_count: 3 },
    { eligible: false },
    { participant_count: 1, signal_participant_count: 0 },
  ] satisfies Partial<HotKeyAPI.EventAttentionView>[])(
    "does not guess thresholds, reasons or windows for unsupported/inconsistent receipts: %j",
    (overrides) => {
      render(<EventQualification data={{ ...current(), ...overrides }} />);
      expect(screen.getByText("资格说明待确定")).toBeTruthy();
      expect(screen.getByText(/服务端资格回执/)).toBeTruthy();
      expect(screen.queryByText(/实际 .* 至少/)).toBeNull();
      expect(screen.queryByText(/^未满足原因/)).toBeNull();
      expect(document.querySelector("time")).toBeNull();
      expect(screen.queryByText("满足当前48小时热榜条件")).toBeNull();
    },
  );
});
