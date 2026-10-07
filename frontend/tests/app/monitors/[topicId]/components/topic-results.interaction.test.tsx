// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { TopicResults } from "@/app/monitors/[topicId]/components/topic-results";
import { listContentRecords } from "@/api/zuopinziliao";
import { ApiRequestError } from "@/request";

vi.mock("@/api/zuopinziliao", () => ({ listContentRecords: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("scopes results to the topic and distinguishes empty results from loading", async () => {
  vi.mocked(listContentRecords).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
  render(<TopicResults topicId="topic-1" />);
  expect(screen.getByLabelText("正在加载监控结果")).toBeTruthy();
  await screen.findByText("还没有采集结果");
  expect(listContentRecords).toHaveBeenCalledWith(
    { topic_id: "topic-1", limit: 5 },
    { signal: expect.any(AbortSignal) },
  );
});

it("shows permission errors without keeping content visible", async () => {
  vi.mocked(listContentRecords).mockRejectedValue(
    new ApiRequestError({ kind: "http", status: 403, message: "forbidden" }),
  );
  render(<TopicResults topicId="topic-1" />);
  await screen.findByText("请登录有权限的账号查看监控结果。");
  expect(screen.queryByText("还没有采集结果")).toBeNull();
});

it("can retry a failed read without starting a collection job", async () => {
  vi.mocked(listContentRecords)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue({ items: [], next_cursor: null });
  render(<TopicResults topicId="topic-1" />);
  await screen.findByText("监控结果加载失败，请重试。");
  fireEvent.click(screen.getByRole("button", { name: "刷新结果" }));
  await screen.findByText("还没有采集结果");
  await waitFor(() => expect(listContentRecords).toHaveBeenCalledTimes(2));
});

const observedRecord: HotKeyAPI.ContentRecordSummaryView = {
  id: "post-1",
  source_key: "bilibili",
  source_name: "bilibili",
  object_type: "post",
  native_scope: null,
  external_id: "fixed-1",
  identity_basis: null,
  latest_observation: {
    id: "observation-1",
    observed_at: "2026-10-07T12:09:24Z",
    received_at: "2026-10-07T12:09:24Z",
    published_at: null,
    published_at_fractional_digits: null,
    canonical_url: null,
    final_url: null,
    author_external_id: null,
    metrics: {
      like_count: null,
      comment_count: null,
      repost_count: null,
      view_count: null,
      play_count: null,
      danmaku_count: null,
    },
    content_version: null,
  },
  current_visibility: null,
  discovery_count: 1,
};

it("keeps stale results after a network refresh failure but clears them when permission is revoked", async () => {
  vi.mocked(listContentRecords)
    .mockResolvedValueOnce({ items: [observedRecord], next_cursor: null })
    .mockRejectedValueOnce(new Error("offline"))
    .mockRejectedValueOnce(
      new ApiRequestError({ kind: "http", status: 403, message: "forbidden" }),
    );
  render(<TopicResults topicId="topic-1" />);
  await screen.findByText("B 站");
  expect(screen.getByText("发布时间未知")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "查看内容与评论" }).getAttribute("href"),
  ).toBe("/content/post-1");
  fireEvent.click(screen.getByRole("button", { name: "刷新结果" }));
  await screen.findByText("结果刷新失败，已显示内容可能过期");
  expect(screen.getByRole("link", { name: "查看内容与评论" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "刷新结果" }));
  await screen.findByText("请登录有权限的账号查看监控结果。");
  expect(screen.queryByRole("link", { name: "查看内容与评论" })).toBeNull();
});
