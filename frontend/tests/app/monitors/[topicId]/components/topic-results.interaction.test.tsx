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
