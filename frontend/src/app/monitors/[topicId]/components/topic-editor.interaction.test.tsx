// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
vi.mock("./topic-run-actions", () => ({ TopicRunActions: () => null }));

import { ApiRequestError } from "@/request";
import { TopicEditor } from "./topic-editor";

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
    expect(
      await screen.findByText(
        "这个主题已在其他页面更新。重新读取后再确认你的修改。",
      ),
    ).toBeTruthy();
    expect((name as HTMLInputElement).value).toBe("尚未保存的草稿");
    expect(api.push).not.toHaveBeenCalled();
    api.get.mockResolvedValueOnce({
      ...topic,
      name: "其他页面已保存",
      current_version: 2,
    });
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    await waitFor(() =>
      expect(
        (screen.getByLabelText("主题名称") as HTMLInputElement).value,
      ).toBe("其他页面已保存"),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps business errors and request IDs inline without losing the draft", async () => {
    api.update.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 503,
        code: "demo_scope_conflict",
        message: "历史数据分区冲突",
        requestId: "request-demo-scope",
      }),
    );
    render(<TopicEditor topicId={topic.id} />);
    const name = await screen.findByLabelText("主题名称");
    fireEvent.change(name, { target: { value: "尚未保存的草稿" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "request-demo-scope",
      ),
    );
    expect(screen.getByRole("alert").textContent).toContain("历史数据分区冲突");
    expect((name as HTMLInputElement).value).toBe("尚未保存的草稿");
    expect(api.push).not.toHaveBeenCalled();
  });
});
