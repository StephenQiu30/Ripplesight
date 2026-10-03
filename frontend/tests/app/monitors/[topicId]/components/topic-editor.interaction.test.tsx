// @vitest-environment happy-dom

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
  push: vi.fn(),
}));
vi.mock("@/api/jiankongzhuti", () => ({
  getMonitorTopic: api.get,
  updateMonitorTopic: api.update,
  archiveMonitorTopic: vi.fn(),
  cloneMonitorTopic: vi.fn(),
  pauseMonitorTopic: vi.fn(),
  resumeMonitorTopic: vi.fn(),
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
  api.get.mockResolvedValue(topic);
  api.sources.mockResolvedValue({ items: [], next_cursor: null });
});
afterEach(() => {
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

  it("keeps saved report preferences while removing their controls from the core form", async () => {
    const saved = {
      ...topic,
      report_time: "18:45:00",
      weekly_report_enabled: true,
      notification_target_names: ["已有日报邮箱"],
    };
    api.get.mockResolvedValueOnce(saved);
    api.update.mockResolvedValueOnce(saved);
    render(<TopicEditor topicId={topic.id} />);
    await screen.findByLabelText("主题名称");
    expect(screen.queryByLabelText("每日报告时间")).toBeNull();
    expect(screen.queryByLabelText("生成周报")).toBeNull();
    expect(screen.queryByLabelText("推送目标名称")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith(
        { topic_id: topic.id },
        expect.objectContaining({
          expected_version: 1,
          report_time: "18:45:00",
          weekly_report_enabled: true,
          notification_target_names: ["已有日报邮箱"],
        }),
      ),
    );
  });

  it("opens advanced settings for a 422 field error and blocks duplicate writes", async () => {
    let reject!: (error: unknown) => void;
    api.update.mockImplementationOnce(
      () =>
        new Promise((_, fail) => {
          reject = fail;
        }),
    );
    render(<TopicEditor topicId={topic.id} />);
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
});
