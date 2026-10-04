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
    await screen.findByText("告警操作失败，请保留输入后重试。");
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
    await screen.findByText(/指标：未知/);
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
