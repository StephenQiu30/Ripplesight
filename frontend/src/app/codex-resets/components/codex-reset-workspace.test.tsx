// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  configuration: vi.fn(),
  snapshot: vi.fn(),
  recent: vi.fn(),
  version: vi.fn(),
  posts: vi.fn(),
}));
vi.mock("@/api/zhongzhigonggao", () => ({
  getCodexResetConfiguration: api.configuration,
  getCodexResetSnapshot: api.snapshot,
  getRecentCodexResets: api.recent,
  getCodexResetVersion: api.version,
  listCodexResetPosts: api.posts,
}));
vi.mock("@/components/navigation/workspace-header", () => ({
  WorkspaceHeader: () => <nav>工作区导航</nav>,
}));

import { CodexResetWorkspace } from "./codex-reset-workspace";

const event: HotKeyAPI.ResetEventView = {
  id: "reset-100-0-0",
  kind: "direct_reset",
  status: "announced",
  revision: 1,
  created_at: "2026-10-02T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
  title: "重置窗口已过，尚无源确认",
  presentation_status: "likely_completed",
  estimate: {
    starts_at: "2026-10-01T00:00:00Z",
    ends_at: "2026-10-01T01:00:00Z",
    basis: "history",
    label: "历史估计窗口",
    reason: "历史推测",
  },
  posts: [
    {
      post_id: "p100",
      external_id: "100",
      action: "announce",
      stage: "announce",
      published_at: "2026-10-02T00:00:00Z",
      excerpt: "Will reset",
      excerpt_zh: "即将重置",
      original_text: "Will reset",
      translation_zh: "即将重置",
      url: "https://x.com/thsottiaux/status/100",
      context: [],
    },
  ],
};
const snapshot: HotKeyAPI.ResetSnapshot = {
  today: "2026-10-02",
  checked_at: null,
  history_from: null,
  events: [event],
  activities: [],
  monitor: {
    status: "unknown",
    enabled: true,
    last_attempt_at: null,
    last_collected_at: null,
    last_verified_at: null,
    pending_count: 0,
    review_count: 1,
    held_window_count: 1,
  },
  outage: null,
  calendar: [
    {
      date: "2026-10-02",
      event_id: event.id,
      kind: "direct_reset",
      state: "likely",
      label: "推测已完成",
    },
  ],
  statistics: {
    resets_90: 0,
    credits_90: 0,
    median_interval_days: null,
    last_reset_date: null,
  },
  current: event,
  last_landed: null,
  confirm_minutes: [],
  version: "version1",
};

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function ready() {
  api.configuration.mockResolvedValue({
    enabled: true,
    configuration_version: 1,
  });
  api.snapshot.mockResolvedValue(snapshot);
  api.recent.mockResolvedValue(snapshot);
  api.posts.mockResolvedValue([]);
}

describe("Codex reset reading", () => {
  it("shows unconfigured state without creating records or loading source posts", async () => {
    api.configuration.mockResolvedValue(null);
    api.snapshot.mockResolvedValue(null);
    api.recent.mockResolvedValue(null);
    render(<CodexResetWorkspace />);
    expect(
      await screen.findByRole("heading", { name: "尚未配置公告监控" }),
    ).toBeTruthy();
    expect(screen.getByText("工作区导航")).toBeTruthy();
    expect(api.posts).not.toHaveBeenCalled();
  });

  it("keeps predicted and source-confirmed states separate and preserves old data on refresh failure", async () => {
    ready();
    render(<CodexResetWorkspace />);
    expect(
      await screen.findByRole("heading", { name: event.title }),
    ).toBeTruthy();
    expect(screen.getByText("历史估计窗口")).toBeTruthy();
    expect(screen.getByText("暂无完整核验")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /2026-10-02.*推测已完成/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "阅读公告原帖" }).getAttribute("href"),
    ).toBe(event.posts?.[0].url);
    api.snapshot.mockRejectedValue(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: "刷新公告" }));
    expect(
      await screen.findByText(/刷新失败，仍显示上次读取的数据/),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: event.title })).toBeTruthy();
  });

  it("pages persistent posts and resets page on status filter", async () => {
    ready();
    api.posts.mockResolvedValue(
      Array.from({ length: 50 }, (_, i) => ({
        id: `p${i}`,
        external_id: `${i}`,
        published_at: "2026-10-02T00:00:00Z",
        text: `Source ${i}`,
        translation_zh: null,
        url: `https://x.com/thsottiaux/status/${i}`,
        context: [],
        processed_at: null,
        needs_review: false,
        reviewed: false,
        review_version: 1,
        failure_count: 0,
        failure_code: null,
      })),
    );
    render(<CodexResetWorkspace />);
    await screen.findByText("Source 0");
    fireEvent.click(screen.getByRole("button", { name: "全部帖子" }));
    expect(screen.getByText("Source 0")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "下一页帖子" }));
    await waitFor(() =>
      expect(api.posts).toHaveBeenLastCalledWith(
        { page: 2, filter_key: "all" },
        expect.anything(),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "需复核" }));
    await waitFor(() =>
      expect(api.posts).toHaveBeenLastCalledWith(
        { page: 1, filter_key: "review" },
        expect.anything(),
      ),
    );
  });

  it("reads disabled historical monitors and keeps a post failure separate from the calendar", async () => {
    ready();
    api.configuration.mockResolvedValue({
      enabled: false,
      configuration_version: 1,
    });
    api.posts.mockRejectedValue(new Error("offline"));
    render(<CodexResetWorkspace />);
    expect(
      await screen.findByText(/监控已关闭。下方保留已有记录/),
    ).toBeTruthy();
    expect(await screen.findByText("源帖子读取失败。")).toBeTruthy();
    expect(screen.getByRole("heading", { name: event.title })).toBeTruthy();
    expect(screen.getByRole("button", { name: "重试读取帖子" })).toBeTruthy();
  });
});
