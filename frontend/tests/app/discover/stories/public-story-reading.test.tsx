// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { publicItem } from "../../../components/events/fixtures";

const api = vi.hoisted(() => ({
  developments: vi.fn(),
  privateHeat: vi.fn(),
  privateMembers: vi.fn(),
  privateRelated: vi.fn(),
}));
vi.mock("@/api/gongkaifabu", () => ({
  getPublicStoryDevelopments: api.developments,
}));
vi.mock("@/api/shijian", () => ({
  getEventHeat: api.privateHeat,
  listEventMembers: api.privateMembers,
  listRelatedEvents: api.privateRelated,
}));
vi.mock("@/components/publication/poster-download", () => ({
  PosterDownload: () => null,
}));

import { PublicStoryReading } from "@/app/discover/stories/[eventId]/components/public-story-reading";
import { ApiRequestError } from "@/request";

const story: HotKeyAPI.PublicStoryView = {
  id: "event",
  revision: 2,
  title: "公开事件",
  summary: "允许公开的摘要",
  latest_progress: "允许公开的进展",
  phase: "active",
  first_seen_at: "2026-10-02T00:00:00Z",
  heat: 0,
  reports: [publicItem()],
};

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("keeps anonymous public reading inside public APIs, counts actual sources, and maps fact citations to report rows", async () => {
  api.developments.mockResolvedValue({
    event_id: "event",
    revision: "snapshot-1",
    developments: [
      {
        fact_id: "fact",
        title: "真实公开事实",
        anchor_at: story.first_seen_at,
        report_count: 3,
        representative: publicItem(),
      },
    ],
    next_cursor: null,
  });
  render(<PublicStoryReading story={story} />);
  expect(
    await screen.findByRole("heading", { name: "真实公开事实" }),
  ).toBeTruthy();
  expect(screen.getByText("允许公开的摘要")).toBeTruthy();
  expect(screen.getByText("事件更新时间未提供")).toBeTruthy();
  expect(
    screen.getByText(
      (_, node) => node?.tagName === "P" && node.textContent === "1 个来源",
    ),
  ).toBeTruthy();
  expect(
    screen.getByText(
      (_, node) => node?.tagName === "P" && node.textContent === "热度 0",
    ),
  ).toBeTruthy();
  const citation = screen.getByRole("link", { name: "来源 1" });
  expect(
    document.getElementById(citation.getAttribute("href")!.slice(1)),
  ).toBeTruthy();
  expect(screen.getByText("公开资料暂未提供代表评论。")).toBeTruthy();
  expect(screen.getByText("公开资料暂未提供关联事件。")).toBeTruthy();
  expect(
    screen.getByText("公开资料暂未提供热度历史，不绘制曲线。"),
  ).toBeTruthy();
  expect(api.developments).toHaveBeenCalledWith(
    { event_id: "event", limit: 20, window: "7d" },
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  expect(api.privateHeat).not.toHaveBeenCalled();
  expect(api.privateMembers).not.toHaveBeenCalled();
  expect(api.privateRelated).not.toHaveBeenCalled();
  expect(screen.queryByText(/情感分布|关注事件|收藏事件/)).toBeNull();
});

it("shows development loading and empty members without inventing content", async () => {
  let resolve!: (page: HotKeyAPI.PublicDevelopmentsPage) => void;
  api.developments.mockReturnValue(
    new Promise<HotKeyAPI.PublicDevelopmentsPage>((done) => {
      resolve = done;
    }),
  );
  render(<PublicStoryReading story={{ ...story, reports: [] }} />);
  expect(screen.getByLabelText("正在读取公开事实与进展")).toBeTruthy();
  resolve({
    event_id: "event",
    revision: "empty",
    developments: [],
    next_cursor: null,
  });
  expect(
    await screen.findByText("当前窗口尚无可公开的事实与进展。"),
  ).toBeTruthy();
  expect(screen.getByText("当前事件尚无成员。")).toBeTruthy();
  expect(screen.getByText("当前事件尚无可读来源。")).toBeTruthy();
});

it("binds pagination to the returned public snapshot and clears old developments after a stale cursor", async () => {
  api.developments.mockResolvedValueOnce({
    event_id: "event",
    revision: "snapshot-1",
    developments: [
      {
        fact_id: "fact",
        title: "旧的公开事实",
        anchor_at: story.first_seen_at,
        report_count: 2,
        representative: publicItem("old"),
      },
    ],
    next_cursor: "next",
  });
  api.developments.mockRejectedValueOnce(
    new ApiRequestError({
      kind: "http",
      code: "publication_cursor_stale",
      status: 409,
      message: "projection changed",
    }),
  );
  api.developments.mockResolvedValueOnce({
    event_id: "event",
    revision: "snapshot-2",
    developments: [],
    next_cursor: null,
  });
  render(<PublicStoryReading story={story} />);
  await screen.findByRole("heading", { name: "旧的公开事实" });
  fireEvent.click(screen.getByRole("button", { name: "加载更多事实与进展" }));
  await screen.findByRole("heading", { name: "无法读取公开事实与进展" });
  expect(screen.getByText("publication_cursor_stale · 409")).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "旧的公开事实" })).toBeNull();
  expect(screen.queryByText("公开报道 old")).toBeNull();
  expect(api.developments).toHaveBeenNthCalledWith(
    2,
    {
      event_id: "event",
      limit: 20,
      window: "7d",
      cursor: "next",
      revision: "snapshot-1",
    },
    expect.anything(),
  );
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await screen.findByText("当前窗口尚无可公开的事实与进展。");
  expect(api.developments).toHaveBeenNthCalledWith(
    3,
    { event_id: "event", limit: 20, window: "7d" },
    expect.anything(),
  );
});

it("aborts development reads when leaving the public event", async () => {
  api.developments.mockReturnValue(new Promise(() => {}));
  const { unmount } = render(<PublicStoryReading story={story} />);
  await waitFor(() => expect(api.developments).toHaveBeenCalledTimes(1));
  const signal = api.developments.mock.calls[0][1].signal as AbortSignal;
  unmount();
  expect(signal.aborted).toBe(true);
});
