// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({
  run: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}));
vi.mock("@/api/jiankongzhuti", () => ({ runMonitorTopic: api.run }));
vi.mock("sonner", () => ({
  toast: { error: api.error, success: api.success },
}));
import { TopicRunActions } from "@/app/monitors/[topicId]/components/topic-run-actions";
import { ApiRequestError } from "@/request";
const topic: HotKeyAPI.MonitorTopicView = {
  id: "topic-a",
  name: "主题一",
  status: "active",
  readiness_status: "ready",
  current_version: 2,
  rules: { match_any: ["任一词"], match_all: [], exclude: [] },
  source_keys: ["hackernews", "google_news"],
  collection_interval_seconds: 3600,
  report_time: "08:00:00",
  report_timezone: "Asia/Shanghai",
  weekly_report_enabled: true,
  notification_target_names: [],
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T01:00:00Z",
};
const result: HotKeyAPI.MonitorTopicRunView = {
  operation_id: "run-a",
  topic_id: topic.id,
  topic_version: 2,
  sources: [
    { source_key: "hackernews", job_ids: ["job-a"], skip_reason: null },
    { source_key: "google_news", job_ids: [], skip_reason: "rate_limited" },
  ],
};
const sourceNames = { hackernews: "Hacker News", google_news: "Google 新闻" };
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);
it("uses source switches, only marks the run button busy, and renders real acceptance without hit counts", async () => {
  let resolve!: (value: HotKeyAPI.MonitorTopicRunView) => void;
  api.run.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  render(<TopicRunActions topic={topic} sourceNames={sourceNames} />);
  expect(screen.getByText("本页尚无手动运行结果。")).toBeTruthy();
  const submit = screen.getByRole("button", { name: "立即采集" });
  fireEvent.click(submit);
  fireEvent.click(submit);
  expect(api.run).toHaveBeenCalledTimes(1);
  expect(
    screen.getByRole("button", { name: "正在受理" }).getAttribute("aria-busy"),
  ).toBe("true");
  expect(
    screen
      .getByRole("switch", { name: "Hacker News" })
      .getAttribute("aria-busy"),
  ).toBeNull();
  expect(screen.queryByRole("button", { name: "取消" })).toBeNull();
  resolve(result);
  await screen.findByText("已受理 1 个任务");
  expect(screen.getByText("来源间隔尚未到期")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "查看任务 job-a" }).getAttribute("href"),
  ).toBe("/jobs/job-a");
  expect(screen.queryByText(/命中\s*\d+\s*条/)).toBeNull();
  const firstId = api.run.mock.calls[0][1].operation_id;
  fireEvent.click(screen.getByRole("button", { name: "发起新一轮" }));
  fireEvent.click(screen.getByRole("switch", { name: "Google 新闻" }));
  api.run.mockResolvedValueOnce(result);
  fireEvent.click(screen.getByRole("button", { name: "立即采集" }));
  await waitFor(() => expect(api.run).toHaveBeenCalledTimes(2));
  expect(api.run.mock.calls[1][1].source_keys).toEqual(["hackernews"]);
  expect(api.run.mock.calls[1][1].operation_id).not.toBe(firstId);
});
it("retries an unconfirmed run with the same operation and keeps permission/session untouched", async () => {
  api.run
    .mockRejectedValueOnce(
      new ApiRequestError({ kind: "network", message: "offline" }),
    )
    .mockResolvedValueOnce(result);
  render(<TopicRunActions topic={topic} sourceNames={sourceNames} />);
  fireEvent.click(screen.getByRole("button", { name: "立即采集" }));
  await waitFor(() =>
    expect(api.error).toHaveBeenCalledWith("offline", {
      description: undefined,
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "立即采集" }));
  await screen.findByText("已受理 1 个任务");
  expect(api.run.mock.calls[1][1].operation_id).toBe(
    api.run.mock.calls[0][1].operation_id,
  );
});
it.each(["paused", "archived"] as const)(
  "does not run a %s topic",
  (status) => {
    render(
      <TopicRunActions
        topic={{ ...topic, status }}
        sourceNames={sourceNames}
      />,
    );
    expect(screen.queryByRole("button", { name: "立即采集" })).toBeNull();
    expect(api.run).not.toHaveBeenCalled();
  },
);

it("shows all-skipped query evidence without jobs or zero hits and requires an explicit new round", async () => {
  const skipped: HotKeyAPI.MonitorTopicRunView = {
    ...result,
    sources: [
      {
        source_key: "hackernews",
        job_ids: [],
        skip_reason: "budget",
        query_plan: {
          version: 1,
          topic_version: 2,
          max_queries: null,
          collection: null,
          queries: [
            {
              query_index: 0,
              query: "任一词",
              admitted: false,
              skip_reason: "budget",
            },
          ],
        },
      },
    ],
  };
  api.run.mockResolvedValue(skipped);
  render(
    <TopicRunActions
      topic={{ ...topic, source_keys: ["hackernews"] }}
      sourceNames={sourceNames}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "立即采集" }));
  await screen.findByText("冻结主题版本：v2");
  expect(screen.getByText("任一词")).toBeTruthy();
  expect(screen.getByText(/未受理（预算不足）/)).toBeTruthy();
  expect(screen.queryByRole("link", { name: /查看任务/ })).toBeNull();
  expect(screen.queryByText(/已受理 0|命中 0|采集完成/)).toBeNull();
  expect(
    (screen.getByRole("switch", { name: "Hacker News" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  const operation = api.run.mock.calls[0][1].operation_id;
  fireEvent.click(screen.getByRole("button", { name: "发起新一轮" }));
  expect(screen.getByText("本页尚无手动运行结果。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "立即采集" }));
  await screen.findByText("冻结主题版本：v2");
  expect(api.run).toHaveBeenCalledTimes(2);
  expect(api.run.mock.calls[1][1].operation_id).not.toBe(operation);
});

it("distinguishes a topic that stopped running from source admission skips", async () => {
  api.run.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      code: "topic_not_ready",
      status: 409,
      message: "not ready",
    }),
  );
  render(<TopicRunActions topic={topic} sourceNames={sourceNames} />);
  fireEvent.click(screen.getByRole("button", { name: "立即采集" }));
  await waitFor(() =>
    expect(api.error).toHaveBeenCalledWith(
      "主题当前不可运行，请刷新确认主题状态。",
      { description: undefined },
    ),
  );
  expect(screen.queryByText(/冻结主题版本/)).toBeNull();
  expect(api.success).not.toHaveBeenCalled();
});
