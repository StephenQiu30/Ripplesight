// @vitest-environment happy-dom
import { expectOnePageHeading } from "../../../page-heading";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  sources: vi.fn(),
  pause: vi.fn(),
  resume: vi.fn(),
  update: vi.fn(),
  push: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}));
vi.mock("@/api/jiankongzhuti", () => ({
  listMonitorTopics: api.list,
  getMonitorTopic: api.get,
  listMonitorEditorialSources: () => Promise.resolve([]),
  pauseMonitorTopic: api.pause,
  resumeMonitorTopic: api.resume,
  updateMonitorTopic: api.update,
  archiveMonitorTopic: vi.fn(),
  cloneMonitorTopic: vi.fn(),
  runMonitorTopic: vi.fn(),
}));
vi.mock("@/api/laiyuannengli", () => ({ listSourceCapabilities: api.sources }));
vi.mock("@/api/gerentufagaojing", () => ({
  listAlerts: () => Promise.resolve([]),
}));
vi.mock("@/components/monitors/topic-rule-preview", () => ({
  TopicRulePreview: () => null,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));
vi.mock("sonner", () => ({
  toast: { error: api.error, success: api.success },
}));
import { TopicsWorkspace } from "@/app/topics/components/topics-workspace";
import { ApiRequestError } from "@/request";
const topic: HotKeyAPI.MonitorTopicView = {
  id: "topic-a",
  name: "主题一",
  status: "active",
  readiness_status: "ready",
  current_version: 2,
  rules: { match_any: ["任一词"], match_all: ["全部词"], exclude: ["排除词"] },
  source_keys: [],
  collection_interval_seconds: 3600,
  report_time: "08:00:00",
  report_timezone: "Asia/Shanghai",
  weekly_report_enabled: true,
  notification_target_names: [],
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T01:00:00Z",
};
beforeEach(() => {
  vi.resetAllMocks();
  api.list.mockResolvedValue({
    items: [topic, { ...topic, id: "topic-b", name: "主题二" }],
    next_cursor: null,
  });
  api.get.mockResolvedValue(topic);
  api.sources.mockResolvedValue({ items: [], next_cursor: null });
});
afterEach(() => {
  expectOnePageHeading();
  cleanup();
});
it("selects the first real topic, keeps old detail links, and reflects pause and resume in both panes", async () => {
  api.pause.mockResolvedValue({ ...topic, status: "paused" });
  api.resume.mockResolvedValue(topic);
  render(<TopicsWorkspace workspace />);
  await screen.findByRole("heading", { name: "主题一" });
  expect(screen.getByRole("heading", { name: "我的工作台" })).toBeTruthy();
  expect(
    screen.getByRole("link", { name: /主题一/ }).getAttribute("aria-current"),
  ).toBe("page");
  expect(
    screen.getByRole("link", { name: /主题二/ }).getAttribute("href"),
  ).toBe("/monitors/topic-b");
  expect(screen.getByLabelText("已保存关键词").textContent).toContain("任一词");
  expect(screen.getByLabelText("已保存关键词").textContent).toContain("全部词");
  expect(screen.getByLabelText("已保存关键词").textContent).toContain("排除词");
  expect(screen.queryByRole("img")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "暂停关注" }));
  await screen.findByRole("button", { name: "恢复关注" });
  expect(api.pause).toHaveBeenCalledWith({ topic_id: "topic-a" });
  expect(screen.getByRole("link", { name: /主题一/ }).textContent).toContain(
    "已暂停",
  );
  fireEvent.click(screen.getByRole("button", { name: "恢复关注" }));
  await screen.findByRole("button", { name: "暂停关注" });
  expect(api.resume).toHaveBeenCalledWith({ topic_id: "topic-a" });
  expect(screen.getByRole("link", { name: /主题一/ }).textContent).toContain(
    "运行中",
  );
});
it("honors a deep linked topic outside the first list page", async () => {
  api.get.mockResolvedValue({ ...topic, id: "topic-b", name: "主题二" });
  render(<TopicsWorkspace topicId="topic-b" />);
  await screen.findByRole("heading", { name: "主题二" });
  expect(api.get).toHaveBeenCalledWith({ topic_id: "topic-b" });
  expect(
    screen.getByRole("link", { name: /主题二/ }).getAttribute("aria-current"),
  ).toBe("page");
});
it("keeps an empty workspace empty without making an invented detail request", async () => {
  api.list.mockResolvedValue({ items: [], next_cursor: null });
  render(<TopicsWorkspace />);
  await screen.findByText("还没有关注的话题");
  expect(api.get).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("编辑主题设置")).toBeNull();
});
it.each([401, 403])(
  "shows permission state for HTTP %s and offers login",
  async (status) => {
    api.list.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        status,
        code: "access_denied",
        message: "无权限",
      }),
    );
    render(<TopicsWorkspace />);
    await screen.findByRole("status", { name: "无权读取监控主题" });
    expect(screen.getByRole("link", { name: "登录" })).toBeTruthy();
    expect(api.get).not.toHaveBeenCalled();
  },
);
it("keeps a network failure retryable without showing login or pretending the list is empty", async () => {
  api.list
    .mockRejectedValueOnce(
      new ApiRequestError({ kind: "network", message: "offline" }),
    )
    .mockResolvedValueOnce({ items: [topic], next_cursor: null });
  render(<TopicsWorkspace />);
  await screen.findByText("network");
  expect(screen.queryByRole("link", { name: "登录" })).toBeNull();
  expect(screen.queryByText("还没有关注的话题")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await screen.findByRole("heading", { name: "主题一" });
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
});

it("retains one page heading while the topic list is loading", () => {
  api.list.mockReturnValue(new Promise(() => {}));
  render(<TopicsWorkspace workspace />);
  expect(screen.getByRole("status", { name: "正在读取关注" })).toBeTruthy();
  expectOnePageHeading();
});

it.each([
  [404, "没有找到这个主题"],
  [401, "无权读取监控主题"],
  [403, "无权读取监控主题"],
  [503, "暂时无法读取主题"],
] as const)(
  "keeps embedded HTTP %s states below the workspace h1",
  async (status, title) => {
    api.get.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        status,
        code: status === 404 ? "resource_not_found" : "topic_read_failed",
        message: "failed",
      }),
    );
    render(<TopicsWorkspace topicId="topic-a" />);
    await screen.findByRole("heading", { level: 2, name: title });
    expectOnePageHeading();
  },
);

it("retains one page heading while the embedded topic is loading", async () => {
  api.get.mockReturnValue(new Promise(() => {}));
  render(<TopicsWorkspace topicId="topic-a" />);
  await screen.findByRole("link", { name: /主题一/ });
  expect(screen.getByRole("status", { name: "正在读取主题" })).toBeTruthy();
  expectOnePageHeading();
});

it("keeps a failed embedded refresh below the workspace heading", async () => {
  render(<TopicsWorkspace topicId="topic-a" />);
  const name = await screen.findByLabelText("主题名称");
  fireEvent.change(name, { target: { value: "未保存的草稿" } });
  api.update.mockRejectedValueOnce(
    new ApiRequestError({
      kind: "http",
      status: 409,
      code: "topic_version_conflict",
      message: "conflict",
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() => expect(api.error).toHaveBeenCalled());
  api.get.mockRejectedValueOnce(
    new ApiRequestError({ kind: "network", message: "offline" }),
  );
  api.error.mock.calls.at(-1)?.[1].action.onClick();
  await screen.findByRole("heading", { level: 2, name: /主题刷新失败/ });
  expectOnePageHeading();
});

vi.mock("@/app/monitors/[topicId]/components/topic-results", () => ({
  TopicResults: () => null,
}));
