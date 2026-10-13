// @vitest-environment happy-dom
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { PlatformTrends } from "@/components/publication/platform-trends";
import { readableHomeReading } from "@/app/components/home-format";

afterEach(cleanup);
const board: HotKeyAPI.PublicPlatformTrend = {
  source_key: "hotlist_weibo",
  source_name: "微博热搜",
  state: "partial",
  observed_at: "2026-10-13T01:02:00Z",
  received_at: "2026-10-13T01:02:01Z",
  due_at: "2026-10-13T01:00:00Z",
  valid_until: "2026-10-13T02:02:00Z",
  permission_reviewed_at: "2026-10-12T00:00:00Z",
  permission_expires_at: "2026-10-14T00:00:00Z",
  license_name: "受控许可",
  license_url: "https://example.com/license",
  entry_count: 7,
  source_entry_count: 7,
  reasons: ["native_rank_unknown", "source_time_unknown"],
  comparison_reason: "no_baseline",
  items: Array.from({ length: 7 }, (_, i) => ({
    rank: i + 1,
    title: `条目${i + 1}`,
    url: `https://example.com/${i}`,
  })),
};
it("shows source permission and distinct times, unknown native values, and expands fixed entries", () => {
  render(<PlatformTrends boards={[board]} />);
  expect(screen.getByText("数据部分可用")).toBeTruthy();
  expect(screen.getByText(/来源更新 未知 · 采集/)).toBeTruthy();
  expect(screen.getByText(/公开许可/)).toBeTruthy();
  expect(screen.getAllByText(/原生名次 未知/)).toHaveLength(5);
  expect(screen.queryByRole("link", { name: "条目6" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "展开其余 2 条" }));
  expect(screen.getByRole("link", { name: "条目7" }).getAttribute("href")).toBe(
    "https://example.com/6",
  );
});
it.each([
  "not_configured",
  "unavailable",
  "failed",
  "collecting",
  "no_snapshot",
  "stale",
] as const)("hides stale entries for %s", (state) => {
  render(<PlatformTrends boards={[{ ...board, state }]} />);
  expect(screen.queryByRole("link", { name: "条目1" })).toBeNull();
  expect(screen.queryByText(/保存 7/)).toBeNull();
});
it("distinguishes genuine empty and absent DTO", () => {
  const { rerender } = render(
    <PlatformTrends
      boards={[
        {
          ...board,
          state: "empty",
          items: [],
          entry_count: 0,
          source_entry_count: 0,
        },
      ]}
    />,
  );
  expect(screen.getByText("本次榜单为空")).toBeTruthy();
  expect(screen.getByText(/保存 0 \/ 来源 0 条/)).toBeTruthy();
  rerender(<PlatformTrends />);
  expect(screen.getByText("尚未返回平台榜单依据。")).toBeTruthy();
});
it.each([403, 503])("clears old boards on request failure %s", (status) => {
  render(<PlatformTrends boards={[board]} failure={{ status }} />);
  expect(screen.queryByRole("link")).toBeNull();
  expect(
    screen.getByText(
      status === 403 ? "无权读取平台榜单。" : "平台榜单读取失败，请刷新重试。",
    ),
  ).toBeTruthy();
  expect(
    readableHomeReading({
      stories: [],
      editions: [],
      unavailable: [],
      platformTrends: [board],
      failures: { stories: { status } },
    }).platformTrends,
  ).toBeUndefined();
});
