// @vitest-environment happy-dom
import { expectOnePageHeading } from "../../../../page-heading";

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));
afterEach(() => vi.clearAllMocks());

const api = vi.hoisted(() => ({
  get: vi.fn(),
  update: vi.fn(),
  sources: vi.fn(),
  email: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@/api/jiankongzhuti", () => ({
  listMonitorEditorialSources: () => Promise.resolve([]),
  getMonitorTopic: api.get,
  updateMonitorTopic: api.update,
  archiveMonitorTopic: vi.fn(),
  cloneMonitorTopic: vi.fn(),
  pauseMonitorTopic: vi.fn(),
  resumeMonitorTopic: vi.fn(),
}));
vi.mock("@/api/gerenbaogaotongzhi", () => ({
  getReportEmailSubscription: api.email,
}));
vi.mock("@/api/laiyuannengli", () => ({ listSourceCapabilities: api.sources }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));
vi.mock("@/components/monitors/topic-rule-preview", () => ({
  TopicRulePreview: () => null,
}));
vi.mock("@/app/monitors/[topicId]/components/topic-run-actions", () => ({
  TopicRunActions: () => null,
}));

import { ApiRequestError } from "@/request";
vi.mock("@/components/monitors/topic-alerts", () => ({
  TopicAlerts: () => null,
}));

import { TopicEditor } from "@/app/monitors/[topicId]/components/topic-editor";

const topic: HotKeyAPI.MonitorTopicView = {
  id: "topic-1",
  name: "已有主题",
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
};

beforeEach(() => {
  window.history.replaceState(null, "", "/topics");
  api.email.mockResolvedValue({
    target_name: "我的报告邮箱",
    email: "reader@example.com",
    enabled: true,
    delivery_available: true,
    revision: 1,
    email_matches_target: true,
  });
  api.get.mockResolvedValue(topic);
  api.sources.mockResolvedValue({ items: [], next_cursor: null });
});
afterEach(() => {
  if (document.body.textContent) expectOnePageHeading();
  cleanup();
  vi.clearAllMocks();
});

describe("Demo topic editing", () => {
  it("preserves the draft after a version conflict and reloads on request", async () => {
    api.update.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 409,
        code: "topic_version_conflict",
        message: "版本冲突",
      }),
    );
    render(<TopicEditor topicId={topic.id} />);
    await screen.findByRole("tab", { name: "主题设置" });
    fireEvent.mouseDown(screen.getByRole("tab", { name: "主题设置" }), {
      button: 0,
      ctrlKey: false,
    });
    const name = await screen.findByLabelText("主题名称");
    await waitFor(() =>
      expect((name as HTMLInputElement).value).toBe("已有主题"),
    );
    fireEvent.change(name, { target: { value: "尚未保存的草稿" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith(
        "这个主题已在其他页面更新。重新读取后再确认你的修改。",
        expect.objectContaining({
          action: expect.objectContaining({ label: "重新读取" }),
        }),
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect((name as HTMLInputElement).value).toBe("尚未保存的草稿");
    expect(api.push).not.toHaveBeenCalled();
    api.get.mockResolvedValueOnce({
      ...topic,
      name: "其他页面已保存",
      current_version: 2,
    });
    toasts.error.mock.calls.at(-1)?.[1].action.onClick();
    await waitFor(() =>
      expect(
        (screen.getByLabelText("主题名称") as HTMLInputElement).value,
      ).toBe("其他页面已保存"),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("toasts business errors and request IDs without losing the draft", async () => {
    api.update.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 503,
        code: "database_unavailable",
        message: "依赖服务暂时不可用",
        requestId: "request-dependency",
      }),
    );
    render(<TopicEditor topicId={topic.id} />);
    await screen.findByRole("tab", { name: "主题设置" });
    fireEvent.mouseDown(screen.getByRole("tab", { name: "主题设置" }), {
      button: 0,
      ctrlKey: false,
    });
    const name = await screen.findByLabelText("主题名称");
    fireEvent.change(name, { target: { value: "尚未保存的草稿" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith(
        "依赖服务暂时不可用",
        expect.objectContaining({
          description: "请求编号：request-dependency",
        }),
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect((name as HTMLInputElement).value).toBe("尚未保存的草稿");
    expect(api.push).not.toHaveBeenCalled();
  });

  it("opens saved report preferences separately and persists changes without losing notification targets", async () => {
    const saved = {
      ...topic,
      report_time: "18:45:00",
      weekly_report_enabled: true,
      notification_target_names: ["已有日报邮箱"],
    };
    api.get.mockResolvedValueOnce(saved);
    api.update.mockResolvedValueOnce({
      ...saved,
      report_time: "10:30:00",
      weekly_report_enabled: false,
    });
    render(<TopicEditor topicId={topic.id} />);
    await screen.findByRole("tab", { name: "主题设置" });
    fireEvent.mouseDown(screen.getByRole("tab", { name: "主题设置" }), {
      button: 0,
      ctrlKey: false,
    });
    await screen.findByLabelText("主题名称");
    expect(screen.queryByLabelText("每日报告时间")).toBeNull();
    expect(screen.queryByLabelText("生成周报")).toBeNull();
    expect(screen.queryByLabelText("推送目标名称")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "报告设置" }));
    expect(
      (screen.getByLabelText("每日报告时间") as HTMLInputElement).value,
    ).toBe("18:45");
    fireEvent.change(screen.getByLabelText("每日报告时间"), {
      target: { value: "10:30:00" },
    });
    fireEvent.click(screen.getByRole("switch", { name: "生成周报" }));
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith(
        { topic_id: topic.id },
        expect.objectContaining({
          expected_version: 1,
          report_time: "10:30",
          weekly_report_enabled: false,
          notification_target_names: ["已有日报邮箱"],
        }),
      ),
    );
  });

  it("opens advanced settings for a 422 field error and blocks duplicate writes", async () => {
    api.get.mockResolvedValueOnce({
      ...topic,
      collection_interval_seconds: 3600,
    });
    let reject!: (error: unknown) => void;
    api.update.mockImplementationOnce(
      () =>
        new Promise((_, fail) => {
          reject = fail;
        }),
    );
    render(<TopicEditor topicId={topic.id} />);
    await screen.findByRole("tab", { name: "主题设置" });
    fireEvent.mouseDown(screen.getByRole("tab", { name: "主题设置" }), {
      button: 0,
      ctrlKey: false,
    });
    await screen.findByLabelText("主题名称");
    expect(screen.queryByLabelText("全部包含")).toBeNull();
    const save = screen.getByRole("button", { name: "保存修改" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(api.update).toHaveBeenCalledTimes(1);
    reject(
      new ApiRequestError({
        kind: "http",
        status: 422,
        code: "request_validation_failed",
        message: "输入不符合要求",
        details: [
          {
            location: ["body", "match_all", 0],
            message: "关键词过长",
            type: "string_too_long",
          },
        ],
      }),
    );
    expect(await screen.findByLabelText("全部包含")).toBeTruthy();
    expect(toasts.error).toHaveBeenCalledWith(
      "输入不符合要求",
      expect.objectContaining({ description: "关键词过长" }),
    );
    expect(screen.getByLabelText("全部包含").getAttribute("aria-invalid")).toBe(
      "true",
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("binds the personal email target while preserving other delivery preferences", async () => {
    api.get.mockResolvedValueOnce({
      ...topic,
      notification_target_names: ["已有日报邮箱"],
    });
    api.update.mockResolvedValueOnce({
      ...topic,
      notification_target_names: ["已有日报邮箱", "我的报告邮箱"],
    });
    render(<TopicEditor topicId={topic.id} />);
    await screen.findByRole("tab", { name: "主题设置" });
    fireEvent.mouseDown(screen.getByRole("tab", { name: "主题设置" }), {
      button: 0,
      ctrlKey: false,
    });
    await screen.findByLabelText("主题名称");
    fireEvent.click(screen.getByRole("button", { name: "报告设置" }));
    await screen.findByText(/发送到 reader@example.com/);
    fireEvent.click(screen.getByRole("switch", { name: "邮件发送日报和周报" }));
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith(
        { topic_id: topic.id },
        expect.objectContaining({
          notification_target_names: ["已有日报邮箱", "我的报告邮箱"],
          collection_interval_seconds: 1800,
          report_time: "09:00:00",
        }),
      ),
    );
  });
});

it("retains the draft and marks saved rules stale when a conflict reload fails", async () => {
  api.update.mockRejectedValueOnce(
    new ApiRequestError({
      kind: "http",
      status: 409,
      code: "topic_version_conflict",
      message: "版本冲突",
    }),
  );
  render(<TopicEditor topicId={topic.id} />);
  await screen.findByRole("tab", { name: "主题设置" });
  fireEvent.mouseDown(screen.getByRole("tab", { name: "主题设置" }), {
    button: 0,
    ctrlKey: false,
  });
  const name = await screen.findByLabelText("主题名称");
  fireEvent.change(name, { target: { value: "尚未保存的草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() =>
    expect(toasts.error).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        action: expect.objectContaining({ label: "重新读取" }),
      }),
    ),
  );
  api.get.mockRejectedValueOnce(
    new ApiRequestError({ kind: "network", message: "offline" }),
  );
  toasts.error.mock.calls.at(-1)?.[1].action.onClick();
  await screen.findByText("已过期");
  expectOnePageHeading();
  expect((screen.getByLabelText("主题名称") as HTMLInputElement).value).toBe(
    "尚未保存的草稿",
  );
  expect(screen.getByText("network")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "登录" })).toBeNull();
  expect(api.push).not.toHaveBeenCalled();
  api.get.mockResolvedValueOnce({ ...topic, current_version: 2 });
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await waitFor(() => expect(screen.queryByText("已过期")).toBeNull());
});
it.each([401, 403])("renders a forbidden topic for %s", async (status) => {
  api.get.mockRejectedValueOnce(
    new ApiRequestError({
      kind: "http",
      status,
      code: "access_denied",
      message: "无权限",
    }),
  );
  render(<TopicEditor topicId={topic.id} />);
  await screen.findByRole("status", { name: "无权读取监控主题" });
  expect(screen.getByRole("link", { name: "登录" })).toBeTruthy();
  expect(screen.queryByLabelText("主题名称")).toBeNull();
});

vi.mock("@/app/monitors/[topicId]/components/topic-results", () => ({
  TopicResults: () => null,
}));
