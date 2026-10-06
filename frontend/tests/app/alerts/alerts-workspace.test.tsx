// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const toasts = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: toasts }));

const api = vi.hoisted(() => ({
  list: vi.fn(),
  targets: vi.fn(),
  topics: vi.fn(),
  events: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  history: vi.fn(),
}));
vi.mock("@/api/gerentufagaojing", () => ({
  listAlerts: api.list,
  listAlertTargets: api.targets,
  createAlert: api.create,
  updateAlert: api.update,
  listAlertHistory: api.history,
}));
vi.mock("@/api/jiankongzhuti", () => ({ listMonitorTopics: api.topics }));
vi.mock("@/api/shijian", () => ({ listEvents: api.events }));
import { selectOption } from "../../select";
import { ApiRequestError } from "@/request";
import { AlertsWorkspace } from "@/app/alerts/components/alerts-workspace";

const rule: HotKeyAPI.AlertRuleView = {
  id: "rule-a",
  name: "产品反馈告警",
  revision: 1,
  enabled: false,
  topic_id: "topic-a",
  topic_rule_version: 2,
  event_id: null,
  metric: "negative_count",
  threshold: 10,
  cooldown_seconds: 3600,
  target_id: "target-a",
  target_revision: 3,
  readiness: "blocked",
  reason: "notifications_disabled",
  last_trigger_at: null,
  created_at: "2026-10-04T00:00:00Z",
  updated_at: "2026-10-04T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  api.list.mockResolvedValue([rule]);
  api.targets.mockResolvedValue([
    {
      id: "target-a",
      name: "已有邮件目标",
      revision: 3,
      eligible: false,
      reason: "notifications_disabled",
    },
  ]);
  api.topics.mockResolvedValue({
    items: [{ id: "topic-a", name: "产品反馈", current_version: 2 }],
    next_cursor: null,
  });
  api.events.mockResolvedValue({ items: [], next_cursor: null });
});
afterEach(cleanup);

describe("alert rules", () => {
  it("uses the bounded topic API and follows the fixed cursor for more choices", async () => {
    api.topics
      .mockResolvedValueOnce({ items: [], next_cursor: "next-page" })
      .mockResolvedValueOnce({
        items: [{ id: "topic-a", name: "产品反馈", current_version: 2 }],
        next_cursor: null,
      });
    render(<AlertsWorkspace />);
    await screen.findByText("产品反馈告警");
    expect(api.topics.mock.calls).toEqual([
      [{ limit: 50, cursor: null }],
      [{ limit: 50, cursor: "next-page" }],
    ]);
  });
  it("cannot enable an unready target and keeps the same operation when a save is unconfirmed", async () => {
    api.update
      .mockRejectedValueOnce(new Error("unconfirmed"))
      .mockResolvedValueOnce(rule);
    render(<AlertsWorkspace />);
    await screen.findByText("产品反馈告警");
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    expect(
      (screen.getByLabelText("启用规则") as HTMLInputElement).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "保存规则" }));
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith(
        "告警操作失败，请保留输入后重试。",
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect((screen.getByLabelText("规则名称") as HTMLInputElement).value).toBe(
      rule.name,
    );
    fireEvent.click(screen.getByRole("button", { name: "保存规则" }));
    await waitFor(() => expect(api.update).toHaveBeenCalledTimes(2));
    expect(api.update.mock.calls[0]?.[1]).toEqual(
      api.update.mock.calls[1]?.[1],
    );
    expect(api.update.mock.calls[0]?.[1]).toMatchObject({
      enabled: false,
      topic_rule_version: 2,
      target_revision: 3,
    });
    expect(api.create).not.toHaveBeenCalled();
  });

  it("shows unknown measurements without turning them into zero or sending a notification", async () => {
    api.history.mockResolvedValue([
      {
        id: "evaluation",
        rule_id: rule.id,
        rule_version: 1,
        window_start: "2026-10-04T00:00:00Z",
        window_end: "2026-10-04T01:00:00Z",
        status: "unknown",
        reason: "insufficient_inputs",
        value: null,
        cooldown_until: null,
        created_at: "2026-10-04T01:00:00Z",
      },
    ]);
    render(<AlertsWorkspace />);
    await screen.findByText("产品反馈告警");
    fireEvent.click(screen.getByRole("button", { name: "评估历史" }));
    await screen.findByText(
      (_, element) =>
        element?.getAttribute("data-slot") === "text" &&
        Boolean(element.textContent?.includes("指标：未知")),
    );
    expect(screen.getByText("缺少可用的固定输入，无法判定。")).toBeTruthy();
    expect(api.update).not.toHaveBeenCalled();
    expect(api.create).not.toHaveBeenCalled();
  });

  it("retries failed reads without losing an open form", async () => {
    render(<AlertsWorkspace />);
    await screen.findByText("产品反馈告警");
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.change(screen.getByLabelText("规则名称"), {
      target: { value: "尚未保存的名称" },
    });
    api.history
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce([]);
    fireEvent.click(screen.getByRole("button", { name: "评估历史" }));
    await screen.findByRole("button", { name: "重试历史" });
    fireEvent.click(screen.getByRole("button", { name: "重试历史" }));
    await screen.findByText(/尚无评估记录/);
    expect((screen.getByLabelText("规则名称") as HTMLInputElement).value).toBe(
      "尚未保存的名称",
    );
    expect(api.update).not.toHaveBeenCalled();
  });
});

it("keeps client validation, marks invalid fields and focuses the first correction without sending", async () => {
  render(<AlertsWorkspace />);
  await screen.findByText("产品反馈告警");
  fireEvent.click(screen.getByRole("button", { name: "编辑" }));
  const name = screen.getByLabelText("规则名称");
  fireEvent.change(name, { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("触发阈值"), {
    target: { value: "1.5" },
  });
  fireEvent.change(screen.getByLabelText("冷却时间（分钟）"), {
    target: { value: "5.5" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存规则" }));
  await waitFor(() => expect(document.activeElement).toBe(name));
  expect(name.getAttribute("aria-invalid")).toBe("true");
  expect(screen.getByLabelText("触发阈值").getAttribute("aria-invalid")).toBe(
    "true",
  );
  expect(
    screen.getByLabelText("冷却时间（分钟）").getAttribute("aria-invalid"),
  ).toBe("true");
  expect(toasts.error).toHaveBeenCalledWith(
    expect.stringContaining("有效阈值"),
  );
  expect(api.update).not.toHaveBeenCalled();
});
it("marks a server field error and retains values with Sonner feedback", async () => {
  api.update.mockRejectedValueOnce(
    new ApiRequestError({
      kind: "http",
      status: 422,
      code: "request_validation_failed",
      message: "阈值无效",
      details: [
        {
          location: ["body", "threshold"],
          message: "阈值无效",
          type: "value_error",
        },
      ],
    }),
  );
  render(<AlertsWorkspace />);
  await screen.findByText("产品反馈告警");
  fireEvent.click(screen.getByRole("button", { name: "编辑" }));
  fireEvent.click(screen.getByRole("button", { name: "保存规则" }));
  const threshold = screen.getByLabelText("触发阈值");
  await waitFor(() => expect(document.activeElement).toBe(threshold));
  expect(threshold.getAttribute("aria-invalid")).toBe("true");
  expect((screen.getByLabelText("规则名称") as HTMLInputElement).value).toBe(
    rule.name,
  );
  expect(toasts.error).toHaveBeenCalledWith("阈值无效");
  expect(screen.queryByRole("alert")).toBeNull();
});
it("enables and disables an eligible rule while keeping frozen topic and target versions", async () => {
  api.targets.mockResolvedValue([
    {
      id: "target-a",
      name: "已有邮件目标",
      revision: 3,
      eligible: true,
      reason: null,
    },
  ]);
  api.update
    .mockResolvedValueOnce({
      ...rule,
      enabled: true,
      readiness: "ready",
      reason: null,
      revision: 2,
    })
    .mockResolvedValueOnce({ ...rule, revision: 3 });
  render(<AlertsWorkspace />);
  await screen.findByText("产品反馈告警");
  fireEvent.click(screen.getByRole("button", { name: "编辑" }));
  fireEvent.click(screen.getByRole("switch", { name: "启用规则" }));
  fireEvent.click(screen.getByRole("button", { name: "保存规则" }));
  await screen.findByText("已启用");
  expect(api.update.mock.calls[0][1]).toMatchObject({
    enabled: true,
    expected_revision: 1,
    topic_rule_version: 2,
    target_revision: 3,
  });
  fireEvent.click(screen.getByRole("button", { name: "编辑" }));
  fireEvent.click(screen.getByRole("switch", { name: "启用规则" }));
  fireEvent.click(screen.getByRole("button", { name: "保存规则" }));
  await screen.findByText("已关闭");
  expect(api.update.mock.calls[1][1]).toMatchObject({
    enabled: false,
    expected_revision: 2,
    topic_rule_version: 2,
    target_revision: 3,
  });
  expect(toasts.success).toHaveBeenCalledWith("告警规则已保存。");
});
it.each([401, 403])(
  "renders permission state for %s without a rule form",
  async (status) => {
    api.list.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        status,
        code: "access_denied",
        message: "无权限",
      }),
    );
    render(<AlertsWorkspace />);
    await screen.findByRole("status", { name: "无权读取告警配置" });
    expect(screen.queryByRole("button", { name: "新建规则" })).toBeNull();
    expect(screen.getByRole("link", { name: "登录" })).toBeTruthy();
  },
);
it("shows no-alert and error states separately and does not infer unread counts", async () => {
  api.list.mockResolvedValueOnce([]);
  const view = render(<AlertsWorkspace />);
  await screen.findByRole("status", { name: "尚未配置告警规则" });
  expect(screen.queryByText(/未读|标为已读/)).toBeNull();
  view.unmount();
  api.list.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 503,
      code: "alerts_busy",
      message: "忙碌",
    }),
  );
  render(<AlertsWorkspace />);
  await screen.findByText("alerts_busy · 503");
  expect(screen.queryByRole("status", { name: "尚未配置告警规则" })).toBeNull();
  expect(screen.queryByRole("link", { name: "登录" })).toBeNull();
});

it("creates a rule through the generated API with fixed revisions and blocks duplicate saves", async () => {
  api.targets.mockResolvedValue([
    {
      id: "target-a",
      name: "已有邮件目标",
      revision: 3,
      eligible: true,
      reason: null,
    },
  ]);
  let resolve!: (row: HotKeyAPI.AlertRuleView) => void;
  api.create.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  render(<AlertsWorkspace />);
  await screen.findByText("产品反馈告警");
  fireEvent.click(screen.getByRole("button", { name: "新建规则" }));
  fireEvent.change(screen.getByLabelText("规则名称"), {
    target: { value: "新建告警" },
  });
  await selectOption(
    screen.getByRole("combobox", { name: "关注方向" }),
    "产品反馈",
  );
  await selectOption(
    screen.getByRole("combobox", { name: "通知目标" }),
    "已有邮件目标",
  );
  const save = screen.getByRole("button", { name: "保存规则" });
  fireEvent.click(save);
  fireEvent.click(save);
  expect(api.create).toHaveBeenCalledTimes(1);
  expect(api.create.mock.calls[0][0]).toMatchObject({
    expected_revision: 0,
    topic_id: "topic-a",
    topic_rule_version: 2,
    target_id: "target-a",
    target_revision: 3,
    enabled: false,
    metric: "negative_count",
    threshold: 10,
    cooldown_seconds: 3600,
  });
  resolve({ ...rule, id: "new-rule", name: "新建告警" });
  await screen.findByText("新建告警");
  expect(toasts.success).toHaveBeenCalledWith("告警规则已保存。");
});
