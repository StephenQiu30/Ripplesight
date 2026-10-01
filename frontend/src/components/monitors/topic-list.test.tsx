// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@/api/jiankongzhuti", () => ({ listMonitorTopics: api.list }));
import { ApiRequestError } from "@/request";
import { TopicList } from "./topic-list";

const topic = (id: string): HotKeyAPI.MonitorTopicView => ({
  id,
  name: id,
  status: "paused",
  readiness_status: "pending_source_selection",
  current_version: 1,
  rules: { match_any: ["AI"], match_all: [], exclude: [] },
  source_keys: [],
  collection_interval_seconds: 1800,
  report_time: "09:00:00",
  report_timezone: "Asia/Shanghai",
  weekly_report_enabled: false,
  notification_target_names: [],
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
});
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

describe("topic list pagination", () => {
  it("keeps readable items when the next cursor fails and retries the same page", async () => {
    api.list
      .mockResolvedValueOnce({
        items: [topic("第一条关注")],
        next_cursor: "next-page",
      })
      .mockRejectedValueOnce(
        new ApiRequestError({
          kind: "http",
          status: 503,
          code: "service_unavailable",
          message: "读取暂不可用",
          requestId: "page-error",
        }),
      )
      .mockResolvedValueOnce({
        items: [topic("第二条关注")],
        next_cursor: null,
      });
    render(<TopicList />);
    await screen.findByText("第一条关注");
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    await screen.findByText("请求编号：page-error");
    expect(screen.getByText("第一条关注")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试加载更多" }));
    await screen.findByText("第二条关注");
    expect(api.list.mock.calls[1][0]).toEqual({
      include_archived: false,
      limit: 20,
      cursor: "next-page",
    });
    expect(api.list.mock.calls[2][0]).toEqual(api.list.mock.calls[1][0]);
    expect(screen.queryByRole("button", { name: "加载更多" })).toBeNull();
  });

  it("aborts and ignores an old page when the archive filter changes", async () => {
    let resolve!: (page: HotKeyAPI.PageViewMonitorTopicView_) => void;
    api.list
      .mockResolvedValueOnce({
        items: [topic("原筛选关注")],
        next_cursor: "old-page",
      })
      .mockImplementationOnce(
        () =>
          new Promise((done) => {
            resolve = done;
          }),
      )
      .mockResolvedValueOnce({
        items: [topic("含归档的关注")],
        next_cursor: null,
      });
    render(<TopicList />);
    await screen.findByText("原筛选关注");
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    fireEvent.click(screen.getByRole("switch", { name: "显示已归档" }));
    await screen.findByText("含归档的关注");
    expect(api.list.mock.calls[1][1].signal.aborted).toBe(true);
    resolve({ items: [topic("不应出现的旧页")], next_cursor: null });
    await waitFor(() =>
      expect(screen.queryByText("不应出现的旧页")).toBeNull(),
    );
    expect(screen.getByText("含归档的关注")).toBeTruthy();
  });
});
